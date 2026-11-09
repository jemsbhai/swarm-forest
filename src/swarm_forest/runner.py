"""Runner CLI: execute all three conditions, replay each, write results.

Usage:
    python -m swarm_forest.runner [--out results] [--scenario quick]

For every condition the runner records a fresh run into its own SQLite
store, then replays the same driver against that store in pollard
HYBRID mode and compares the forest recorder digests. Outputs:
``results.json`` (machine-readable) and ``results.md`` (the table).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import platform
from pathlib import Path

import epicormic
import pollard
from pollard import ReplayMode

from .scenario import Scenario
from .swarm import CONDITIONS, SwarmRun, reset_fn_calls, FN_CALLS


def run_condition(condition: str, scenario: Scenario, out_dir: Path) -> dict:
    db_path = out_dir / f"{condition}.db"
    if db_path.exists():
        db_path.unlink()
    record = SwarmRun(condition, scenario, db_path, mode=ReplayMode.RECORD)
    result = record.run_all()

    reset_fn_calls()
    replay = SwarmRun(condition, scenario, db_path, mode=ReplayMode.HYBRID)
    replay_result = replay.run_all()
    fn_invocations = FN_CALLS["work"] + FN_CALLS["delegate"]
    result["replay"] = {
        "trace_hash": replay_result["trace_hash"],
        "trace_hash_match": replay_result["trace_hash"] == result["trace_hash"],
        "step_function_invocations": fn_invocations,
        "store_verify_ok": replay.verify_chains(),
        "spend_accounting_match": replay_result["spend_accounting_match"],
    }
    return result


def render_markdown(doc: dict) -> str:
    lines = [
        "# Results: Alignment Does Not Compose",
        "",
        "Three conditions, same swarm, same scenario parameters, deterministic agents.",
        "",
        "| Metric | Ungoverned | Governed | Governed + drift |",
        "| --- | --- | --- | --- |",
    ]

    def row(label: str, key, fmt=str) -> None:
        vals = []
        for cond in CONDITIONS:
            r = doc["conditions"][cond]
            v = r
            for part in key.split("."):
                v = v[part]
            vals.append(fmt(v))
        lines.append(f"| {label} | " + " | ".join(vals) + " |")

    row("Total spend (credits)", "total_spend_credits")
    row("Pool (credits)", "pool_credits")
    row("Over pool", "over_pool", lambda v: "yes" if v else "no")
    row("Max delegation depth", "max_delegation_depth")
    row("Items created", "items_created")
    row("Items completed", "items_completed")
    row("Items failed", "items_failed")
    row("Sub-items abandoned at refused splits", "items_abandoned")
    row("Task success (complete and within pool)", "task_success", lambda v: "yes" if v else "no")
    row("Policy denials", "gate_interventions.policy_denials")
    row("Confirmations requested", "gate_interventions.confirmations_requested")
    row("Confirmations approved", "gate_interventions.confirmations_approved")
    row("Confirmations lapsed", "gate_interventions.confirmations_lapsed")
    row("Budget refusals", "gate_interventions.budget_refusals")
    row("Drift refusals", "gate_interventions.drift_refusals")
    row("Replay trace hash match", "replay.trace_hash_match", lambda v: "yes" if v else "no")
    row("Step functions invoked in replay", "replay.step_function_invocations")
    row("Store verify ok", "replay.store_verify_ok", lambda v: "yes" if v else "no")
    lines.append("")
    drift = doc["conditions"]["governed_drift"].get("drift")
    if drift:
        lines += [
            "## Drift condition detail",
            "",
            f"- Watched agent: {drift['agent']} (work cost x{drift['cost_multiplier']} after onset)",
            f"- Onset at stream index {drift['onset_stream_index']}; "
            f"Page-Hinkley alarm at index {drift['alarm_stream_index']}; "
            f"detection delay {drift['detection_delay_steps']} steps",
            f"- CUSUM cross-check alarm at index {drift['cusum_alarm_stream_index']}",
            f"- False alarm before onset: Page-Hinkley "
            f"{drift['false_alarm_before_onset_page_hinkley']}, "
            f"CUSUM {drift['false_alarm_before_onset_cusum']}",
            "- Containment:",
        ]
        for entry in drift["containment"]:
            lines.append(f"  - {entry}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="results", help="output directory")
    args = parser.parse_args(argv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenario = Scenario()
    doc = {
        "title": "Alignment Does Not Compose: Governed Execution Forests for Agent Swarms",
        "packages": {
            "pollard": pollard.__version__,
            "epicormic": epicormic.__version__,
            "python": platform.python_version(),
        },
        "scenario": dataclasses.asdict(scenario),
        "conditions": {},
    }
    for condition in CONDITIONS:
        doc["conditions"][condition] = run_condition(condition, scenario, out_dir)
        r = doc["conditions"][condition]
        print(
            f"{condition}: spend={r['total_spend_credits']} pool={r['pool_credits']} "
            f"success={r['task_success']} depth={r['max_delegation_depth']} "
            f"replay_match={r['replay']['trace_hash_match']}"
        )
    (out_dir / "results.json").write_text(json.dumps(doc, indent=2) + "\n")
    (out_dir / "results.md").write_text(render_markdown(doc))
    print(f"wrote {out_dir / 'results.json'} and {out_dir / 'results.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
