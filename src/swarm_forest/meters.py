"""Pollard meter that prices swarm actions in credits.

Every model_call (local work) and tool_call (delegation) payload carries a
``cost`` in credits, either at the top level (work) or inside ``args``
(registered tool calls). The meter charges that cost under the meter name
``credits`` and reports it as the precheck estimate, so pollard budget
scopes (per-run sub-allocations and the shared pool) refuse an action
before dispatch when it would exceed a limit.
"""

from __future__ import annotations

from typing import Any


class CreditMeter:
    name = "credits"

    @staticmethod
    def _cost(payload: dict[str, Any]) -> int | None:
        cost = payload.get("cost")
        if cost is None and isinstance(payload.get("args"), dict):
            cost = payload["args"].get("cost")
        return int(cost) if cost is not None else None

    def charge(self, node_kind: str, payload: dict[str, Any], result: Any, meta: Any) -> int:
        if node_kind not in ("model_call", "tool_call"):
            return 0
        cost = self._cost(payload)
        return cost if cost is not None else 0

    def precheck_estimate(self, node_kind: str, payload: dict[str, Any]) -> int | None:
        if node_kind not in ("model_call", "tool_call"):
            return None
        return self._cost(payload)
