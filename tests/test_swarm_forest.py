"""Tests for swarm_forest.

Unit tests exercise the pollard/epicormic integration points directly
(pool accounting through a SharedBudget, the delegation gate, the drift
monitor). Integration tests run the real conditions and assert the
designed contrast plus exact replay.
"""

from __future__ import annotations

import pytest
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
)

from swarm_forest.drift import DriftMonitor
from swarm_forest.gates import DelegationPolicy
from swarm_forest.meters import CreditMeter
from swarm_forest.scenario import Scenario
from swarm_forest.swarm import FN_CALLS, SwarmRun, reset_fn_calls


def _work(payload):
    return {"output": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}}


@pytest.fixture()
def scenario() -> Scenario:
    return Scenario()


# -- pool accounting ----------------------------------------------------------


def test_shared_pool_accounting_and_refusal(tmp_path):
    """Two runs draw on one SharedBudget; the pool refuses across runs."""
    store = SQLiteStore(tmp_path / "pool.db")
    runtime = Runtime(
        store,
        meters=[CreditMeter()],
        shared_budgets=[SharedBudget("pool", Budget(extra={"credits": 25}))],
    )
    run_a = runtime.run("agent:a", budget=Budget(extra={"credits": 100}))
    run_b = runtime.run("agent:b", budget=Budget(extra={"credits": 100}))
    run_a.model_call({"model": "w", "task": "a1", "cost": 10}, fn=_work)
    run_b.model_call({"model": "w", "task": "b1", "cost": 10}, fn=_work)
    # 20 of 25 pool credits spent; a further 10-credit action in either
    # run would exceed the shared pool and must be refused pre-dispatch.
    with pytest.raises(BudgetExceeded):
        run_a.model_call({"model": "w", "task": "a2", "cost": 10}, fn=_work)
    total = sum(
        float(recompute_charges(store, r.root_id).get("credits", 0))
        for r in (run_a, run_b)
    )
    assert total == 20.0


def test_sub_allocation_refusal(tmp_path):
    """A per-run sub-allocation refuses even while the pool has headroom."""
    store = SQLiteStore(tmp_path / "sub.db")
    runtime = Runtime(
        store,
        meters=[CreditMeter()],
        shared_budgets=[SharedBudget("pool", Budget(extra={"credits": 500}))],
    )
    run = runtime.run("agent:a", budget=Budget(extra={"credits": 15}))
    run.model_call({"model": "w", "task": "a1", "cost": 10}, fn=_work)
    with pytest.raises(BudgetExceeded):
        run.model_call({"model": "w", "task": "a2", "cost": 10}, fn=_work)


# -- delegation gate ------------------------------------------------------------


def _gated_runtime(tmp_path, policy):
    store = SQLiteStore(tmp_path / "gate.db")

    def handler(args):
        return {"accepted": True, "to": args["to"], "task": args["task"]}

    spec = ActionSpec(
        name="delegate",
        version="1",
        description="delegate",
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
        handler=handler,
    )
    return Runtime(
        store,
        meters=[CreditMeter()],
        registry=Registry([spec]),
        policies=[policy],
    )


def test_depth_gate_deny_and_confirm(tmp_path):
    policy = DelegationPolicy(max_depth=2, spawn_limit=10)
    runtime = _gated_runtime(tmp_path, policy)
    run = runtime.run("agent:atlas", budget=Budget(extra={"credits": 100}))
    # depth 3 exceeds the gate: denied by policy, recorded as a refusal.
    with pytest.raises(PolicyViolation):
        run.tool_call("delegate", {"to": "gale", "task": "x", "depth": 3, "cost": 1})
    assert policy.stats.depth_denials == 1
    # depth 2 sits exactly at the gate: confirmation required, then runs.
    with pytest.raises(ConfirmationRequired) as excinfo:
        run.tool_call("delegate", {"to": "gale", "task": "x", "depth": 2, "cost": 1})
    node = run.confirm(excinfo.value.resume_token)
    assert node.kind == "tool_call"
    assert policy.stats.confirmations_requested == 1


