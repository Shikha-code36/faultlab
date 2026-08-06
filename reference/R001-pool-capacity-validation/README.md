# R001 -- Reference-grade validation of Experiment 005's pool-capacity linearity claim

**Status.** closed

**Evidence grade.** reference -- this validates a specific prior claim
under replication; it does not ask a new causal question. See
`experiments/005-connection-pool-capacity/README.md` for the original,
still-closed, research-grade experiment. Nothing about 005 is reopened,
revised, or reinterpreted by this document -- 005 stands exactly as
published. R001 exists because a different audience (engineers outside
this repo) requires a different evidence standard (replicated, with
reported variance) than the one 001-009 were built under, not because the
original standard was wrong for its original purpose.

**Relationship to 005, precisely.** Experiment 005 made two claims from a
single run per condition:

1. The collapse boundary scales linearly with pool size across a 4x
   range (10, 20, 40), with two ratios holding exactly: last-clean-RPS /
   pool_size = 1.2, and first-collapse-RPS / pool_size = 1.4.
2. The collapse stays equally sharp at every pool size -- error rate
   near-zero at the clean edge, near-total at the collapse point --
   rather than softening as pool size grows.

R001 replicates only the six specific `(pool_size, rps)` cells that
define those two ratios -- not 005's full 15-run Phase A sweep. The
interior bracket points (16/18, 32/36, 64/72) established that collapse
persists past the boundary but were never load-bearing for the linearity
claim itself; replicating them would widen scope without strengthening
the specific claim this document validates. This mirrors the project's
existing evidence-model principle: add the minimum additional evidence a
claim actually needs, not evidence for its own sake.

**The six cells:**

| pool_size | rps | role in 005's claim |
|---|---|---|
| 10 | 12 | clean edge |
| 10 | 14 | collapse point |
| 20 | 24 | clean edge |
| 20 | 28 | collapse point |
| 40 | 48 | clean edge |
| 40 | 56 | collapse point |

**What this document estimates, not what it proves.** Per the same
preregistration discipline as every experiment since 007, this is stated
as an estimation question, not a pass/fail test against thresholds
invented for this document:

1. Estimate the error-rate distribution (mean, spread, range) at each of
   the three clean-edge cells, across replicated runs.
2. Estimate the error-rate distribution at each of the three collapse
   cells, across replicated runs.
3. Describe, from those estimated distributions, whether the clean-edge
   and collapse populations remain clearly separated at every pool size
   -- i.e., whether the sharp, binary character of the collapse that a
   single run suggested holds up once run-to-run variance is visible for
   the first time.
4. **The central research question:** does replication support the claim
   that the two boundary ratios (1.2 and 1.4) are consistent across pool
   sizes, or does the observed variability require weakening the
   original "exactly linear, no curvature" conclusion? No specific
   statistical method (confidence intervals, equivalence testing,
   bootstrap, ANOVA) is committed to in advance -- the right method
   depends on the shape of the variance actually observed, which doesn't
   exist yet. Choosing one now would be choosing blind.

**Explicitly not a numeric pass/fail criterion.** No threshold like
"error rate must stay under X%" or "distributions must be separated by
at least Y points" is stated here, because no such number would be
justified by anything external to this document -- it would be invented,
not derived, exactly the kind of design choice this project has
consistently avoided making just because it "feels right." The
conclusion is written from the estimates after they exist, not measured
against a bar fixed before they do.

**Sample size and its escalation rule.** N=5 independent runs per cell
(30 runs total), stated as a first-pass design choice, not a
power-calculated sample size -- no prior variance data exists to
calculate power from, since every run in 005 was N=1. This is the
minimum replication that produces a real spread (not just two data
points) for the first time at each cell.

The initial design uses five independent runs per cell. If observed
variability is substantially larger than anticipated, additional
replications may be added before analysis. Any increase in sample size
will be documented together with the reason for the change.

**If replication weakens 005's original claim, that is a successful
outcome of this validation, not a failure of it.** The purpose of
reference-grade evidence is to find out whether a claim holds under
scrutiny appropriate to an external, skeptical audience -- not to
reproduce a number this project already believes. A methodology that is
only willing to publish confirmations isn't a methodology; it's
marketing. This document's Finding section will report whichever outcome
the replicated data actually supports.

**Fixed parameters, identical to 005.** `injected_latency_ms=400`,
`retry_policy=none`, `breaker_enabled=false`, `enable_arrival_trace=false`.
Only `pool_size` and `rps` vary, and only across the six preregistered
cells above.

**Finding.**

**What this document does and does not show.** R001 does not
independently re-estimate the collapse boundary or re-derive the 1.2 and
1.4 ratios -- it intentionally replicates the six operating points 005
already identified, rather than searching for new ones. The ratios are
therefore unchanged *by construction*, not by discovery: replicating the
same discrete RPS values 005 used cannot, on its own, confirm or refute
where the boundary sits. What R001 actually tests is a different and, in
some ways, more useful question: is the behavior at those specific
points real and stable, or could 005's single run per condition have
been an artifact of one lucky (or unlucky) execution?

**The result: remarkably stable.** Across all 15 clean-edge runs (5 each
at pool sizes 10, 20, and 40), error rate was exactly 0.00% -- every
single time, no exceptions:

| Cell | n | Mean error | Stdev | Range |
|---|---|---|---|---|
| pool=10, rps=12 | 5 | 0.00% | 0 | [0.00%, 0.00%] |
| pool=20, rps=24 | 5 | 0.00% | 0 | [0.00%, 0.00%] |
| pool=40, rps=48 | 5 | 0.00% | 0 | [0.00%, 0.00%] |

Across all 15 collapse-point runs, error rate stayed tightly clustered
near-total, with sub-percentage-point spread at every pool size:

| Cell | n | Mean error | Stdev | Range |
|---|---|---|---|---|
| pool=10, rps=14 | 5 | 99.86% | 0.066pp | [99.76%, 99.92%] |
| pool=20, rps=28 | 5 | 99.89% | 0.095pp | [99.76%, 100.00%] |
| pool=40, rps=56 | 5 | 99.74% | 0.066pp | [99.68%, 99.84%] |

**The escalation rule was not triggered.** This document's preregistered
design committed to adding replicates if observed variability turned out
substantially larger than anticipated. It didn't -- if anything, the
variance observed is smaller than a first pass would typically expect.
No additional replicates were run.

**What this supports, precisely.** The clean-edge and collapse
distributions remain about as separated as two distributions can be --
one pinned at exactly zero, the other pinned near-total, at every pool
size tested -- giving measured confidence that 005's single-run
observations were not artifacts of one lucky execution. This is a
narrower and more defensible claim than "005 was proven right": R001
strengthens confidence in the *stability of the behavior* 005 reported,
without independently testing where the boundary itself sits or whether
the 1.2/1.4 ratios would survive a fresh, undirected search. Testing
that would require a differently-designed study -- one that searches for
the boundary at each pool size rather than replicating a boundary
already found.

**A secondary observation, not to be overstated.** This is the first
time SlimyBug has subjected one of its own conclusions to a higher
evidence standard than the one it was originally produced under. In that
narrow sense, R001 is validating something about the project's
methodology as much as it is strengthening confidence in Experiment 005
specifically -- the single-run research-grade process didn't produce a
number that fell apart under replication. That is worth noting as a
milestone; it is not a claim that every research-grade finding in this
project would hold up equally well, and no such generalization is made
here.
