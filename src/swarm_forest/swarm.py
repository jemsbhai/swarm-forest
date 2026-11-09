"""The swarm driver: a forest of pollard trees joined by governed edges.

Each agent owns one pollard run (its execution tree). Local work is a
``model_call`` on the agent's run, priced by the CreditMeter. Delegation
is a registered ``delegate`` tool call on the delegator's run: the edge
exists in the delegator's tree, carries the target agent, the child item
and the delegation depth, and is subject to the DelegationPolicy gate
and to every budget scope. Governed conditions bind one pollard
SharedBudget named ``pool`` across all runs, plus a per-run
sub-allocation. The ungoverned condition uses the same trees and the
same registered action, with no policy, no pool and no sub-allocations.

The driver is deterministic: fixed roster order, fixed rotation for
delegation targets, fixed approver rule. Step functions are pure, so a
HYBRID replay against the recorded store resolves every executed call
from its recording and re-derives every refusal.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from pollard import (
    ActionSpec,
    Budget,
    BudgetExceeded,
    ConfirmationRequired,
    PolicyViolation,
    Registry,
    ReplayMode,
    Runtime,
    SQLiteStore,
    SharedBudget,
    recompute_charges,
    verify,
)
from epicormic import DriftMeter, Ledger

from .drift import MONITOR_ID, PANEL_DIGEST, DriftMonitor
from .gates import DelegationPolicy
from .meters import CreditMeter
from .recorder import ForestRecorder
from .scenario import COORDINATOR, ROSTER, Scenario, WorkItem, local_cost, root_items

CONDITIONS = ("ungoverned", "governed", "governed_drift")

# Step-function invocation counter. Replay must leave this at zero:
# executed calls resolve from recordings, refused calls never dispatch.
FN_CALLS = {"work": 0, "delegate": 0}


def reset_fn_calls() -> None:
    FN_CALLS["work"] = 0
    FN_CALLS["delegate"] = 0


def _work_step(payload: dict[str, Any]) -> dict[str, Any]:
    FN_CALLS["work"] += 1
    return {
        "output": f"worked {payload['task']}",
        "usage": {"input_tokens": 8, "output_tokens": 4},
    }


def _delegate_handler(args: dict[str, Any]) -> dict[str, Any]:
    FN_CALLS["delegate"] += 1
    return {"accepted": True, "to": args["to"], "task": args["task"]}


def _delegate_spec() -> ActionSpec:
    return ActionSpec(
        name="delegate",
        version="1",
        description="Delegate a sub-item of work to another agent in the swarm.",
        schema={
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "task": {"type": "string"},
                "depth": {"type": "integer"},
                "cost": {"type": "integer"},
            },
            "required": ["to", "task", "depth", "cost"],
        },
        side_effects=True,
        handler=_delegate_handler,
    )


class SwarmRun:
    def __init__(
        self,
        condition: str,
        scenario: Scenario,
        db_path: str | Path,
        mode: ReplayMode = ReplayMode.RECORD,
    ) -> None:
        if condition not in CONDITIONS:
            raise ValueError(f"unknown condition {condition!r}")
        self.condition = condition
        self.scenario = scenario
        self.governed = condition != "ungoverned"
        self.drift_condition = condition == "governed_drift"
        self.store = SQLiteStore(db_path)
        self.policy = (
            DelegationPolicy(
                max_depth=scenario.max_delegation_depth,
                spawn_limit=scenario.spawn_limit_per_agent,
            )
            if self.governed
            else None
        )
        meters: list[Any] = [CreditMeter()]
        if self.drift_condition:
            meters.append(
                DriftMeter(Ledger(self.store), MONITOR_ID, kinds=("tool_call",))
            )
        self.runtime = Runtime(
            self.store,
            meters=meters,
            registry=Registry([_delegate_spec()]),
            policies=[self.policy] if self.policy is not None else [],
            mode=mode,
            shared_budgets=(
                [
                    SharedBudget(
                        "pool", Budget(extra={"credits": scenario.pool_credits})
                    )
                ]
                if self.governed
                else []
            ),
        )
        run_budget = (
            Budget(extra={"credits": scenario.sub_allocation_credits})
            if self.governed
            else None
        )
        self.runs = {
            name: self.runtime.run(f"agent:{name}", budget=run_budget) for name in ROSTER
        }
        self.recorder = ForestRecorder()
        self.monitor = (
            DriftMonitor(
                ph_delta=scenario.ph_delta,
                ph_threshold=scenario.ph_threshold,
                cusum_k_fraction=scenario.cusum_k_fraction,
                cusum_h=scenario.cusum_h,
                min_samples=scenario.drift_min_samples,
            )
            if self.drift_condition
            else None
        )
        self.items: dict[str, WorkItem] = {}
        self.assign_counter = 0
        self.spent = 0
        self.max_depth = 0
        self.budget_refusals = 0
        self.drift_refusals = 0
        self.frozen_agents: set[str] = set()
        self.containment: list[str] = []
        # drift bookkeeping
        self.drift_active = False
        self.onset_index: int | None = None
        self.alarmed = False
        self.verdict_status: str | None = None

    # -- primitive attempts ---------------------------------------------------

    def _classify_refusal(self, exc: BudgetExceeded) -> str:
        try:
            payload = self.store.get(exc.refusal_id).payload
        except Exception:
            return "refused_budget"
        marker = f"{payload.get('reason', '')}:{payload.get('meter', '')}"
        return "refused_drift" if "epicormic" in marker else "refused_budget"

    def _attempt_work(self, agent: str, item: WorkItem) -> str:
        cost = local_cost(item.splits)
        inflated = (
            self.drift_condition
            and agent == self.scenario.drift_agent
            and self.drift_active
        )
        if inflated:
            cost *= self.scenario.drift_cost_multiplier
        run = self.runs[agent]
        try:
            run.model_call(
                {"model": "swarm-worker-v1", "task": item.item_id, "cost": cost},
                fn=_work_step,
            )
        except BudgetExceeded as exc:
            kind = self._classify_refusal(exc)
            if kind == "refused_drift":
                self.drift_refusals += 1
            else:
                self.budget_refusals += 1
            self.recorder.work(agent, item.item_id, cost, kind)
            return kind
        self.spent += cost
        self.recorder.work(agent, item.item_id, cost, "ok")
        self._feed_drift(agent, cost, inflated=inflated)
        return "ok"

    def _attempt_delegate(
        self, delegator: str, target: str, child: WorkItem
    ) -> str:
        fee = self.scenario.delegation_fee
        args = {"to": target, "task": child.item_id, "depth": child.depth, "cost": fee}
        run = self.runs[delegator]
        outcome: str
        try:
            run.tool_call("delegate", args)
            outcome = "ok"
        except ConfirmationRequired as exc:
            assert self.policy is not None
            if self._approver_allows():
                self.policy.note_confirmed(delegator, True)
                try:
                    run.confirm(exc.resume_token)
                    outcome = "ok_confirmed"
                except BudgetExceeded as exc2:
                    kind = self._classify_refusal(exc2)
                    if kind == "refused_drift":
                        self.drift_refusals += 1
                    else:
                        self.budget_refusals += 1
                    outcome = kind
            else:
                self.policy.note_confirmed(delegator, False)
                outcome = "lapsed"
        except PolicyViolation:
            outcome = "denied_policy"
        except BudgetExceeded as exc:
            kind = self._classify_refusal(exc)
            if kind == "refused_drift":
                self.drift_refusals += 1
            else:
                self.budget_refusals += 1
            outcome = kind
        if outcome in ("ok", "ok_confirmed"):
            self.spent += fee
            self.max_depth = max(self.max_depth, child.depth)
            self._feed_drift(delegator, fee, inflated=False)
        self.recorder.delegate(delegator, target, child.item_id, child.depth, outcome)
        return outcome

    def _approver_allows(self) -> bool:
        """Deterministic approver: confirm only while the pool keeps its floor."""
        floor = self.scenario.confirm_pool_floor_fraction * self.scenario.pool_credits
        return (self.scenario.pool_credits - self.spent) >= floor

    # -- drift ----------------------------------------------------------------

    def _feed_drift(self, agent: str, cost: int, *, inflated: bool) -> None:
        if not self.drift_condition or agent != self.scenario.drift_agent:
            return
        assert self.monitor is not None
        if inflated and self.onset_index is None:
            self.onset_index = len(self.monitor.stream)
        alarm = self.monitor.feed(cost)
        if (
            not self.drift_active
            and len(self.monitor.stream) >= self.scenario.drift_onset_after_actions
        ):
            self.drift_active = True
        if alarm is not None and not self.alarmed:
            self.alarmed = True
            self._contain(alarm.stream_index)

    def _contain(self, stream_index: int) -> None:
        agent = self.scenario.drift_agent
        assert self.monitor is not None and self.policy is not None
        self.recorder.drift_alarm(agent, stream_index)
        self.verdict_status = self.monitor.record_verdict(
            self.store, window_id=f"stream-{stream_index}"
        )
        entry = Ledger(self.store).state(MONITOR_ID, PANEL_DIGEST)
        self.containment.append(
            "epicormic verdict recorded through record_verdict "
            f"(status={self.verdict_status}); ledger state="
            f"{entry.state if entry is not None else 'missing'}"
        )
        self.policy.freeze(agent)
        self.frozen_agents.add(agent)
        self.recorder.freeze(agent)
        queued = sum(
            1 for it in self.items.values() if it.owner == agent and it.state == "queued"
        )
        self.containment.append(
            f"agent {agent} frozen at the delegation gate; "
            f"{queued} queued items reassigned to other agents"
        )
        probe = WorkItem(item_id="probe", splits=0, depth=1, owner="birch")
        outcome = self._attempt_delegate(COORDINATOR, "birch", probe)
        self.containment.append(
            f"post-verdict delegation probe by {COORDINATOR} -> {outcome} "
            "(epicormic DriftMeter refuses tool calls while the ledger state is drift)"
        )
        self.runs[agent].note(
            {"event": "frozen", "reason": "drift", "stream_index": stream_index}
        )

    # -- economy --------------------------------------------------------------

    def _next_open_agent(self, after: str) -> str:
        idx = ROSTER.index(after)
        for j in range(1, len(ROSTER) + 1):
            candidate = ROSTER[(idx + j) % len(ROSTER)]
            if candidate not in self.frozen_agents:
                return candidate
        return after

    def _work(self, item: WorkItem, actor: str | None = None) -> None:
        outcome = self._attempt_work(actor or item.owner, item)
        item.state = "worked" if outcome == "ok" else "failed"

    def _split(self, item: WorkItem, queue: deque[WorkItem]) -> None:
        agent = item.owner
        children: list[WorkItem] = []
        for j in range(self.scenario.fanout(agent)):
            owner = ROSTER[self.assign_counter % len(ROSTER)]
            self.assign_counter += 1
            child = WorkItem(
                item_id=f"{item.item_id}.{j}",
                splits=item.splits - 1,
                depth=item.depth + 1,
                owner=owner,
            )
            children.append(child)
            self.items[child.item_id] = child
        item.children = [c.item_id for c in children]
        for idx, child in enumerate(children):
            outcome = self._attempt_delegate(agent, child.owner, child)
            if outcome in ("ok", "ok_confirmed"):
                queue.append(child)
                continue
            # The split cannot complete: the delegator abandons it and
            # works the item itself, at its own local cost. Children
            # already delegated keep their sub-work; the failed child and
            # the ones never attempted are abandoned, covered by the
            # local work on the parent item.
            for undone in children[idx:]:
                undone.state = "abandoned"
            self._work(item, actor=agent)
            return
        item.state = "split"

    def run_all(self) -> dict[str, Any]:
        queue: deque[WorkItem] = deque(root_items(self.scenario))
        for item in queue:
            self.items[item.item_id] = item
        steps = 0
        while queue:
            steps += 1
            if steps > 10000:
                raise RuntimeError("economy did not terminate")
            item = queue.popleft()
            if item.owner in self.frozen_agents:
                item.owner = self._next_open_agent(item.owner)
                queue.append(item)
                continue
            if self.scenario.wants_split(item.owner, item.splits, item.depth):
                self._split(item, queue)
            else:
                self._work(item)
        return self._result()

    # -- results ----------------------------------------------------------------

    def _pollard_spend(self) -> float:
        total = 0.0
        for name in ROSTER:
            charges = recompute_charges(self.store, self.runs[name].root_id)
            total += float(charges.get("credits", 0))
        return total

    def verify_chains(self) -> bool:
        ok = True
        for name in ROSTER:
            root_id = self.runs[name].root_id
            nodes = list(self.store.walk(root_id))
            tips = [n for n in nodes if not self.store.children(n.id)]
            for tip in tips:
                ok = ok and verify(self.store, tip.id).ok
        return ok

    def _result(self) -> dict[str, Any]:
        roots = [self.items[f"r{i}"] for i in range(self.scenario.root_items)]
        completed = sum(
            1 for it in self.items.values() if it.state in ("worked", "split")
        )
        failed = sum(1 for it in self.items.values() if it.state == "failed")
        abandoned = sum(1 for it in self.items.values() if it.state == "abandoned")
        roots_done = all(it.state in ("worked", "split") for it in roots)
        pollard_spend = self._pollard_spend()
        result: dict[str, Any] = {
            "condition": self.condition,
            "total_spend_credits": self.spent,
            "pollard_recomputed_spend_credits": pollard_spend,
            "spend_accounting_match": abs(pollard_spend - self.spent) < 1e-9,
            "pool_credits": self.scenario.pool_credits,
            "pool_enforced": self.governed,
            "over_pool": self.spent > self.scenario.pool_credits,
            "max_delegation_depth": self.max_depth,
            "items_created": len(self.items),
            "items_completed": completed,
            "items_failed": failed,
            "items_abandoned": abandoned,
            "roots_completed": roots_done,
            "task_success": bool(roots_done and self.spent <= self.scenario.pool_credits),
            "gate_interventions": {
                "policy_denials": self.policy.stats.policy_denials if self.policy else 0,
                "depth_denials": self.policy.stats.depth_denials if self.policy else 0,
                "spawn_denials": self.policy.stats.spawn_denials if self.policy else 0,
                "frozen_denials": self.policy.stats.frozen_denials if self.policy else 0,
                "confirmations_requested": (
                    self.policy.stats.confirmations_requested if self.policy else 0
                ),
                "confirmations_approved": (
                    self.policy.stats.confirmations_approved if self.policy else 0
                ),
                "confirmations_lapsed": (
                    self.policy.stats.confirmations_lapsed if self.policy else 0
                ),
                "budget_refusals": self.budget_refusals,
                "drift_refusals": self.drift_refusals,
            },
            "trace_hash": self.recorder.digest(),
            "trace_events": len(self.recorder.events),
        }
        if self.drift_condition:
            assert self.monitor is not None
            alarm = self.monitor.alarm
            onset = self.onset_index
            ph_false, cusum_false = (
                self.monitor.prefix_alarms(onset) if onset is not None else (False, False)
            )
            result["drift"] = {
                "agent": self.scenario.drift_agent,
                "cost_multiplier": self.scenario.drift_cost_multiplier,
                "onset_stream_index": onset,
                "alarm_stream_index": alarm.stream_index if alarm else None,
                "detection_delay_steps": (
                    alarm.stream_index - onset
                    if alarm is not None and onset is not None
                    else None
                ),
                "cusum_alarm_stream_index": alarm.cusum_alarm_index if alarm else None,
                "false_alarm_before_onset_page_hinkley": ph_false,
                "false_alarm_before_onset_cusum": cusum_false,
                "stream_length": len(self.monitor.stream),
                "verdict_status": self.verdict_status,
                "verdict_node_id": self.monitor.verdict_node_id,
                "containment": self.containment,
                "frozen_agent": self.scenario.drift_agent if self.alarmed else None,
            }
        return result
