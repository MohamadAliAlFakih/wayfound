"""Fetch Wikivoyage destination articles via MediaWiki API."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"

# 15 destinations drawn from the travel_classifier training set (destinations.csv)
# covering all 6 travel styles: Adventure, Relaxation, Culture, Budget, Luxury, Family
DESTINATIONS: list[str] = [
    "Bangkok",
    "Paris",
    "Tokyo",
    "Bali",
    "New York City",
    "Barcelona",
    "Rome",
    "Kyoto",
    "Istanbul",
    "Cape Town",
    "Reykjavik",
    "Maldives",
    "Chiang Mai",
    "Vienna",
    "Lisbon",
]

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "wikivoyage"


def _strip_wikitext(text: str) -> str:
    """Remove MediaWiki markup, leaving readable prose."""
    # Remove templates {{...}}
    text = re.sub(r"\{\{[^}]*\}\}", "", text, flags=re.DOTALL)
    # Remove file/image links [[File:...]] [[Image:...]]
    text = re.sub(r"\[\[(File|Image):[^\]]*\]\]", "", text, flags=re.IGNORECASE)
    # Unwrap wiki links [[target|label]] -> label, [[target]] -> target
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_destination(destination: str, out_dir: Path) -> Path:
    """Fetch one Wikivoyage article and write to out_dir/<destination>.txt.

    Returns the path written. Raises httpx.HTTPError on network failure.
    Idempotent: skips fetch if file already exists and is > 500 bytes.
    """
    slug = destination.replace(" ", "_")
    out_path = out_dir / f"{slug}.txt"

    if out_path.exists() and out_path.stat().st_size > 500:
        logger.info("skip %s — already fetched (%d bytes)", destination, out_path.stat().st_size)
        return out_path

    params = {
        "action": "query",
        "titles": destination,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "redirects": "1",
        "format": "json",
        "formatversion": "2",
    }
    headers = {
        "User-Agent": "WayfoundTravelPlanner/1.0 (https://github.com/wayfound; mafakih1@gmail.com) httpx/0.27",
    }
    resp = httpx.get(WIKIVOYAGE_API, params=params, timeout=30, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    pages = data["query"]["pages"]
    page = pages[0]
    if "missing" in page:
        logger.warning("Wikivoyage page not found for %s", destination)
        # Write a stub so ingest skips gracefully rather than crashing
        out_path.write_text(f"# {destination}\n\nNo Wikivoyage article found.\n", encoding="utf-8")
        return out_path

    raw_wikitext = page["revisions"][0]["slots"]["main"]["content"]
    clean = _strip_wikitext(raw_wikitext)
    out_path.write_text(clean, encoding="utf-8")
    logger.info("fetched %s -> %s (%d bytes)", destination, out_path.name, len(clean))
    return out_path


def fetch_all(destinations: list[str] = DESTINATIONS, out_dir: Path = RAW_DIR) -> list[Path]:
    """Fetch all destinations. Returns list of written paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for dest in destinations:
        try:
            paths.append(fetch_destination(dest, out_dir))
        except httpx.HTTPError as exc:
            logger.error("HTTP error fetching %s: %s", dest, exc)
    return paths


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fetch_all()
