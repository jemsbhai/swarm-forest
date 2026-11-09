"""Scenario definition: the deterministic task economy.

A workload is a set of root work items. An item with ``splits > 0`` can be
split by delegation into ``fanout`` sub-items with ``splits - 1``; an item
that is not split is worked locally at cost ``local_cost(splits)``.
Splitting is locally rational for every agent: delegating an item costs
``fanout * delegation_fee`` charged to the splitter, far less than working
it locally, while the sub-work cost lands on the delegatees and on the
shared pool. Each agent follows the same local rule, and the swarm-level
cost is what grows. That is the non-composition failure under test.

Agents are deterministic. ``atlas`` is the coordinator and entry point.
``gale`` is the aggressive agent: fanout 3 and it splits at any depth,
while the other agents split only above depth 3 and use fanout 2 (atlas
fanout 3). Sub-items are assigned round-robin across the roster by a
global creation counter, so delegation targets are spread evenly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

COORDINATOR = "atlas"
AGGRESSIVE = "gale"
ROSTER: tuple[str, ...] = ("atlas", "gale", "birch", "cedar", "dune")


def local_cost(splits: int) -> int:
    """Cost of working an item locally instead of splitting it."""
    return 6 + 2 * splits


@dataclass(frozen=True)
class Scenario:
    seed: int = 20261108
    root_items: int = 3
    root_splits: int = 4
    delegation_fee: int = 1
    fanout_default: int = 2
    fanout_wide: int = 3
    habit_depth: int = 3  # non-aggressive agents split only above this depth
    # governance parameters (conditions 2 and 3)
    pool_credits: int = 300
    sub_allocation_credits: int = 100
    max_delegation_depth: int = 2
    spawn_limit_per_agent: int = 60
    confirm_pool_floor_fraction: float = 0.25
    # drift parameters (condition 3)
    drift_agent: str = AGGRESSIVE
    drift_onset_after_actions: int = 5
    drift_cost_multiplier: int = 4
    drift_min_samples: int = 5
    ph_delta: float = 1.0
    ph_threshold: float = 6.0
    cusum_k_fraction: float = 0.5
    cusum_h: float = 8.0

    def fanout(self, agent: str) -> int:
        if agent in (COORDINATOR, AGGRESSIVE):
            return self.fanout_wide
        return self.fanout_default

    def wants_split(self, agent: str, splits: int, depth: int) -> bool:
        if splits <= 0:
            return False
        if agent == AGGRESSIVE:
            return True
        return depth < self.habit_depth


@dataclass
class WorkItem:
    item_id: str
    splits: int
    depth: int
    owner: str
    state: str = "queued"  # queued | split | worked | failed
    children: list[str] = field(default_factory=list)


def root_items(scenario: Scenario) -> list[WorkItem]:
    return [
        WorkItem(item_id=f"r{i}", splits=scenario.root_splits, depth=0, owner=COORDINATOR)
        for i in range(scenario.root_items)
    ]
