# FaultLab

A reproducible laboratory for injecting real failures into small systems,
observing how those failures propagate, and explaining why.

The first experiment: what happens to a healthy backend as its database
becomes slower?

```
Load Generator (k6) -> Service A (FastAPI + asyncpg) -> Toxiproxy -> PostgreSQL
```

Everything in the request path is real: a real bounded connection pool, a
real proxy injecting real latency, a real database.

## Running the stack

```
docker compose up -d --build postgres toxiproxy toxiproxy-init service-a
```

Wait for `service-a` to report healthy, then confirm it can reach the
database through the proxy:

```
curl http://localhost:8000/healthz
curl http://localhost:8000/work?id=1
```

## Running a single experiment

```
python scripts/run_experiment.py --rps 20 --latency-ms 100
```

This configures the Toxiproxy latency toxic, polls Service A's internal
metrics once a second, runs a k6 load test (30s warmup / 90s measurement /
15s cooldown by default), and writes everything to
`experiments/runs/<run_id>/`:

- `metadata.json` — run configuration (rps, injected latency, pool size, timeout)
- `results.json` — load generator + application metric summaries
- `proxy_state.json` — the Toxiproxy configuration used
- `raw_app_samples.jsonl` — per-second application metric snapshots
- `loadgen/summary.json`, `loadgen/raw.jsonl` — k6 summary and per-request events

## Running the full sweep

```
python scripts/run_experiment.py --sweep
```

Sweeps RPS in `[5, 10, 20, 40, 60]` against injected DB latency in
`[0, 50, 100, 200, 400, 800]` ms, per the Week 1 plan.

## Analyzing results

```
python scripts/analyze_results.py
python scripts/analyze_results.py --csv experiments/runs/summary.csv
```

Prints a table across all completed runs and flags the first
(rps, latency) point per RPS where the system degrades relative to its own
0ms-latency baseline (p95 latency > 2x baseline, or error rate > 1%). This
is a starting heuristic for finding where saturation begins, not a final
verdict — read the raw samples for the real story.
