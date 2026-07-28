"""Loads every run under experiments/runs/ and reports retry amplification
and saturation behavior for Experiment 002.

Injecting latency always makes requests slower -- that's just propagation,
not a problem on its own. What actually matters is saturation: Service B's
connection pool running out of capacity. A run is flagged as saturated if
any of the following hold:
  - error rate (timeouts + errors) above 0%,
  - any pool-acquisition timeouts occurred on Service B, or
  - Service B's pool ran at its configured max size (no spare capacity left).

On top of that, this analyzer reports the retry-specific metrics that make
Experiment 002 distinct from Experiment 001:
  - amplification factor: requests Service B received / requests Service A
    was offered. ~1.0 baseline, up to ~2.0 for a single retry policy.
  - retry rate: retries made per request offered to Service A.
  - retry success rate: fraction of successes that needed a retry.
  - the collapse point per retry policy: the lowest RPS (at a given
    injected latency) where that policy saturates, so you can see whether
    retries shift the collapse point earlier than the no-retry baseline.

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
        service_a = app.get("service_a", {})
        service_b = app.get("service_b", {})

        runs.append(
            {
                "run_id": metadata["run_id"],
                "rps": metadata["rps"],
                "injected_latency_ms": metadata["injected_latency_ms"],
                "retry_policy": metadata.get("retry_policy", "none"),
                "pool_size": metadata.get("pool_size"),
                "throughput_rps": load.get("throughput_rps"),
                "error_rate": load.get("error_rate"),
                "p95_latency_ms": (load.get("latency_ms") or {}).get("p95"),
                "p99_latency_ms": (load.get("latency_ms") or {}).get("p99"),
                "amplification_factor": app.get("amplification_factor"),
                "retry_rate": app.get("retry_rate"),
                "retry_success_rate": app.get("retry_success_rate"),
                "a_offered_count": service_a.get("offered_count"),
                "a_timeout_count": service_a.get("timeout_count"),
                "a_upstream_error_count": service_a.get("upstream_error_count"),
                "b_received_count": service_b.get("received_count"),
                "b_pool_active_max": service_b.get("pool_active_max"),
                "b_pool_timeout_count": service_b.get("pool_timeout_count"),
                "b_query_timeout_count": service_b.get("query_timeout_count"),
                "b_error_count": service_b.get("error_count"),
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

        if r["b_pool_timeout_count"]:
            saturated = True
            reasons.append(f"pool_timeouts={r['b_pool_timeout_count']}")

        if (
            r["b_pool_active_max"] is not None
            and r["pool_size"] is not None
            and r["b_pool_active_max"] >= r["pool_size"]
        ):
            saturated = True
            reasons.append(f"pool_active={r['b_pool_active_max']} (max={r['pool_size']})")

        r["saturated"] = saturated
        r["saturation_reasons"] = "; ".join(reasons)


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

    print()
    first_saturated_per_policy: dict[str, dict] = {}
    for r in sorted(runs, key=lambda x: (x["retry_policy"], x["rps"])):
        key = r["retry_policy"]
        if r["saturated"] and key not in first_saturated_per_policy:
            first_saturated_per_policy[key] = r

    if first_saturated_per_policy:
        print("First saturation (collapse) point per retry policy:")
        for policy, r in sorted(first_saturated_per_policy.items()):
            print(
                f"  {policy}: rps={r['rps']} latency={r['injected_latency_ms']}ms "
                f"amp={r['amplification_factor']:.2f} ({r['saturation_reasons']})"
                if r["amplification_factor"] is not None
                else f"  {policy}: rps={r['rps']} latency={r['injected_latency_ms']}ms ({r['saturation_reasons']})"
            )
    else:
        print("No runs crossed the saturation thresholds.")


def write_csv(runs: list[dict], path: Path) -> None:
    fieldnames = [
        "run_id",
        "rps",
        "injected_latency_ms",
        "retry_policy",
        "throughput_rps",
        "error_rate",
        "p95_latency_ms",
        "p99_latency_ms",
        "amplification_factor",
        "retry_rate",
        "retry_success_rate",
        "a_offered_count",
        "a_timeout_count",
        "a_upstream_error_count",
        "b_received_count",
        "b_pool_active_max",
        "b_pool_timeout_count",
        "b_query_timeout_count",
        "b_error_count",
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
