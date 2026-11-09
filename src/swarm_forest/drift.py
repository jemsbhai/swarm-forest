"""The drift layer: sequential detection over a per-agent cost stream.

The monitored stream is the sequence of executed action costs (work
charges and delegation fees) of one watched agent, in execution order.
Detection uses epicormic's own sequential detectors,
``epicormic.stats.sequential.page_hinkley`` (primary) and ``cusum``
(cross-check), evaluated on the stream prefix after every new sample.

On the first Page-Hinkley alarm the swarm layer assembles an epicormic
verdict document from the detector output (state ``drift``, rule
``page_hinkley``, the sequential states of both detectors) and records it
through epicormic's own ``record_verdict``, so the monitor chain and the
epicormic ``Ledger`` carry the verdict. From that point epicormic's
``DriftMeter`` (registered on the runtime for tool calls) refuses every
further delegation swarm-wide, and the driver freezes the watched agent.

The verdict document is assembled by this layer rather than produced by
epicormic's probe-panel scorer pipeline, because the monitored stream is
swarm telemetry, not provider probe responses. The opinion field is the
vacuous opinion: no panel opinion is computed. Everything downstream of
the verdict (ledger state, DriftMeter refusal) is epicormic code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from epicormic import Ledger
from epicormic.opinion import vacuous
from epicormic.stats.sequential import cusum, page_hinkley
from epicormic.verdict import VERDICT_FORMAT, Monitor, Verdict, record_verdict
from pollard import SQLiteStore

MONITOR_ID = "swarm-drift"
PANEL_DOCUMENT = b"swarm-forest/panel/v1: per-agent executed action cost stream"
PANEL_DIGEST = hashlib.sha256(PANEL_DOCUMENT).hexdigest()
BASELINE_WINDOW_ID = "swarm-baseline"


@dataclass
class Alarm:
    stream_index: int
    ph_excursion: float
    cusum_alarm_index: int | None


@dataclass
class DriftMonitor:
    ph_delta: float
    ph_threshold: float
    cusum_k_fraction: float
    cusum_h: float
    min_samples: int
    stream: list[float] = field(default_factory=list)
    alarm: Alarm | None = None
    verdict_recorded: bool = False
    verdict_node_id: str | None = None

    def _baseline_mean(self) -> float:
        head = self.stream[: self.min_samples] or self.stream
        return sum(head) / len(head) if head else 0.0

    def _cusum(self, values: list[float]):
        k = max(1.0, self._baseline_mean() * (1.0 + self.cusum_k_fraction))
        return cusum(values, k=k, h=self.cusum_h)

    def feed(self, cost: float) -> Alarm | None:
        """Append one executed action cost; return an Alarm on first detection."""
        self.stream.append(float(cost))
        if self.alarm is not None or len(self.stream) <= self.min_samples:
            return None
        ph = page_hinkley(self.stream, delta=self.ph_delta, threshold=self.ph_threshold)
        if not ph.alarm:
            return None
        cs = self._cusum(self.stream)
        self.alarm = Alarm(
            stream_index=ph.alarm_index,
            ph_excursion=ph.excursion,
            cusum_alarm_index=cs.alarm_index if cs.alarm else None,
        )
        return self.alarm

    def prefix_alarms(self, end: int) -> tuple[bool, bool]:
        """Whether PH / CUSUM alarm on the prefix before ``end`` (false-alarm check)."""
        prefix = self.stream[:end]
        if len(prefix) <= self.min_samples:
            return (False, False)
        ph = page_hinkley(prefix, delta=self.ph_delta, threshold=self.ph_threshold)
        cs = self._cusum(prefix)
        return (ph.alarm, cs.alarm)

    def record_verdict(self, store: SQLiteStore, *, window_id: str) -> str:
        """Record the drift verdict through epicormic's ledger path.

        Returns "recorded", "already_recorded" (replay: the verdict is in
        the chain from the recorded pass), or "no_alarm".
        """
        if self.alarm is None:
            return "no_alarm"
        ledger = Ledger(store)
        existing = ledger.state(MONITOR_ID, PANEL_DIGEST)
        if existing is not None and existing.state == "drift":
            self.verdict_recorded = True
            self.verdict_node_id = existing.verdict_node_id
            return "already_recorded"
        history = ledger.history(MONITOR_ID, PANEL_DIGEST)
        sequence_index = len(history) + 1
        ph = page_hinkley(self.stream, delta=self.ph_delta, threshold=self.ph_threshold)
        cs = self._cusum(self.stream)
        monitor = Monitor(
            monitor_id=MONITOR_ID,
            panel_digest=PANEL_DIGEST,
            baseline_window_ids=(BASELINE_WINDOW_ID,),
        )
        payload = {
            "format": VERDICT_FORMAT,
            "event": "epicormic_verdict",
            "monitor_id": MONITOR_ID,
            "panel_digest": PANEL_DIGEST,
            "baseline_window_ids": [BASELINE_WINDOW_ID],
            "current_window_id": window_id,
            "sequence_index": sequence_index,
            "state": "drift",
            "rule_fired": "page_hinkley",
            "sample_counts": {"stream": len(self.stream)},
            "scorers": {
                "agent_action_cost": {
                    "kind": "swarm_telemetry",
                    "sequential": {
                        "page_hinkley": {
                            "excursion": str(ph.excursion),
                            "delta": str(ph.delta),
                            "lambda": str(ph.threshold),
                            "windows": ph.steps,
                            "alarm": ph.alarm,
                            "alarm_index": ph.alarm_index,
                        },
                        "cusum": {
                            "s_plus": str(cs.s_plus),
                            "s_minus": str(cs.s_minus),
                            "k": str(cs.k),
                            "h": str(cs.h),
                            "windows": cs.steps,
                            "alarm": cs.alarm,
                            "alarm_index": cs.alarm_index,
                        },
                    },
                }
            },
        }
        verdict = Verdict(
            monitor=monitor,
            current_window_id=window_id,
            sequence_index=sequence_index,
            state="drift",
            rule_fired="page_hinkley",
            opinion=vacuous(),
            payload=payload,
        )
        recorded = record_verdict(store, verdict)
        self.verdict_recorded = True
        self.verdict_node_id = recorded.node_id
        return "recorded"
