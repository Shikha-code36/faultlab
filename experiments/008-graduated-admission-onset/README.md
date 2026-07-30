# Experiment 008 -- Graduated admission onset vs. hard threshold

**Status.** closed (inconclusive on the primary hypothesis; see Finding)

**Phase II working thesis.** Capacity determines *where* saturation
occurs (Experiment 005). Arbitration determines *how* saturation
manifests (Experiment 006), and that "how" itself decomposes into
independent causal properties: Experiment 006 established *location*
(server-side vs. client-side), Experiment 007 established *information
freshness* (instantaneous vs. trailing signal) as one such property.
Experiment 008 tests a third, orthogonal property of arbitration:
*decision-rule shape*.

**Question.** Experiments 006 and 007 both used the same decision rule --
a hard threshold, reject iff utilization >= 1.0 -- and varied only where
that rule runs and how fresh its input is. Every experiment from 001
through 007 has shown a sharp discontinuity at the collapse boundary,
regardless of those two properties. Does the discontinuity come from the
rule itself being a step function, or is it a more fundamental property
of this architecture that no admission rule removes? Concretely: does
replacing the hard threshold with a rule whose rejection probability
ramps smoothly as utilization approaches capacity reduce the jump at the
collapse boundary, holding location, information source, and capacity
fixed at Experiment 006's values?

**Hypothesis.** If a graduated onset produces a smoother error-rate curve
across the RPS sweep than Experiment 006's hard threshold -- specifically
a smaller jump at the collapse boundary -- decision-rule shape is an
independent causal factor in arbitration, distinct from both location and
freshness. If graduated onset produces a curve statistically
indistinguishable from 006's, the discontinuity is not attributable to
the rule's shape, and the step function was never the source of the jump
in the first place.

**Success does not require graduated admission to outperform the hard
threshold.** The purpose of this experiment is to determine whether
decision-rule continuity is itself a causal determinant of overload
behavior -- not to produce a smoother curve by construction. Either
outcome in the hypothesis above is a finding. `u_low = 0.8` and the
linear ramp are fixed once implementation begins; if the result surprises
us, that is the result, not a cue to adjust the ramp until it looks
better.

**Why this is a distinct mechanism, not a variation on 007.** 007 varied
the *temporal character* of the input to an otherwise identical rule
(reject iff [signal] >= 1.0). 008 holds the input character fixed
(instantaneous, matching 006 exactly -- deliberately not reusing 007's
EWMA, so this experiment isolates rule shape alone rather than
compounding it with freshness) and instead varies the *rule itself*: from
a step function to a continuous ramp. Location, information source, and
capacity are all held at Experiment 006's values on purpose, so any
difference observed is attributable only to how the rule turns a
utilization reading into an admit/reject decision.

**The rule.** A linear ramp between two utilization bounds:

```
p_reject(u) = 0                          for u <= u_low
p_reject(u) = (u - u_low) / (1.0 - u_low) for u_low < u < 1.0
p_reject(u) = 1                          for u >= 1.0
```

`u_high` is fixed at exactly `1.0` -- the same "full" threshold 006 and
007 both use, so this comparison isn't also silently redefining what
"saturated" means. `u_low` is the new parameter this experiment
introduces (see below).

**Why linear, from first principles -- not because it's the standard RED
shape.** 006's rule is a step function: a discontinuity at u = 1.0. 008's
manipulated variable is *continuity itself* -- does removing that
discontinuity change collapse shape -- the same kind of single-property
isolation 007 used for freshness. To isolate that as cleanly as possible,
the replacement rule should be the simplest function that is continuous
and monotonic between the two endpoints the experiment already requires
(`u_low`, and `u_high = 1.0`), introducing no further parameters beyond
those two. A straight line is the unique function fully determined by two
endpoints, with zero added degrees of freedom. Any curved alternative
(sigmoid, quadratic, power-law) would need at least one more shape
parameter, which would itself need principled derivation -- the same
reasoning 007 used to prefer EWMA's single decay constant over a sliding
window's two parameters. Linear is chosen because it adds nothing beyond
what the experiment already needs to define, not because of external
convention. Ramp-shape sensitivity (curved vs. linear) is a natural
follow-on once we know whether continuity matters at all -- not this
experiment's job.

**Deriving bounds for `u_low` from measured system properties, then
choosing a value within them -- the same philosophy as 007's half-life.**
This experiment introduces one new parameter, `u_low`, and it should be
constrained by evidence that exists independent of this experiment's own
results, exactly as 007's half-life was bounded by request-service-time
and warmup-convergence facts already on record before 007 ran.

