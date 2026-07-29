# Experiment 006 -- Server-side admission control

**Status.** open

**Question.** Experiment 003 showed a *client-side* breaker (Service A
inferring Service B's health from aggregate failure history) cuts load
reaching Service B and improves client-visible success. Service B itself
has no self-protection -- when saturated, every request blocks on
`pool.acquire(timeout=2.0)` and they all collectively time out together,
which is the mechanism behind the ~100% error cliff in every prior
experiment. Does giving Service B its own admission control -- rejecting
excess requests before they ever attempt to acquire a connection --
behave differently from Service A's breaker, given it has direct
knowledge of the resource's own state rather than reconstructing that
state after failures accumulate?

**Mechanism.** A gate in `services/service-b/app/main.py`'s `/work`
handler, checked *before* `pool.acquire()` is ever called: if
`pool.get_size() - pool.get_idle_size() >= POOL_MAX_SIZE` (no idle
connections), reject immediately with a 503 and record it as a distinct
`admission_rejected` outcome. If a connection may be available, proceed
to `pool.acquire(timeout=2.0)` exactly as in every prior experiment --
admitted requests experience no change to the pool's own queueing
behavior. Default off (`ADMISSION_CONTROL_ENABLED=false`), so Experiments
001-005 are unaffected and this is a true no-op when disabled: the entire
check is skipped, not a threshold set to always-admit.

**Why this signal, not a proxy.** The gate condition is not a heuristic
correlated with saturation -- it is the exact criterion every experiment
since 001 has used to define saturation (`pool_active_max >= pool_size`
in `faultlab/analysis.py`), expressed in the same units as the resource's
own capacity limit. Necessity: it triggers exactly when, and only when,
admitting the request would force it to wait -- a proxy like in-flight
request count could reject a request that would have found a free
connection, or admit one that then waits anyway, reintroducing the exact
collapse this experiment tests whether admission control prevents.
Sufficiency: for the comparison against Experiment 003 to isolate
something meaningful, Service B's decision needs to be as close to
perfect information as the architecture allows -- otherwise a result
favoring 006 over 003 could mean "our proxy was more accurate than their
proxy," not "server-side decisions outperform client-side ones." Tying
the signal directly to the literal resource removes that confound.

**Why this is admission control and not a queueing-policy change.** An
earlier draft of this experiment considered implementing the mechanism as
`pool.acquire(timeout≈0)` -- shortening the pool's own wait rather than
gating ahead of it. That's a different experiment: `acquire()` *is* the
pool's queueing mechanism, so changing its timeout changes the resource's
own arbitration policy (an extreme, zero-length-queue policy), not a
decision made upstream of it. This design keeps `acquire()`'s timeout at
its existing 2.0s, untouched, for every admitted request. The queueing-
policy question (should the pool's own wait behavior change, e.g. bounded
queueing) is deliberately left to a future experiment.

**Is decision locus separable from information quality here?** No, and
that's stated as part of the hypothesis rather than treated as a flaw.
Service A has exactly one way to learn Service B's pool state: through
the outcomes of requests it has already sent -- necessarily retrospective
and delayed by at least a network round trip. Service B has direct,
local, zero-latency access to its own resource's state. In this
architecture, "server-side" *entails* direct/instantaneous information
and "client-side" *entails* indirect/delayed information -- they cannot
be varied independently without building a mechanism neither 003 nor 006
actually represents (e.g. giving Service A synchronous access to Service
B's exact state through a side-channel, which is a different, more
artificial question, out of scope here). The independent variable is
**decision locus**; information quality is a structural consequence of
locus in this architecture, not a second, separately-manipulated factor.
If 006 outperforms 003, the supportable claim is "server-side placement --
which here inherently comes with direct, instantaneous information --
outperforms client-side inference," not "location matters independent of
information quality."

**Primary variable.** `admission_control_enabled` (off / on).

**Fixed parameters.** `pool_size=10`, `retry_policy=none`,
`breaker_enabled=false` (isolates this mechanism from Experiment 003's,
the same discipline 003 used against Experiment 002's retries),
`injected_latency_ms=400`. RPS swept at `12, 14, 16, 18` -- the exact
boundary Experiments 002/003/004 established, so results land on the same
axis as Experiment 003's table for direct comparison.

**Internal validity: a same-session control, not reused historical data.**
The natural comparator is Experiment 003's breaker-off condition, but the
codebase has changed since 003 ran (the Runner refactor, the arrival-trace
instrumentation added in 004, and more) -- reusing that historical data
as this experiment's "no protection" baseline would risk conflating
"does admission control help" with "did anything else about the system
drift since 003's data was collected." Experiment 005 guarded against the
same risk by re-running its own pool=10 control rather than trusting an
assumed baseline. Accordingly, the matrix below includes its own
`admission_control_enabled=False` condition at all four RPS points,
collected in the same session as the `=True` condition. Experiment 003's
historical numbers are used only as contextual reference, not as the
actual control this experiment's comparison depends on.

**Measurement validity: distinguishing "reached Service B" from
"attempted the pool."** In Experiment 003, the breaker decides at Service
A, so breaker-on genuinely reduces the number of requests that reach
Service B at all. In this experiment, *every* request still reaches
Service B's HTTP handler -- the gate only decides whether it may attempt
`pool.acquire()`. So `b_received_count` (originally "requests reaching B")
is redefined here to mean *requests that attempted pool acquisition* --
the actual analog of what Experiment 003's breaker prevented from
reaching B -- and a new field, `b_admission_rejected_count` (plus its own
p95 latency, `b_admission_rejected_latency_p95_ms`), tracks rejections as
a distinct, first-class outcome rather than folding them into generic
error counts. `admission_rejection_rate` (in `faultlab/runner.py`'s
`summarize_app_metrics`) is rejections as a fraction of everything that
reached Service B (rejected + pool-attempted), giving a direct read on
how much demand was shed at the door.

**What determines the result.**
1. **Rejected-request latency** (`b_admission_rejected_latency_p95_ms`) --
   expected near-instant, mirroring Experiment 003's short-circuited
   requests resolving in well under a millisecond, confirming genuine
   fail-fast rather than a different failure mode.
2. **Load actually reaching the pool** (`b_received_count`, redefined
   above) -- expected to stay bounded once admission control is on,
   mirroring Experiment 003's "requests reaching B" reduction.
3. **Validity check, mirroring Experiment 003's "no false positives"
   check** -- at RPS 12 (below the collapse boundary),
   `admission_rejection_rate` should be ~0%. A non-trivial rejection rate
   there would mean the gate is triggering on ordinary contention, not
   genuine saturation, undermining the signal's justification rather than
   just being an unexpected result.
4. **The shape of the transition across RPS 12->18** -- does a server-side
   gate acting on instantaneous local state produce a smoother,
   more-proportional-to-load degradation than the breaker's aggregate,
   trailing-window decision, or does it collapse similarly sharply once
   triggered?

**Documented limitations (not further addressed by this design).**
- **TOCTOU race.** Reading `pool_active` and then calling `acquire()`
  isn't atomic, so under high concurrency two requests could both see one
  free slot and both be admitted, with one briefly waiting. This is a
  microsecond-scale race, not a design choice -- categorically different
  from a deliberately-loose admission threshold, which would be a
  sustained, intentional allowance for queueing.
- **Locus and information quality are bundled**, as argued above -- this
  experiment cannot decompose whether locus alone (absent better
  information) would produce the same effect.
- **Single run per condition**, consistent with every experiment so far
  (001-005) -- no repeated-trial estimate of run-to-run noise.

**Finding.** _TODO: fill in once the experiment is closed._
