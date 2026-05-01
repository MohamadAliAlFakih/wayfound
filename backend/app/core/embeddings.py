"""Local embedding model wrapper using sentence-transformers/all-MiniLM-L6-v2.

384-dim vectors. Runs on CPU. ~80MB model cached on first run.

Replaces OpenAI text-embedding-ada-002 (1536-dim) for cost-free local embeddings.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384


class LocalEmbedder:
    """Wraps a sentence-transformers model behind an async interface."""

    def __init__(self, model: SentenceTransformer) -> None:
        self._model = model

    @classmethod
    def load(cls) -> LocalEmbedder:
        """Load the model into memory (downloads on first run, then cached)."""
        from sentence_transformers import SentenceTransformer

        logger.info("loading embedding model %s", EMBED_MODEL_NAME)
        model = SentenceTransformer(EMBED_MODEL_NAME)
        logger.info("embedding model loaded (dim=%d)", EMBED_DIM)
        return cls(model)

    async def embed_one(self, text: str) -> list[float]:
        """Embed a single string. Runs the CPU encode in a thread."""
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of strings. Returns list of 384-dim float vectors."""
        return await asyncio.to_thread(self._encode, texts)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, show_progress_bar=False).tolist()