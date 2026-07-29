# Experiment 004 -- Retry scheduling (backoff + jitter)

**Status.** closed

**Question.** Experiment 002 showed immediate retries add ~2x load on an
already-saturated dependency without adding completed throughput. Is the
problem retrying itself, or specifically *how* retries are scheduled? Can
exponential backoff with full jitter desynchronize retry waves and reduce
that overload, compared to immediate retries?

**Method.** Same topology as Experiment 002 (breaker absent, not just off —
combining it with retry scheduling would confound which mechanism caused
any change). Two changes from Experiment 002's setup, both deliberate:

- **Retry budget raised from 2 to 3 total attempts.** With a single retry,
  comparing scheduling policies only compares one delay's length — jitter's
  actual purpose (decorrelating a *wave* of clients across multiple rounds)
  never gets exercised. Three attempts is the minimum that creates more
  than one retry wave while staying bounded.
- **A new optional per-request arrival trace at Service B** (`arrival_ns`
  only — no payload, no headers, no request ID; gated behind
  `--trace-arrivals`/`--exp004`, off by default so Experiments 001-003 are
  unaffected). The existing ~1Hz snapshot polling can't distinguish a
  synchronized retry burst from a smoothed one, since a 100-200ms backoff
  schedule lives entirely inside one polling bucket — without this trace,
  the experiment could only measure the hypothesis's *outcome*, not its
  claimed *mechanism*.

Three retry policies — `none`, `immediate`, `full_jitter` (100ms/200ms
exponential base, full jitter: `random(0, base)`) — swept across the exact
RPS boundary Experiments 002/003 identified (12/14/16/18) at a fixed 400ms
injected latency, 12 runs (`summary.csv`). Fixed backoff was deliberately
excluded from this sweep: it shifts a retry wave in time without spreading
it, so it doesn't test the desynchronization mechanism under
investigation.

**Finding.** The outcome metrics replicate Experiment 002 almost exactly.
The collapse boundary is unchanged — still exactly RPS 12 → 14 for all
three policies. `immediate` and `full_jitter` are statistically
indistinguishable on amplification (~3.0x, tracking the new 3-attempt
budget), client-visible error rate (~99.6-99.9%), and Service B's completed
throughput, which stays flat around 1,100-1,110 requests per 90s window
regardless of policy:

| RPS | Policy | Error rate | Amplification | B completed |
|---|---|---|---|---|
| 12 | all three | 0% | 1.00 | ~1,062 |
| 14 | `immediate` / `full_jitter` | ~99.9% | ~3.00 | ~1,105 |
| 16 | `immediate` / `full_jitter` | ~99.9% | ~2.99 | ~1,100 |
| 18 | `immediate` / `full_jitter` | ~99.6-99.9% | ~2.98-2.99 | ~1,108 |

Taken alone, that would read as "jitter didn't help" — not a very
interesting result. The arrival trace is what makes this a stronger
finding than that. Bucketing each run's arrival trace into 25ms windows and
computing the coefficient of variation (a burstiness measure — lower means
smoother, more evenly spread arrivals) shows full_jitter consistently,
monotonically reducing burstiness at every saturated RPS tested:

| RPS | `immediate` arrival CV | `full_jitter` arrival CV |
|---|---|---|
| 14 | 1.499 | 1.196 |
| 16 | 1.275 | 1.082 |
| 18 | 1.308 | 1.027 |

So the experiment answered two separate questions, not one. **Does full
jitter desynchronize retries? Yes, consistently.** **Does that
desynchronization improve system-level outcomes? No — not in this system.**
The results are consistent with the fixed-size connection pool remaining
the dominant bottleneck after saturation: although full jitter reduced
arrival burstiness, the throughput ceiling stayed unchanged, suggesting
that smoothing arrivals alone was insufficient to overcome the resource
constraint. Once Service B's 10-connection pool is the binding constraint,
a smoother arrival pattern still funnels into the same fixed-rate drain —
retries add the same ~3x wasted load either way, just spread out
differently in time.

This closes the four-experiment arc that opened with Experiment 001:
001 identified the mechanism (pool saturation), 002 showed a plausible
mitigation makes things worse (naive retries amplify without helping), 003
showed a mitigation that works (fail-fast + probe), and 004 verified that a
second plausible mitigation's proposed mechanism is real — full jitter
does desynchronize retries — while showing that mechanism alone doesn't
overcome a fixed-capacity bottleneck. Eliminating a plausible hypothesis
with direct mechanistic evidence, not just an absence of effect, is why
this counts as a completed result rather than an inconclusive one.

![Error rate vs offered load, by retry policy](figures/08_error_rate_by_policy.png)

![Amplification factor vs offered load, by retry policy](figures/09_amplification_by_policy.png)

![Completed throughput vs offered load, by retry policy](figures/10_completed_throughput_by_policy.png)

![Arrival burstiness (coefficient of variation, 25ms buckets) at Service B: immediate vs. full_jitter — lower is smoother, more desynchronized arrivals](figures/11_arrival_burst_cv.png)
