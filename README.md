# FaultLab

A reproducible laboratory for injecting real failures into small systems,
observing how those failures propagate, and explaining why.

```
Load Generator (k6) -> Service A (FastAPI, retry client) -> Service B (FastAPI + asyncpg) -> Toxiproxy -> PostgreSQL
```

Service A is a thin HTTP client with a configurable retry policy (none /
immediate / retry-with-backoff). Service B owns the bounded connection pool
and is the one instrumented behind Toxiproxy's injected network latency, on
a real PostgreSQL database. Every component in the request path is real.

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

## Running a single experiment

```
python scripts/run_experiment.py --rps 20 --latency-ms 100 --retry-policy none
```

`--retry-policy` is `none` (default), `immediate`, or `backoff` — it sets
Service A's retry behavior for the run. This configures the Toxiproxy
latency toxic on the Service B <-> PostgreSQL link, polls both Service A's
and Service B's internal metrics once a second, runs a k6 load test (30s
warmup / 90s measurement / 15s cooldown by default), and writes everything
to `experiments/runs/<run_id>/`:

- `metadata.json` — run configuration (rps, injected latency, retry policy, pool size, timeout)
- `results.json` — load generator summary plus `service_a`/`service_b` metric
  summaries and the derived `amplification_factor` / `retry_rate` / `retry_success_rate`
- `proxy_state.json` — the Toxiproxy configuration used
- `raw_app_samples.jsonl` — per-second snapshots from both services
- `loadgen/summary.json`, `loadgen/raw.jsonl` — k6 summary and per-request events

## Running the full sweep

```
python scripts/run_experiment.py --sweep
python scripts/run_experiment.py --phase-a   # Experiment 002: 400ms x 3 retry policies x RPS {5,10,20,40,60}
python scripts/run_experiment.py --phase-b   # same, at 200ms
```

`--sweep` runs RPS in `[5, 10, 20, 40, 60]` against injected DB latency in
`[0, 50, 100, 200, 400, 800]` ms, per the Week 1 plan.

## Analyzing results

```
python scripts/analyze_results.py
python scripts/analyze_results.py --csv experiments/summary.csv
```

Prints a table across all completed runs and flags the first (rps, latency)
point per retry policy where the system saturates: error rate above 0%, any
connection-pool acquisition timeouts on Service B, or its pool running at
full configured size. Injected latency alone always makes requests slower —
that's just propagation, not saturation, so it isn't used as a signal on
its own.

## Experiment 001 — database latency propagation

**Question.** How does injected database latency interact with offered
load — where does a healthy backend stop absorbing a slower dependency and
start failing?

**Method.** Full sweep: RPS `[5, 10, 20, 40, 60]` × injected DB latency
`[0, 50, 100, 200, 400, 800]` ms, 30 runs (`experiments/summary.csv`).

**Finding.** At low offered load, injected latency propagated almost
linearly into request latency with no failures — the pool had spare
capacity to absorb slower connections. As offered load increased, the
connection pool became the limiting resource: the latency needed to
trigger saturation dropped from 800ms at 5 RPS to just 100ms at 60 RPS.
Failures were driven by connection-pool acquisition timeouts, not query
timeouts — the collapse was caused by resource contention on the pool, not
by the database query itself running slow.

All figures below are generated from the canonical 30-condition
experiment matrix (`experiments/summary.csv`).

![Request latency vs injected DB latency, by RPS](experiments/figures/01_latency_propagation.png)

![Error rate by RPS x injected latency](experiments/figures/02_error_rate_heatmap.png)

![Saturation boundary per offered load](experiments/figures/03_saturation_boundary.png)

## Experiment 002 — retry amplification

**Question.** When a client (Service A) retries a slow dependency (Service
B), does that help it recover, or does it amplify overload? And does
retrying shift the point where the system collapses to a lower offered
load?

**Method.** Service A was split off from the database: Service B is a copy
of the original Service A, now owning the connection pool behind Toxiproxy;
Service A became a thin HTTP client with a configurable retry policy
(`none`, `immediate`, `backoff` with a random 50-100ms delay). At a fixed
400ms injected latency, 27 runs swept RPS `[5, 10, 12, 14, 16, 18, 20, 40,
60]` across all three retry policies (`experiments/summary_002.csv`) — the
finer 12/14/16/18 points were added specifically to resolve the collapse
boundary after the initial 5/10/20/40/60 sweep showed it as a step function
between 10 and 20 RPS.

*Methodology note:* the initial sweep's RPS 40 and 60 conditions showed
Service B receiving less traffic than Service A sent, or none at all —
Service A's `httpx.AsyncClient` was relying on its library-default 100
connection limit, which silently failed requests client-side (before they
ever reached Service B) once concurrency exceeded that under retry-doubled
load. Raising the limit explicitly (`httpx.Limits(max_connections=1000)`)
and re-running the affected conditions confirmed the client was the
artifact, not Service B's database pool.

**Finding.** Below saturation (RPS 5-12), retries were dormant — there was
nothing to retry, so `immediate` and `backoff` were indistinguishable from
no retries at all (amplification ≈ 1.0, 0% errors). All three policies
collapsed at the *same* boundary, between 12 and 14 RPS, to the RPS level
— retrying did not shift the collapse point measurably. Past that boundary,
retries amplified load on Service B by almost exactly 2x (one retry = two
attempts) while Service B's real successful-query throughput stayed flat
around 1,100 requests per 90-second window regardless of retry policy —
retries added load without adding recovery. The collapse itself was sharp
rather than gradual: at RPS 12 the system ran clean end to end, and at RPS
14 it was already at ~100% errors, consistent with classic queueing
collapse once offered load exceeds a fixed service capacity.

Given retries showed no measurable effect on the collapse boundary at
400ms, a second latency sweep (Phase B) was judged unlikely to change that
qualitative conclusion and was not run — Experiment 002 was closed on this
result.

![Error rate vs offered load, by retry policy](experiments/figures/04_002_error_rate_by_policy.png)

![Amplification factor vs offered load, by retry policy](experiments/figures/05_002_amplification_by_policy.png)
