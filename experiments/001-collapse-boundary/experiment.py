"""Experiment 001: Database latency propagation."""

from __future__ import annotations

from slimybug.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="001",
    slug="collapse-boundary",
    title="Database latency propagation",
    status="closed",
    question=(
        "How does injected database latency interact with offered load -- "
        "where does a healthy backend stop absorbing a slower dependency and "
        "start failing?"
    ),
    hypothesis=(
        "Injected latency propagates harmlessly at low offered load, but the "
        "connection pool becomes the limiting resource as load rises, so the "
        "latency needed to trigger saturation drops as offered load increases."
    ),
    primary_variable="injected_latency_ms",
    fixed_params={"retry_policy": "none", "breaker_enabled": False},
)

SWEEP_RPS = [5, 10, 20, 40, 60]
SWEEP_LATENCY_MS = [0, 50, 100, 200, 400, 800]


class ExperimentCollapseBoundary(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        return [
            {"rps": rps, "latency_ms": latency_ms, "retry_policy": "none", "breaker_enabled": False}
            for latency_ms in SWEEP_LATENCY_MS
            for rps in SWEEP_RPS
        ]


experiment = ExperimentCollapseBoundary()
