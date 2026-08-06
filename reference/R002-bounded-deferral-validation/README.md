# R002 -- Reference-grade validation of Experiment 009's bounded-deferral claim

**Status.** closed

**Evidence grade.** reference -- this validates a specific prior claim
under replication; it does not ask a new causal question. See
`experiments/009-bounded-grace-period/README.md` for the original, still-
closed, research-grade experiment. Nothing about 009 is reopened, revised,
or reinterpreted by this document -- 009 stands exactly as published. R002
exists because a different audience (engineers outside this repo) requires
a different evidence standard (replicated, with reported variance) than
the one 001-009 were built under, not because the original standard was
wrong for its original purpose.

**Relationship to 009, precisely.** Experiment 009 made a regime-dependent
claim from a single run per condition: bounded admission deferral
(`grace_ms=20`) measurably reduces client-visible error near the collapse
boundary (RPS 14: 16.7% `instantaneous` vs 13.1% `bounded_grace`), that
benefit shrinks as offered load increases (RPS 16: 22.9% vs 23.0%; RPS 18:
33.3% vs 33.3%, statistically indistinguishable), and RPS 12 is a clean
validity check showing 0% error for both conditions. The mechanism 009
attributes this to is a rescue rate that falls sharply across the same
range -- 77% of deferred decisions resolved at RPS 14, 11.5% at RPS 16,
0.4% at RPS 18.

R002 replicates only the cells that define this comparison: both
conditions the claim compares (`instantaneous`, `bounded_grace`), at all
four RPS points 009 swept. The `off` condition is excluded -- that
comparison belongs to Experiment 006, not to what 009 claims about
deferral itself. Unlike R001's linear-ratio claim (which only needed two
boundary points per pool size), 009's claim is a *comparison across a
curve*, so all four RPS points are load-bearing here, not just the
endpoints -- dropping RPS 16 would remove the ability to assess whether
the transition itself is a smooth decline or something noisier.

**The eight cells:**

| admission_control_mode | rps | role in 009's claim |
|---|---|---|
| instantaneous | 12 | validity check (clean edge) |
| bounded_grace | 12 | validity check (clean edge) |
| instantaneous | 14 | baseline at largest claimed effect |
| bounded_grace | 14 | largest claimed effect (16.7% -> 13.1%) |
| instantaneous | 16 | baseline at transition |
| bounded_grace | 16 | transition point (effect shrinking) |
| instantaneous | 18 | baseline at convergence |
| bounded_grace | 18 | convergence (effect ~gone) |

**What this document estimates, not what it proves.** Per the same
preregistration discipline as R001 and every experiment since 007, this is
stated as an estimation question, not a pass/fail test against thresholds
invented for this document:

1. Estimate the error-rate distribution (mean, spread, range) at each of
   the eight cells, across replicated runs.
2. At the four `bounded_grace` cells, additionally estimate the
   distribution of the deferred-decision rescue rate -- the fraction of
   provisional rejects resolved after the wait -- since this is the
   mechanism 009 attributes the error-rate gap to, not an incidental
   number.
3. Describe, from those estimated distributions, whether `bounded_grace`
   remains measurably below `instantaneous` at RPS 14, whether that gap
   visibly narrows through RPS 16, and whether it remains negligible at
   RPS 18 -- i.e., whether the regime-transition shape a single run
   suggested holds up once run-to-run variance is visible for the first
   time.
4. **The central research question:** does replication support 009's
   regime-transition claim, or does the observed variability require
   weakening it -- for example, if RPS 16's gap turns out not to be
   reliably distinguishable from noise, or if RPS 14's rescue rate varies
   enough to call the 77% figure into question? No specific statistical
   method (confidence intervals, equivalence testing, bootstrap, ANOVA) is
   committed to in advance -- the right method depends on the shape of the
   variance actually observed, which doesn't exist yet.

**Explicitly not a numeric pass/fail criterion.** No threshold like "the
gap must exceed X points" or "rescue rate must stay within Y% of 77%" is
stated here, for the same reason R001 didn't invent one: any such number
would be invented, not derived. The conclusion is written from the
estimates after they exist, not measured against a bar fixed before they
do.

**Sample size and its escalation rule.** N=5 independent runs per cell (40
runs total), the same first-pass design choice R001 made and for the same
reason -- no prior variance data exists, since every run in 009 was N=1.

The initial design uses five independent runs per cell. If observed
variability is substantially larger than anticipated, additional
replications may be added before analysis. Any increase in sample size
will be documented together with the reason for the change.

