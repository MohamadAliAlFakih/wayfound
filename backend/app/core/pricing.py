"""Groq token-cost table and cost computation (D-28, AGT-07).

Source: groq.com/pricing reviewed 2026-04-30. Refresh in Phase 6 for the
README cost table. Prices are USD per 1,000,000 tokens; pricing returned
by `compute_cost_usd` is plain USD.

No `os.getenv` calls — pure constants module.
"""
from __future__ import annotations

from typing import Mapping

GROQ_PRICES_USD_PER_M_TOKENS: Mapping[str, Mapping[str, float]] = {
    "llama-3.1-8b-instant":    {"prompt": 0.05, "completion": 0.08},
    "llama-3.3-70b-versatile": {"prompt": 0.59, "completion": 0.79},
}


def compute_cost_usd(model: str, usage: Mapping[str, int]) -> float:
    """Compute USD cost for a single LLM call.

    Args:
        model: Groq model name (must match a key in GROQ_PRICES_USD_PER_M_TOKENS,
               else returns 0.0). Names match D-01 model IDs exactly.
        usage: dict with keys 'prompt_tokens' and 'completion_tokens' (missing
               keys treated as 0).

    Returns:
        Total cost in USD (float, can be 0.0 if model unknown or usage empty).
    """
    rates = GROQ_PRICES_USD_PER_M_TOKENS.get(model)
    if not rates:
        return 0.0
    pt = int(usage.get("prompt_tokens", 0) or 0)
    ct = int(usage.get("completion_tokens", 0) or 0)
    return (pt * rates["prompt"] + ct * rates["completion"]) / 1_000_000
