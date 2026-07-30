# Experiment 009 -- Bounded admission deferral vs. immediate rejection

**Status.** closed

**Phase II working thesis.** Capacity determines *where* saturation
occurs (Experiment 005). Arbitration determines *how* saturation
manifests, and "how" itself decomposes into independent properties:
decision location (Experiment 006), information freshness (Experiment
007), and decision-rule shape (Experiment 008, inconclusive -- its
preregistered onset parameter entered the control regime, confounding
continuity with earlier admission, so that axis remains open). Experiment
009 tests a fourth, orthogonal property: whether a rejection decision
must be final the instant it's made.

**Question.** Every admission mechanism tested so far (006, 007, 008)
commits its decision the moment the signal is read -- reject means reject,
immediately. Must overload be rejected immediately, or can a single
bounded postponement of the decision -- re-reading the same signal once
more after a short, fixed interval, with no resource queueing involved --
recover requests caught in a momentary blip without reintroducing the
collapse a zero-tolerance policy prevents?

**Hypothesis.** Three distinguishable outcomes, not a single pass/fail:
- If bounded deferral measurably reduces error rate relative to
  Experiment 006's immediate-rejection baseline *without* reintroducing
  pool timeouts (rejections stay clean, the pool never overflows),
  tolerance for transient state is an independent lever in arbitration --
  some immediately-rejected requests were momentary blips a brief
  re-check would have admitted.
- If deferral produces no meaningful difference from immediate rejection,
  the instantaneous `pool_active` reading is already a reliable indicator
  of genuine sustained saturation at this system's timescale, and
  zero-tolerance costs nothing.
- If deferral reduces error rate but the rescued requests simply absorb
  the wait as added latency with no net throughput gain, that is a
  distinct third outcome -- cost redistribution, not cost reduction --
  and is reported as such rather than folded into either of the above.

**The manipulated variable is decision finality, not waiting.** The
naive framing -- "how long should we wait?" -- undersells what actually
changes. Every prior controller observes the signal once and immediately
commits. 009's controller observes, then treats a preliminary *reject* as
provisional rather than final, re-reads the identical signal against the
identical decision rule after a fixed interval, and only then commits.
The wait is a consequence of that reframing, not the mechanism itself.

This is deliberately asymmetric, and the asymmetry is load-bearing, not
incidental: only a preliminary *reject* is provisional. A preliminary
*admit* commits immediately, exactly as in 006-008 -- there is no
re-check that could revoke an admission. If both outcomes were
provisional, this would no longer be "tolerance for transient
saturation"; it would be a different, stranger mechanism with its own
justification burden. Restricting provisionality to the reject branch is
what keeps this a direct, minimal extension of 006's decision rather than
a new one.

**The first and second reads use the identical decision rule against the
identical signal.** Nothing about *what* is being decided changes --
same `pool_active / pool_max_size` reading, same hard threshold from
Experiment 006 (not Experiment 008's graduated rule; stacking an
unresolved rule-shape axis on top of an unresolved finality axis would
confound both). The only thing a reject's provisional status adds is
*when* it becomes final. This also fixes a question someone could
otherwise reasonably ask -- "did the second check become more lenient?"
-- with a clean "no."

**Why this necessarily introduces one cooperative-scheduling point.**
Every controller before this one (`InstantaneousAdmission`,
`EwmaAdmission`, `GraduatedAdmission`) is deliberately synchronous -- no
`await` inside `should_reject()`, stated explicitly in `admission.py` as
an invariant the rest of the codebase's counters rely on. Experiment 009
intentionally changes the temporal structure of the admission decision,
which necessarily introduces one `await asyncio.sleep(...)` between the
initial observation and the final one. This is not an implementation
compromise; it is the experimental consequence of the thing being tested
-- a decision that is no longer instantaneous by construction cannot be
made by code that assumes it always is. Other requests' admission checks
may legitimately interleave with a deferred request's wait; that
interleaving is expected, not a hidden side effect to guard against.

