"""Thin dispatcher: loads an experiment's matrix() and executes it via Runner.

All the actual work -- what varies, what's held fixed, how many runs --
lives in experiments/<id>-<slug>/experiment.py's matrix(). This script
just resolves that experiment and feeds its matrix to the shared Runner.

Usage:
  python scripts/run_experiment.py 005
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from brinkline.experiment import load_experiment
from brinkline.runner import Runner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment_id", help="experiment id, e.g. 005")
    args = parser.parse_args()

    experiment = load_experiment(args.experiment_id)
    configs = experiment.matrix()

    runner = Runner(experiment.runs_dir, experiment.metadata.id)
    print(f"[{experiment.metadata.id}] running {len(configs)} run(s) from matrix()")
    for config in configs:
        runner.run(**config)


if __name__ == "__main__":
    main()
