"""Experiment 005: Connection pool capacity as the collapse lever."""

from __future__ import annotations

from faultlab.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="005",
    slug="connection-pool-capacity",
    title="Connection pool capacity as the collapse lever",
    status="open",
    question="Experiments 001-004 all converged on Service B's fixed 10-connection pool as the binding constraint once the system saturates. Does increasing the pool size shift the collapse boundary to a higher offered load, or does the bottleneck just relocate elsewhere (e.g. the database itself)?",
    hypothesis="Raising POOL_MAX_SIZE will push the collapse boundary to a higher RPS, up to the point where some other resource (DB CPU/connections, network) becomes the new binding constraint.",
    primary_variable="pool_size",
    fixed_params={},
)


class ExperimentConnectionPoolCapacity(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        # TODO: declare the run configs for this experiment's sweep, e.g.
        # return [
        #     {"rps": rps, "latency_ms": 400, "retry_policy": policy}
        #     for policy in ["none", "immediate"]
        #     for rps in [12, 14, 16, 18]
        # ]
        raise NotImplementedError("define this experiment's run matrix")

    # Override analyze() here only if this experiment needs a derived
    # metric beyond the shared saturation/collapse check, e.g.:
    #
    # def analyze(self, runs: list[dict]) -> dict:
    #     result = super().analyze(runs)
    #     result["my_metric"] = ...
    #     return result


experiment = ExperimentConnectionPoolCapacity()