**Why exactly one re-evaluation, not a polling loop.** A single
re-evaluation is the minimum mechanism that can test whether transient
saturation differs from sustained saturation at all: it is a binary test
of whether the contested state resolves within one grace interval or
not. Two or more re-evaluations would turn this into characterizing the
*survival-time distribution* of saturation episodes (does it resolve
within 1x the interval? 2x? 3x?) -- a legitimate but different question,
better answered by analyzing existing snapshot data's saturation-episode
durations directly than by embedding repeated polling into the admission
path. Exactly one re-evaluation is also what keeps the third hypothesis
branch (cost redistribution) measurable at all: with one bounded wait, a
request that is ultimately still rejected pays a fixed, known latency
cost -- exactly the grace interval, no more -- rather than a cost that
varies with how many times a loop happened to spin.

**Deriving bounds for the grace interval from measured constants, then
choosing a value within them -- the same philosophy as 007's half-life
and 008's `u_low`.**
- *Upper bound* -- the interval must stay well below how often new
  requests arrive, or it stops being "a brief second look at one
  contested request" and starts reshaping the arrival/departure dynamics
  themselves (the same kind of capacity-adjacent confound Experiment 005
  already demonstrated). Mean interarrival time across the RPS sweep used
  since Experiment 002 ranges from `1000/12 ≈ 83ms` (RPS 12) down to
  `1000/18 ≈ 56ms` (RPS 18, the tightest case in this matrix). Keeping
  the interval at roughly half of that tightest gap or less bounds it at
  approximately **25-28ms**. (It is trivially far below the ~806-808ms
  per-request service time and the 2.0s `POOL_ACQUIRE_TIMEOUT` too, but
  those bounds are so loose they constrain nothing -- the interarrival
  bound is the one doing real work.)
- *Lower bound* -- the interval must have a non-negligible chance of
  resolving anything. Approximating each of the 10 in-flight connections'
  residual holding time as roughly uniform over the ~806-808ms service
  time consistently measured since Experiment 002 (low variance, so this
  approximation is reasonable), the probability that at least one of 10
  connections frees within a window of length `g` is approximately
  `10 x g / 806`. For that to exceed roughly 15-20% during a genuine
  transient blip, `g` needs to be at least approximately **12-15ms**;
  below that, the mechanism is theoretically present but practically
  inert.
- **`grace_ms = 20`**, comfortably inside `[12, 28]`ms, chosen as a
  documented design choice within these bounds -- not a mathematically
  optimized value, and not adjusted after seeing results, consistent with
  every parameter choice in this project since Experiment 007.

