"""Core FaultLab experiment model.

An Experiment describes work -- its identity, its question, and the run
matrix that answers it -- it does not execute that work. Execution is
Runner's job (faultlab.runner), aggregation is faultlab.aggregate's, and
the saturation/collapse check every experiment has relied on lives in
faultlab.analysis. Keeping Experiment free of I/O means its definition
stays reviewable as data: matrix() and analyze() are the only things that
change from one experiment to the next.
"""

from __future__ import annotations

import importlib.util
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = REPO_ROOT / "experiments"


@dataclass(frozen=True)
class ExperimentMetadata:
    """An experiment's identity. No `version` field: git already versions
    the experiment's definition (matrix/analysis code), and a run's own
    commit hash plus run_id are enough to reproduce it exactly."""

    id: str
    slug: str
    title: str
    status: str  # "open" | "closed"
    question: str
    hypothesis: str
    primary_variable: str
    fixed_params: dict = field(default_factory=dict)

    @property
    def dir_name(self) -> str:
        return f"{self.id}-{self.slug}"


class Experiment(ABC):
    """Describes one experiment's work. Never executes it directly."""

    metadata: ExperimentMetadata

    @abstractmethod
    def matrix(self) -> list[dict]:
        """The run configs (rps, latency_ms, retry_policy, ...) that make
        up this experiment's sweep, fed one at a time to Runner.run()."""

    def analyze(self, runs: list[dict]) -> dict:
        """Annotate aggregated run rows with saturation/collapse signals.

        Default implementation delegates to the saturation check shared
        by every experiment so far. Override to layer on experiment-
        specific derived metrics (e.g. Experiment 004's arrival-CV), calling
        super().analyze(runs) first so the shared check still runs.
        """
        from faultlab.analysis import annotate_saturation, first_saturation_points

        annotate_saturation(runs)
        return {
            "collapse_points": first_saturation_points(
                runs, group_key=self.metadata.primary_variable
            )
        }

    @property
    def dir_path(self) -> Path:
        return EXPERIMENTS_DIR / self.metadata.dir_name

    @property
    def runs_dir(self) -> Path:
        return self.dir_path / "runs"

    @property
    def summary_csv(self) -> Path:
        return self.dir_path / "summary.csv"


def load_experiment(experiment_id: str) -> Experiment:
    """Locate experiments/<experiment_id>-*/experiment.py and return the
    `experiment` instance it defines at module level."""
    matches = sorted(EXPERIMENTS_DIR.glob(f"{experiment_id}-*/experiment.py"))
    if not matches:
        raise FileNotFoundError(
            f"no experiments/{experiment_id}-*/experiment.py found under {EXPERIMENTS_DIR}"
        )
    if len(matches) > 1:
        raise RuntimeError(f"multiple experiment folders match id {experiment_id!r}: {matches}")

    module_path = matches[0]
    spec = importlib.util.spec_from_file_location(f"faultlab_experiment_{experiment_id}", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "experiment"):
        raise AttributeError(f"{module_path} must define a module-level `experiment = ...` instance")
    return module.experiment
