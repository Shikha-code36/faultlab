"""Experiment 003: Circuit breaker."""

from __future__ import annotations

from slimybug.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="003",
    slug="circuit-breaker",
    title="Circuit breaker",
    status="closed",
    question=(
        "Can failing fast (a circuit breaker) reduce the load a saturated "
        "Service B receives -- and does it improve client-visible success -- "
        "compared to Experiment 002's finding that retries just add ~2x "
        "overhead once saturated?"
    ),
    hypothesis=(
        "A circuit breaker that fails fast once Service B's failure rate "
        "crosses a threshold will reduce both the load reaching Service B "
        "and client-visible error rate above the collapse boundary, without "
        "false-positive trips below it."
    ),
    primary_variable="breaker_enabled",
    fixed_params={"injected_latency_ms": 400, "retry_policy": "none"},
)

# The exact RPS boundary Experiment 002 identified.
EXP003_LATENCY_MS = 400
EXP003_RPS = [12, 14, 16, 18]


class ExperimentCircuitBreaker(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        return [
            {
                "rps": rps,
                "latency_ms": EXP003_LATENCY_MS,
                "retry_policy": "none",
                "breaker_enabled": breaker_enabled,
            }
            for breaker_enabled in (False, True)
            for rps in EXP003_RPS
        ]


experiment = ExperimentCircuitBreaker()
