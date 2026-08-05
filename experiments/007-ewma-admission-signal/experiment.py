"""Experiment 007: EWMA admission signal vs. instantaneous state."""

from __future__ import annotations

from brinkline.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="007",
    slug="ewma-admission-signal",
    title="EWMA admission signal vs. instantaneous state",
    status="open",
    question=(
        "Experiment 006 showed a server-side admission decision based on "
        "the pool's instantaneous state substantially outperforms "
        "Experiment 003's client-side breaker -- but that comparison "
        "changed both decision location and information freshness at "
        "once. Does server-side placement alone explain 006's result, or "
        "does information freshness matter independently of location?"
    ),
    hypothesis=(
        "If a server-side admission decision based on a trailing EWMA of "
        "pool utilization (half-life 2s, a stated design choice derived "
        "from the ~800ms measured request-service-time and the 30s warmup "
        "duration -- not a value being optimized here) performs "
        "comparably to Experiment 006's instantaneous signal, locality is "
        "the dominant causal factor. If it instead performs closer to "
        "Experiment 003's client-side, inferred-and-delayed breaker, "
        "information freshness is an independent causal factor beyond "
        "mere co-location with the resource."
    ),
    primary_variable="admission_control_mode",
    fixed_params={
        "injected_latency_ms": 400,
        "retry_policy": "none",
        "breaker_enabled": False,
        "pool_size": 10,
        "admission_ewma_half_life_s": 2.0,
    },
)

# Same RPS boundary as Experiments 002/003/004/006, for direct comparability.
EWMA_LATENCY_MS = METADATA.fixed_params["injected_latency_ms"]
EWMA_RPS = [12, 14, 16, 18]

# Three conditions: admission control off (a same-session control, not a
# reuse of Experiment 006's historical data -- the admission-gate code was
# refactored into services/service-b/app/admission.py for this experiment,
# so re-establishing the baseline here follows the same discipline 006
# applied against reusing Experiment 003's numbers), 006's instantaneous
# signal (also re-run in this session, for the same reason), and 007's new
# EWMA signal.
ADMISSION_CONDITIONS = ["off", "instantaneous", "ewma"]


class ExperimentEwmaAdmissionSignal(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        configs = []
        for condition in ADMISSION_CONDITIONS:
            for rps in EWMA_RPS:
                configs.append(
                    {
                        "rps": rps,
                        "latency_ms": EWMA_LATENCY_MS,
                        "retry_policy": "none",
                        "breaker_enabled": False,
                        "pool_size": 10,
                        "admission_control_enabled": condition != "off",
                        "admission_control_mode": "instantaneous" if condition == "off" else condition,
                        "admission_ewma_half_life_s": 2.0,
                    }
                )
        return configs

    def analyze(self, runs: list[dict]) -> dict:
        # admission_control_mode alone can't distinguish "off" from
        # "instantaneous" (the mode field is reported even when admission
        # control is disabled, since it reflects config, not effect) -- so
        # group by a derived label instead of relying on the base class's
        # default grouping by primary_variable directly.
        for r in runs:
            r["admission_condition"] = (
                "off" if not r.get("admission_control_enabled") else r.get("admission_control_mode")
            )

        from brinkline.analysis import annotate_saturation, first_saturation_points

        annotate_saturation(runs)
        collapse_points = first_saturation_points(runs, group_key="admission_condition")

        # Validity check, mirroring Experiment 006's RPS-12 false-positive
        # check: at RPS 12, admission_rejection_rate should be ~0% for
        # both instantaneous and ewma conditions.
        rps12_by_condition = {
            r["admission_condition"]: r.get("admission_rejection_rate")
            for r in runs
            if r.get("rps") == 12 and r.get("admission_condition") in ("instantaneous", "ewma")
        }

        return {
            "collapse_points": collapse_points,
            "false_positive_check_rps12": rps12_by_condition,
        }


experiment = ExperimentEwmaAdmissionSignal()
