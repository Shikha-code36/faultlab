"""Loads every run under experiments/runs/ and reports where the system
starts to saturate.

Injecting latency always makes requests slower -- that's just propagation,
not a problem on its own. What actually matters is saturation: the
connection pool running out of capacity. A run is flagged as saturated if
any of the following hold:
  - error rate (timeouts + errors) above 0%,
  - any pool-acquisition timeouts occurred, or
  - the pool ran at its configured max size (no spare capacity left).

Usage:
  python scripts/analyze_results.py
  python scripts/analyze_results.py --csv experiments/runs/summary.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "experiments" / "runs"

ERROR_RATE_THRESHOLD = 0.0


def load_runs() -> list[dict]:
    runs = []
    for run_dir in sorted(RUNS_DIR.iterdir()):
        metadata_path = run_dir / "metadata.json"
        results_path = run_dir / "results.json"
        if not metadata_path.exists() or not results_path.exists():
            continue

        metadata = json.loads(metadata_path.read_text())
        results = json.loads(results_path.read_text())
        load = results.get("load_generator", {})
        app = results.get("application", {})

        runs.append(
            {
                "run_id": metadata["run_id"],
                "rps": metadata["rps"],
                "injected_latency_ms": metadata["injected_latency_ms"],
                "pool_size": metadata.get("pool_size"),
                "throughput_rps": load.get("throughput_rps"),
                "error_rate": load.get("error_rate"),
                "p95_latency_ms": (load.get("latency_ms") or {}).get("p95"),
                "p99_latency_ms": (load.get("latency_ms") or {}).get("p99"),
                "app_pool_active_max": app.get("pool_active_max"),
                "app_in_flight_max": app.get("in_flight_max"),
                "app_pool_wait_p95_ms_max": app.get("pool_wait_p95_ms_max"),
                "app_pool_timeout_count": app.get("pool_timeout_count_in_window"),
                "app_query_timeout_count": app.get("query_timeout_count_in_window"),
                "app_error_count": app.get("error_count_in_window"),
            }
        )
    return runs


def annotate_saturation(runs: list[dict]) -> None:
    for r in runs:
        saturated = False
        reasons = []

        if r["error_rate"] is not None and r["error_rate"] > ERROR_RATE_THRESHOLD:
            saturated = True
            reasons.append(f"error_rate={r['error_rate']:.2%}")

        if r["app_pool_timeout_count"]:
            saturated = True
            reasons.append(f"pool_timeouts={r['app_pool_timeout_count']}")

        if (
            r["app_pool_active_max"] is not None
            and r["pool_size"] is not None
            and r["app_pool_active_max"] >= r["pool_size"]
        ):
            saturated = True
            reasons.append(f"pool_active={r['app_pool_active_max']} (max={r['pool_size']})")

        r["saturated"] = saturated
        r["saturation_reasons"] = "; ".join(reasons)


def print_table(runs: list[dict]) -> None:
    header = (
        f"{'RPS':>5} {'lat(ms)':>8} {'p95(ms)':>9} {'p99(ms)':>9} "
        f"{'err%':>7} {'pool_active':>11} {'in_flight':>9} {'saturated':>9}"
    )
    print(header)
    print("-" * len(header))
    for r in sorted(runs, key=lambda x: (x["rps"], x["injected_latency_ms"])):
        p95 = f"{r['p95_latency_ms']:.0f}" if r["p95_latency_ms"] is not None else "-"
        p99 = f"{r['p99_latency_ms']:.0f}" if r["p99_latency_ms"] is not None else "-"
        err = f"{r['error_rate']*100:.2f}" if r["error_rate"] is not None else "-"
        pool = r["app_pool_active_max"] if r["app_pool_active_max"] is not None else "-"
        inflight = r["app_in_flight_max"] if r["app_in_flight_max"] is not None else "-"
        flag = "YES" if r["saturated"] else ""
        print(
            f"{r['rps']:>5} {r['injected_latency_ms']:>8} {p95:>9} {p99:>9} "
            f"{err:>7} {pool!s:>11} {inflight!s:>9} {flag:>9}"
        )

    print()
    first_saturated_per_rps: dict[int, dict] = {}
    for r in sorted(runs, key=lambda x: (x["rps"], x["injected_latency_ms"])):
        if r["saturated"] and r["rps"] not in first_saturated_per_rps:
            first_saturated_per_rps[r["rps"]] = r

    if first_saturated_per_rps:
        print("First saturation point per RPS:")
        for rps, r in sorted(first_saturated_per_rps.items()):
            print(f"  rps={rps}: latency={r['injected_latency_ms']}ms ({r['saturation_reasons']})")
    else:
        print("No runs crossed the saturation thresholds.")


def write_csv(runs: list[dict], path: Path) -> None:
    fieldnames = [
        "run_id",
        "rps",
        "injected_latency_ms",
        "throughput_rps",
        "error_rate",
        "p95_latency_ms",
        "p99_latency_ms",
        "app_pool_active_max",
        "app_in_flight_max",
        "app_pool_wait_p95_ms_max",
        "app_pool_timeout_count",
        "app_query_timeout_count",
        "app_error_count",
        "saturated",
        "saturation_reasons",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in runs:
            writer.writerow({k: r.get(k) for k in fieldnames})
    print(f"wrote {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=None, help="also write a CSV summary to this path")
    args = parser.parse_args()

    runs = load_runs()
    if not runs:
        print(f"No completed runs found under {RUNS_DIR}")
        return

    annotate_saturation(runs)
    print_table(runs)

    if args.csv:
        write_csv(runs, args.csv)


if __name__ == "__main__":
    main()
