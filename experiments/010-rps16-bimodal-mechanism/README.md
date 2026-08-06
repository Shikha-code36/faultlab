# Experiment 010 -- What causes RPS16's bimodal bounded-grace rescue rate

**Status.** closed

**Question.** R002 found that bounded_grace at RPS16 splits into two distinct rescue-rate regimes (~20% vs ~62%) across otherwise-identical replicate runs, invisible to the aggregate error rate. Does a timestamped decision trace show each run settling into one stable mode from the start, a mid-run phase transition, or continuous fine-grained oscillation between modes?

**Hypothesis.** Not a directional hypothesis -- a characterization question, using new per-decision timestamp instrumentation (admission_decision_trace.csv's t_ns field, added this session) not available when R002 was run. No new (condition, rps) cells are compared; this replicates only the single bounded_grace/RPS16 cell already identified as anomalous, at higher time-resolution.

**Primary variable.** admission_control_mode

**Method.** Single cell, replicated: `bounded_grace`, RPS 16, `injected_latency_ms=400`, `retry_policy=none`, `breaker_enabled=false`, `pool_size=10`, `admission_grace_ms=20` — identical to R002's anomalous cell. `enable_admission_decision_trace=True` on every run. New instrumentation: `admission_decision_trace.csv` gained a `t_ns` column (monotonic nanosecond timestamp per decision, added to `services/service-b/app` this session — R002's trace had no way to place a decision in time within a run). Each run's decisions are split into 9 equal-width time buckets across the ~90s measurement window to show rescue rate's shape over time, not just its overall value.

Initial N=10 (matching R002's escalated sample size for this cell). Zero of the first 10 hit R002's ~62% high-mode band — escalated to N=20 per the same discipline as R001/R002 (a characterization question with an unseen shape isn't answered by an unlucky sample), which caught one high-mode run on the 11th.

**Finding.**

**The rescue rate is not two discrete regimes — it's driven by a single underlying mechanism: whether the connection pool's saturation self-resolves quickly or gets stuck.** `deferred` is set exactly when `pool_active >= pool_size` (10) at the first read — verified directly against the trace for representative runs, not inferred. What differs between runs is not the admission logic (identical, hard-threshold, confirmed against `services/service-b/app/admission.py` — see [[r002_status]]'s correction) but how the pool's real-time occupancy actually evolves.

Across N=20 runs, four shapes appeared:

| Shape | Count (of 20) | Overall rescue rate | Timeline |
|---|---|---|---|
| Stable-low | 15 | ~0% | Flat at 0% for all 9 buckets |
| Transient blip | 1 | 3.8% | Brief 2-bucket rise (~12-17%), fully reverts |
| Mid-plateau | 2 | 10-21% | 0% for ~5 buckets, then rises and *holds* at ~24-26% through the end |
| Locked-high | 1 | 76.2% | ~68% already in bucket 0, stays 68-78% the entire run |

(R002's original N=10 at this same cell, without timestamp data, showed overall rates consistent with this split: 2/10 landed in the ~62% band matching locked-high, the remaining 8/10 spread 0-25% matching stable-low/mid-plateau — this document resolves what R002 could only see as aggregate variance.)

**The distinguishing mechanism is streak length, not frequency.** Counting consecutive at-capacity decisions: the locked-high run has **exactly one streak, covering all 2126 of its deferred decisions** — the pool saturates once and never recovers for the rest of the 135s run. Every stable-low, mid-plateau, and blip run instead shows **150-167 separate streaks averaging only 3-5 decisions each** — the pool constantly enters and exits capacity, self-resolving within roughly one k6 request-interval. A one-run spot check each at RPS14 and RPS18 (from R002's data) shows the same short-streak, self-resolving pattern, consistent with R002 finding no comparable instability at those points.

**Onset is early, not gradual.** The locked-high run's rescue rate is already ~68% in the very first time bucket — the lock-in happens at or near the start of the run (plausibly during warmup or the opening seconds of measurement), not a drift that builds up over 90+ seconds. The mid-plateau runs are the interesting middle case: they start at a clean 0% for roughly half the run, then transition to a sustained (not reverting) elevated rate — a partial, later-onset version of the same lock-in behavior, not a separate mechanism.

**What this is consistent with, not proven.** RPS16 at `pool_size=10` sits close enough to the point where offered load and pool service capacity are nearly balanced that small, irreducible timing differences between runs (k6 arrival jitter, host scheduling) can occasionally tip the pool into a self-reinforcing saturated state — once full, contention delays completions, which keeps it full — rather than the normal short-lived contention that resolves itself. This is a plausible account grounded in the streak-length evidence above, not a confirmed causal mechanism: this document does not trace *what specific event* in a run's opening seconds tips it into lock-in, which would need per-request arrival-timestamp correlation this data doesn't capture. That's flagged as further work, not attempted here.

**What this means for R002.** R002's headline finding is unchanged — the aggregate error rate stays essentially identical regardless of which mode a run lands in, so nothing here revises R002's Finding. What this adds is a mechanistic account of *why* RPS16 specifically (and, by the R002/010 cross-check, not RPS14 or RPS18) is where that instability shows up: it's the one point in this sweep close enough to critical pool utilization for a rare, self-locking saturation event to occasionally occur and persist for a full run.
