"""Orchestrates one FaultLab experiment run end to end.

For a single (rps, injected latency, retry policy, breaker on/off)
combination this script:
  1. sets Service A's retry policy and circuit-breaker toggle by
     recreating it with RETRY_POLICY / BREAKER_ENABLED in its environment
     (a no-op if it's already running that configuration),
  2. configures Toxiproxy to inject the requested latency between
     Service B and PostgreSQL,
  3. starts a background poller that samples Service A's snapshot +
     breaker state and Service B's snapshot once a second for the whole
     run,
  4. runs the k6 load generator against Service A for
     warmup + measure + cooldown seconds,
  5. writes run metadata, load generator results, application metrics
     (for both services plus the derived amplification factor and
     breaker stats), proxy state, and raw per-second/per-request samples
     to experiments/runs/<run_id>/.

Usage:
  python scripts/run_experiment.py --rps 20 --latency-ms 400 --retry-policy immediate
  python scripts/run_experiment.py --rps 14 --latency-ms 400 --breaker on
  python scripts/run_experiment.py --phase-a
  python scripts/run_experiment.py --exp003
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
SERVICE_B_URL = "http://localhost:8001"
TOXIPROXY_URL = "http://localhost:8474"
PROXY_NAME = "postgres"
TOXIC_NAME = "latency_downstream"

DEFAULT_WARMUP_S = 30
DEFAULT_MEASURE_S = 90
DEFAULT_COOLDOWN_S = 15

RETRY_POLICIES = ["none", "immediate", "backoff", "full_jitter"]

# Week 1's flat matrix, kept for re-running the no-retry baseline topology.
SWEEP_RPS = [5, 10, 20, 40, 60]
SWEEP_LATENCY_MS = [0, 50, 100, 200, 400, 800]

# Experiment 002's locked phased sweep (see experiment_002 design notes).
# Deliberately its own list, not RETRY_POLICIES -- Experiment 002/003 are
# CLOSED and their locked sweep must stay exactly {none, immediate, backoff}
# even after full_jitter is added to RETRY_POLICIES for Experiment 004.
PHASE_A_POLICIES = ["none", "immediate", "backoff"]
PHASE_A_LATENCY_MS = 400
PHASE_A_RPS = [5, 10, 20, 40, 60]
PHASE_B_LATENCY_MS = 200

# Experiment 003's locked sweep (see experiment_003 design notes): retry
# disabled throughout, breaker off/on x RPS at the boundary Experiment 002
# identified.
EXP003_LATENCY_MS = 400
EXP003_RPS = [12, 14, 16, 18]

# Experiment 004's locked sweep (see experiment_004 design notes / plan.txt):
# retry budget raised to 3 total attempts, breaker disabled throughout,
# arrival tracing enabled to measure retry desynchronization directly.
EXP004_LATENCY_MS = 400
EXP004_RPS = [12, 14, 16, 18]
EXP004_POLICIES = ["none", "immediate", "full_jitter"]


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


def set_experiment_config(
    retry_policy: str, breaker_enabled: bool, enable_arrival_trace: bool = False
) -> None:
    """Recreate Service A / Service B with the given config if needed.

    Written to a .env file (which every `docker compose` invocation reads
    automatically) rather than passed as a one-off subprocess env var --
    run_k6() below also shells out to `docker compose run loadgen`, and
    since loadgen depends_on service-a, compose re-resolves the whole
    project against whatever environment it sees and will silently recreate
    service-a back to the default config if these vars aren't set there too.
    A .env file keeps every subsequent compose call consistent.

    Writes all three vars in one file (rather than one function per service)
    since .env is written wholesale each time -- two separate writers would
    silently clobber each other's variables.

    docker compose only recreates a container when its resolved config
    changed, so passing both services to `up` is a no-op for whichever one
    didn't change.
    """
    current_a = http_get_json(f"{SERVICE_A_URL}/internal/config")
    current_b_trace = http_get_json(f"{SERVICE_B_URL}/internal/arrival_trace")
    if (
        current_a.get("retry_policy") == retry_policy
        and current_a.get("breaker_enabled") == breaker_enabled
        and current_b_trace.get("enabled") == enable_arrival_trace
    ):
        return

    (REPO_ROOT / ".env").write_text(
        f"RETRY_POLICY={retry_policy}\n"
        f"BREAKER_ENABLED={'true' if breaker_enabled else 'false'}\n"
        f"ENABLE_ARRIVAL_TRACE={'true' if enable_arrival_trace else 'false'}\n"
    )
    subprocess.run(
        ["docker", "compose", "up", "-d", "--wait", "service-a", "service-b"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )


class SnapshotPoller:
    def __init__(self, interval_s: float = 1.0):
        self.interval_s = interval_s
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _poll_one(self, url: str) -> dict:
        try:
            return http_get_json(url, timeout=2.0)
        except Exception as exc:
            return {"error": str(exc)}

    def _run(self):
        while not self._stop.is_set():
            start = time.monotonic()
            now = time.monotonic()
            self.samples.append(
                {
                    "poll_monotonic": now,
                    "a": self._poll_one(f"{SERVICE_A_URL}/internal/snapshot"),
                    "b": self._poll_one(f"{SERVICE_B_URL}/internal/snapshot"),
                    "breaker": self._poll_one(f"{SERVICE_A_URL}/internal/breaker"),
                }
            )
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


def _select_window(samples: list[dict], key: str, warmup_s: int, cooldown_s: int, measure_window: dict | None):
    """Pick the sub-list of per-service snapshots (a or b) inside the measure window."""
    valid = [s[key] for s in samples if "error" not in s.get(key, {"error": "missing"})]
    if not valid:
        return []

    if measure_window is not None:
        # Preferred: k6 reports the measurement window as absolute epoch-ms,
        # timestamped from its own scenario clock. Aligning app samples to
        # that -- rather than to when our polling thread happened to start --
        # avoids skew from docker/container startup latency between the two.
        measure_start = measure_window["start_epoch_ms"] / 1000
        measure_end = measure_window["end_epoch_ms"] / 1000
        return [s for s in valid if measure_start <= s["timestamp"] <= measure_end]

    poll_times = [s["poll_monotonic"] for s in samples if "error" not in s.get(key, {"error": "missing"})]
    t0, t_last = poll_times[0], poll_times[-1]
    measure_start = t0 + warmup_s
    measure_end = t_last - cooldown_s
    return [s for s, t in zip(valid, poll_times) if measure_start <= t <= measure_end]


def summarize_service_a(window: list[dict]) -> dict:
    if not window:
        return {"sample_count": 0}

    in_flight_values = [s["in_flight"] for s in window]
    p95_latencies = [s["recent_latency_ms"]["p95"] for s in window if s["recent_latency_ms"]["p95"] is not None]
    open_state_p95_latencies = [
        s["recent_short_circuit_latency_ms"]["p95"]
        for s in window
        if s.get("recent_short_circuit_latency_ms", {}).get("p95") is not None
    ]
    retry_delay_p50s = [
        s["recent_retry_delay_ms"]["p50"]
        for s in window
        if s.get("recent_retry_delay_ms", {}).get("p50") is not None
    ]
    retry_delay_p95s = [
        s["recent_retry_delay_ms"]["p95"]
        for s in window
        if s.get("recent_retry_delay_ms", {}).get("p95") is not None
    ]

    first, last = window[0]["cumulative"], window[-1]["cumulative"]

    return {
        "sample_count": len(window),
        "in_flight_max": max(in_flight_values) if in_flight_values else None,
        "in_flight_avg": sum(in_flight_values) / len(in_flight_values) if in_flight_values else None,
        "request_latency_p95_ms_max": max(p95_latencies) if p95_latencies else None,
        "open_state_latency_p95_ms_max": max(open_state_p95_latencies) if open_state_p95_latencies else None,
        # Experiment 004: rolling-window retry delay percentiles, averaged
        # across the measure window's per-second samples (not maxed, unlike
        # the latency fields above) -- this approximates the delay
        # distribution actually sampled over the run, for verifying the
        # jitter implementation matches its intended random(0, backoff)
        # shape rather than confirming a single moment's worst case.
        "retry_delay_p50_ms_avg": (
            sum(retry_delay_p50s) / len(retry_delay_p50s) if retry_delay_p50s else None
        ),
        "retry_delay_p95_ms_avg": (
            sum(retry_delay_p95s) / len(retry_delay_p95s) if retry_delay_p95s else None
        ),
        "offered_count": last["total_count"] - first["total_count"],
        "success_count": last["success_count"] - first["success_count"],
        "timeout_count": last["timeout_count"] - first["timeout_count"],
        "upstream_error_count": last["upstream_error_count"] - first["upstream_error_count"],
        "error_count": last["error_count"] - first["error_count"],
        "retry_count": last["retry_count"] - first["retry_count"],
        "retry_success_count": last["retry_success_count"] - first["retry_success_count"],
        "short_circuit_count": last.get("short_circuit_count", 0) - first.get("short_circuit_count", 0),
    }


def summarize_breaker(window: list[dict]) -> dict:
    if not window:
        return {"sample_count": 0}

    states_seen = sorted({s["state"] for s in window})
    first, last = window[0], window[-1]

    return {
        "sample_count": len(window),
        "states_seen": states_seen,
        "final_state": last["state"],
        "open_count_in_window": last["open_count"] - first["open_count"],
        "open_seconds_in_window": round(last["open_seconds_total"] - first["open_seconds_total"], 3),
        "short_circuit_count_in_window": last["short_circuit_count"] - first["short_circuit_count"],
        "probe_count_in_window": last["probe_count"] - first["probe_count"],
        "probe_success_count_in_window": last["probe_success_count"] - first["probe_success_count"],
    }


def summarize_service_b(window: list[dict]) -> dict:
    if not window:
        return {"sample_count": 0}

    pool_active_values = [s["pool_active"] for s in window]
    pool_wait_p95 = [s["recent_pool_wait_ms"]["p95"] for s in window if s["recent_pool_wait_ms"]["p95"] is not None]

    first, last = window[0]["cumulative"], window[-1]["cumulative"]

    return {
        "sample_count": len(window),
        "pool_active_max": max(pool_active_values) if pool_active_values else None,
        "pool_wait_p95_ms_max": max(pool_wait_p95) if pool_wait_p95 else None,
        "received_count": last["total_count"] - first["total_count"],
        "success_count": last["success_count"] - first["success_count"],
        "pool_timeout_count": last["pool_timeout_count"] - first["pool_timeout_count"],
        "query_timeout_count": last["query_timeout_count"] - first["query_timeout_count"],
        "error_count": last["error_count"] - first["error_count"],
    }


def summarize_app_metrics(
    samples: list[dict],
    warmup_s: int,
    cooldown_s: int,
    measure_window: dict | None = None,
) -> dict:
    window_a = _select_window(samples, "a", warmup_s, cooldown_s, measure_window)
    window_b = _select_window(samples, "b", warmup_s, cooldown_s, measure_window)
    window_breaker = _select_window(samples, "breaker", warmup_s, cooldown_s, measure_window)

    service_a = summarize_service_a(window_a)
    service_b = summarize_service_b(window_b)
    breaker = summarize_breaker(window_breaker)

    offered = service_a.get("offered_count")
    received = service_b.get("received_count")
    amplification_factor = (received / offered) if offered else None
    retry_rate = (service_a.get("retry_count") / offered) if offered else None
    retry_success_rate = (
        service_a.get("retry_success_count") / service_a.get("success_count")
        if service_a.get("success_count")
        else None
    )
    # Probes are rare, discrete events (a handful per run), and probe_count
    # increments when a probe is granted while probe_success_count only
    # increments once its result arrives up to ~2s later -- so a probe that
    # starts just before the measure window and resolves just after can make
    # the windowed success count exceed the windowed grant count. Clamp the
    # denominator rather than report a >100% rate from that boundary lag.
    probe_count_in_window = breaker.get("probe_count_in_window") or 0
    probe_success_count_in_window = breaker.get("probe_success_count_in_window") or 0
    probe_success_rate = (
        probe_success_count_in_window / max(probe_count_in_window, probe_success_count_in_window)
        if (probe_count_in_window or probe_success_count_in_window)
        else None
    )

    return {
        "service_a": service_a,
        "service_b": service_b,
        "breaker": breaker,
        "amplification_factor": amplification_factor,
        "retry_rate": retry_rate,
        "retry_success_rate": retry_success_rate,
        "probe_success_rate": probe_success_rate,
    }


def run_experiment(
    rps: int,
    latency_ms: int,
    retry_policy: str = "none",
    breaker_enabled: bool = False,
    enable_arrival_trace: bool = False,
    warmup_s: int = DEFAULT_WARMUP_S,
    measure_s: int = DEFAULT_MEASURE_S,
    cooldown_s: int = DEFAULT_COOLDOWN_S,
    run_id: str | None = None,
) -> Path:
    timestamp = datetime.now(timezone.utc)
    breaker_suffix = "_breaker-on" if breaker_enabled else ""
    run_id = (
        run_id
        or f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_rps{rps}_lat{latency_ms}_{retry_policy}{breaker_suffix}"
    )
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"[{run_id}] setting retry_policy={retry_policy} breaker_enabled={breaker_enabled} "
        f"enable_arrival_trace={enable_arrival_trace}"
    )
    set_experiment_config(retry_policy, breaker_enabled, enable_arrival_trace)

    print(f"[{run_id}] configuring toxiproxy latency={latency_ms}ms")
    proxy_state = set_toxic_latency(latency_ms)

    if enable_arrival_trace:
        http_json("POST", f"{SERVICE_B_URL}/internal/arrival_trace/reset")

    poller = SnapshotPoller(interval_s=1.0)
    try:
        a_config = http_get_json(f"{SERVICE_A_URL}/internal/config")
        b_config = http_get_json(f"{SERVICE_B_URL}/internal/config")

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

    if enable_arrival_trace:
        trace = http_get_json(f"{SERVICE_B_URL}/internal/arrival_trace")
        arrival_trace_path = run_dir / "arrival_trace.csv"
        with arrival_trace_path.open("w") as f:
            f.write("arrival_ns\n")
            for arrival_ns in trace.get("arrivals_ns", []):
                f.write(f"{arrival_ns}\n")
        print(f"[{run_id}] arrival trace: {trace.get('count', 0)} arrivals -> {arrival_trace_path}")

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
        "retry_policy": retry_policy,
        "breaker_enabled": breaker_enabled,
        "enable_arrival_trace": enable_arrival_trace,
        "max_attempts": a_config.get("max_attempts"),
        "pool_size": b_config.get("pool_max_size"),
        "query_timeout_s": b_config.get("query_timeout"),
        "http_timeout_s": a_config.get("http_timeout"),
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
    parser.add_argument(
        "--retry-policy", choices=RETRY_POLICIES, default="none", help="Service A retry policy for this run"
    )
    parser.add_argument(
        "--breaker", choices=["off", "on"], default="off", help="Service A circuit breaker for this run"
    )
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
    parser.add_argument(
        "--phase-a",
        action="store_true",
        help="run Experiment 002 Phase A: 400ms latency x 3 retry policies x RPS {5,10,20,40,60} (15 runs)",
    )
    parser.add_argument(
        "--phase-b",
        action="store_true",
        help="run Experiment 002 Phase B: same as Phase A but at 200ms latency (only run if Phase A shows a signal)",
    )
    parser.add_argument(
        "--exp003",
        action="store_true",
        help="run Experiment 003: 400ms latency, retries disabled, breaker off/on x RPS {12,14,16,18} (8 runs)",
    )
    parser.add_argument(
        "--exp004",
        action="store_true",
        help=(
            "run Experiment 004: 400ms latency, breaker disabled, retry budget 3 attempts, "
            "policies {none,immediate,full_jitter} x RPS {12,14,16,18} (12 runs), arrival tracing on"
        ),
    )
    parser.add_argument(
        "--trace-arrivals",
        action="store_true",
        help="enable Service B's per-request arrival trace for a single --rps/--latency-ms run",
    )
    args = parser.parse_args()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    if args.phase_a or args.phase_b:
        latency_ms = PHASE_B_LATENCY_MS if args.phase_b else PHASE_A_LATENCY_MS
        for retry_policy in PHASE_A_POLICIES:
            for rps in PHASE_A_RPS:
                run_experiment(
                    rps=rps,
                    latency_ms=latency_ms,
                    retry_policy=retry_policy,
                    warmup_s=args.warmup_s,
                    measure_s=args.measure_s,
                    cooldown_s=args.cooldown_s,
                )
        return

    if args.exp003:
        for breaker_enabled in (False, True):
            for rps in EXP003_RPS:
                run_experiment(
                    rps=rps,
                    latency_ms=EXP003_LATENCY_MS,
                    retry_policy="none",
                    breaker_enabled=breaker_enabled,
                    warmup_s=args.warmup_s,
                    measure_s=args.measure_s,
                    cooldown_s=args.cooldown_s,
                )
        return

    if args.exp004:
        for retry_policy in EXP004_POLICIES:
            for rps in EXP004_RPS:
                run_experiment(
                    rps=rps,
                    latency_ms=EXP004_LATENCY_MS,
                    retry_policy=retry_policy,
                    breaker_enabled=False,
                    enable_arrival_trace=True,
                    warmup_s=args.warmup_s,
                    measure_s=args.measure_s,
                    cooldown_s=args.cooldown_s,
                )
        return

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
                    retry_policy=args.retry_policy,
                    warmup_s=args.warmup_s,
                    measure_s=args.measure_s,
                    cooldown_s=args.cooldown_s,
                )
        return

    if args.rps is None or args.latency_ms is None:
        parser.error(
            "--rps and --latency-ms are required unless --sweep/--phase-a/--phase-b/--exp003/--exp004 is given"
        )

    run_experiment(
        rps=args.rps,
        latency_ms=args.latency_ms,
        retry_policy=args.retry_policy,
        breaker_enabled=(args.breaker == "on"),
        enable_arrival_trace=args.trace_arrivals,
        warmup_s=args.warmup_s,
        measure_s=args.measure_s,
        cooldown_s=args.cooldown_s,
    )


if __name__ == "__main__":
    main()