**Primary variable.** `admission_control_mode`: `off` / `instantaneous`
(006's rule, re-run as a same-session control -- the admission-gate code
is touched again for this experiment, the same discipline 007 and 008
both applied) / `bounded_grace` (this experiment's mechanism).

**Fixed parameters.** `pool_size=10`, `retry_policy=none`,
`breaker_enabled=false`, `injected_latency_ms=400`, server-side location
(Service B), instantaneous signal (not EWMA), Experiment 006's hard
threshold as the decision rule for both reads (not Experiment 008's
graduated rule), `admission_grace_ms=20`. RPS swept at `12, 14, 16, 18`,
the same boundary used since Experiment 002.

**Evidence model.** Gate 1 here is not "does the signal converge
correctly" (007) or "does an empirical curve match an intended shape"
(008) -- it's "did the deferral mechanism actually do what it claims for
every provisional reject": exactly one wait of the intended duration,
the same decision rule applied on both reads, and a final outcome that's
attributable to the second read. This requires per-request logging for
every provisional reject: the first-read `pool_active`, the measured
wait duration, the second-read `pool_active`, and the final decision --
richer than 008's `(pool_active, rejected)` pair, because this
experiment's fidelity question is about a two-step process, not a single
decision's shape.

**Documented limitations.**
- `grace_ms = 20` is a stated design choice within derived bounds, not
  swept -- see above. Sensitivity to the interval's duration is a natural
  follow-on once this experiment shows deferral matters at all, not this
  experiment's job.
- Single run per condition, consistent with every experiment so far
  (001-008) -- replication remains a project-level methodology question.
- This is the first admission controller with a cooperative-scheduling
  point inside its decision path -- see above. Interleaving between a
  deferred request's wait and other requests' admission checks is
  expected and is not itself a confound, but it is a documented
  architectural first for this codebase.
- Fairness between requests remains out of scope, as in every prior
  experiment: the load generator produces undifferentiated requests.

**Finding.**

**Implementation validity.** Gate 1 passed: every deferred decision
waited almost exactly the intended interval (mean ~20.1-20.2ms across all
four RPS values, min ~19.1ms, max ~30.8ms -- the upper spread is Windows
timer granularity, anticipated in advance, not a defect), then
re-evaluated the identical signal against the identical rule exactly
once. No polling, no drift.

**Experimental validity.** The RPS-12 validity check passed cleanly:
0.00% error for both `instantaneous` and `bounded_grace`. Unlike
Experiment 008, no premature admission rejection was introduced --
`bounded_grace` never sheds load that 006's rule wouldn't already have
rejected; it only ever defers an *already-provisional* reject, so there
is no mechanism by which it could shed load 006 wouldn't.

**Primary finding.** Near the collapse boundary (RPS 14), bounded
postponement reduced client-visible errors from 16.7% (`instantaneous`)
to 13.1% (`bounded_grace`) because most provisional rejects corresponded
to transient saturation that resolved within one grace interval: of
1,059 deferred decisions at RPS 14, 814 (77%) were ultimately admitted
after the wait.

| RPS | instantaneous error% | bounded_grace error% | deferred decisions | resolved after wait |
|---|---|---|---|---|
| 12 | 0% | 0% | 9 | 0 (0%) |
| 14 | 16.7% | 13.1% | 1059 | 814 (77%) |
| 16 | 22.9% | 23.0% | 573 | 66 (11.5%) |
| 18 | 33.3% | 33.3% | 811 | 3 (0.4%) |

**Regime transition.** As offered load increased from RPS 14 to RPS 18,
the proportion of deferred decisions that resolved fell sharply -- 77%,
then 11.5%, then 0.4% -- and `bounded_grace`'s error-rate curve converged
to `instantaneous`'s until the two were statistically indistinguishable
at RPS 16 and RPS 18. The results indicate that transient-state tolerance
is beneficial near the collapse boundary, but its effectiveness rapidly
diminishes as overload becomes sustained -- RPS 14 and RPS 16-18 are not
competing hypotheses to choose between, but different operating regimes
of the same system, both visible within one preregistered design.

**Cost.** The improvement was purchased through deterministic latency
equal to approximately one grace interval, paid by both rescued and
ultimately-rejected requests. Rejection latency p95 rose from
~0.04-0.06ms under `instantaneous` to ~21-28ms under `bounded_grace` --
every rejection now costs the wait, not just the ones that resolve. At
RPS 14, overall p95 latency rose from ~806ms to ~826ms, almost exactly
the 20ms grace interval, confirming that even admitted-after-wait
requests pay the full deferral as added latency. This is precisely why
exactly-one-re-evaluation mattered: the added cost is fixed and
attributable to the grace interval itself, not to an unbounded or
variable number of retries.

**Conclusion.** Bounded postponement is an independent arbitration
mechanism -- orthogonal to location (006), information freshness (007),
and decision-rule shape (008) -- whose benefit is conditional on
operating near the collapse boundary, where transient saturation
episodes remain common. Unlike 008, this experiment's preregistered
design held under its own validity checks: the mechanism was isolated
cleanly, and both the benefit and its cost are directly measured rather
than inferred.
