# FaultLab

A reproducible laboratory for injecting real failures into small systems,
observing how those failures propagate, and explaining why.

```
Load Generator (k6) -> Service A (FastAPI, retry client + circuit breaker) -> Service B (FastAPI + asyncpg) -> Toxiproxy -> PostgreSQL
```

Service A is a thin HTTP client with a configurable retry policy (none /
immediate / retry-with-backoff / exponential backoff with full jitter) and a
circuit breaker that can wrap the call to Service B. Service B owns the
bounded connection pool and is the one instrumented behind Toxiproxy's
injected network latency, on a real PostgreSQL database. Every component in
the request path is real.

## Current experiments

| Experiment | Status | Key finding |
|---|---|---|
| [001 — collapse boundary](experiments/001-collapse-boundary/README.md) | closed | Injected DB latency propagates harmlessly until the connection pool saturates; the latency needed to trigger saturation drops sharply as offered load rises. |
| [002 — retry amplification](experiments/002-retry-amplification/README.md) | closed | Retries roughly double load on an already-saturated dependency without increasing completed throughput, and don't measurably shift the collapse boundary. |
| [003 — circuit breaker](experiments/003-circuit-breaker/README.md) | closed | A minimal breaker cuts load reaching the saturated dependency by up to ~44%, cuts client-visible errors by up to ~61 points, and every recovery probe succeeded — confirming the collapse is a queueing effect, not a hard failure. |
| [004 — jitter](experiments/004-jitter/README.md) | closed | Full jitter measurably desynchronizes retry arrivals at every saturated RPS tested, but that desynchronization doesn't move amplification, error rate, or completed throughput — a fixed-capacity pool, not burst-induced overflow, remains the dominant constraint once saturated. |
| [005 — connection pool capacity](experiments/005-connection-pool-capacity/README.md) | closed | The collapse boundary scales exactly linearly with pool size (10→20→40, RPS 14→28→56, all at a 1.4 RPS-per-connection ratio) with no curvature — a bigger pool moves the collapse point but doesn't soften it: client-visible success still collapses to near 0% at the new boundary, while Service B keeps completing about the same amount of real work. |

## Running the stack

```
docker compose up -d --build postgres toxiproxy toxiproxy-init service-b service-a
```

Wait for `service-a` to report healthy, then confirm it can reach the
database through the proxy:

```
curl http://localhost:8000/healthz
curl http://localhost:8000/work?id=1
```

## Running an experiment

Every experiment lives under `experiments/<id>-<slug>/` and declares its own
run matrix in `experiment.py` (see `faultlab/experiment.py` for the model).
To run one end to end:

```
python scripts/run_experiment.py 005
python scripts/analyze_results.py 005 --csv
```

`run_experiment.py` loads the experiment's `matrix()` and executes each run
via the shared `Runner`, writing artifacts to
`experiments/<id>-<slug>/runs/<run_id>/`:

- `metadata.json` — run configuration (rps, injected latency, retry policy, breaker enabled, pool size, timeout)
- `results.json` — load generator summary plus `service_a`/`service_b`/`breaker`
  metric summaries and the derived `amplification_factor` / `retry_rate` /
  `retry_success_rate` / `probe_success_rate`
- `proxy_state.json` — the Toxiproxy configuration used
- `raw_app_samples.jsonl` — per-second snapshots from both services plus the breaker
- `arrival_trace.csv` — one arrival timestamp per request reaching Service B, only when the experiment enables arrival tracing
- `loadgen/summary.json`, `loadgen/raw.jsonl` — k6 summary and per-request events

`analyze_results.py` aggregates those runs into `experiments/<id>-<slug>/summary.csv`
and reports each experiment's saturation/collapse analysis (see
`faultlab/analysis.py`): a run is flagged saturated when its error rate is
above 0%, any pool-acquisition timeout occurred on Service B, or Service B's
pool ran at its configured max size. Injected latency alone always makes
requests slower — that's just propagation, not saturation, so it isn't used
as a signal on its own.

## Starting a new experiment

```
python scripts/new_experiment.py 006 my-slug \
    --title "..." --question "..." --hypothesis "..." --variable my_variable
```

Scaffolds `experiments/006-my-slug/` with an `experiment.py` stub (fill in
`matrix()`) and a `README.md` skeleton. See `experiments/005-connection-pool-capacity/`
for a complete example of the model in use.