**Escalation triggered, once.** After the initial N=5 sweep, the
`bounded_grace_rps16` cell showed a rescue-rate spread far outside what
every other cell showed (individual runs: 0%, 10.4%, 20.1%, 23.7%, 61.9% --
stdev roughly equal to the mean). Every other cell's variance was tight
(RPS14 stdev 0.6 percentage points, RPS18 stdev 0.3). Per the rule above, 5
additional
replicates each of `instantaneous_rps16` and `bounded_grace_rps16` were
added (seed 2, distinct from the main sweep's seed 1) before writing this
Finding. This is Brinkline's first triggered escalation -- R001's
equivalent rule was never triggered because R001's variance came in
smaller than anticipated, not larger.

**If replication weakens 009's original claim, that is a successful
outcome of this validation, not a failure of it.** Same cultural statement
as R001: the purpose of reference-grade evidence is to find out whether a
claim holds under scrutiny appropriate to an external, skeptical audience
-- not to reproduce a number this project already believes. This
document's Finding section will report whichever outcome the replicated
data actually supports, including a weakened or partial version of 009's
claim if that is what the data shows.

**Run order.** Shuffled (seeded, `SHUFFLE_SEED=1`), not grouped by cell --
same rationale as R001: at 40 runs, time-of-day, thermal, or host-machine-
state drift over the sweep's duration would otherwise correlate with a
single condition rather than averaging out across all eight.

**Fixed parameters, identical to 009.** `injected_latency_ms=400`,
`retry_policy=none`, `breaker_enabled=false`, `pool_size=10`,
`admission_grace_ms=20`, same hard threshold decision rule on both reads.
Only `admission_control_mode` and `rps` vary, and only across the eight
preregistered cells above.

**Finding.**

| RPS | instantaneous err% (N=5 or 10) | bounded_grace err% | error delta | rescue rate (mean ± stdev) |
|---|---|---|---|---|
| 12 | 0.00% | 0.17% | ~0 | 0.0% ± 0.0% |
| 14 | 16.81% | 13.10% | **−3.71pp** | 76.1% ± 0.6% |
| 16 (N=10) | 23.03% | 23.03% | ~0 | 22.7% ± 22.5% |
| 18 | 33.33% | 33.32% | ~0 | 0.47% ± 0.3% |

**RPS12 validity check passes**, same as R001's approach: both conditions
show ~0% error, confirming this operating point sits below the collapse
boundary for either condition, so it cannot confound the comparison at the
other three points.

**RPS14 and RPS18 replicate 009's claim closely, with tight variance.**
009's single run found 16.7% -> 13.1% error (a 3.6pp reduction) with a 77%
rescue rate at RPS14; R002's five replicates found 16.81% -> 13.10%
(3.71pp) with 76.1% rescue, essentially the same number now backed by
variance data instead of N=1. At RPS18, 009's near-zero benefit and 0.4%
rescue rate are also replicated closely (33.33% vs 33.32% error, 0.47%
rescue). **The regime-transition claim's two endpoints -- large benefit
near the boundary, negligible benefit deep in overload -- hold up under
replication.**

**RPS16 replicates the mean-error convergence but reveals something 009
could not have seen: the mechanism underneath it is bimodal, not
intermediate.** 009's single run reported an 11.5% rescue rate at RPS16,
read as a midpoint between 77% and 0.4%. Ten replicates instead show two
distinct behaviors: 8 of 10 runs cluster low (0-25% rescue, roughly
500-660 deferred decisions over the measurement window), while 2 of 10
runs jump to ~62% rescue with roughly double the deferred-decision count
(~1315). The *error rate* stays tight across all ten runs regardless of
which mode a given run lands in (23.03% mean, 0.08pp stdev) -- the
instability is entirely inside the deferred-decision mechanism, invisible
to the aggregate metric 009 relied on. The escalation from N=5 to N=10
did not narrow this spread (rescue-rate stdev was 23.5pp at N=5, 22.5pp at
N=10) -- this is a real bimodal split, not a small-sample artifact that
more replicates would smooth out.

**What this means for 009's claim.** The regime-transition shape --
large rescue effect near the boundary, shrinking to negligible deep in
overload -- is supported, not weakened, by replication at RPS14 and
RPS18. RPS16 is where replication adds something 009's single run
structurally could not provide: the transition isn't a smooth midpoint,
it's a point where the admission-control system intermittently flips
between two qualitatively different operating modes while still landing
on nearly the same client-visible error rate either way.

**What causes the split is not yet known, and is narrower than it might
look.** `bounded_grace` (`BoundedGraceAdmission`, see
`services/service-b/app/admission.py`) uses the same hard instantaneous
threshold as 006 (`pool_active >= pool_max_size`) on both the first read
and the re-read after the grace wait -- it does not involve the EWMA
signal or `u_low` at all; those belong to 007 and 008 respectively, not
to this mechanism. So the bimodal split is a property of how pool
occupancy itself behaves near RPS16, not of any trailing-signal staleness.
A plausible but unconfirmed account: at RPS16 offered load sits close
enough to the pool's effective capacity that whether a given run's pool
occupancy clears within the 20ms grace window is sensitive to exactly how
request arrivals and query completions happen to interleave over that
run's ~90s measurement window -- which could plausibly settle into
different quasi-stable occupancy patterns from run to run. This document
does not test that account; it only establishes that the bimodal split
itself is real and reproducible, not a small-sample artifact. A dedicated
follow-up would need timestamped, time-resolved pool-occupancy data within
a single RPS16 run (neither `admission_decision_trace.csv`'s current
schema nor `enable_arrival_trace` currently records this) to confirm or
rule out this account.

**Sample size, final.** RPS12/14/18: N=5. RPS16: N=10 (escalated per the
preregistered rule, documented above). 50 runs total.
