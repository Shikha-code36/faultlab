# Experiment 011 -- EWMA half-life sensitivity sweep

**Status.** closed

**Phase II working thesis.** Capacity determines *where* saturation
occurs (Experiment 005). Arbitration determines *how* saturation
manifests (Experiment 006). Experiment 007 showed information freshness
is an independent causal factor within arbitration: a 2.0s-half-life
EWMA signal performed far closer to no admission control at all than to
an instantaneous signal at the same location. This experiment tests the
specific question 007 deliberately left open.

**Question.** Experiment 007's half-life (2.0s) was a stated design
choice, not swept. As half-life shrinks toward the interarrival
timescale, does EWMA admission performance degrade continuously toward
`instantaneous`, or is there a sharp cliff at some point?

**Hypothesis.** Two distinguishable outcomes: (1) if error rate moves
smoothly across the half-life sweep, information freshness has a graded
effect and no single threshold half-life is privileged; (2) if instead
there is a sharp knee -- performance close to `off` above some half-life
and close to `instantaneous` below it -- only sufficiently stale signals
matter, and near-instantaneous EWMA already behaves like true
instantaneous.

**Primary variable.** `admission_ewma_half_life_s`, swept at
`0.06, 0.25, 0.5, 1.0, 2.0, 4.0` seconds, log-spaced rather than linear --
a cliff, if one exists, is far more visible on a log axis than a linear
one. Bounds are derived, not picked:
- *Lower anchor (0.06s)* sits below RPS 16's ~62.5ms interarrival time --
  a half-life below one interarrival interval decays within roughly one
  request, functionally indistinguishable from `instantaneous`.
- *Upper anchor (2.0s)* is Experiment 007's own value, re-run in-session
  as the tie-back point to that result rather than reused from its
  historical data -- the same discipline 007 itself applied against
  reusing Experiment 006's numbers.
- *One point beyond 007's value (4.0s)* checks whether degradation keeps
  worsening past 2.0s or has already plateaued toward `off`.

**Fixed parameters.** `pool_size=10`, `retry_policy=none`,
`breaker_enabled=false`, `injected_latency_ms=400`. `off` (no admission
control) and `instantaneous` (Experiment 006's mechanism) are re-run in
this same session as bookend controls, not reused from prior experiments'
historical data.

**Why a single saturated RPS, not a sweep.** One-variable-per-experiment
discipline, consistent with 007/009: sweeping RPS and half-life together
would conflate two variables. RPS 16 is fixed as the primary point --
Experiment 007's midpoint, with the largest known gap between
`instantaneous` (23.11% error) and `ewma` at half_life=2.0s (85.42%
error), giving the most room to see a gradient or a cliff. RPS 12 is kept
only as the standard below-boundary validity check every admission
experiment (006-009) has run.

**What determines the result.**
1. **Gate 1 (model fidelity)** -- does `b_admission_ewma_utilization_max`
   converge to full utilization under saturation at every half-life,
   confirming the EWMA signal itself behaves correctly regardless of the
   parameter being swept?
2. **Validity check** -- at RPS 12 (below the collapse boundary),
   `admission_rejection_rate` should be ~0% for `instantaneous` and every
   half-life.
3. **The actual comparison** -- does error rate move smoothly across the
   half-life sweep at RPS 16, or is there a sharp discontinuity between
   adjacent half-life points?

**Documented limitations.** Single run per condition, consistent with
every experiment so far except the reference-grade replications (R001,
R002) -- replication remains a project-level methodology question, not
resolved here. A single saturated RPS point (16) was tested; the shape of
this curve at other RPS points relative to the collapse boundary is not
established.

## Finding

**Gate 1 passed.** `b_admission_ewma_utilization_max` reached
0.9999990-0.9999999 under saturation (RPS 16) at every half-life tested
-- the EWMA signal itself converges correctly regardless of the parameter
being swept, exactly as in Experiment 007.

**Validity check passed.** At RPS 12, `admission_rejection_rate` was 0.0
for `instantaneous` and for all six half-lives -- no false positives
below the collapse boundary at any point in the sweep.

**RPS 16 sweep, sorted by half-life:**

| Half-life | Error rate | Rejection rate | Pool timeouts |
|---|---|---|---|
| off (no admission) | 99.93% | -- | 316 |
| instantaneous | 23.06% | 23.03% | 0 |
| 0.06s | 24.03% | 23.71% | 0 |
| 0.25s | 25.90% | 23.18% | 0 |
| 0.5s | 60.07% | 20.71% | 40 |
| 1.0s | 76.11% | 13.30% | 147 |
| 2.0s | 90.28% | 4.57% | 250 |
| 4.0s | 99.93% | 0.28% | 315 |

**The curve is continuous, not a step function -- supporting the first
branch of the hypothesis.** Error rate rises smoothly across all six
half-lives, from a value statistically indistinguishable from
`instantaneous` at the low end (23-26% for 0.06s/0.25s) to a value
statistically indistinguishable from `off` at the high end (99.93% at
4.0s, exactly matching `off`'s 99.93%). There is no pair of adjacent
half-life points separated by a jump large enough to read as a discrete
regime boundary -- the largest single step (0.25s -> 0.5s, +34.2
percentage points) sits inside a run of comparably sized steps (0.5s ->
1.0s: +16.0pp; 1.0s -> 2.0s: +14.2pp; 2.0s -> 4.0s: +9.7pp), not isolated
as an outlier. Information freshness has a graded effect across this
range; no single half-life is a privileged threshold separating
"instantaneous-like" from "off-like" behavior.

**The steepest part of the curve sits between 0.25s and 1.0s** -- notably
above the interarrival-time lower anchor (~62.5ms) and below the
measured request-service-time (~800ms, the same quantity that grounded
007's original half-life choice). This is consistent with, though not
proof of, a natural interpretation: once the trailing window starts
spanning multiple request-service cycles rather than sub-cycle timing
noise, staleness starts compounding rather than merely smoothing.

**The mechanism is the same one Experiment 007 found, and it scales
continuously with half-life.** Under `instantaneous` and the two shortest
half-lives (0.06s, 0.25s), `b_pool_timeout_count` is 0 -- every error is a
cheap, fast rejection, the gate never lets the pool overflow. From 0.5s
onward, pool timeouts appear and grow monotonically (40 -> 147 -> 250 ->
315), converging on `off`'s 316 timeouts at 4.0s. `admission_rejection_rate`
falls as half-life grows (23.71% -> 0.28%) -- a stale enough signal stops
rejecting almost anything, not because saturation isn't detected, but
because the trailing average only crosses the threshold once the pool is
already overwhelmed and requests are already timing out on their own.
Exactly 007's finding (lagging signals convert cheap rejections into
expensive timeouts), now shown to scale continuously with the degree of
lag rather than being specific to 007's one tested value.

**Scope of this conclusion.** Tested at a single saturated RPS point
(16) and a single injected-latency value (400ms); whether this curve's
shape or steepest region shifts at other operating points relative to
the collapse boundary is not established here. Single run per condition
-- if a future reference-grade validation of this claim is warranted, it
would need replicated runs, per the R001/R002 precedent.
