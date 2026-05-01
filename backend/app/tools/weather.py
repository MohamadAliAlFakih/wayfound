"""weather_tool — OpenWeatherMap current + 5-day forecast (D-11).

- Cache: cachetools.TTLCache(maxsize=128, ttl=600) keyed by destination,
  protected by asyncio.Lock (P-03 — TTLCache is not thread-safe).
- Retries: tenacity AsyncRetrying with stop_after_attempt(3) +
  wait_exponential(min=1, max=8); only on RequestError/TimeoutException
  (P-06 — do NOT retry HTTPStatusError 4xx).
- On missing API key: returns informational dict so the LLM can adapt.
- Uses deprecated `q={city}` param (RESEARCH §6 — still functional, no
  extra geocoding hop). Documented in tool description for future swap.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from cachetools import TTLCache
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

_OWM_BASE = "https://api.openweathermap.org/data/2.5"
_CACHE: TTLCache = TTLCache(maxsize=128, ttl=600)
_CACHE_LOCK = asyncio.Lock()


class WeatherToolInput(BaseModel):
    """D-11: flat schema for weather_tool."""

    destination: str = Field(min_length=2, max_length=128, description="City name, e.g. 'Paris'.")


async def _fetch_owm(client: httpx.AsyncClient, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
    """Single GET, raise_for_status. Caller wraps in tenacity."""
    resp = await client.get(f"{_OWM_BASE}/{endpoint}", params=params, timeout=8.0)
    resp.raise_for_status()
    return resp.json()


async def _fetch_with_retry(
    client: httpx.AsyncClient, endpoint: str, params: dict[str, Any]
) -> dict[str, Any]:
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        reraise=True,
    ):
        with attempt:
            return await _fetch_owm(client, endpoint, params)
    raise RuntimeError("unreachable")  # tenacity raises before this; satisfy type checker


def make_weather_tool() -> StructuredTool:
    """Build the weather_tool. Reads settings.openweather_api_key at call time."""

    async def _weather(destination: str) -> dict[str, Any]:
        api_key = (
            settings.openweather_api_key.get_secret_value()
            if settings.openweather_api_key is not None
            else None
        )
        if api_key is None:
            logger.warning("weather_tool: OPENWEATHER_API_KEY not set; returning stub")
            return {
                "current": None,
                "forecast_5day": None,
                "note": "Weather data unavailable (OPENWEATHER_API_KEY not configured).",
            }

        cache_key = destination.strip().lower()
        async with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
        if cached is not None:
            logger.info("weather_tool: cache hit for %s", cache_key)
            return cached

        params_common = {"q": destination, "appid": api_key, "units": "metric"}
        try:
            async with httpx.AsyncClient() as client:
                current = await _fetch_with_retry(client, "weather", params_common)
                forecast = await _fetch_with_retry(client, "forecast", {**params_common, "cnt": 8})
        except (httpx.HTTPStatusError, RetryError, httpx.RequestError) as exc:
            logger.warning("weather_tool: fetch failed for %s: %s", destination, type(exc).__name__)
            return {
                "current": None,
                "forecast_5day": None,
                "note": f"Weather lookup failed for {destination}: {type(exc).__name__}",
            }

        result = {
            "current": {
                "temp_c": current.get("main", {}).get("temp"),
                "feels_like_c": current.get("main", {}).get("feels_like"),
                "humidity": current.get("main", {}).get("humidity"),
                "description": (current.get("weather") or [{}])[0].get("description"),
                "wind_speed_mps": current.get("wind", {}).get("speed"),
                "city": current.get("name"),
                "country": current.get("sys", {}).get("country"),
            },
            "forecast_5day": [
                {
                    "dt_txt": item.get("dt_txt"),
                    "temp_c": item.get("main", {}).get("temp"),
                    "description": (item.get("weather") or [{}])[0].get("description"),
                    "pop": item.get("pop"),
                }
                for item in (forecast.get("list") or [])[:8]
            ],
        }

        async with _CACHE_LOCK:
            _CACHE[cache_key] = result
        logger.info("weather_tool: fetched + cached %s", cache_key)
        return result

    return StructuredTool.from_function(
        coroutine=_weather,
        name="weather_tool",
        description=(
            "Fetch current weather and a 5-day (3-hour interval, next 24h) forecast for a destination. "
            "Returns metric (Celsius) units. Cached 10 minutes per destination."
        ),
        args_schema=WeatherToolInput,
    )