def test_spawn_limit_and_freeze(tmp_path):
    policy = DelegationPolicy(max_depth=5, spawn_limit=1)
    runtime = _gated_runtime(tmp_path, policy)
    run = runtime.run("agent:atlas", budget=Budget(extra={"credits": 100}))
    run.tool_call("delegate", {"to": "gale", "task": "x", "depth": 1, "cost": 1})
    with pytest.raises(PolicyViolation):
        run.tool_call("delegate", {"to": "gale", "task": "y", "depth": 1, "cost": 1})
    assert policy.stats.spawn_denials == 1
    policy.freeze("atlas")
    with pytest.raises(PolicyViolation):
        run.tool_call("delegate", {"to": "gale", "task": "z", "depth": 1, "cost": 1})
    assert policy.stats.frozen_denials == 1


# -- drift monitor ---------------------------------------------------------------


def _monitor() -> DriftMonitor:
    return DriftMonitor(
        ph_delta=1.0, ph_threshold=6.0, cusum_k_fraction=0.5, cusum_h=8.0,
        min_samples=5,
    )


def test_drift_alarm_fires_after_onset_not_before():
    monitor = _monitor()
    for cost in (1, 1, 1, 1, 1, 1):
        assert monitor.feed(cost) is None
    assert monitor.prefix_alarms(6) == (False, False)
    alarm = monitor.feed(40)
    assert alarm is not None
    assert alarm.stream_index == 6
    assert alarm.cusum_alarm_index == 6


def test_drift_monitor_quiet_on_stationary_stream():
    monitor = _monitor()
    for cost in (10, 12, 10, 11, 10, 12, 11, 10, 12, 11):
        assert monitor.feed(cost) is None
    assert monitor.alarm is None


# -- full conditions ---------------------------------------------------------------


def _run_pair(condition: str, scenario: Scenario, tmp_path):
    db = tmp_path / f"{condition}.db"
    record = SwarmRun(condition, scenario, db, mode=ReplayMode.RECORD)
    record_result = record.run_all()
    reset_fn_calls()
    replay = SwarmRun(condition, scenario, db, mode=ReplayMode.HYBRID)
    replay_result = replay.run_all()
    return record_result, replay_result, replay


def test_condition_contrast(scenario, tmp_path):
    ungoverned, _, _ = _run_pair("ungoverned", scenario, tmp_path)
    governed, _, _ = _run_pair("governed", scenario, tmp_path)
    # Ungoverned: the locally rational delegation cascade overruns the pool.
    assert ungoverned["roots_completed"]
    assert ungoverned["total_spend_credits"] > ungoverned["pool_credits"]
    assert not ungoverned["task_success"]
    assert ungoverned["max_delegation_depth"] > governed["max_delegation_depth"]
    # Governed: contained by the gate, completes inside the pool.
    assert governed["task_success"]
    assert governed["total_spend_credits"] <= governed["pool_credits"]
    assert governed["max_delegation_depth"] == scenario.max_delegation_depth
    assert governed["gate_interventions"]["depth_denials"] > 0
    assert governed["gate_interventions"]["confirmations_approved"] > 0
    assert governed["total_spend_credits"] < ungoverned["total_spend_credits"]


def test_replay_equality(scenario, tmp_path):
    for condition in ("ungoverned", "governed", "governed_drift"):
        record_result, replay_result, replay = _run_pair(condition, scenario, tmp_path)
        assert replay_result["trace_hash"] == record_result["trace_hash"]
        assert replay_result["total_spend_credits"] == record_result["total_spend_credits"]
        assert FN_CALLS["work"] + FN_CALLS["delegate"] == 0
        assert replay.verify_chains()


def test_drift_condition_contained(scenario, tmp_path):
    result, _, _ = _run_pair("governed_drift", scenario, tmp_path)
    drift = result["drift"]
    assert drift["onset_stream_index"] is not None
    assert drift["alarm_stream_index"] >= drift["onset_stream_index"]
    assert drift["detection_delay_steps"] <= 2
    assert drift["false_alarm_before_onset_page_hinkley"] is False
    assert drift["false_alarm_before_onset_cusum"] is False
    assert drift["verdict_status"] in ("recorded", "already_recorded")
    assert drift["frozen_agent"] == scenario.drift_agent
    assert result["gate_interventions"]["drift_refusals"] >= 1
    assert result["task_success"]
