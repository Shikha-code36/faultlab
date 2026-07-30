"""R001: Reference-grade replication of Experiment 005's pool-capacity
linearity claim, at the six cells that define its two boundary ratios."""

from __future__ import annotations

import random
import statistics
from collections import defaultdict

from faultlab.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="R001",
    slug="pool-capacity-validation",
    title="Reference-grade validation of Experiment 005's pool-capacity linearity claim",
    status="closed",
    evidence_grade="reference",
    question=(
        "Experiment 005 found (from a single run per condition) that the "
        "collapse boundary scales linearly with pool size across a 4x "
        "range, with two exact ratios: last-clean-RPS/pool_size=1.2 and "
        "first-collapse-RPS/pool_size=1.4. Does replication at the six "
        "cells that define those ratios support that claim, or does "
        "observed run-to-run variance require weakening it?"
    ),
    hypothesis=(
        "Not a directional hypothesis -- an estimation question. This "
        "document estimates the error-rate distribution at each clean-edge "
        "and collapse cell across replicated runs, and describes whether "
        "005's claimed ratios and sharp-collapse-at-every-pool-size picture "
        "hold up once variance is visible for the first time. No pass/fail "
        "threshold is preregistered; see README for why."
    ),
    primary_variable="pool_size",
    fixed_params={
        "injected_latency_ms": 400,
        "retry_policy": "none",
        "breaker_enabled": False,
        "enable_arrival_trace": False,
    },
)

# The six cells that define Experiment 005's two boundary ratios -- not its
# full 15-run Phase A sweep. See README for why the interior bracket points
# aren't replicated here.
CELLS = [
    {"pool_size": 10, "rps": 12},  # clean edge
    {"pool_size": 10, "rps": 14},  # collapse point
    {"pool_size": 20, "rps": 24},  # clean edge
    {"pool_size": 20, "rps": 28},  # collapse point
    {"pool_size": 40, "rps": 48},  # clean edge
    {"pool_size": 40, "rps": 56},  # collapse point
]

# First-pass design choice, not power-calculated -- see README's escalation
# rule for what happens if this turns out to be too few.
REPLICATION_N = 5

# Run order is shuffled, not grouped by cell -- otherwise all 5 replicates
# of one cell execute back-to-back as a contiguous block, and any
# time-of-day, thermal, or host-machine-state drift over the sweep's ~75
# minutes would correlate with a single condition rather than averaging out
# across all six. Seeded for reproducibility of the executed order itself,
# not because the seed value is scientifically meaningful.
SHUFFLE_SEED = 1


class ExperimentR001(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        configs = [
            {
                "rps": cell["rps"],
                "latency_ms": METADATA.fixed_params["injected_latency_ms"],
                "retry_policy": "none",
                "breaker_enabled": False,
                "pool_size": cell["pool_size"],
            }
            for cell in CELLS
            for _ in range(REPLICATION_N)
        ]
        random.Random(SHUFFLE_SEED).shuffle(configs)
        return configs

    def analyze(self, runs: list[dict]) -> dict:
        # Not a saturation sweep -- every cell here is already a known
        # boundary point from 005, replicated to estimate its distribution.
        # The base class's first-saturation-point machinery assumes an RPS
        # sweep to search within, which doesn't apply to two fixed points
        # per pool size, so this overrides rather than calls super() --
        # but still annotates each run (for the shared CLI's table printer,
        # and because "did the shared saturation flag agree" is itself a
        # useful cross-check, not because collapse points are searched here.
        from faultlab.analysis import annotate_saturation

        annotate_saturation(runs)

        groups = defaultdict(list)
        for r in runs:
            groups[(r.get("pool_size"), r.get("rps"))].append(r)

        cell_statistics = {}
        for (pool_size, rps), group_runs in sorted(groups.items()):
            error_rates = [r["error_rate"] for r in group_runs if r.get("error_rate") is not None]
            amp_factors = [
                r["amplification_factor"] for r in group_runs if r.get("amplification_factor") is not None
            ]
            cell_statistics[f"pool{pool_size}_rps{rps}"] = {
                "n": len(group_runs),
                "error_rate_mean": statistics.mean(error_rates) if error_rates else None,
                "error_rate_stdev": statistics.stdev(error_rates) if len(error_rates) > 1 else None,
                "error_rate_min": min(error_rates) if error_rates else None,
                "error_rate_max": max(error_rates) if error_rates else None,
                "amplification_factor_mean": statistics.mean(amp_factors) if amp_factors else None,
            }

        return {"cell_statistics": cell_statistics}


experiment = ExperimentR001()
