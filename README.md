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
python scripts/analyze_results.py --csv experiments/summary.csv
```

Prints a table across all completed runs and flags the first (rps, latency)
point per RPS where the system saturates: error rate above 0%, any
connection-pool acquisition timeouts, or the pool running at its full
configured size. Injected latency alone always makes requests slower —
that's just propagation, not saturation, so it isn't used as a signal on
its own.

## Experiment 001 — database latency propagation

Full sweep: RPS `[5, 10, 20, 40, 60]` × injected DB latency
`[0, 50, 100, 200, 400, 800]` ms, 30 runs (`experiments/summary.csv`).

At low offered load, injected latency propagated almost linearly into
request latency with no failures — the pool had spare capacity to absorb
slower connections. As offered load increased, the connection pool became
the limiting resource: the latency needed to trigger saturation dropped
from 800ms at 5 RPS to just 100ms at 60 RPS.

Failures were driven by connection-pool acquisition timeouts, not query
timeouts — the collapse was caused by resource contention on the pool, not
by the database query itself running slow.
