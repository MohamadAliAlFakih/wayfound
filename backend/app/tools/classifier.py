"""classifier_tool — Phase 1 sklearn Pipeline wrapped as a LangChain tool (D-10).

Factory pattern: `make_classifier_tool(model)` returns a `StructuredTool`
wrapping an async function with closure over the sklearn Pipeline (loaded once
in lifespan as `app.state.ml_model`).

Returns travel_style + confidence + top_3_alternatives via predict_proba.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ClassifierToolInput(BaseModel):
    """D-10: flat schema with bounds. 10 fields matching Phase 1 dataset."""

    cost_per_day_usd: float = Field(
        ge=0, description="USD per day budget for the destination."
    )
    avg_temp_celsius: float = Field(
        ge=-30, le=50, description="Average temperature, Celsius."
    )
    outdoor_activity_score: int = Field(ge=1, le=10)
    cultural_site_count: int = Field(ge=0, le=500)
    safety_index: float = Field(ge=0, le=100)
    beach_access: int = Field(ge=0, le=1, description="1 if has beach access, else 0.")
    nightlife_score: int = Field(ge=1, le=10)
    family_amenity_score: int = Field(ge=1, le=10)
    crowd_level: int = Field(ge=1, le=5)
    continent: str = Field(
        description="One of: Europe, Asia, Africa, North America, South America, Oceania."
    )


def make_classifier_tool(model: Any) -> StructuredTool:
    """Build the classifier_tool with an injected sklearn Pipeline.

    `model` must expose `predict_proba(DataFrame)` and `classes_`.
    """

    async def _classify(
        cost_per_day_usd: float,
        avg_temp_celsius: float,
        outdoor_activity_score: int,
        cultural_site_count: int,
        safety_index: float,
        beach_access: int,
        nightlife_score: int,
        family_amenity_score: int,
        crowd_level: int,
        continent: str,
    ) -> dict[str, Any]:
        row = {
            "cost_per_day_usd": cost_per_day_usd,
            "avg_temp_celsius": avg_temp_celsius,
            "outdoor_activity_score": outdoor_activity_score,
            "cultural_site_count": cultural_site_count,
            "safety_index": safety_index,
            "beach_access": beach_access,
            "nightlife_score": nightlife_score,
            "family_amenity_score": family_amenity_score,
            "crowd_level": crowd_level,
            "continent": continent,
        }
        df = pd.DataFrame([row])
        proba = model.predict_proba(df)[0]
        classes = list(model.classes_)
        ranked = sorted(zip(classes, proba), key=lambda x: -x[1])
        top1 = ranked[0]
        top3 = [{"style": str(c), "prob": float(p)} for c, p in ranked[:3]]
        result = {
            "travel_style": str(top1[0]),
            "confidence": float(top1[1]),
            "top_3_alternatives": top3,
        }
        logger.info(
            "classifier_tool: top=%s conf=%.3f continent=%s",
            result["travel_style"],
            result["confidence"],
            continent,
        )
        return result

    return StructuredTool.from_function(
        coroutine=_classify,
        name="classifier_tool",
        description=(
            "Classify a destination's travel style given 10 numeric/categorical features. "
            "Returns top-1 style + confidence + top-3 alternatives. "
            "Classes: Adventure, Relaxation, Culture, Budget, Luxury, Family."
        ),
        args_schema=ClassifierToolInput,
    )
