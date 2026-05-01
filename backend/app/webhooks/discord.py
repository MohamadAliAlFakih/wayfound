"""Discord webhook delivery (WH-01, WH-02, WH-03; D-23..D-26).

- build_discord_embed: shapes the rich embed payload (D-23, OQ-5).
- deliver_webhook: tenacity-retried POST, restricted to transient errors
  (P-06); 401/404 logged + abandoned (RESEARCH §9).

Caller is `app/services/agent.py::plan_trip` which schedules this via
asyncio.create_task with strong reference (P-02).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# Discord embed text caps (RESEARCH §9 / P-07).
_DESCRIPTION_CAP = 3500   # leave headroom under 6000-char total
_TITLE_CAP = 256
_FIELD_VALUE_CAP = 1024
_FOOTER_CAP = 2048

_COLOR_GREEN = 5763719   # 0x57F287 — completed
_COLOR_RED = 15548997    # 0xED4245 — failed


def _truncate(s: str, n: int) -> str:
    """Truncate string to <=n chars, appending an ellipsis if cut."""
    return s if len(s) <= n else s[: n - 1] + "…"


def build_discord_embed(
    *,
    trip_id: UUID,
    status: str,
    answer: str,
    tool_names: list[str],
    travel_style: str | None,
    top_destination: str | None,
    total_tokens: int,
    cost_usd: float,
    completed_at: datetime,
) -> dict[str, Any]:
    """Build the Discord webhook payload (D-23, OQ-5).

    Footer always shows trip_id + tokens + cost — these are independent of
    LangSmith availability (OQ-5: always compute).
    """
    title = f"Wayfound Trip Plan ({status})"
    color = _COLOR_GREEN if status == "completed" else _COLOR_RED
    footer_text = (
        f"trip_id={trip_id} · {total_tokens} tokens · ${cost_usd:.4f}"
    )
    embed: dict[str, Any] = {
        "title": _truncate(title, _TITLE_CAP),
        "description": _truncate(answer or "(no answer)", _DESCRIPTION_CAP),
        "color": color,
        "fields": [
            {
                "name": "Travel style",
                "value": _truncate(travel_style or "N/A", _FIELD_VALUE_CAP),
                "inline": True,
            },
            {
                "name": "Top destination",
                "value": _truncate(top_destination or "N/A", _FIELD_VALUE_CAP),
                "inline": True,
            },
            {
                "name": "Tools fired",
                "value": _truncate(", ".join(tool_names) or "none", _FIELD_VALUE_CAP),
                "inline": False,
            },
        ],
        "footer": {"text": _truncate(footer_text, _FOOTER_CAP)},
        "timestamp": completed_at.isoformat(),
    }
    return {"embeds": [embed]}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=10),
    # P-06: only retry on transient errors. NEVER bare HTTPError (parent of
    # HTTPStatusError 4xx — would loop on 401/404).
    retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
    reraise=True,
)
async def _post_with_retry(url: str, payload: dict[str, Any]) -> None:
    """Single POST attempt with tenacity-driven retries on transient errors."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(url, json=payload)
        # 401/404 are permanent — log and abandon (do NOT raise so retry filter
        # never sees a HTTPStatusError; per P-06 we exclude HTTPStatusError, so
        # 5xx will not retry either — they raise once and the outer wrapper
        # logs+swallows).
        if resp.status_code in (401, 404):
            logger.warning(
                "Discord webhook permanent failure: %d body=%s",
                resp.status_code,
                resp.text[:200],
            )
            return
        resp.raise_for_status()


async def deliver_webhook(url: str, payload: dict[str, Any]) -> None:
    """Fire-and-forget delivery — exceptions logged + swallowed (WH-03)."""
    try:
        await _post_with_retry(url, payload)
        logger.info("Discord webhook delivered to %s...", url[:60])
    except Exception as exc:  # noqa: BLE001 — WH-03: never propagate to caller
        logger.warning(
            "Discord webhook delivery failed (swallowed per WH-03): %s: %s",
            type(exc).__name__,
            str(exc)[:200],
        )
