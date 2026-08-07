"""R003: Reference-grade replication of Experiment 011's claim that EWMA
admission performance degrades continuously with half-life, not as a
cliff, at the eight (condition) cells that define it -- all at RPS 16."""

from __future__ import annotations

import random
import statistics
from collections import defaultdict

from slimybug.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="R003",
    slug="half-life-sensitivity-validation",
    title="Reference-grade validation of Experiment 011's half-life sensitivity claim",
    status="closed",
    evidence_grade="reference",
    question=(
        "Experiment 011 found (from a single run per condition) that error "
        "rate rises smoothly across a log-spaced half-life sweep at RPS 16 "
        "-- 23-26% at the shortest half-lives (matching instantaneous), "
        "climbing to 99.93% at 4.0s (matching off), with no adjacent pair "
        "of half-lives separated by a disproportionate jump. But RPS 16 is "
        "specifically the operating point Experiment 010 showed is prone to "
        "rare, self-locking pool-saturation events -- most runs flicker in "
        "and out of capacity in short streaks, but occasionally one run "
        "locks into a single continuous saturated streak for its whole "
        "duration. Does replication at each of 011's eight cells support "
        "the smooth-curve claim, or does variance at this RPS point reveal "
        "that individual half-lives are less stable than a single run "
        "could show?"
    ),
    hypothesis=(
        "Not a directional hypothesis -- an estimation question. This "
        "document estimates the error-rate distribution at each of 011's "
        "eight cells (off, instantaneous, and six half-lives) across "
        "replicated runs. It describes whether 011's shape -- a continuous "
        "rise with no disproportionate step between adjacent half-lives, "
        "converging to instantaneous at the low end and to off at the high "
        "end -- holds up once variance is visible for the first time, and "
        "whether any cell shows the kind of bimodal spread Experiment 010 "
        "found in a different mechanism at this same RPS point. No "
        "pass/fail threshold is preregistered; see README for why."
    ),
    primary_variable="admission_ewma_half_life_s",
    fixed_params={
        "injected_latency_ms": 400,
        "retry_policy": "none",
        "breaker_enabled": False,
        "pool_size": 10,
        "rps": 16,
    },
)

# The eight cells that define Experiment 011's claim, all at RPS 16 -- the
# single saturated point 011 tested. Unlike R002 (which excluded 009's "off"
# control), "off" is included here: 011's claim explicitly anchors the low
# end of the sweep at instantaneous and the high end at off, so both bookend
# controls are part of what's being validated, not incidental context.
HALF_LIVES_S = [0.06, 0.25, 0.5, 1.0, 2.0, 4.0]
RPS = METADATA.fixed_params["rps"]

# First-pass design choice, not power-calculated -- same choice R001/R002
# made, for the same reason: no prior variance data exists, since every run
# in 011 was N=1. Escalation rule (see README): if any cell's variance comes
# in much larger than the others -- the specific risk this validation exists
# to check, given Experiment 010's RPS16 finding -- additional replicates
# are added before writing the Finding, documented rather than silently
# expanded, same discipline R002 applied when it found real bimodality.
REPLICATION_N = 5

# Run order is shuffled, not grouped by cell -- same rationale as R001/R002:
# at 40 runs, time-of-day/thermal/host-state drift over the sweep's
# duration would otherwise correlate with a single condition rather than
# averaging out across all eight cells.
SHUFFLE_SEED = 1


class ExperimentR003(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        base = {
            "rps": RPS,
            "latency_ms": METADATA.fixed_params["injected_latency_ms"],
            "retry_policy": "none",
            "breaker_enabled": False,
            "pool_size": 10,
        }
        cells = [
            {**base, "admission_control_enabled": False, "admission_control_mode": "instantaneous"},
            {**base, "admission_control_enabled": True, "admission_control_mode": "instantaneous"},
        ] + [
            {
                **base,
                "admission_control_enabled": True,
                "admission_control_mode": "ewma",
                "admission_ewma_half_life_s": half_life,
            }
            for half_life in HALF_LIVES_S
        ]

        configs = [dict(cell) for cell in cells for _ in range(REPLICATION_N)]
        random.Random(SHUFFLE_SEED).shuffle(configs)
        return configs

    def analyze(self, runs: list[dict]) -> dict:
        # Same reasoning as R001/R002: this replicates known cells rather
        # than searching an RPS sweep for a new boundary, so the base
        # class's first-saturation-point machinery doesn't apply.
        from slimybug.analysis import annotate_saturation

        annotate_saturation(runs)

        def label(r: dict) -> str:
            if not r.get("admission_control_enabled"):
                return "off"
            if r.get("admission_control_mode") == "ewma":
                return f"ewma_hl{r.get('admission_ewma_half_life_s')}"
            return "instantaneous"

        groups = defaultdict(list)
        for r in runs:
            groups[label(r)].append(r)

        def _order(cond: str) -> tuple:
            if cond == "off":
                return (0, 0.0)
            if cond == "instantaneous":
                return (1, 0.0)
            return (2, float(cond.removeprefix("ewma_hl")))

        cell_statistics = {}
        for condition, group_runs in sorted(groups.items(), key=lambda kv: _order(kv[0])):
            error_rates = [r["error_rate"] for r in group_runs if r.get("error_rate") is not None]
            timeouts = [r["b_pool_timeout_count"] for r in group_runs if r.get("b_pool_timeout_count") is not None]
            ewma_max = [
                r["b_admission_ewma_utilization_max"]
                for r in group_runs
                if r.get("b_admission_ewma_utilization_max") is not None
            ]

            cell_statistics[condition] = {
                "n": len(group_runs),
                "error_rate_mean": statistics.mean(error_rates) if error_rates else None,
                "error_rate_stdev": statistics.stdev(error_rates) if len(error_rates) > 1 else None,
                "error_rate_min": min(error_rates) if error_rates else None,
                "error_rate_max": max(error_rates) if error_rates else None,
                "pool_timeout_count_mean": statistics.mean(timeouts) if timeouts else None,
                "ewma_utilization_max_mean": statistics.mean(ewma_max) if ewma_max else None,
            }

        return {"cell_statistics": cell_statistics}


experiment = ExperimentR003()
