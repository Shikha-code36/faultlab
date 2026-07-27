"""Orchestrates one FaultLab experiment run end to end.

For a single (rps, injected latency) combination this script:
  1. configures Toxiproxy to inject the requested latency between
     Service A and PostgreSQL,
  2. starts a background poller that samples Service A's internal
     metrics endpoint once a second for the whole run,
  3. runs the k6 load generator against Service A for
     warmup + measure + cooldown seconds,
  4. writes run metadata, load generator results, application metrics,
     proxy state, and raw per-second/per-request samples to
     experiments/runs/<run_id>/.

Usage:
  python scripts/run_experiment.py --rps 20 --latency-ms 100
  python scripts/run_experiment.py --sweep
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "experiments" / "runs"

SERVICE_A_URL = "http://localhost:8000"
TOXIPROXY_URL = "http://localhost:8474"
PROXY_NAME = "postgres"
TOXIC_NAME = "latency_downstream"

DEFAULT_WARMUP_S = 30
DEFAULT_MEASURE_S = 90
DEFAULT_COOLDOWN_S = 15

SWEEP_RPS = [5, 10, 20, 40, 60]
SWEEP_LATENCY_MS = [0, 50, 100, 200, 400, 800]


def http_get_json(url: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def http_json(method: str, url: str, payload: dict | None = None, timeout: float = 5.0):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def set_toxic_latency(latency_ms: int) -> dict:
    """Replace any existing latency toxic with one matching latency_ms.

    latency_ms == 0 means "no toxic configured" (clean baseline).
    """
    http_json("DELETE", f"{TOXIPROXY_URL}/proxies/{PROXY_NAME}/toxics/{TOXIC_NAME}")

    if latency_ms > 0:
        http_json(
            "POST",
            f"{TOXIPROXY_URL}/proxies/{PROXY_NAME}/toxics",
            {
                "name": TOXIC_NAME,
                "type": "latency",
                "stream": "downstream",
                "attributes": {"latency": latency_ms, "jitter": 0},
            },
        )

    return {"active": latency_ms > 0, "configured_latency_ms": latency_ms}


class SnapshotPoller:
    def __init__(self, interval_s: float = 1.0):
        self.interval_s = interval_s
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _run(self):
        while not self._stop.is_set():
            start = time.monotonic()
            try:
                snap = http_get_json(f"{SERVICE_A_URL}/internal/snapshot", timeout=2.0)
                snap["poll_monotonic"] = time.monotonic()
                self.samples.append(snap)
            except Exception as exc:  # keep polling even if one request fails
                self.samples.append({"error": str(exc), "poll_monotonic": time.monotonic()})
            elapsed = time.monotonic() - start
            self._stop.wait(max(0.0, self.interval_s - elapsed))

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5.0)


def run_k6(run_dir: Path, target_url: str, rps: int, warmup_s: int, measure_s: int, cooldown_s: int):
    results_dir = run_dir / "loadgen"
    results_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "docker",
        "compose",
        "run",
        "--rm",
        "-v",
        f"{results_dir}:/results",
        "loadgen",
        "run",
        "-e",
        f"TARGET_URL={target_url}",
        "-e",
        f"RPS={rps}",
        "-e",
        f"WARMUP_S={warmup_s}",
        "-e",
        f"MEASURE_S={measure_s}",
        "-e",
        f"COOLDOWN_S={cooldown_s}",
        "--out",
        "json=/results/raw.jsonl",
        "/scripts/load.js",
    ]

    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    (results_dir / "k6_stdout.log").write_text(proc.stdout)
    (results_dir / "k6_stderr.log").write_text(proc.stderr)
    if proc.returncode != 0:
        print(f"k6 exited with code {proc.returncode}; see {results_dir}/k6_stderr.log", file=sys.stderr)
    return results_dir


def summarize_app_metrics(
    samples: list[dict],
    warmup_s: int,
    cooldown_s: int,
    measure_window: dict | None = None,
) -> dict:
    valid = [s for s in samples if "error" not in s]
    if not valid:
        return {"sample_count": 0}

    if measure_window is not None:
        # Preferred: k6 reports the measurement window as absolute epoch-ms,
        # timestamped from its own scenario clock. Aligning app samples to
        # that -- rather than to when our polling thread happened to start --
        # avoids skew from docker/container startup latency between the two.
        measure_start = measure_window["start_epoch_ms"] / 1000
        measure_end = measure_window["end_epoch_ms"] / 1000
        measure_samples = [s for s in valid if measure_start <= s["timestamp"] <= measure_end]
    else:
        t0 = valid[0]["poll_monotonic"]
        t_last = valid[-1]["poll_monotonic"]
        measure_start = t0 + warmup_s
        measure_end = t_last - cooldown_s
        measure_samples = [s for s in valid if measure_start <= s["poll_monotonic"] <= measure_end]

    window = measure_samples or valid

    in_flight_values = [s["in_flight"] for s in window]
    pool_active_values = [s["pool_active"] for s in window]
    p95_latencies = [s["recent_latency_ms"]["p95"] for s in window if s["recent_latency_ms"]["p95"] is not None]
    pool_wait_p95 = [s["recent_pool_wait_ms"]["p95"] for s in window if s["recent_pool_wait_ms"]["p95"] is not None]

    first = window[0]["cumulative"]
    last = window[-1]["cumulative"]

    return {
        "sample_count": len(window),
        "in_flight_max": max(in_flight_values) if in_flight_values else None,
        "in_flight_avg": sum(in_flight_values) / len(in_flight_values) if in_flight_values else None,
        "pool_active_max": max(pool_active_values) if pool_active_values else None,
        "request_latency_p95_ms_max": max(p95_latencies) if p95_latencies else None,
        "pool_wait_p95_ms_max": max(pool_wait_p95) if pool_wait_p95 else None,
        "pool_timeout_count_in_window": last["pool_timeout_count"] - first["pool_timeout_count"],
        "query_timeout_count_in_window": last["query_timeout_count"] - first["query_timeout_count"],
        "error_count_in_window": last["error_count"] - first["error_count"],
        "success_count_in_window": last["success_count"] - first["success_count"],
    }


def run_experiment(
    rps: int,
    latency_ms: int,
    warmup_s: int = DEFAULT_WARMUP_S,
    measure_s: int = DEFAULT_MEASURE_S,
    cooldown_s: int = DEFAULT_COOLDOWN_S,
    run_id: str | None = None,
) -> Path:
    timestamp = datetime.now(timezone.utc)
    run_id = run_id or f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_rps{rps}_lat{latency_ms}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{run_id}] configuring toxiproxy latency={latency_ms}ms")
    proxy_state = set_toxic_latency(latency_ms)

    poller = SnapshotPoller(interval_s=1.0)
    try:
        pool_config = http_get_json(f"{SERVICE_A_URL}/internal/config")

        poller.start()

        print(
            f"[{run_id}] running load: rps={rps} warmup={warmup_s}s measure={measure_s}s cooldown={cooldown_s}s"
        )
        run_k6(
            run_dir,
            target_url="http://service-a:8000",
            rps=rps,
            warmup_s=warmup_s,
            measure_s=measure_s,
            cooldown_s=cooldown_s,
        )
    finally:
        poller.stop()
        # Always leave the proxy clean so a crashed/interrupted run never
        # leaves stale latency injected for whatever runs next.
        set_toxic_latency(0)

    raw_samples_path = run_dir / "raw_app_samples.jsonl"
    with raw_samples_path.open("w") as f:
        for sample in poller.samples:
            f.write(json.dumps(sample) + "\n")

    summary_path = run_dir / "loadgen" / "summary.json"
    load_results = json.loads(summary_path.read_text()) if summary_path.exists() else {}

    app_metrics = summarize_app_metrics(
        poller.samples, warmup_s, cooldown_s, measure_window=load_results.get("measure_window")
    )

    metadata = {
        "run_id": run_id,
        "timestamp": timestamp.isoformat(),
        "rps": rps,
        "injected_latency_ms": latency_ms,
        "pool_size": pool_config.get("pool_max_size"),
        "query_timeout_s": pool_config.get("query_timeout"),
        "warmup_s": warmup_s,
        "measure_s": measure_s,
        "cooldown_s": cooldown_s,
        "duration_s": warmup_s + measure_s + cooldown_s,
    }

    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    (run_dir / "results.json").write_text(
        json.dumps({"load_generator": load_results, "application": app_metrics}, indent=2)
    )
    (run_dir / "proxy_state.json").write_text(json.dumps(proxy_state, indent=2))

    print(f"[{run_id}] done -> {run_dir}")
    return run_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rps", type=int, help="requests per second")
    parser.add_argument("--latency-ms", type=int, help="injected DB latency in ms")
    parser.add_argument("--warmup-s", type=int, default=DEFAULT_WARMUP_S)
    parser.add_argument("--measure-s", type=int, default=DEFAULT_MEASURE_S)
    parser.add_argument("--cooldown-s", type=int, default=DEFAULT_COOLDOWN_S)
    parser.add_argument("--sweep", action="store_true", help="run the full RPS x latency matrix from the Week 1 plan")
    parser.add_argument(
        "--rps-list",
        type=str,
        default=None,
        help="comma-separated RPS values for a custom sweep, e.g. 10,40 (implies --sweep)",
    )
    parser.add_argument(
        "--latency-ms-list",
        type=str,
        default=None,
        help="comma-separated injected latency values (ms) for a custom sweep, e.g. 0,100,400 (implies --sweep)",
    )
    args = parser.parse_args()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    if args.sweep or args.rps_list or args.latency_ms_list:
        rps_values = [int(v) for v in args.rps_list.split(",")] if args.rps_list else SWEEP_RPS
        latency_values = (
            [int(v) for v in args.latency_ms_list.split(",")] if args.latency_ms_list else SWEEP_LATENCY_MS
        )
        for latency_ms in latency_values:
            for rps in rps_values:
                run_experiment(
                    rps=rps,
                    latency_ms=latency_ms,
                    warmup_s=args.warmup_s,
                    measure_s=args.measure_s,
                    cooldown_s=args.cooldown_s,
                )
        return

    if args.rps is None or args.latency_ms is None:
        parser.error("--rps and --latency-ms are required unless --sweep is given")

    run_experiment(
        rps=args.rps,
        latency_ms=args.latency_ms,
        warmup_s=args.warmup_s,
        measure_s=args.measure_s,
        cooldown_s=args.cooldown_s,
    )


if __name__ == "__main__":
    main()
