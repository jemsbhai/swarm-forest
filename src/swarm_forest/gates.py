"""The delegation gate: a pollard policy over the registered delegate action.

Rules, evaluated in order for every ``delegate`` tool call:

1. Delegations from a frozen agent are denied (the drift layer freezes).
2. Delegations that would exceed the per-agent spawn limit are denied.
3. Delegations creating an edge deeper than ``max_depth`` are denied.
4. Delegations creating an edge exactly at ``max_depth`` require
   confirmation (pollard's approval gate). The driver acts as the
   approver and confirms only while the shared pool retains at least the
   configured floor fraction; it counts approvals and lapses.

Allowed delegations increment the delegator's spawn count. All counts are
kept on the policy object, which is shared by every run in the swarm
runtime, so the gate sees swarm-level state rather than one agent's tree.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pollard import Decision, PolicyContext


@dataclass
class GateStats:
    policy_denials: int = 0
    depth_denials: int = 0
    spawn_denials: int = 0
    frozen_denials: int = 0
    confirmations_requested: int = 0
    confirmations_approved: int = 0
    confirmations_lapsed: int = 0


@dataclass
class DelegationPolicy:
    max_depth: int
    spawn_limit: int
    stats: GateStats = field(default_factory=GateStats)
    spawns: dict[str, int] = field(default_factory=dict)
    frozen: set[str] = field(default_factory=set)

    def freeze(self, agent: str) -> None:
        self.frozen.add(agent)

    def decide(self, ctx: PolicyContext) -> Decision:
        if ctx.spec.name != "delegate":
            return Decision.ALLOW
        # The run label is "agent:<name>"; the delegator is the caller.
        delegator = ctx.run_label.split(":", 1)[-1]
        args = ctx.args
        depth = int(args["depth"])
        if delegator in self.frozen:
            self.stats.policy_denials += 1
            self.stats.frozen_denials += 1
            return Decision.DENY
        if self.spawns.get(delegator, 0) >= self.spawn_limit:
            self.stats.policy_denials += 1
            self.stats.spawn_denials += 1
            return Decision.DENY
        if depth > self.max_depth:
            self.stats.policy_denials += 1
            self.stats.depth_denials += 1
            return Decision.DENY
        if depth == self.max_depth:
            self.stats.confirmations_requested += 1
            return Decision.CONFIRM
        self.spawns[delegator] = self.spawns.get(delegator, 0) + 1
        return Decision.ALLOW

    def note_confirmed(self, delegator: str, approved: bool) -> None:
        """Record the outcome of a confirmation-gated delegation.

        Called by the driver after it approves (confirm) or lets the
        confirmation lapse. An approved delegation counts as a spawn.
        """
        if approved:
            self.stats.confirmations_approved += 1
            self.spawns[delegator] = self.spawns.get(delegator, 0) + 1
        else:
            self.stats.confirmations_lapsed += 1
