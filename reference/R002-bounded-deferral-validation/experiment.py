"""R002: Reference-grade replication of Experiment 009's regime-dependent
bounded-deferral claim, at the eight (condition, rps) cells that define it."""

from __future__ import annotations

import random
import statistics
from collections import defaultdict

from faultlab.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="R002",
    slug="bounded-deferral-validation",
    title="Reference-grade validation of Experiment 009's bounded-deferral claim",
    status="closed",
    evidence_grade="reference",
    question=(
        "Experiment 009 found (from a single run per condition) that bounded "
        "admission deferral reduces client-visible error near the collapse "
        "boundary (RPS 14: 16.7% instantaneous vs 13.1% bounded_grace) but "
        "that benefit converges to zero as offered load increases further "
        "(RPS 16, RPS 18), with RPS 12 as a clean validity check (0%/0% for "
        "both conditions). Does replication at the eight cells that define "
        "this regime-transition claim support it, or does observed "
        "run-to-run variance require weakening it?"
    ),
    hypothesis=(
        "Not a directional hypothesis -- an estimation question. This "
        "document estimates the error-rate distribution at each "
        "(admission_control_mode, rps) cell across replicated runs, and at "
        "the bounded_grace cells also estimates the distribution of the "
        "deferred-decision rescue rate (the fraction of provisional rejects "
        "resolved after the wait) -- the mechanism 009 attributes the "
        "error-rate gap to. It describes whether 009's regime-transition "
        "shape (large effect at RPS14, shrinking through RPS16, negligible "
        "by RPS18) holds up once variance is visible for the first time. No "
        "pass/fail threshold is preregistered; see README for why."
    ),
    primary_variable="admission_control_mode",
    fixed_params={
        "injected_latency_ms": 400,
        "retry_policy": "none",
        "breaker_enabled": False,
        "pool_size": 10,
        "admission_grace_ms": 20,
    },
)

# The eight cells that define Experiment 009's regime-transition claim --
# both conditions the finding compares, at all four RPS points the original
# swept. The "off" condition is excluded: it was a same-session control
# against Experiment 006, not part of what 009 claims about deferral itself.
CONDITIONS = ["instantaneous", "bounded_grace"]
CELLS_RPS = [12, 14, 16, 18]

# First-pass design choice, not power-calculated -- see README's escalation
# rule for what happens if this turns out to be too few. Same choice R001
# made, for the same reason: no prior variance data exists, since every run
# in 009 was N=1.
REPLICATION_N = 5

# Run order is shuffled, not grouped by cell -- same rationale as R001: at
# 40 runs, time-of-day/thermal/host-state drift over the sweep's duration
# would otherwise correlate with a single condition rather than averaging
# out across all eight. Seeded for reproducibility of the executed order
# itself, not because the seed value is scientifically meaningful.
SHUFFLE_SEED = 1


class ExperimentR002(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        configs = [
            {
                "rps": rps,
                "latency_ms": METADATA.fixed_params["injected_latency_ms"],
                "retry_policy": "none",
                "breaker_enabled": False,
                "pool_size": 10,
                "admission_control_enabled": True,
                "admission_control_mode": condition,
                "admission_grace_ms": 20,
                # Needed to estimate the rescue-rate distribution at the
                # bounded_grace cells, mirroring 009's Gate 1 fidelity check.
                "enable_admission_decision_trace": True,
            }
            for condition in CONDITIONS
            for rps in CELLS_RPS
            for _ in range(REPLICATION_N)
        ]
        random.Random(SHUFFLE_SEED).shuffle(configs)
        return configs

    def _rescue_rate(self, run_id: str) -> float | None:
        # The rescue rate isn't in results.json -- only the raw per-decision
        # trace 009 also relied on is (admission_decision_trace.csv, written
        # by Runner when enable_admission_decision_trace=True). Deferred rows
        # are provisional rejects; a deferred row that ends up not rejected
        # was rescued by the second read.
        import csv as csv_module

        trace_path = self.runs_dir / run_id / "admission_decision_trace.csv"
        if not trace_path.exists():
            return None

        deferred_total = 0
        rescued = 0
        with trace_path.open(newline="") as f:
            for row in csv_module.DictReader(f):
                if row["deferred"] != "True":
                    continue
                deferred_total += 1
                if row["rejected"] != "True":
                    rescued += 1

        return (rescued / deferred_total) if deferred_total else None

    def analyze(self, runs: list[dict]) -> dict:
        # Same reasoning as R001: this replicates known cells rather than
        # searching an RPS sweep for a new boundary, so the base class's
        # first-saturation-point machinery doesn't apply -- override rather
        # than calling super(). Each run is still annotated (shared CLI
        # table printer, and cross-checking the saturation flag agrees).
        from faultlab.analysis import annotate_saturation

        annotate_saturation(runs)

        groups = defaultdict(list)
        for r in runs:
            groups[(r.get("admission_control_mode"), r.get("rps"))].append(r)

        cell_statistics = {}
        for (condition, rps), group_runs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            error_rates = [r["error_rate"] for r in group_runs if r.get("error_rate") is not None]

            cell = {
                "n": len(group_runs),
                "error_rate_mean": statistics.mean(error_rates) if error_rates else None,
                "error_rate_stdev": statistics.stdev(error_rates) if len(error_rates) > 1 else None,
                "error_rate_min": min(error_rates) if error_rates else None,
                "error_rate_max": max(error_rates) if error_rates else None,
            }

            if condition == "bounded_grace":
                rescue_rates = [
                    rate
                    for r in group_runs
                    if (rate := self._rescue_rate(r["run_id"])) is not None
                ]
                cell["rescue_rate_mean"] = statistics.mean(rescue_rates) if rescue_rates else None
                cell["rescue_rate_stdev"] = statistics.stdev(rescue_rates) if len(rescue_rates) > 1 else None

            cell_statistics[f"{condition}_rps{rps}"] = cell

        return {"cell_statistics": cell_statistics}


experiment = ExperimentR002()
