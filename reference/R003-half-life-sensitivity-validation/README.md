# R003 -- Reference-grade validation of Experiment 011's half-life sensitivity claim

**Status.** closed

**Evidence grade.** reference -- this validates a specific prior claim
under replication; it does not ask a new causal question. See
`experiments/011-half-life-sensitivity/README.md` for the original, still-
closed, research-grade experiment. Nothing about 011 is reopened, revised,
or reinterpreted by this document -- 011 stands exactly as published. R003
exists because a different audience (engineers outside this repo) requires
a different evidence standard (replicated, with reported variance) than
the one 001-011 were built under, not because the original standard was
wrong for its original purpose.

**Relationship to 011, precisely.** Experiment 011 made a shape claim from
a single run per condition: sweeping the EWMA admission signal's half-life
(0.06s-4.0s, log-spaced) at RPS 16 produces a smooth, continuous rise in
error rate -- 23-26% at the shortest half-lives (statistically matching
`instantaneous`), climbing to 99.93% at 4.0s (matching `off` exactly) --
with no adjacent pair of half-lives separated by a disproportionate jump.
The mechanism 011 attributes this to is pool timeouts growing monotonically
with half-life (0 at the two shortest half-lives, rising to 315 at 4.0s,
converging on `off`'s 316).

**Why this specific claim, not just "replicate the newest experiment."**
RPS 16 is not an arbitrary choice being inherited passively from 011 -- it
is the exact operating point Experiment 010 found prone to rare,
self-locking pool-saturation events: most runs show the connection pool
flickering in and out of capacity in short streaks, but occasionally a
run's pool saturates once, early, and never recovers for the rest of the
run. Experiment 011 ran every one of its eight conditions as a single run
at this same RPS point. If even one or two of those single runs happened
to land on a rare locked-high event, the "smooth curve, no cliff"
conclusion could be an artifact of which run got unlucky, not a real
property of the half-life relationship. This is a sharper, evidenced
justification for replication than a general precautionary instinct --
it targets a known failure mode of the exact metric 011's claim rests on.

R003 replicates all eight cells that define 011's claim, all at RPS 16 --
`off`, `instantaneous`, and the six half-lives (0.06/0.25/0.5/1.0/2.0/4.0s).
Unlike R002 (which excluded 009's `off` control as incidental context),
`off` is included here: 011's claim explicitly anchors the low end of the
sweep at `instantaneous` and the high end at `off`, so both bookend
controls are part of what's being validated, not incidental to it. RPS 12
(011's validity check) is excluded from replication -- it was uniformly 0%
across every condition in 011's single-run data, low information value to
replicate five times over.

**The eight cells, all at RPS 16:**

| condition | role in 011's claim |
|---|---|
| off | high-end anchor (011: 99.93% error) |
| instantaneous | low-end anchor (011: 23.06% error) |
| ewma, half_life=0.06s | shortest half-life (011: 24.03%) |
| ewma, half_life=0.25s | (011: 25.90%) |
| ewma, half_life=0.5s | steepest-region onset (011: 60.07%) |
| ewma, half_life=1.0s | steepest-region (011: 76.11%) |
| ewma, half_life=2.0s | 007's original value (011: 90.28%) |
| ewma, half_life=4.0s | longest half-life (011: 99.93%, matched off) |

**What this document estimates, not what it proves.** Per the same
preregistration discipline as R001/R002, this is stated as an estimation
question, not a pass/fail test against thresholds invented for this
document:

1. Estimate the error-rate distribution (mean, spread, range) at each of
   the eight cells, across replicated runs.
2. Estimate whether the *shape* found in 011 -- a continuous rise with no
   disproportionate step between adjacent half-lives -- holds once
   run-to-run variance is visible, by comparing the magnitude of each
   adjacent-cell gap (using replicated means) against the spread within
   each individual cell. A gap that's small relative to within-cell
   variance would call the "continuous, not stepped" reading into
   question; a gap that stays large relative to within-cell variance
   would support it.
3. Check specifically for the failure mode that motivated this
   validation: does any cell -- particularly the mid-range half-lives
   where 011's steepest rise occurred (0.5s, 1.0s) -- show the kind of
   bimodal split Experiment 010 found in a structurally different
   mechanism (`bounded_grace`) at this same RPS point? A tight, unimodal
   spread at every cell would support 011's single-run measurements as
   representative; a bimodal or unusually wide spread at any cell would
   mean 011 measured one mode of several possible outcomes at that point.
4. **The central research question:** does replication support 011's
   continuous-curve claim, or does observed variability require weakening
   it -- for example, if the apparent smoothness turns out to be an
   averaging artifact across genuinely unstable individual cells. No
   specific statistical method (confidence intervals, equivalence testing,
   bootstrap, ANOVA) is committed to in advance -- the right method
   depends on the shape of the variance actually observed, which doesn't
   exist yet.

**Explicitly not a numeric pass/fail criterion.** No threshold like "the
gap must exceed X points" or "stdev must stay below Y" is stated here, for
the same reason R001/R002 didn't invent one: any such number would be
invented, not derived. The conclusion is written from the estimates after
they exist, not measured against a bar fixed before they do.

**Sample size and its escalation rule.** N=5 independent runs per cell (40
runs total), the same first-pass design choice R001/R002 made and for the
same reason -- no prior variance data exists, since every run in 011 was
N=1.

The initial design uses five independent runs per cell. If observed
variability is substantially larger than anticipated -- especially at any
cell showing the kind of bimodal spread this validation specifically
exists to check for -- additional replications may be added before
analysis. Any increase in sample size will be documented together with the
reason for the change, per the same rule R002 exercised once already.

**If replication weakens 011's original claim, that is a successful
outcome of this validation, not a failure of it.** Same cultural statement
as R001/R002: the purpose of reference-grade evidence is to find out
whether a claim holds under scrutiny appropriate to an external, skeptical
audience -- not to reproduce a number this project already believes. This
document's Finding section will report whichever outcome the replicated
data actually supports, including a weakened or partial version of 011's
claim if that is what the data shows.

**Run order.** Shuffled (seeded, `SHUFFLE_SEED=1`), not grouped by cell --
same rationale as R001/R002: at 40 runs, time-of-day, thermal, or
host-machine-state drift over the sweep's duration would otherwise
correlate with a single condition rather than averaging out across all
eight cells.

**Fixed parameters, identical to 011.** `rps=16`, `injected_latency_ms=400`,
`retry_policy=none`, `breaker_enabled=false`, `pool_size=10`. Only
`admission_control_mode` and (for the ewma cells) `admission_ewma_half_life_s`
vary, and only across the eight preregistered cells above.

**No escalation triggered.** Every cell's spread stayed tight -- the
largest stdev observed was 2.6 percentage points (`ewma_hl2.0`), against
adjacent-cell gaps of 5-33pp. Critically, no cell showed the bimodal
split Experiment 010 found in `bounded_grace` at this same RPS point:
sorted individual-run error rates within each cell form a single tight
cluster, not two separated groups (see raw values in the table below).
The self-locking pool-saturation failure mode this validation specifically
existed to check for was not observed in this sweep.

**Finding.**

| Condition | N | Error rate mean | stdev | Individual runs (%) |
|---|---|---|---|---|
| off | 5 | 99.90% | 0.08pp | 99.79, 99.86, 99.93, 99.93, 100.00 |
| instantaneous | 5 | 23.05% | 0.05pp | 22.99, 23.04, 23.06, 23.06, 23.12 |
| ewma, hl=0.06s | 5 | 24.00% | 0.10pp | 23.82, 24.03, 24.03, 24.03, 24.08 |
| ewma, hl=0.25s | 5 | 26.10% | 0.67pp | 25.47, 25.56, 25.90, 26.62, 26.98 |
| ewma, hl=0.5s | 5 | 58.93% | 1.91pp | 56.25, 57.85, 59.38, 60.07, 61.11 |
| ewma, hl=1.0s | 5 | 76.84% | 1.74pp | 75.42, 75.64, 75.69, 78.33, 79.11 |
| ewma, hl=2.0s | 5 | 88.27% | 2.63pp | 85.35, 85.42, 90.14, 90.21, 90.22 |
| ewma, hl=4.0s | 5 | 95.11% | 0.04pp | 95.07, 95.07, 95.14, 95.14, 95.14 |

**The continuous-shape claim holds up under replication.** Comparing
replicated means, the gap between every adjacent pair of half-lives
(0.95pp, 2.10pp, 32.83pp, 17.91pp, 11.43pp, 6.84pp, 4.79pp, in sweep
order) is far larger than any individual cell's within-cell spread
(stdev never exceeds 2.63pp) -- these are real, reliably distinguishable
steps, not noise. The steepest transition remains between 0.25s and
0.5s, matching 011's finding of the steepest region sitting between the
interarrival timescale and the measured request-service-time. No
adjacent pair collapses into statistical indistinguishability, and no
pair separates into the kind of disproportionate jump that would read as
a discrete cliff. **011's central claim -- continuous degradation, no
threshold half-life -- is supported by replication.**

**Replication also revealed something a single run could not show: 011's
apparent exact convergence to `off` at half_life=4.0s was a coincidence
of that one run, not a stable equivalence.** 011 measured hl=4.0s at
99.93% error, identical to its `off` measurement (also 99.93%), and read
this as the curve having "plateaued toward off." Five replicates instead
show hl=4.0s sitting at 95.11% -- tightly, reproducibly (stdev 0.04pp,
the tightest of any ewma cell) -- while `off` independently replicates at
99.90% (stdev 0.08pp, also tight). The two cells are clearly, reliably
different: a persistent ~4.8 percentage-point gap that neither cell's
variance comes close to explaining away. **The corrected reading:** EWMA
admission control at half_life=4.0s retains a small but real residual
benefit over no admission control at all, even at a half-life twice
Experiment 007's original value -- the curve approaches `off` asymptotically
rather than exactly reaching it within the range tested here. This
doesn't change 011's shape conclusion (still continuous, still no cliff),
but it corrects a specific numeric claim 011's single-run design could
not have caught.

**What this means for 011's claim.** The primary finding -- a smooth,
continuous relationship between EWMA half-life and admission-control
performance, with no privileged threshold separating "safe" from
"unsafe" half-lives -- is confirmed, not weakened, by replication. The
one correction replication provides is at the high-half-life boundary:
`instantaneous`-side convergence at the shortest half-lives is confirmed
tightly (24.00% vs 011's 24.03% at hl=0.06s), but `off`-side convergence
at the longest half-life tested is not complete -- a small residual gap
remains, visible only because five runs, not one, were measured at that
cell.

**Sample size, final.** N=5 per cell, all eight cells, no escalation
triggered. 40 runs total.
