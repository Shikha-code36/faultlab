# Experiment 007 -- EWMA admission signal vs. instantaneous state

**Status.** closed

**Phase II working thesis.** Capacity determines *where* saturation
occurs (Experiment 005). Arbitration determines *how* saturation
manifests (Experiment 006). Experiment 006 showed failure shape is
separable from the underlying resource constraint -- a server-side
admission decision, using no additional capacity, converted a binary
collapse into a load-proportional curve. Experiment 007 tests a specific
causal question underneath that result, rather than optimizing the
mechanism further.

**Question.** Experiment 006's server-side admission gate substantially
outperformed Experiment 003's client-side breaker. But that comparison
changed two things at once: *where* the decision is made (server vs.
client) and *how fresh* the information behind it is (instantaneous
ground truth vs. delayed, inferred aggregate). Does server-side placement
alone explain 006's result, or does information freshness matter
independently of location?

**Hypothesis.** If a server-side admission decision based on a trailing
EWMA of pool utilization performs comparably to Experiment 006's
instantaneous signal, locality is the dominant causal factor -- being
co-located with the resource is what mattered, and freshness is
secondary. If it instead performs closer to Experiment 003's client-side,
inferred-and-delayed breaker, information freshness is an independent
causal factor -- 006's result required not just asking the server, but
asking it *right now*.

**Why this is a distinct mechanism, not a policy variation.** Of three
candidate arbitration mechanisms considered for this phase (graduated/
probabilistic admission onset, a bounded grace period before rejecting,
and this trailing-signal design), this one was prioritized because it
targets *which characteristic of arbitration is causally responsible*
for Experiment 006's result, rather than optimizing an already-established
mechanism. The other two are natural follow-ons once we know which
property of arbitration actually matters.

**Why the observable is pool utilization, not recent failures or recent
latency.** For this comparison to isolate freshness as the *only*
variable, the trailing signal must be a lagged version of the exact same
quantity Experiment 006 used -- not a different quantity that happens to
correlate with saturation:
- *Recent latency* is a downstream effect of contention, filtered through
  an extra interpretive step (what latency counts as "too high"), one
  layer more removed from the resource than 006's signal already was.
- *Recent admission failures / timeout rate* is essentially Experiment
  003's breaker mechanism relocated to the server -- a trailing window
  over *outcomes*, the same signal type 003 already used. Using it here
  would conflate signal type with signal freshness, rather than isolating
  freshness alone.
- *Trailing pool utilization* (`pool_active / pool_max_size`, aggregated
  over time) is the same quantity 006 reads instantaneously, just
  time-averaged. Nothing about *what* is measured changes -- only its
  temporal character.

**Why the aggregation is time-based (EWMA), not request-count-based.**
RPS is the variable being swept across this experiment's matrix, which
rules out a request-count window (e.g., "the last N requests"): at low
RPS, N requests span far more wall-clock time than at high RPS, so a
count-based window's actual freshness would shift with the very variable
under test -- a hidden confound. Aggregating over wall-clock time avoids
this.

**Why EWMA over a fixed sliding window.** A sliding window has a hard
temporal edge -- an observation just inside the window counts fully, one
instant older counts zero -- reintroducing a discontinuity, just
relocated from the utilization dimension (006's hard threshold) into the
time dimension. Avoiding artificial discontinuities is the throughline of
this whole phase (it's why graduated/probabilistic admission is a
candidate for a later experiment). A sliding window would also need two
parameters (window length, and how observations within it are combined)
where EWMA needs one: a decay constant that directly represents
informational staleness -- the exact causal quantity this experiment
manipulates -- rather than an indirect proxy that conflates how much
history is used with how it's weighted.

**Deriving the half-life from measured system properties, not picking a
number.** Two bounds, both grounded in quantities this project has
already measured, not invented for this experiment:
- *Lower bound* -- it must span multiple request completions, or it
  isn't aggregating anything. Every experiment at 400ms injected latency
  (002-006) has shown p95/p99 request latency consistently at ~806-808ms
  -- the actual cycle time of one connection held for one request. A
  half-life shorter than that would just be reacting to whether the last
  request or two happened to find the pool full, indistinguishable in
  practice from 006's instantaneous signal.
- *Upper bound* -- it must fully converge within the 30s warmup preceding
  every run's measurement window (an EWMA reaches ~97% convergence after
  ~5 half-lives), so the measured 90s window reflects steady dynamics,
  not the metric's own startup transient. This is a loose bound in
  practice -- it only rules out half-lives of 10s or more.
