"""Admission control signals for Service B's /work handler.

Two modes, corresponding to Experiments 006 and 007:

- InstantaneousAdmission (006): reject if the pool has no idle connections
  right now. Zero lag, ground truth.
- EwmaAdmission (007): reject based on an exponentially-weighted trailing
  estimate of pool utilization, not the instantaneous reading. Isolates
  information freshness as the only variable relative to 006 -- same
  threshold (utilization >= 1.0), same resource, same location (Service B),
  different temporal character of the signal.

Both are synchronous, no `await` inside should_reject(), so no locking is
needed: uvicorn runs a single worker on one asyncio event loop, and the
rest of this codebase (Metrics' counters) already relies on that same
cooperative-scheduling guarantee.
"""

from __future__ import annotations

import math
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
