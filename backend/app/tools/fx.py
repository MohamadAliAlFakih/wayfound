"""fx_tool — Open Exchange Rates current cross-rate (D-13).

Free tier forces base=USD (RESEARCH §8). Cross-rate formula:
    from_to = rates[to_currency] / rates[from_currency]

Returns {"rate": float, "as_of": ISO timestamp} per D-13. tenacity on
transient HTTP errors only (P-06).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.settings import settings

logger = logging.getLogger(__name__)

_OXR_URL = "https://openexchangerates.org/api/latest.json"


class FXToolInput(BaseModel):
    """D-13: ISO 4217 3-letter currency codes."""

    from_currency: str = Field(
        pattern=r"^[A-Z]{3}$", description="ISO 4217 source currency, e.g. USD."
    )
    to_currency: str = Field(
        pattern=r"^[A-Z]{3}$", description="ISO 4217 target currency, e.g. EUR."
    )


async def _fetch_oxr_with_retry(client: httpx.AsyncClient, app_id: str) -> dict[str, Any]:
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        reraise=True,
    ):
        with attempt:
            resp = await client.get(_OXR_URL, params={"app_id": app_id}, timeout=8.0)
            resp.raise_for_status()
            return resp.json()
    raise RuntimeError("unreachable")


def make_fx_tool() -> StructuredTool:
    """Build the fx_tool. Reads settings.open_exchange_rates_app_id at call time."""

    async def _fx(from_currency: str, to_currency: str) -> dict[str, Any]:
        if settings.open_exchange_rates_app_id is None:
            logger.warning("fx_tool: OPEN_EXCHANGE_RATES_APP_ID not set; returning stub")
            return {
                "rate": None,
                "as_of": None,
                "note": "FX data unavailable (OPEN_EXCHANGE_RATES_APP_ID not configured).",
            }
        app_id = settings.open_exchange_rates_app_id.get_secret_value()
        try:
            async with httpx.AsyncClient() as client:
                body = await _fetch_oxr_with_retry(client, app_id)
        except (httpx.HTTPStatusError, RetryError, httpx.RequestError) as exc:
            logger.warning("fx_tool fetch failed: %s", type(exc).__name__)
            return {
                "rate": None,
                "as_of": None,
                "note": f"FX lookup failed: {type(exc).__name__}",
            }

        rates = body.get("rates") or {}
        ts = body.get("timestamp")
        try:
            if from_currency == "USD":
                rate = float(rates[to_currency])
            elif to_currency == "USD":
                rate = 1.0 / float(rates[from_currency])
            else:
                rate = float(rates[to_currency]) / float(rates[from_currency])
        except (KeyError, ZeroDivisionError, TypeError, ValueError) as exc:
            logger.warning(
                "fx_tool: cross-rate compute failed %s->%s: %s",
                from_currency,
                to_currency,
                type(exc).__name__,
            )
            return {
                "rate": None,
                "as_of": None,
                "note": f"Unsupported currency pair {from_currency}->{to_currency}.",
            }

        as_of = (
            datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
            if ts is not None
            else None
        )
        return {"rate": rate, "as_of": as_of}

    return StructuredTool.from_function(
        coroutine=_fx,
        name="fx_tool",
        description=(
            "Fetch current FX cross-rate. Inputs: from_currency + to_currency as "
            "3-letter ISO 4217 codes (USD, EUR, GBP, JPY...). Returns {rate, as_of}. "
            "Base USD enforced by free tier; cross-rates computed locally."
        ),
        args_schema=FXToolInput,
    )
