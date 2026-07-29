# Experiment 002 -- Retry amplification

**Status.** closed

**Question.** When a client (Service A) retries a slow dependency (Service
B), does that help it recover, or does it amplify overload? And does
retrying shift the point where the system collapses to a lower offered
load?

**Method.** Service A was split off from the database: Service B is a copy
of the original Service A, now owning the connection pool behind Toxiproxy;
Service A became a thin HTTP client with a configurable retry policy
(`none`, `immediate`, `backoff` with a random 50-100ms delay). At a fixed
400ms injected latency, 27 runs swept RPS `[5, 10, 12, 14, 16, 18, 20, 40,
60]` across all three retry policies (`summary.csv`) — the finer
12/14/16/18 points were added specifically to resolve the collapse
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

![Error rate vs offered load, by retry policy](figures/04_error_rate_by_policy.png)

![Amplification factor vs offered load, by retry policy](figures/05_amplification_by_policy.png)
