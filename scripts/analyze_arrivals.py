"""Offline analysis of Service B's optional arrival trace (Experiment 004).

The runner writes one arrival_ns per line to <run_dir>/arrival_trace.csv when
a run is started with --trace-arrivals / --exp004. This script buckets those
arrivals into fixed-width windows to show whether they land in synchronized
bursts (immediate retries) or a smoother spread (full_jitter) -- the ~1Hz
snapshot polling used everywhere else in SlimyBug can't show this, since a
100-200ms backoff schedule lives entirely inside one polling bucket.

Usage:
  python scripts/analyze_arrivals.py experiments/runs/<run_id>
  python scripts/analyze_arrivals.py experiments/runs/<run_id> --bucket-ms 25
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def load_arrivals(run_dir: Path) -> list[int]:
    trace_path = run_dir / "arrival_trace.csv"
    if not trace_path.exists():
        raise FileNotFoundError(
            f"{trace_path} not found -- was this run started with --trace-arrivals/--exp004?"
        )
    with trace_path.open(newline="") as f:
        reader = csv.DictReader(f)
        return [int(row["arrival_ns"]) for row in reader]


def bucket_counts(arrivals_ns: list[int], bucket_ms: float) -> list[int]:
    """Bucket arrivals into fixed-width windows, returning counts per bucket.

    Buckets are relative to the first arrival in the trace, not wall-clock
    epoch, since only relative spacing (burst vs. spread) matters here.
    """
    if not arrivals_ns:
        return []

    bucket_ns = int(bucket_ms * 1_000_000)
    t0 = min(arrivals_ns)
    max_bucket = (max(arrivals_ns) - t0) // bucket_ns
    counts = [0] * (max_bucket + 1)
    for ts in arrivals_ns:
        counts[(ts - t0) // bucket_ns] += 1
    return counts


def summarize(counts: list[int]) -> dict:
    if not counts:
        return {"bucket_count": 0}
    n = len(counts)
    mean = sum(counts) / n
    variance = sum((c - mean) ** 2 for c in counts) / n
    return {
        "bucket_count": n,
        "max_per_bucket": max(counts),
        "mean_per_bucket": round(mean, 3),
        "stdev_per_bucket": round(variance**0.5, 3),
        # Coefficient of variation: higher = burstier arrivals relative to
        # their own mean rate, comparable across policies/RPS.
        "cv_per_bucket": round((variance**0.5) / mean, 3) if mean else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="path to experiments/runs/<run_id>")
    parser.add_argument("--bucket-ms", type=float, default=25.0, help="bucket width in ms")
    args = parser.parse_args()

    arrivals_ns = load_arrivals(args.run_dir)
    counts = bucket_counts(arrivals_ns, args.bucket_ms)
    stats = summarize(counts)

    print(f"run: {args.run_dir}")
    print(f"arrivals: {len(arrivals_ns)}")
    print(f"bucket width: {args.bucket_ms}ms")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
