"""The forest recorder: a canonical trace of decisions and edges.

The recorder observes every action the driver attempts, in order, as a
tuple of plain values: work actions with their charged cost, delegation
edges with their outcome (executed, confirmed then executed, denied by
policy, refused by budget, refused by the drift lever), drift alarms and
freezes. The trace digest is the SHA-256 of the canonical JSON encoding
of the event list.

Replay runs the same driver against the same pollard store in HYBRID
mode: executed calls resolve from their recordings without invoking the
step functions, and refusals re-derive from the same policy and budget
state. If the replayed recorder produces the same digest, the recorded
forest replays exactly at the level of decisions and edges.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


@dataclass
class ForestRecorder:
    events: list[tuple] = field(default_factory=list)

    def work(self, agent: str, item_id: str, cost: int, outcome: str) -> None:
        self.events.append(("work", agent, item_id, cost, outcome))

    def delegate(
        self, delegator: str, target: str, item_id: str, depth: int, outcome: str
    ) -> None:
        self.events.append(("delegate", delegator, target, item_id, depth, outcome))

    def drift_alarm(self, agent: str, stream_index: int) -> None:
        self.events.append(("drift_alarm", agent, stream_index))

    def freeze(self, agent: str) -> None:
        self.events.append(("freeze", agent))

    def digest(self) -> str:
        blob = json.dumps(self.events, separators=(",", ":"), sort_keys=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
