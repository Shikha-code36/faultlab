# Experiment 005 -- Connection pool capacity as the collapse lever

**Status.** open

**Question.** Experiments 001-004 all converged on Service B's fixed
10-connection pool as the binding constraint once the system saturates,
but none of them varied it. Does increasing `POOL_MAX_SIZE` shift the
collapse boundary to a higher offered load, or does the bottleneck
relocate elsewhere (query time, Postgres itself, network) once the pool
stops being the limit?

**Hypothesis.** Two regimes are predicted:

- **Pool-limited regime** -- while the connection pool is the binding
  constraint, increasing `POOL_MAX_SIZE` raises the collapse boundary
  roughly in proportion to the pool size increase.
- **Bottleneck-relocated regime** -- past some pool size, a different
  subsystem (Postgres query capacity, CPU, network) becomes binding
  instead, and further pool increases yield diminishing or no improvement
  in the collapse boundary.

**Primary variable.** `pool_size` (`POOL_MAX_SIZE`), tested at **10, 20,
40**.

**Why these three values, without intermediate points.** 10 is the
baseline used throughout 001-004, included as a control to confirm this
environment reproduces the known ~RPS 12-14 boundary before trusting the
new pool-size points. 20 and 40 are two consecutive doublings, giving
three points across a 4x range -- enough to tell the two hypothesized
regimes apart, since that only requires enough ratio between points to
make curvature visible above noise: if the boundary keeps doubling too
(~26 RPS, then ~52 RPS), that's the pool-limited regime continuing; if the
second doubling's gain shrinks noticeably instead, that's the
bottleneck-relocated regime. Intermediate points (15, 30) would sharpen
*where* a transition sits but aren't needed to answer the binary regime
question this experiment asks. If Phase A shows bending, a Phase B
bracketing the transition (the same conditional-phase precedent
Experiment 002 set) is the right follow-up, not more upfront points now.

**Method.** Fixed at 400ms injected DB latency (matches 002-004, keeps
this comparable to the established boundary), `retry_policy=none`,
`breaker_enabled=false` -- isolating pool size as the only variable, the
same discipline 003/004 applied to the breaker/jitter. Arrival tracing is
off (not relevant here). Postgres's `max_connections` stays at its
default (100, unconfigured in `docker-compose.yml`), comfortably above
every pool size tested here -- this design says nothing about pool sizes
approaching that ceiling.

Phase A (coarse bracket, 15 runs) centers each pool size's RPS sweep on
the ~1.3 RPS-of-capacity-per-connection ratio implied by the pool=10
baseline, rather than reusing one fixed RPS range that would be
uninformative at the extremes:

| pool_size | Phase A RPS points |
|---|---|
| 10 (control) | 10, 12, 14, 16, 18 |
| 20 | 20, 24, 28, 32, 36 |
| 40 | 40, 48, 56, 64, 72 |

A Phase B fine sweep (3-4 points bracketing whatever boundary Phase A
finds per pool size) runs only if Phase A's coarse boundary needs
narrowing.

**What determines whether the hypothesis is supported.**

1. **Primary signal** -- the collapse boundary (lowest RPS flagged
   saturated: error rate > 0, any pool-acquisition timeout, or
   `pool_active_max >= pool_size`) computed per pool size. Monotonically
   increasing boundaries as pool size grows supports the pool-limited
   regime; a boundary that doesn't move despite 2x/4x more pool capacity
   falsifies pool size as the lever at that point.
2. **Throughput at collapse** -- Service B's completed-query count
   (`b_success_count`) at each pool size's collapse boundary, not just the
   RPS it collapsed at. A higher offered load surviving longer doesn't by
   itself mean more work got done; this is what actually answers whether
   a bigger pool does useful work or just delays the same ceiling.
3. **Where the constraint relocates, if it does** -- watch
   `b_query_timeout_count` and query latency at larger pool sizes even
   *below* their saturation point. Failures appearing while
   `pool_active_max < pool_size` (spare pool capacity, but queries
   themselves degrading) would be evidence the real constraint moved to
   Postgres itself, not the pool.
4. **Confound check** -- `amplification_factor` should stay ~1.0 across
   every run (retries are off); if it doesn't, something's misconfigured,
   not a genuine result.

**Finding.** _TODO: fill in once the experiment is closed._
