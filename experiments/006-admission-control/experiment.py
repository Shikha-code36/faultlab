"""Experiment 006: Server-side admission control."""

from __future__ import annotations

from faultlab.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="006",
    slug="admission-control",
    title="Server-side admission control",
    status="closed",
    question=(
        "Does rejecting excess demand at Service B, using the pool's own "
        "real-time state, behave differently from Service A's client-side "
        "breaker (Experiment 003)?"
    ),
    hypothesis=(
        "Server-side admission control -- gated on the pool's own "
        "instantaneous state (no idle connections free), checked before "
        "pool.acquire() is ever called, with acquire()'s own queueing "
        "behavior left unchanged for admitted requests -- reduces "
        "client-visible errors and load reaching the pool at least as "
        "effectively as Experiment 003's client-side breaker. In this "
        "architecture, decision locus (server vs. client) and information "
        "quality (direct/instantaneous vs. inferred/delayed) are bundled "
        "together, not independent variables: Service A can only learn "
        "Service B's pool state through the outcomes of requests it has "
        "already sent, so a server-side decision is inherently also a "
        "direct-information decision here. This experiment tests that "
        "bundled effect, not a decomposition of locus from information "
        "quality."
    ),
    primary_variable="admission_control_enabled",
    fixed_params={
        "injected_latency_ms": 400,
        "retry_policy": "none",
        "breaker_enabled": False,
        "pool_size": 10,
    },
)

# The exact RPS boundary Experiments 002/003/004 identified -- reused so
# this lands on the same axis as Experiment 003's breaker on/off table for
# direct comparison. Includes its own admission-control-off condition
# (rather than reusing Experiment 003's historical numbers) so both arms
# of the comparison are collected in the same session, under the same
# codebase and environment -- see README's "Internal validity" section.
ADMISSION_LATENCY_MS = METADATA.fixed_params["injected_latency_ms"]
ADMISSION_RPS = [12, 14, 16, 18]


class ExperimentAdmissionControl(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        return [
            {
                "rps": rps,
                "latency_ms": ADMISSION_LATENCY_MS,
                "retry_policy": "none",
                "breaker_enabled": False,
                "pool_size": 10,
                "admission_control_enabled": admission_control_enabled,
            }
            for admission_control_enabled in (False, True)
            for rps in ADMISSION_RPS
        ]

    def analyze(self, runs: list[dict]) -> dict:
        result = super().analyze(runs)

        # Validity check, mirroring Experiment 003's "no false positives"
        # check: at RPS 12 (below the collapse boundary), admission control
        # should reject essentially nothing. A non-trivial rejection rate
        # here would mean the gate is triggering on ordinary contention,
        # not genuine saturation -- a sign the signal isn't behaving as
        # justified, not a property of the hypothesis under test.
        rps12_admission_on = [
            r for r in runs
            if r.get("rps") == 12 and r.get("admission_control_enabled") in (True, "True")
        ]
        result["false_positive_check_rps12"] = {
            "admission_rejection_rate": (
                rps12_admission_on[0].get("admission_rejection_rate") if rps12_admission_on else None
            )
        }
        return result


experiment = ExperimentAdmissionControl()