- One honest limitation: "react within a typical saturation transition"
  doesn't have direct empirical grounding here, since every run's load
  profile is a step function (k6 ramps to a fixed target RPS during
  warmup, then holds it for the full 90s measurement window) -- there is
  no live transition within a run for the signal to react to. The
  relevant property is convergence-before-measurement, not
  reaction-to-a-transition.

**Half-life: 2 seconds**, roughly 2.5x the measured request-service-time,
comfortably inside both bounds. This is stated explicitly as **a design
choice, not an optimized parameter** -- Experiment 007 tests whether
temporally aggregated resource state behaves differently from
instantaneous state, not what the optimal aggregation timescale is. If
this experiment shows a meaningful difference, sensitivity to the
half-life becomes a natural follow-on, not something to resolve here.

**The decision rule.** Structurally identical to Experiment 006's --
reject if utilization (now the EWMA estimate rather than the
instantaneous reading) is >= 1.0. The EWMA used to decide a given
request's admission reflects history *strictly before* that request: it
is read first (deciding admission), then updated afterward with this
request's own instantaneous observation -- so a request never influences
the signal that gates it, the same principle behind Experiment 003's
breaker excluding short-circuited requests from its own failure-rate
window. The very first request of a run has no history yet and falls
back to an instantaneous reading exactly once -- a documented, negligible
bootstrap artifact given thousands of requests per run.

**Primary variable.** `admission_control_mode`: `off` / `instantaneous`
(Experiment 006's mechanism) / `ewma` (this experiment's mechanism).

**Fixed parameters.** `pool_size=10`, `retry_policy=none`,
`breaker_enabled=false`, `injected_latency_ms=400`,
`admission_ewma_half_life_s=2.0`. RPS swept at `12, 14, 16, 18`, the same
boundary used since Experiment 002.

**Internal validity: same-session controls for both `off` and
`instantaneous`, not reused historical data.** The admission-gate code
was refactored into `services/service-b/app/admission.py` for this
experiment (previously inlined in `main.py` for Experiment 006) --
exactly the kind of change that, per Experiment 006's own reasoning
against reusing Experiment 003's historical numbers, means Experiment
006's historical data shouldn't be assumed identical to what this
codebase would produce today. Both the `off` baseline and the
`instantaneous` condition are re-run in this same session, at the same
four RPS points, rather than reused from Experiment 006's closed results.

**What determines the result.**
1. **Gate 1 (model fidelity)** -- does the EWMA-driven condition's
   observed rejection behavior lag the instantaneous condition's in a way
   consistent with a ~2s half-life (e.g., visible via
   `b_admission_ewma_utilization_max`/`_mean`, exposed specifically so
   this can be checked directly rather than inferred)? This is a
   precondition for trusting the comparison, not itself a measure of
   which mode is "better."
2. **Validity check, mirroring Experiment 006's RPS-12 check** -- at RPS
   12 (below the collapse boundary), `admission_rejection_rate` should be
   ~0% for both `instantaneous` and `ewma`.
3. **The actual comparison** -- do `instantaneous` and `ewma` produce
   similar error-rate curves across RPS 12-18 (supporting locality as the
   dominant factor), or does `ewma` look measurably closer to Experiment
   003's client-side breaker numbers (supporting information freshness as
   an independent factor)?

**Documented limitations.**
- The half-life (2s) is a stated design choice, not derived from a
  sensitivity sweep -- see above.