The relevant fact here is Little's Law applied to a quantity this project
has already measured repeatedly: request service time at 400ms injected
latency has been ~806-808ms, consistently, in every experiment since 002.
Under Little's Law, expected steady-state work-in-flight at offered load
`R` is `L(R) = R x T`. At `RPS = 12` -- the established below-boundary
control point used since Experiment 002 -- with `T ~= 0.807s`:
`L(12) ~= 9.68`, i.e. an *expected* utilization of roughly `0.97` against
`pool_max_size = 10`.

This is an uncomfortable, useful a priori fact, not a convenient one: RPS
12 is not comfortably below saturation, it is close to the knee already.
It's also consistent with something already on record -- `b_pool_active_max`
reaching `10` even at RPS 12 has been documented since Experiment 005 as
this system running near its capacity boundary at the established "safe"
RPS, not with slack to spare. The honest conclusion is that this
architecture leaves only a narrow region between normal operation and
saturation for any graduated onset to occupy -- a property of the system,
established before 008 runs, not something to widen for this
experiment's convenience.

**What this calculation does and does not do.** It establishes that
`u_low` must sit comfortably below `1.0` to avoid clipping into RPS 12's
near-saturated operating range, and that the available room to do so is
narrow. It does not uniquely determine a value. Consistent with how
Experiment 007 treated its half-life -- derived bounds, then a stated
design choice within them, not a mathematically optimized output --
**`u_low = 0.8`** is chosen here as a documented design choice: enough
margin below the ~0.97 Little's-Law estimate for RPS 12 to make
premature shedding unlikely, while staying as close to the boundary as
that constraint plausibly allows.

**The RPS-12 control run validates this choice; it does not define it.**
Mirroring every prior admission experiment's validity check: if
`graduated`'s `admission_rejection_rate` at RPS 12 comes back meaningfully
above ~0%, that is evidence `u_low = 0.8` was set too low for this system
and the design choice needs revisiting -- a falsifiable check applied
*after* the value was fixed, not the value's source.

