"""Experiment 005: Connection pool capacity as the collapse lever."""

from __future__ import annotations

from faultlab.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="005",
    slug="connection-pool-capacity",
    title="Connection pool capacity as the collapse lever",
    status="open",
    question=(
        "Experiments 001-004 all converged on Service B's fixed 10-connection pool as "
        "the binding constraint once the system saturates, but none of them varied it. "
        "Does increasing POOL_MAX_SIZE shift the collapse boundary to a higher offered "
        "load, or does the bottleneck relocate elsewhere (query time, Postgres itself, "
        "network) once the pool stops being the limit?"
    ),
    hypothesis=(
        "Two regimes are predicted. Pool-limited regime: while the connection pool is "
        "the binding constraint, increasing POOL_MAX_SIZE raises the collapse boundary "
        "roughly in proportion to the pool size increase. Bottleneck-relocated regime: "
        "past some pool size, a different subsystem (Postgres query capacity, CPU, "
        "network) becomes binding instead, and further pool increases yield diminishing "
        "or no improvement in the collapse boundary."
    ),
    primary_variable="pool_size",
    fixed_params={
        "injected_latency_ms": 400,
        "retry_policy": "none",
        "breaker_enabled": False,
        "enable_arrival_trace": False,
    },
)

# Phase A: coarse bracket around each pool size's expected boundary. Baseline
# (pool=10) collapses at RPS 12-14 at 400ms latency (Experiments 002-004) --
# roughly 1.3 RPS of capacity per pool connection. Each RPS list below is
# centered on that ratio scaled to its pool size, so every pool size actually
# has a chance to show a boundary within its own sweep, rather than reusing
# one fixed RPS range that would be uninformative at the extremes (pool=40
# never saturating, or pool=10 just replicating old data).
PHASE_A_LATENCY_MS = METADATA.fixed_params["injected_latency_ms"]
PHASE_A_POOL_SIZES = [10, 20, 40]
PHASE_A_RPS = {
    10: [10, 12, 14, 16, 18],
    20: [20, 24, 28, 32, 36],
    40: [40, 48, 56, 64, 72],
}


class ExperimentConnectionPoolCapacity(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        return [
            {
                "rps": rps,
                "latency_ms": PHASE_A_LATENCY_MS,
                "retry_policy": "none",
                "breaker_enabled": False,
                "pool_size": pool_size,
            }
            for pool_size in PHASE_A_POOL_SIZES
            for rps in PHASE_A_RPS[pool_size]
        ]

    def analyze(self, runs: list[dict]) -> dict:
        result = super().analyze(runs)

        # Throughput at collapse: a higher offered load surviving longer
        # doesn't by itself mean more work got done. b_success_count is
        # Service B's actual completed-query count in the measure window --
        # the same quantity 002/004 called "completed throughput" (there
        # recomputed ad hoc; now a stored column via faultlab.aggregate).
        result["throughput_at_collapse"] = {
            pool_size: run.get("b_success_count")
            for pool_size, run in result["collapse_points"].items()
        }
        return result


experiment = ExperimentConnectionPoolCapacity()
