"""Thin dispatcher: aggregates one experiment's runs and reports its analysis.

Loads experiments/<id>-<slug>/experiment.py, aggregates every run under its
runs/ directory into a summary table, and calls its analyze() (which
defaults to the shared saturation/collapse check every experiment has used
so far -- see slimybug.analysis).

Usage:
  python scripts/analyze_results.py 005
  python scripts/analyze_results.py 005 --csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from slimybug.aggregate import load_runs, write_csv
from slimybug.experiment import load_experiment


def print_table(runs: list[dict]) -> None:
    header = (
        f"{'RPS':>5} {'retry':>9} {'lat(ms)':>8} {'p95(ms)':>9} {'p99(ms)':>9} "
        f"{'err%':>7} {'amp':>6} {'retry%':>7} {'pool_active':>11} {'saturated':>9}"
    )
    print(header)
    print("-" * len(header))
    for r in sorted(runs, key=lambda x: (x["retry_policy"], x["injected_latency_ms"], x["rps"])):
        p95 = f"{r['p95_latency_ms']:.0f}" if r["p95_latency_ms"] is not None else "-"
        p99 = f"{r['p99_latency_ms']:.0f}" if r["p99_latency_ms"] is not None else "-"
        err = f"{r['error_rate']*100:.2f}" if r["error_rate"] is not None else "-"
        amp = f"{r['amplification_factor']:.2f}" if r["amplification_factor"] is not None else "-"
        retry_pct = f"{r['retry_rate']*100:.1f}" if r["retry_rate"] is not None else "-"
        pool = r["b_pool_active_max"] if r["b_pool_active_max"] is not None else "-"
        flag = "YES" if r["saturated"] else ""
        print(
            f"{r['rps']:>5} {r['retry_policy']:>9} {r['injected_latency_ms']:>8} {p95:>9} {p99:>9} "
            f"{err:>7} {amp:>6} {retry_pct:>7} {pool!s:>11} {flag:>9}"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment_id", help="experiment id, e.g. 005")
    parser.add_argument("--csv", action="store_true", help="write summary.csv into the experiment folder")
    args = parser.parse_args()

    experiment = load_experiment(args.experiment_id)
    runs = load_runs(experiment.runs_dir)
    if not runs:
        print(f"No completed runs found under {experiment.runs_dir}")
        return

    analysis = experiment.analyze(runs)
    print_table(runs)

    print()
    collapse_points = analysis.get("collapse_points", {})
    if collapse_points:
        print(f"First saturation (collapse) point per {experiment.metadata.primary_variable}:")
        for key, r in sorted(collapse_points.items(), key=lambda kv: str(kv[0])):
            amp = f"amp={r['amplification_factor']:.2f} " if r.get("amplification_factor") is not None else ""
            print(
                f"  {key}: rps={r['rps']} latency={r['injected_latency_ms']}ms "
                f"{amp}({r['saturation_reasons']})"
            )
    else:
        print("No runs crossed the saturation thresholds.")

    if args.csv:
        write_csv(runs, experiment.summary_csv)
        print(f"\nwrote {experiment.summary_csv}")


if __name__ == "__main__":
    main()
