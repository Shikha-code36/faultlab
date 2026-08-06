"""Experiment 011: EWMA half-life sensitivity sweep."""

from __future__ import annotations

from slimybug.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="011",
    slug="half-life-sensitivity",
    title="EWMA half-life sensitivity sweep",
    status="closed",
    question=(
        "Experiment 007 found a 2.0s-half-life EWMA admission signal "
        "performs far closer to no admission control at all than to an "
        "instantaneous signal at the same location -- but 2.0s was a "
        "stated design choice, not swept. As half-life shrinks toward the "
        "interarrival timescale, does EWMA performance degrade "
        "continuously toward instantaneous, or is there a sharp cliff at "
        "some point?"
    ),
    hypothesis=(
        "If error rate moves smoothly across the half-life sweep, "
        "information freshness has a graded effect and no single "
        "threshold half-life is privileged. If instead there is a sharp "
        "knee -- performance close to `off` above some half-life and "
        "close to `instantaneous` below it -- only sufficiently stale "
        "signals matter, and near-instantaneous EWMA already behaves like "
        "true instantaneous."
    ),
    primary_variable="admission_ewma_half_life_s",
    fixed_params={
        "injected_latency_ms": 400,
        "retry_policy": "none",
        "breaker_enabled": False,
        "pool_size": 10,
    },
)

# Single saturated RPS point, not a sweep -- one-variable-per-experiment
# discipline (see 007/009). RPS 16 is 007's midpoint, with the largest
# known gap between `instantaneous` (23.11% error) and `ewma` at
# half_life=2.0s (85.42% error), giving the most room to see a gradient or
# a cliff. RPS 12 is kept only as the standard below-boundary validity
# check every admission experiment (006-009) has run.
HALF_LIFE_LATENCY_MS = METADATA.fixed_params["injected_latency_ms"]
HALF_LIFE_RPS = [12, 16]

# Log-spaced, not linear: this experiment is explicitly asking whether a
# cliff exists, and a cliff is far more visible on a log axis than a
# linear one. Bounds are derived, not picked:
# - Lower anchor (0.06s) sits below RPS 16's ~62.5ms interarrival time --
#   a half-life below one interarrival interval decays within roughly one
#   request, functionally indistinguishable from `instantaneous`.
# - Upper anchor (2.0s) is 007's own value, re-run in-session as the
#   tie-back point to that result rather than reused from its historical
#   data (007 itself applied this same discipline against reusing 006).
# - One point beyond 007's value (4.0s) checks whether degradation keeps
#   worsening past 2.0s or has already plateaued toward `off`.
HALF_LIVES_S = [0.06, 0.25, 0.5, 1.0, 2.0, 4.0]


class ExperimentHalfLifeSensitivity(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        configs = []
        for rps in HALF_LIFE_RPS:
            base = {
                "rps": rps,
                "latency_ms": HALF_LIFE_LATENCY_MS,
                "retry_policy": "none",
                "breaker_enabled": False,
                "pool_size": 10,
            }
            # Same-session controls, not reused from 006/007's historical
            # data -- consistent discipline every admission experiment so
            # far has applied.
            configs.append({**base, "admission_control_enabled": False, "admission_control_mode": "instantaneous"})
            configs.append({**base, "admission_control_enabled": True, "admission_control_mode": "instantaneous"})
            for half_life in HALF_LIVES_S:
                configs.append(
                    {
                        **base,
                        "admission_control_enabled": True,
                        "admission_control_mode": "ewma",
                        "admission_ewma_half_life_s": half_life,
                    }
                )
        return configs

    def analyze(self, runs: list[dict]) -> dict:
        # admission_control_mode alone can't distinguish "off" from
        # "instantaneous" (config, not effect), and can't distinguish
        # between different ewma half-lives -- derive a condition label
        # that carries the half-life for ewma runs.
        for r in runs:
            if not r.get("admission_control_enabled"):
                r["admission_condition"] = "off"
            elif r.get("admission_control_mode") == "ewma":
                r["admission_condition"] = f"ewma_hl{r.get('admission_ewma_half_life_s')}"
            else:
                r["admission_condition"] = "instantaneous"

        from slimybug.analysis import annotate_saturation, first_saturation_points

        annotate_saturation(runs)
        collapse_points = first_saturation_points(runs, group_key="admission_condition")

        # Validity check, mirroring every prior admission experiment: at
        # RPS 12, admission_rejection_rate should be ~0% for instantaneous
        # and for every half-life.
        rps12_by_condition = {
            r["admission_condition"]: r.get("admission_rejection_rate")
            for r in runs
            if r.get("rps") == 12 and r.get("admission_condition") != "off"
        }

        # The actual sweep result: error rate and EWMA convergence
        # (Gate 1 fidelity, per 007) by half-life at the primary RPS 16
        # point, sorted so continuity vs. a cliff is directly readable.
        sweep_rps16 = sorted(
            (
                {
                    "half_life_s": r.get("admission_ewma_half_life_s"),
                    "error_rate": r.get("error_rate"),
                    "admission_rejection_rate": r.get("admission_rejection_rate"),
                    "b_admission_ewma_utilization_max": r.get("b_admission_ewma_utilization_max"),
                    "b_pool_timeout_count": r.get("b_pool_timeout_count"),
                }
                for r in runs
                if r.get("rps") == 16 and r.get("admission_condition", "").startswith("ewma_hl")
            ),
            key=lambda row: row["half_life_s"],
        )

        return {
            "collapse_points": collapse_points,
            "false_positive_check_rps12": rps12_by_condition,
            "half_life_sweep_rps16": sweep_rps16,
        }


experiment = ExperimentHalfLifeSensitivity()
