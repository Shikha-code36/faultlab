"""Admission control signals for Service B's /work handler.

Three modes, corresponding to Experiments 006, 007, and 008:

- InstantaneousAdmission (006): reject if the pool has no idle connections
  right now. Zero lag, ground truth.
- EwmaAdmission (007): reject based on an exponentially-weighted trailing
  estimate of pool utilization, not the instantaneous reading. Isolates
  information freshness as the only variable relative to 006 -- same
  threshold (utilization >= 1.0), same resource, same location (Service B),
  different temporal character of the signal.
- GraduatedAdmission (008): reject probabilistically, ramping from 0 at
  u_low to 1 at u=1.0, instead of 006's hard step at u=1.0. Isolates
  decision-rule shape as the variable relative to 006 -- same resource,
  same location, same instantaneous signal, only the shape of the
  admit/reject decision changes.

All are synchronous, no `await` inside should_reject(), so no locking is
needed: uvicorn runs a single worker on one asyncio event loop, and the
rest of this codebase (Metrics' counters) already relies on that same
cooperative-scheduling guarantee.
"""

from __future__ import annotations

import math
import random
import time

# Floating-point tolerance, not a scientific parameter: an EWMA converging
# toward 1.0 from below approaches it asymptotically and reaches it only
# in the limit as time -> infinity (true in exact arithmetic, not just
# floating point) -- so a strict `>= 1.0` comparison would never trigger
# under sustained saturation. This epsilon is orders of magnitude smaller
# than anything behaviorally meaningful (compare to the 0.16-0.33
# rejection rates this experiment actually measures); it exists purely so
# "the EWMA has converged to full utilization" is satisfiable at all.
_REJECT_EPSILON = 1e-6


class InstantaneousAdmission:
    """Experiment 006: reject if the pool has no idle connections right now."""

    def should_reject(self, pool_active: int, pool_max_size: int) -> bool:
        return pool_active >= pool_max_size

    def current_value(self) -> float | None:
        return None


class EwmaAdmission:
    """Experiment 007: reject based on a trailing EWMA of pool utilization
    with the given half-life, rather than the instantaneous reading.

    The EWMA used to decide a request's own admission reflects history
    strictly *before* that request -- its own observation is folded in
    only after the decision is made, so a request never influences the
    signal that gates it (the same principle behind Experiment 003's
    breaker excluding short-circuited requests from its own window).

    The first request of a run has no history yet and falls back to an
    instantaneous reading exactly once -- a documented, negligible
    bootstrap artifact given thousands of requests per run, not a hidden one.
    """

    def __init__(self, half_life_s: float):
        self.half_life_s = half_life_s
        self._tau = half_life_s / math.log(2)
        self._value: float | None = None
        self._last_update: float | None = None

    def should_reject(self, pool_active: int, pool_max_size: int) -> bool:
        current_ratio = pool_active / pool_max_size
        decision_value = current_ratio if self._value is None else self._value

        reject = decision_value >= 1.0 - _REJECT_EPSILON

        now = time.monotonic()
        if self._last_update is None:
            self._value = current_ratio
        else:
            dt = now - self._last_update
            alpha = 1 - math.exp(-dt / self._tau)
            self._value = alpha * current_ratio + (1 - alpha) * self._value
        self._last_update = now

        return reject

    def current_value(self) -> float | None:
        return self._value


class GraduatedAdmission:
    """Experiment 008: reject with probability that ramps linearly from 0
    at u_low to 1 at u=1.0, rather than 006's hard step at u=1.0.

    u_low is a stated design choice (see Experiment 008's README for the
    Little's-Law-derived bounds it sits within), not a value this
    experiment is trying to optimize. u_high is fixed at exactly 1.0 --
    the same "full" threshold 006 and 007 both use.
    """

    def __init__(self, u_low: float):
        self.u_low = u_low
        self._value: float | None = None

    def should_reject(self, pool_active: int, pool_max_size: int) -> bool:
        u = pool_active / pool_max_size
        self._value = u

        if u <= self.u_low:
            p_reject = 0.0
        elif u >= 1.0:
            p_reject = 1.0
        else:
            p_reject = (u - self.u_low) / (1.0 - self.u_low)

        return random.random() < p_reject

    def current_value(self) -> float | None:
        return self._value
