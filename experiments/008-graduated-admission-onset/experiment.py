"""Experiment 008: Graduated admission onset vs. hard threshold."""

from __future__ import annotations

from brinkline.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="008",
    slug="graduated-admission-onset",
    title="Graduated admission onset vs. hard threshold",
    status="closed",
    question=(
        "Experiments 006 and 007 both used the same hard-threshold "
        "decision rule (reject iff utilization >= 1.0) and varied only "
        "where it runs and how fresh its input is. Every experiment from "
        "001 through 007 has shown a sharp discontinuity at the collapse "
        "boundary regardless. Does the discontinuity come from the rule "
        "being a step function, or is it a more fundamental property of "
        "this architecture?"
    ),
    hypothesis=(
        "If a graduated onset -- rejection probability ramping linearly "
        "from 0 at u_low=0.8 to 1 at u=1.0, a stated design choice within "
        "bounds derived from Little's Law (see README), not an optimized "
        "value -- produces a smaller jump at the collapse boundary than "
        "Experiment 006's hard threshold, decision-rule shape is an "
        "independent causal factor in arbitration. If the curve is "
        "statistically indistinguishable from 006's, the discontinuity is "
        "not attributable to rule shape. Success does not require "
        "graduated admission to outperform the hard threshold -- either "
        "outcome is a finding."
    ),
    primary_variable="admission_control_mode",
    fixed_params={
        "injected_latency_ms": 400,
        "retry_policy": "none",
        "breaker_enabled": False,
        "pool_size": 10,
        "admission_u_low": 0.8,
    },
)

# Same RPS boundary as Experiments 002/003/004/006/007, for direct comparability.
GRADUATED_LATENCY_MS = METADATA.fixed_params["injected_latency_ms"]
GRADUATED_RPS = [12, 14, 16, 18]

# Three conditions: admission control off (a same-session control, not
# reused from 006/007's historical data -- the admission-gate code is
# touched again for this experiment, the same discipline 007 applied
# against reusing 006's numbers), 006's instantaneous hard threshold (also
# re-run in this session), and 008's new graduated rule.
ADMISSION_CONDITIONS = ["off", "instantaneous", "graduated"]


class ExperimentGraduatedAdmissionOnset(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        configs = []
        for condition in ADMISSION_CONDITIONS:
            for rps in GRADUATED_RPS:
                configs.append(
                    {
                        "rps": rps,
                        "latency_ms": GRADUATED_LATENCY_MS,
                        "retry_policy": "none",
                        "breaker_enabled": False,
                        "pool_size": 10,
                        "admission_control_enabled": condition != "off",
                        "admission_control_mode": "instantaneous" if condition == "off" else condition,
                        "admission_u_low": 0.8,
                        # Only needed to validate the graduated rule's Gate
                        # 1 (empirical rejection-probability-vs-utilization
                        # curve vs. the intended ramp) -- harmless no-op
                        # under off/instantaneous, enabled uniformly for
                        # simplicity and so the same-session controls are
                        # captured under identical instrumentation.
                        "enable_admission_decision_trace": True,
                    }
                )
        return configs

    def analyze(self, runs: list[dict]) -> dict:
        # Same reasoning as Experiment 007: admission_control_mode alone
        # can't distinguish "off" from "instantaneous" (the mode field
        # reflects config, not effect), so group by a derived label.
        for r in runs:
            r["admission_condition"] = (
                "off" if not r.get("admission_control_enabled") else r.get("admission_control_mode")
            )

        from brinkline.analysis import annotate_saturation, first_saturation_points

        annotate_saturation(runs)
        collapse_points = first_saturation_points(runs, group_key="admission_condition")

        # Validity check, mirroring every prior admission experiment: at
        # RPS 12, admission_rejection_rate should be ~0% for both
        # instantaneous and graduated. For graduated specifically, this is
        # also the a posteriori check on the u_low=0.8 design choice (see
        # README) -- not the source of that choice.
        rps12_by_condition = {
            r["admission_condition"]: r.get("admission_rejection_rate")
            for r in runs
            if r.get("rps") == 12 and r.get("admission_condition") in ("instantaneous", "graduated")
        }

        return {
            "collapse_points": collapse_points,
            "false_positive_check_rps12": rps12_by_condition,
        }


experiment = ExperimentGraduatedAdmissionOnset()
