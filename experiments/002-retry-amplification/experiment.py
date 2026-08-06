"""Experiment 002: Retry amplification."""

from __future__ import annotations

from slimybug.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="002",
    slug="retry-amplification",
    title="Retry amplification",
    status="closed",
    question=(
        "When a client (Service A) retries a slow dependency (Service B), does "
        "that help it recover, or does it amplify overload? And does retrying "
        "shift the point where the system collapses to a lower offered load?"
    ),
    hypothesis=(
        "Retries add load on an already-saturated dependency roughly "
        "proportional to the retry budget, without adding completed "
        "throughput, and do not measurably shift the collapse boundary."
    ),
    primary_variable="retry_policy",
    fixed_params={"injected_latency_ms": 400, "breaker_enabled": False},
)

# The finer 12/14/16/18 points were added after the initial 5/10/20/40/60
# sweep showed the collapse boundary as a step function between 10 and 20
# RPS -- see README for the full methodology note (including the
# httpx client connection-limit artifact found and fixed mid-sweep).
PHASE_A_LATENCY_MS = 400
PHASE_A_RPS = [5, 10, 12, 14, 16, 18, 20, 40, 60]
PHASE_A_POLICIES = ["none", "immediate", "backoff"]


class ExperimentRetryAmplification(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        return [
            {
                "rps": rps,
                "latency_ms": PHASE_A_LATENCY_MS,
                "retry_policy": policy,
                "breaker_enabled": False,
            }
            for policy in PHASE_A_POLICIES
            for rps in PHASE_A_RPS
        ]


experiment = ExperimentRetryAmplification()
