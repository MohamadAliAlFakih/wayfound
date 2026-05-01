"""Tool isolation tests (TST-01).

These tests run each tool with no real network or model — we verify the
"missing API key" graceful-degradation paths. No LLM, no Postgres needed.
"""
from __future__ import annotations

import pytest

from app.tools.fx import make_fx_tool
from app.tools.weather import make_weather_tool


@pytest.mark.asyncio
async def test_weather_tool_returns_stub_when_unconfigured(monkeypatch):
    """No OPENWEATHER_API_KEY → tool returns a graceful note, not an exception."""
    from app.core import settings as settings_module

    monkeypatch.setattr(
        settings_module.settings, "openweather_api_key", None, raising=False
    )

    tool = make_weather_tool()
    result = await tool.coroutine(destination="Paris")

    assert isinstance(result, dict)
    assert "note" in result
    assert "OPENWEATHER_API_KEY" in result["note"]
    assert result["current"] is None


@pytest.mark.asyncio
async def test_fx_tool_returns_stub_when_unconfigured(monkeypatch):
    """No OPEN_EXCHANGE_RATES_APP_ID → graceful note instead of crash."""
    from app.core import settings as settings_module

    monkeypatch.setattr(
        settings_module.settings, "open_exchange_rates_app_id", None, raising=False
    )

    tool = make_fx_tool()
    result = await tool.coroutine(from_currency="USD", to_currency="EUR")

    assert isinstance(result, dict)
    assert "note" in result
    assert result["rate"] is None