"""Experiment 009: Bounded admission deferral vs. immediate rejection."""

from __future__ import annotations

from slimybug.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="009",
    slug="bounded-grace-period",
    title="Bounded admission deferral vs. immediate rejection",
    status="closed",
    question=(
        "Every admission mechanism tested so far (006, 007, 008) commits "
        "its decision the instant the signal is read. Must overload be "
        "rejected immediately, or can a single bounded postponement of "
        "the decision -- re-reading the same signal once more after a "
        "short, fixed interval, with no resource queueing involved -- "
        "recover requests caught in a momentary blip without "
        "reintroducing the collapse a zero-tolerance policy prevents?"
    ),
    hypothesis=(
        "Three distinguishable outcomes: (1) if bounded deferral "
        "(grace_ms=20, a stated design choice derived from interarrival "
        "and service-time bounds -- see README, not optimized here) "
        "reduces error rate vs. Experiment 006's immediate-rejection "
        "baseline without reintroducing pool timeouts, tolerance for "
        "transient state is an independent causal lever; (2) if it "
        "produces no meaningful difference, the instantaneous signal is "
        "already a reliable indicator of genuine sustained saturation at "
        "this timescale; (3) if it reduces error rate but rescued "
        "requests merely absorb the wait as added latency with no net "
        "throughput gain, that is cost redistribution, not cost "
        "reduction, and is reported as its own distinct outcome."
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

# Same RPS boundary as Experiments 002/003/004/006/007/008, for direct comparability.
GRACE_LATENCY_MS = METADATA.fixed_params["injected_latency_ms"]
GRACE_RPS = [12, 14, 16, 18]

# Three conditions: admission control off (a same-session control, not
# reused from 006/007/008's historical data -- the admission-gate code is
# touched again for this experiment, the same discipline every prior
# admission experiment applied), 006's instantaneous hard threshold (also
# re-run in this session), and 009's new bounded-deferral mechanism.
ADMISSION_CONDITIONS = ["off", "instantaneous", "bounded_grace"]


class ExperimentBoundedGracePeriod(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        configs = []
        for condition in ADMISSION_CONDITIONS:
            for rps in GRACE_RPS:
                configs.append(
                    {
                        "rps": rps,
                        "latency_ms": GRACE_LATENCY_MS,
                        "retry_policy": "none",
                        "breaker_enabled": False,
                        "pool_size": 10,
                        "admission_control_enabled": condition != "off",
                        "admission_control_mode": "instantaneous" if condition == "off" else condition,
                        "admission_grace_ms": 20,
                        # Needed to validate Gate 1: that every provisional
                        # reject under bounded_grace actually waited once,
                        # for the intended duration, before a final decision.
                        "enable_admission_decision_trace": True,
                    }
                )
        return configs

    def analyze(self, runs: list[dict]) -> dict:
        # Same reasoning as Experiments 007/008: admission_control_mode
        # alone can't distinguish "off" from "instantaneous" (the mode
        # field reflects config, not effect), so group by a derived label.
        for r in runs:
            r["admission_condition"] = (
                "off" if not r.get("admission_control_enabled") else r.get("admission_control_mode")
            )

        from slimybug.analysis import annotate_saturation, first_saturation_points

        annotate_saturation(runs)
        collapse_points = first_saturation_points(runs, group_key="admission_condition")

        # Validity check, mirroring every prior admission experiment: at
        # RPS 12, admission_rejection_rate should be ~0% for both
        # instantaneous and bounded_grace.
        rps12_by_condition = {
            r["admission_condition"]: r.get("admission_rejection_rate")
            for r in runs
            if r.get("rps") == 12 and r.get("admission_condition") in ("instantaneous", "bounded_grace")
        }

        return {
            "collapse_points": collapse_points,
            "false_positive_check_rps12": rps12_by_condition,
        }


experiment = ExperimentBoundedGracePeriod()
