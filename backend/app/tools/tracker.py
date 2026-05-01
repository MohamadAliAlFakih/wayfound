"""ToolCallTracker — async context manager for per-call ToolCall persistence (D-15).

Pattern (used by custom tools_node in app/agents/nodes.py):

    async with session_factory() as session, ToolCallTracker(
        session, trip_id, tool_name, input_dict
    ) as tracker:
        try:
            result = await tool.ainvoke(input_dict)
            await tracker.complete(result)
        except Exception as exc:
            await tracker.fail(str(exc))

On `__aenter__`: INSERT a ToolCall row with output_json=null, latency_ms=null,
record start time. The tracker exposes `complete()` and `fail()` methods that
UPDATE the same row with output + latency. `__aexit__` is a no-op for success;
on un-handled exception inside the `with` body it logs the orphan placeholder
if no completion/fail was recorded. Both `complete` and `fail` commit their own
UPDATE and stamp `latency_ms` from `time.perf_counter()`.

No `print()`; uses stdlib logging.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Mapping

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool_call import ToolCall

logger = logging.getLogger(__name__)


class ToolCallTracker:
    """Persist a single tool invocation to the tool_call table.

    Args:
        session: Active AsyncSession (caller-managed scope).
        trip_id: UUID of the parent Trip row.
        tool_name: e.g. 'rag_tool', 'classifier_tool', 'weather_tool'.
        input_json: Tool input dict (must be JSON-serializable).
    """

    def __init__(
        self,
        session: AsyncSession,
        trip_id: uuid.UUID | str,
        tool_name: str,
        input_json: Mapping[str, Any],
    ) -> None:
        self._session = session
        self._trip_id = (
            uuid.UUID(str(trip_id)) if not isinstance(trip_id, uuid.UUID) else trip_id
        )
        self._tool_name = tool_name
        self._input_json = dict(input_json)
        self._row_id: uuid.UUID | None = None
        self._t0: float | None = None
        self._completed: bool = False

    async def __aenter__(self) -> "ToolCallTracker":
        row = ToolCall(
            trip_id=self._trip_id,
            tool_name=self._tool_name,
            input_json=self._input_json,
            output_json=None,
            latency_ms=None,
        )
        self._session.add(row)
        await self._session.flush()  # assign UUID; do NOT commit yet
        await self._session.commit()  # persist the placeholder so concurrent reads see it
        self._row_id = row.id
        self._t0 = time.perf_counter()
        logger.info(
            "tool_call.start tool=%s trip_id=%s", self._tool_name, self._trip_id
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        # If neither complete() nor fail() was called and an exception
        # occurred, log the orphan placeholder. Do NOT swallow.
        if not self._completed and exc_type is not None:
            logger.warning(
                "tool_call.orphan tool=%s trip_id=%s row_id=%s — neither complete() nor fail() called before exception",
                self._tool_name,
                self._trip_id,
                self._row_id,
            )
        return False  # never suppress exceptions

    async def _update(self, output_json: Any, *, ok: bool) -> None:
        if self._row_id is None or self._t0 is None:
            logger.warning("tool_call._update before __aenter__ — skipping")
            return
        latency_ms = int((time.perf_counter() - self._t0) * 1000)
        # output may be a string, dict, list, or None — JSONB accepts any of these.
        normalized: dict | list | str | int | float | bool | None
        if output_json is None or isinstance(
            output_json, (dict, list, str, int, float, bool)
        ):
            normalized = output_json
        else:
            # Fallback: stringify unknown types so JSONB doesn't reject.
            normalized = str(output_json)
        stmt = (
            update(ToolCall)
            .where(ToolCall.id == self._row_id)
            .values(output_json=normalized, latency_ms=latency_ms)
        )
        await self._session.execute(stmt)
        await self._session.commit()
        self._completed = True
        level = logging.INFO if ok else logging.WARNING
        logger.log(
            level,
            "tool_call.end tool=%s trip_id=%s latency_ms=%d ok=%s",
            self._tool_name,
            self._trip_id,
            latency_ms,
            ok,
        )

    async def complete(self, output: Any) -> None:
        """UPDATE the ToolCall row with the successful output + latency."""
        await self._update(output, ok=True)

    async def fail(self, error_message: str) -> None:
        """UPDATE the ToolCall row with an error payload + latency.

        Stored as ``{"error": <truncated message>}`` so downstream queries can
        tell success from failure without parsing free text.
        """
        await self._update({"error": str(error_message)[:500]}, ok=False)
