"""Core SlimyBug experiment model.

An Experiment describes work -- its identity, its question, and the run
matrix that answers it -- it does not execute that work. Execution is
Runner's job (slimybug.runner), aggregation is slimybug.aggregate's, and
the saturation/collapse check every experiment has relied on lives in
slimybug.analysis. Keeping Experiment free of I/O means its definition
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
# Reference-grade validations (e.g. R001) live in a separate top-level
# directory, not experiments/ -- structurally distinguishing "research-grade"
# (one causal question, single-run-per-condition unless noted) from
# "reference-grade" (replicated, variance reported, validates a prior
# experiment's claim rather than asking a new one) rather than relying on a
# field someone has to remember to check.
REFERENCE_DIR = REPO_ROOT / "reference"


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
    # "research" (default, 001-009's standard) or "reference" -- a reference-
    # grade entry validates a specific prior claim under replication rather
    # than asking a new causal question. Defaulted so existing experiments
    # never need touching.
    evidence_grade: str = "research"

    @property
    def dir_name(self) -> str:
        return f"{self.id}-{self.slug}"


class Experiment(ABC):
    """Describes one experiment's work. Never executes it directly."""

    metadata: ExperimentMetadata
    # Set by load_experiment() based on which directory the definition was
    # found in. Defaults to EXPERIMENTS_DIR so every experiment defined
    # directly (rather than via load_experiment) keeps working unchanged.
    base_dir: Path = EXPERIMENTS_DIR

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
        from slimybug.analysis import annotate_saturation, first_saturation_points

        annotate_saturation(runs)
        return {
            "collapse_points": first_saturation_points(
                runs, group_key=self.metadata.primary_variable
            )
        }

    @property
    def dir_path(self) -> Path:
        return self.base_dir / self.metadata.dir_name

    @property
    def runs_dir(self) -> Path:
        return self.dir_path / "runs"

    @property
    def summary_csv(self) -> Path:
        return self.dir_path / "summary.csv"


def load_experiment(experiment_id: str) -> Experiment:
    """Locate <experiment_id>-*/experiment.py under experiments/ or
    reference/ and return the `experiment` instance it defines at module
    level. Searches experiments/ first, then reference/ -- an id should
    only ever exist in one of the two."""
    found_in = None
    matches = sorted(EXPERIMENTS_DIR.glob(f"{experiment_id}-*/experiment.py"))
    if matches:
        found_in = EXPERIMENTS_DIR
    else:
        matches = sorted(REFERENCE_DIR.glob(f"{experiment_id}-*/experiment.py"))
        if matches:
            found_in = REFERENCE_DIR

    if not matches:
        raise FileNotFoundError(
            f"no {experiment_id}-*/experiment.py found under {EXPERIMENTS_DIR} or {REFERENCE_DIR}"
        )
    if len(matches) > 1:
        raise RuntimeError(f"multiple experiment folders match id {experiment_id!r}: {matches}")

    module_path = matches[0]
    spec = importlib.util.spec_from_file_location(f"slimybug_experiment_{experiment_id}", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "experiment"):
        raise AttributeError(f"{module_path} must define a module-level `experiment = ...` instance")
    module.experiment.base_dir = found_in
    return module.experiment
