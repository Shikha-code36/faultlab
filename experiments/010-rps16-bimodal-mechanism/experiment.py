"""Experiment 010: What causes RPS16's bimodal bounded-grace rescue rate."""

from __future__ import annotations

import csv
import statistics

from brinkline.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="010",
    slug="rps16-bimodal-mechanism",
    title="What causes RPS16's bimodal bounded-grace rescue rate",
    status="open",
    question="R002 found that bounded_grace at RPS16 splits into two distinct rescue-rate regimes (~20% vs ~62%) across otherwise-identical replicate runs, invisible to the aggregate error rate. Does a timestamped decision trace show each run settling into one stable mode from the start, a mid-run phase transition, or continuous fine-grained oscillation between modes?",
    hypothesis="Not a directional hypothesis -- a characterization question, using new per-decision timestamp instrumentation (admission_decision_trace.csv's t_ns field, added this session) not available when R002 was run. No new (condition, rps) cells are compared; this replicates only the single bounded_grace/RPS16 cell already identified as anomalous, at higher time-resolution.",
    primary_variable="run_index",
    fixed_params={
        "rps": 16,
        "injected_latency_ms": 400,
        "retry_policy": "none",
        "breaker_enabled": False,
        "pool_size": 10,
        "admission_control_mode": "bounded_grace",
        "admission_grace_ms": 20,
    },
)

# First-pass replicate count for a characterization question, not a
# comparison -- there's nothing to power-calculate against. If the shape
# found is ambiguous (e.g. modes aren't cleanly separable even with
# time-resolution), more replicates may be added, same escalation
# discipline as R001/R002.
N_RUNS = 10

# Number of equal-width time buckets each run's ~90s measurement window is
# split into, to see the rescue rate's shape over time within a run --
# coarse enough to be readable, fine enough to catch a single mid-run
# transition (a 90s window / 9 buckets is one bucket per 10s).
N_BUCKETS = 9


class ExperimentRps16BimodalMechanism(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        return [
            {
                "rps": 16,
                "latency_ms": 400,
                "retry_policy": "none",
                "breaker_enabled": False,
                "pool_size": 10,
                "admission_control_enabled": True,
                "admission_control_mode": "bounded_grace",
                "admission_grace_ms": 20,
                "enable_admission_decision_trace": True,
            }
            for _ in range(N_RUNS)
        ]

    def _decision_timeline(self, run_id: str) -> list[dict]:
        trace_path = self.runs_dir / run_id / "admission_decision_trace.csv"
        with trace_path.open(newline="") as f:
            rows = list(csv.DictReader(f))
        return [
            {
                "t_ns": int(row["t_ns"]),
                "deferred": row["deferred"] == "True",
                "rejected": row["rejected"] == "True",
            }
            for row in rows
            if row.get("t_ns")
        ]

    def _bucketed_rescue_rates(self, decisions: list[dict]) -> list[float | None]:
        deferred = [d for d in decisions if d["deferred"]]
        if not deferred:
            return [None] * N_BUCKETS

        t0 = min(d["t_ns"] for d in decisions)
        t1 = max(d["t_ns"] for d in decisions)
        span = max(t1 - t0, 1)

        buckets: list[list[dict]] = [[] for _ in range(N_BUCKETS)]
        for d in deferred:
            frac = (d["t_ns"] - t0) / span
            idx = min(int(frac * N_BUCKETS), N_BUCKETS - 1)
            buckets[idx].append(d)

        return [
            (sum(1 for d in b if not d["rejected"]) / len(b)) if b else None
            for b in buckets
        ]

    def analyze(self, runs: list[dict]) -> dict:
        from brinkline.analysis import annotate_saturation

        annotate_saturation(runs)

        per_run = {}
        for r in runs:
            run_id = r["run_id"]
            decisions = self._decision_timeline(run_id)
            deferred = [d for d in decisions if d["deferred"]]
            rescued = [d for d in deferred if not d["rejected"]]
            overall_rate = (len(rescued) / len(deferred)) if deferred else None

            per_run[run_id] = {
                "deferred_count": len(deferred),
                "overall_rescue_rate": overall_rate,
                "bucketed_rescue_rate": self._bucketed_rescue_rates(decisions),
            }

        overall_rates = [
            v["overall_rescue_rate"] for v in per_run.values() if v["overall_rescue_rate"] is not None
        ]

        return {
            "per_run": per_run,
            "overall_rescue_rate_mean": statistics.mean(overall_rates) if overall_rates else None,
            "overall_rescue_rate_stdev": statistics.stdev(overall_rates) if len(overall_rates) > 1 else None,
        }


experiment = ExperimentRps16BimodalMechanism()
