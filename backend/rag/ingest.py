"""Ingest Wikivoyage .txt files into pgvector (parent-child chunking + OpenAI embeddings).

Chunking strategy (per STATE.md Advanced RAG stack decision):
- Parent chunks: ~400 tokens, 50-token overlap  — stored for context retrieval
- Child chunks:  ~100 tokens, 50-token overlap  — stored for precision retrieval
  child.parent_id -> parent.id

Embedding model: text-embedding-ada-002 (Vector dimension = 1536)
Batch size: 100 texts per OpenAI API call to stay within rate limits.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from pathlib import Path

from app.core.embeddings import LocalEmbedder

from app.db.engine import async_session_factory, create_tables
from rag.models import Chunk

logger = logging.getLogger(__name__)

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "wikivoyage"

# Chunking parameters
PARENT_TOKENS = 400
CHILD_TOKENS = 100
OVERLAP_TOKENS = 50
# Approximate chars per token for simple word-based splitting (no tiktoken dep for speed)
CHARS_PER_TOKEN = 4
EMBED_BATCH_SIZE = 100
EMBED_MODEL = "text-embedding-ada-002"


def _approx_split(text: str, chunk_tokens: int, overlap_tokens: int) -> list[str]:
    """Split text into overlapping chunks by approximate token count (4 chars/token).

    This is a simple, dependency-free approximation. tiktoken is not required
    because the 4-char heuristic gives adequate chunk sizing for this corpus.
    """
    chunk_chars = chunk_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN
    step = max(chunk_chars - overlap_chars, 1)

    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunk = text[start : start + chunk_chars].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def _parse_sections(text: str) -> list[tuple[str, str]]:
    """Parse wikitext-style == Heading == sections.

    Returns list of (section_name, section_text) tuples.
    Unsectioned lead text is labelled 'Introduction'.
    """
    pattern = re.compile(r"^==+\s*(.+?)\s*==+", re.MULTILINE)
    matches = list(pattern.finditer(text))

    if not matches:
        return [("Introduction", text)]

    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        sections.append(("Introduction", text[: matches[0].start()].strip()))

    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[m.end() : end].strip()
        sections.append((m.group(1), section_text))

    return [(name, body) for name, body in sections if body]


def _build_chunks(destination: str, text: str) -> list[Chunk]:
    """Build parent + child Chunk objects for one destination.

    Returns a flat list: all parents first, then all children with parent_id set.
    """
    sections = _parse_sections(text)
    all_chunks: list[Chunk] = []

    chunk_index = 0
    for section_name, section_body in sections:
        # Parent chunks
        parent_texts = _approx_split(section_body, PARENT_TOKENS, OVERLAP_TOKENS)
        for parent_text in parent_texts:
            parent_id = uuid.uuid4()
            parent = Chunk(
                id=parent_id,
                destination=destination,
                section=section_name,
                chunk_index=chunk_index,
                parent_id=None,
                content=parent_text,
                embedding=[],  # filled by embed step
            )
            all_chunks.append(parent)
            chunk_index += 1

            # Child chunks from same parent text
            child_texts = _approx_split(parent_text, CHILD_TOKENS, OVERLAP_TOKENS)
            for child_text in child_texts:
                child = Chunk(
                    id=uuid.uuid4(),
                    destination=destination,
                    section=section_name,
                    chunk_index=chunk_index,
                    parent_id=parent_id,
                    content=child_text,
                    embedding=[],  # filled by embed step
                )
                all_chunks.append(child)
                chunk_index += 1

    return all_chunks


async def _embed_batch(client: LocalEmbedder, texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts; returns list of 384-dim float vectors."""
    return await client.embed_batch(texts)


async def ingest_file(client: LocalEmbedder, txt_path: Path) -> int:
    """Ingest one .txt file: chunk, embed, store. Returns number of rows inserted."""
    destination = txt_path.stem.replace("_", " ")
    text = txt_path.read_text(encoding="utf-8")

    chunks = _build_chunks(destination, text)
    if not chunks:
        logger.warning("no chunks produced for %s", destination)
        return 0

    # Embed in batches
    texts = [c.content for c in chunks]
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        embeddings.extend(await _embed_batch(client, batch))

    for chunk, emb in zip(chunks, embeddings):
        chunk.embedding = emb

    # Bulk insert
    session_factory = async_session_factory()
    async with session_factory() as session:
        session.add_all(chunks)
        await session.commit()

    logger.info("ingested %s: %d chunks", destination, len(chunks))
    return len(chunks)


async def _ingest_all(raw_dir: Path = RAW_DIR) -> int:
    """Ingest all .txt files in raw_dir. Returns total rows inserted."""
    await create_tables()

    client = LocalEmbedder.load()
    total = 0
    for txt_path in sorted(raw_dir.glob("*.txt")):
        total += await ingest_file(client, txt_path)

    logger.info("ingest complete: %d total chunks across %d destinations", total, 15)
    return total


async def ensure_indexed(raw_dir: Path = RAW_DIR) -> None:
    """Ensure the vector store is populated. Safe to call at startup.

    Swallows OpenAI APIError and logs a WARNING so the app can start even
    when OpenAI is unreachable (ROADMAP Phase 2 success criterion 4).
    Also skips ingest when the chunks table already has rows.
    """
    try:
        await create_tables()

        # Check if already populated
        from sqlalchemy import func, select
        session_factory = async_session_factory()
        async with session_factory() as session:
            count_result = await session.execute(select(func.count()).select_from(Chunk))
            count = count_result.scalar_one()

        if count > 0:
            logger.info("chunks table has %d rows — skipping ingest", count)
            return

        await _ingest_all(raw_dir)

    except Exception as exc:  # noqa: BLE001
        logger.warning("ensure_indexed failed — skipping: %s", exc)


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(_ingest_all())
