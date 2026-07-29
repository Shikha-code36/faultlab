"""Experiment 004: Retry scheduling (backoff + jitter)."""

from __future__ import annotations

from faultlab.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="004",
    slug="jitter",
    title="Retry scheduling (backoff + jitter)",
    status="closed",
    question=(
        "Experiment 002 showed immediate retries add ~2x load on an "
        "already-saturated dependency without adding completed throughput. "
        "Is the problem retrying itself, or specifically how retries are "
        "scheduled? Can exponential backoff with full jitter desynchronize "
        "retry waves and reduce that overload, compared to immediate retries?"
    ),
    hypothesis=(
        "Full jitter desynchronizes retry arrivals (measurable via the "
        "arrival trace) compared to immediate retries, but that "
        "desynchronization alone will not shift the collapse boundary or "
        "improve error rate/completed throughput, since the connection pool "
        "remains a fixed-capacity bottleneck regardless of arrival smoothness."
    ),
    primary_variable="retry_policy",
    fixed_params={"injected_latency_ms": 400, "breaker_enabled": False, "enable_arrival_trace": True},
)

# The exact RPS boundary Experiments 002/003 identified. Retry budget was
# raised from 2 to 3 total attempts in Service A's code for this experiment
# (see README) -- not a per-run parameter, so it isn't part of the matrix.
EXP004_LATENCY_MS = 400
EXP004_RPS = [12, 14, 16, 18]
EXP004_POLICIES = ["none", "immediate", "full_jitter"]


class ExperimentJitter(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        return [
            {
                "rps": rps,
                "latency_ms": EXP004_LATENCY_MS,
                "retry_policy": policy,
                "breaker_enabled": False,
                "enable_arrival_trace": True,
            }
            for policy in EXP004_POLICIES
            for rps in EXP004_RPS
        ]


experiment = ExperimentJitter()