**Primary variable.** `admission_control_mode`: `off` / `instantaneous`
(Experiment 006's rule, re-run as a same-session control -- the
admission-gate code is touched again for this experiment, the same
internal-validity reasoning 007 used for not reusing 006's historical
numbers) / `graduated` (this experiment's mechanism).

**Fixed parameters.** `pool_size=10`, `retry_policy=none`,
`breaker_enabled=false`, `injected_latency_ms=400`, information source =
instantaneous pool utilization (not EWMA), server-side location (Service
B). RPS swept at `12, 14, 16, 18`, the same boundary used since
Experiment 002.

**Evidence model: per-request logging, not just aggregate counts.** 007's
Gate 1 could be checked from existing aggregate columns because the claim
was about a single trailing value converging correctly. 008's Gate 1 is a
claim about a *relationship* -- does empirical P(reject) actually track
the intended ramp as a function of utilization at decision time? Per the
project's evidence-model principle, this calls for the minimum additional
evidence the phenomenon actually requires: not a full time-series (the
question isn't temporal), but a per-request record of
`(pool_active_at_decision, rejected)`, bucketed post-hoc into an empirical
rejection-probability-vs-utilization curve and compared against the
intended linear ramp.

**A methodology note specific to this experiment: `graduated` is the
first stochastic mechanism in this project.** 003, 006, and 007's rules
were all deterministic given system state; a graduated rule admits
randomness by design. That weakens the single-run-per-condition
convention specifically here -- a single run's empirical rejection curve
now carries sampling noise the deterministic mechanisms never did. This
experiment still uses one run per condition, consistent with every prior
experiment (001-007) and the project's deliberate decision to keep the
replication question separate from individual experiments' scientific
questions -- but Gate 1's empirical-vs-intended curve comparison exists
specifically to check whether that one run was representative enough to
trust, rather than silently assuming determinism that no longer holds.

**What determines the result.**
1. **Gate 1 (model fidelity)** -- does the empirical rejection-probability
   curve (from per-request `pool_active_at_decision` / `rejected` logging)
   match the intended linear ramp between `u_low=0.8` and `1.0`? A
   precondition for trusting the comparison, not itself a measure of
   which mode is "better."
2. **Validity check, mirroring every prior admission experiment** -- at
   RPS 12, `admission_rejection_rate` should be ~0% for both
   `instantaneous` and `graduated`. For `graduated` specifically, this is
   also the a posteriori check on the `u_low = 0.8` design choice
   described above.
3. **Gate 2 (utilization efficiency)** -- does `graduated` achieve
   completed work / pool utilization comparable to `instantaneous` at each
   saturated RPS, or does smoothing the onset leave capacity idle?
4. **The actual comparison** -- does `graduated` reduce the largest local
   jump in error rate across the RPS sweep relative to `instantaneous`
   (supporting decision-rule shape as an independent causal factor), or is
   the curve statistically indistinguishable from 006's step-function
   result (supporting that the discontinuity is not attributable to rule
   shape)?

**Documented limitations.**
- `u_low = 0.8` is a stated design choice within Little's-Law-derived
  bounds, not a mathematically optimized value -- see above. Sensitivity
  to `u_low` is a natural follow-on, not this experiment's job.
- Ramp shape is fixed as linear, not swept -- see above. Curved
  alternatives are a natural follow-on once continuity itself is shown to
  matter.
- Single run per condition, consistent with every experiment so far
  (001-007) -- replication remains a project-level methodology question.
  Gate 1's curve-fidelity check is this experiment's own internal
  mitigation for the added stochasticity, not a substitute for that
  broader question.
- Fairness between requests remains out of scope, as in every prior
  experiment: the load generator produces undifferentiated requests.

**Finding.**

This experiment separates two questions that are easy to conflate:
whether it was *built* as specified (implementation validity), and
whether its *design assumptions held* (hypothesis validity). The first is
confirmed; the second is not, and that distinction is itself the result.

**Gate 1 (model fidelity) passed cleanly.** The empirical
rejection-probability-vs-utilization curve, from the per-request decision
trace, matches the intended linear ramp almost exactly at every
utilization level observed, across all four RPS:

| pool_active | u | intended P(reject) | empirical P(reject) (range across RPS 12-18) |
|---|---|---|---|
| ≤7 | ≤0.7 | 0.000 | 0.000 |
| 8 | 0.8 | 0.000 | 0.000 |
| 9 | 0.9 | 0.500 | 0.497-0.525 |
| 10 | 1.0 | 1.000 | 1.000 |

There is no implementation bug. `GraduatedAdmission` does exactly what
`admission.py` specifies.

**The RPS-12 validity check failed -- not because of a bug, but because a
preregistered design assumption turned out to be false.** The assumption
was that `u_low = 0.8` -- chosen with a margin below the Little's-Law
estimate of `L(12) ≈ 9.68` (u ≈ 0.97) -- would stay inactive at RPS 12,
the established below-boundary control point. It didn't:
`admission_rejection_rate` at RPS 12 was 9.07% under `graduated`, versus
0% for both `off` and `instantaneous`. The decision trace shows why: even
at RPS 12, the pool spends a real fraction of its time at `pool_active=9`
(u=0.9, inside the ramp), not just at or below `pool_active=8`. This is
the same "narrow room" risk the README's Little's-Law analysis flagged
*before* this experiment ran -- it just turned out to be sharper than the
chosen margin accounted for. Per the project's methodology (see
[[feedback_no_post_hoc_tuning]] in memory), `u_low` was not adjusted after
seeing this; the run stands as executed against its preregistered design.

| RPS | off (error%) | instantaneous (error%) | graduated (error%) |
|---|---|---|---|
| 12 | 0% | 0% | 9.07% |
| 14 | 99.8-100% | 16.7% | 23.0% |
| 16 | 99.9-100% | 23.0% | 28.8% |
| 18 | 99.9% | 33.3% | 37.6% |

At every RPS, error is accounted for almost entirely by clean rejections,
not pool timeouts (`b_pool_timeout_count = 0` for `graduated` at every
RPS, matching `instantaneous`'s failure mode from both 006 and this
experiment, not 007's EWMA-induced timeout failure mode).

**The primary hypothesis is confounded, not answered.** `graduated`
differs from `instantaneous` in two ways simultaneously, not one:
decision-rule continuity (the intended variable) *and* an effectively
earlier onset, since the ramp is already admitting rejections below the
established collapse boundary where `instantaneous` admits none. A higher
error rate under `graduated` at RPS 14-18 cannot be attributed to
continuity alone -- it's equally explained by `graduated` simply shedding
more total load, starting from a worse (non-zero) baseline. This
experiment cannot distinguish those two explanations, and does not claim
to.

**Confirmed:**
- The probabilistic controller behaves exactly as designed (Gate 1).
- Little's Law correctly identified that this system has limited
  pre-collapse slack at RPS 12 -- the direction of the risk was
  anticipated a priori, even though the specific margin chosen wasn't
  sufficient.
- The system's actual operating point at RPS 12 is closer to saturation
  than the chosen design margin assumed.

**Not answered:**
- Whether decision-rule continuity, in isolation, changes collapse shape.
  The preregistered onset entered the control region, confounding this
  experiment's primary variable with an unintended second one.

**Next step.** Not a revision of this experiment and not a discarded run.
A future experiment, separately preregistered with its own onset
parameter derived to leave a larger empirical margin below RPS 12's
observed utilization distribution (now directly measurable from this
experiment's own decision traces, rather than only from Little's Law's
mean-field estimate) -- isolating continuity cleanly, the way this one
intended to. Tracked in [[phase2_roadmap]] as future work, not scheduled
yet.
