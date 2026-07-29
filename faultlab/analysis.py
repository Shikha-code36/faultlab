"""Shared saturation/collapse analysis, reused by every experiment.

Injecting latency alone always makes requests slower -- that's just
propagation, not a problem on its own. What actually matters is
saturation: the downstream connection pool running out of capacity. A run
is flagged as saturated if any of the following hold:
  - error rate (timeouts + errors) above the threshold,
  - any pool-acquisition timeouts occurred on Service B, or
  - Service B's pool ran at its configured max size (no spare capacity left).

This is the check Experiments 001-004 all applied identically; it now
lives in one place instead of being re-copied into each analyzer.
"""

from __future__ import annotations

ERROR_RATE_THRESHOLD = 0.0


def annotate_saturation(runs: list[dict]) -> None:
    for r in runs:
        saturated = False
        reasons = []

        if r.get("error_rate") is not None and r["error_rate"] > ERROR_RATE_THRESHOLD:
            saturated = True
            reasons.append(f"error_rate={r['error_rate']:.2%}")

        if r.get("b_pool_timeout_count"):
            saturated = True
            reasons.append(f"pool_timeouts={r['b_pool_timeout_count']}")

        if (
            r.get("b_pool_active_max") is not None
            and r.get("pool_size") is not None
            and r["b_pool_active_max"] >= r["pool_size"]
        ):
            saturated = True
            reasons.append(f"pool_active={r['b_pool_active_max']} (max={r['pool_size']})")

        r["saturated"] = saturated
        r["saturation_reasons"] = "; ".join(reasons)


def first_saturation_points(runs: list[dict], group_key: str) -> dict[str, dict]:
    """The lowest-RPS saturated run per distinct value of group_key
    (typically an experiment's primary_variable, e.g. "retry_policy")."""
    first: dict[str, dict] = {}
    for r in sorted(runs, key=lambda x: (x.get(group_key), x.get("rps"))):
        key = r.get(group_key)
        if r.get("saturated") and key not in first:
            first[key] = r
    return first
