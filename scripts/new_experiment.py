"""Scaffolds a new Slimybug experiment folder from the Experiment model.

Creates experiments/<id>-<slug>/ with an experiment.py stub (metadata
filled in, matrix() left for you to define) and a hand-written README.md
skeleton. The scaffold is a rendering of the Experiment model, not a
source of truth in its own right -- edit experiment.py directly for
anything the flags below don't cover.

Usage:
  python scripts/new_experiment.py 005 retry-jitter-with-breaker \\
      --title "Retry jitter combined with a circuit breaker" \\
      --question "..." \\
      --hypothesis "..." \\
      --variable retry_policy
"""

from __future__ import annotations

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = REPO_ROOT / "experiments"

EXPERIMENT_PY_TEMPLATE = '''"""Experiment {id}: {title}."""

from __future__ import annotations

from slimybug.experiment import Experiment, ExperimentMetadata

METADATA = ExperimentMetadata(
    id="{id}",
    slug="{slug}",
    title="{title}",
    status="open",
    question="{question}",
    hypothesis="{hypothesis}",
    primary_variable="{variable}",
    fixed_params={{}},
)


class {class_name}(Experiment):
    metadata = METADATA

    def matrix(self) -> list[dict]:
        # TODO: declare the run configs for this experiment's sweep, e.g.
        # return [
        #     {{"rps": rps, "latency_ms": 400, "retry_policy": policy}}
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


experiment = {class_name}()
'''

README_TEMPLATE = """# Experiment {id} -- {title}

**Status.** open

**Question.** {question}

**Hypothesis.** {hypothesis}

**Primary variable.** {variable}

**Method.** _TODO: describe the fixed parameters and run matrix._

**Finding.** _TODO: fill in once the experiment is closed._
"""


def to_class_name(slug: str) -> str:
    return "Experiment" + "".join(part.capitalize() for part in slug.split("-"))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("id", help="experiment id, e.g. 005")
    parser.add_argument("slug", help="short kebab-case slug, e.g. retry-jitter-with-breaker")
    parser.add_argument("--title", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--hypothesis", required=True)
    parser.add_argument("--variable", required=True, help="the one primary variable this experiment changes")
    args = parser.parse_args()

    exp_dir = EXPERIMENTS_DIR / f"{args.id}-{args.slug}"
    if exp_dir.exists():
        parser.error(f"{exp_dir} already exists")

    (exp_dir / "runs").mkdir(parents=True)
    (exp_dir / "figures").mkdir(parents=True)
    (exp_dir / "runs" / ".gitkeep").touch()
    (exp_dir / "figures" / ".gitkeep").touch()

    class_name = to_class_name(args.slug)
    (exp_dir / "experiment.py").write_text(
        EXPERIMENT_PY_TEMPLATE.format(
            id=args.id,
            slug=args.slug,
            title=args.title,
            question=args.question,
            hypothesis=args.hypothesis,
            variable=args.variable,
            class_name=class_name,
        )
    )
    (exp_dir / "README.md").write_text(
        README_TEMPLATE.format(
            id=args.id,
            title=args.title,
            question=args.question,
            hypothesis=args.hypothesis,
            variable=args.variable,
        )
    )

    print(f"scaffolded {exp_dir}")
    print(f"next: fill in {exp_dir / 'experiment.py'}'s matrix(), then:")
    print(f"  python scripts/run_experiment.py {args.id}")
    print(f"  python scripts/analyze_results.py {args.id} --csv")


if __name__ == "__main__":
    main()