- Single run per condition, consistent with every experiment so far
  (001-006) -- replication remains a project-level methodology question,
  not something this experiment resolves.
- Fairness between requests remains out of scope: the load generator
  produces undifferentiated requests, so there is no "who" to evaluate
  fairness between yet.

**Finding.** Gate 1 passed: `b_admission_ewma_utilization_max` reaches
~0.9999995 under sustained saturation (RPS 14-18), confirming the EWMA
signal itself converges correctly toward the same ground truth
`instantaneous` reads directly -- this is the corrected implementation
described above; an earlier bug (a strict `>= 1.0` comparison against a
signal that only reaches 1.0 in the limit) meant the first attempt at
this sweep produced zero rejections at any RPS and had to be discarded.
The RPS-12 validity check also passed: `admission_rejection_rate` was
0.0 for both `instantaneous` and `ewma` below the collapse boundary.

| RPS | Mode | Error rate | Rejected | Pool timeouts | Rejection p95 latency |
|---|---|---|---|---|---|
| 12 | off | 0.00% | -- | 0 | -- |
| 14 | off | 99.84% | -- | 0 | -- |
| 16 | off | 100.00% | -- | 0 | -- |
| 18 | off | 99.88% | -- | 0 | -- |
| 12 | instantaneous | 0.00% | 0 | 0 | -- |
| 14 | instantaneous | 16.65% | 208 | 0 | 0.027ms |
| 16 | instantaneous | 23.11% | 328 | 0 | 0.045ms |
| 18 | instantaneous | 33.33% | 534 | 0 | 0.055ms |
| 12 | ewma | 0.00% | 0 | 0 | -- |
| 14 | ewma | 67.06% | 86 | 67 | 0.058ms |
| 16 | ewma | 85.42% | 99 | 216 | 0.041ms |
| 18 | ewma | 93.77% | 80 | 413 | 0.038ms |

**The two pre-registered branches were not close.** `ewma`'s error-rate
curve (67.06% / 85.42% / 93.77%) sits far closer to `off`'s near-total
collapse (99.84% / 100.00% / 99.88%) than to `instantaneous`'s
load-proportional curve (16.65% / 23.11% / 33.33%). Per the hypothesis as
stated, this supports the second branch: information freshness is an
independent causal factor, not a detail subordinate to decision location.
A server-side gate reading the same underlying quantity as Experiment
006, at the same location, produces a qualitatively different outcome
once that reading is a 2-second trailing average instead of instantaneous.

**The mechanism is visible directly in the error composition, not just
inferred from the aggregate rate.** Under `instantaneous`, every error is
a cheap, fast rejection: `b_pool_timeout_count` is 0 at every RPS, and
`b_admission_rejected_latency_p95_ms` stays under 0.06ms throughout --
the gate never lets the pool overflow. Under `ewma`, a substantial and
growing share of errors are real pool timeouts (67 / 216 / 413 at RPS
14/16/18) rather than rejections -- the lagging signal admits requests
that then queue and time out expensively, because the trailing average
only crosses the rejection threshold after the pool is already
overwhelmed. This is the same failure mode `instantaneous` (and 006)
eliminated, re-emerging specifically because the signal behind the gate
is stale. Rejection counts alone (86/99/80 for `ewma` vs. 208/328/534 for
`instantaneous`) already show `ewma` rejecting far less at comparable
RPS; the timeout breakdown explains why that gap translates into worse,
not just fewer, outcomes.

**Scope of this conclusion.** The half-life (2.0s) was tested as a single
stated design choice, not swept -- see documented limitations above. This
finding supports that *a* sufficiently stale signal, at this half-life,
produces materially worse arbitration than an instantaneous one at the
same location; it does not establish how performance varies continuously
with staleness, nor identify a threshold half-life below which behavior
would resemble `instantaneous`. That question -- half-life sensitivity --
is deliberately left to a follow-on experiment rather than answered here,
consistent with this experiment's one-variable design.
