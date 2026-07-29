import time

from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Standard Prometheus surface, exposed at /metrics for any external tooling.
REQUEST_LATENCY = Histogram(
    "service_b_request_latency_seconds",
    "End-to-end request latency",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
IN_FLIGHT = Gauge("service_b_in_flight_requests", "Requests currently being handled")
POOL_WAIT = Histogram(
    "service_b_pool_wait_seconds",
    "Time spent waiting to acquire a DB connection from the pool",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
POOL_TIMEOUTS = Counter(
    "service_b_pool_timeouts_total",
    "Requests that timed out waiting to acquire a DB connection (pool exhaustion)",
)
QUERY_TIMEOUTS = Counter(
    "service_b_query_timeouts_total",
    "Requests that timed out waiting for the query itself (slow DB)",
)
ERRORS = Counter("service_b_errors_total", "Requests that errored")
SUCCESSES = Counter("service_b_successes_total", "Requests that succeeded")
ADMISSION_REJECTED = Counter(
    "service_b_admission_rejected_total",
    "Requests rejected by admission control before attempting to acquire a DB connection",
)


class Metrics:
    """In-process tracking used for the /internal/snapshot polling endpoint.

    The experiment runner polls this at ~1Hz to build the per-second raw
    sample series, so this class keeps recent request events with
    timestamps rather than only cumulative counters.
    """

    def __init__(self, window_seconds: float = 2.0) -> None:
        self.window_seconds = window_seconds
        self.in_flight = 0
        self.total_count = 0
        self.success_count = 0
        self.pool_timeout_count = 0
        self.query_timeout_count = 0
        self.error_count = 0
        self.admission_rejected_count = 0
        # Each entry: (timestamp, latency_seconds)
        self._latency_events: list[tuple[float, float]] = []
        self._pool_wait_events: list[tuple[float, float]] = []
        self._admission_rejected_latency_events: list[tuple[float, float]] = []

    def admission_rejected(self, latency_seconds: float) -> None:
        """A request rejected by admission control before ever calling
        pool.acquire() -- tracked separately from request_started/finished
        so it never touches in_flight or the pool_timeout/error/success
        outcome counts. Kept distinct from generic errors so a rejection's
        near-instant latency can be verified directly rather than being
        folded into the same latency distribution as slow collapse-path
        failures."""
        now = time.monotonic()
        self.admission_rejected_count += 1
        self._admission_rejected_latency_events.append((now, latency_seconds))
        ADMISSION_REJECTED.inc()
        self._trim(now)

    def request_started(self) -> None:
        self.in_flight += 1
        IN_FLIGHT.set(self.in_flight)

    def request_finished(
        self, latency_seconds: float, outcome: str, pool_wait_seconds: float | None
    ) -> None:
        self.in_flight -= 1
        IN_FLIGHT.set(self.in_flight)

        now = time.monotonic()
        self.total_count += 1
        self._latency_events.append((now, latency_seconds))
        REQUEST_LATENCY.observe(latency_seconds)

        if pool_wait_seconds is not None:
            self._pool_wait_events.append((now, pool_wait_seconds))
            POOL_WAIT.observe(pool_wait_seconds)

        if outcome == "success":
            self.success_count += 1
            SUCCESSES.inc()
        elif outcome == "pool_timeout":
            self.pool_timeout_count += 1
            POOL_TIMEOUTS.inc()
        elif outcome == "query_timeout":
            self.query_timeout_count += 1
            QUERY_TIMEOUTS.inc()
        elif outcome == "error":
            self.error_count += 1
            ERRORS.inc()

        self._trim(now)

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._latency_events and self._latency_events[0][0] < cutoff:
            self._latency_events.pop(0)
        while self._pool_wait_events and self._pool_wait_events[0][0] < cutoff:
            self._pool_wait_events.pop(0)
        while self._admission_rejected_latency_events and self._admission_rejected_latency_events[0][0] < cutoff:
            self._admission_rejected_latency_events.pop(0)

    @staticmethod
    def _percentile(sorted_values: list[float], pct: float) -> float | None:
        if not sorted_values:
            return None
        k = (len(sorted_values) - 1) * pct
        f = int(k)
        c = min(f + 1, len(sorted_values) - 1)
        if f == c:
            return sorted_values[f]
        return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)

    def snapshot(self, pool_active: int, pool_idle: int) -> dict:
        now = time.monotonic()
        self._trim(now)

        recent_latencies = sorted(v for _, v in self._latency_events)
        recent_pool_waits = sorted(v for _, v in self._pool_wait_events)
        recent_admission_rejected_latencies = sorted(v for _, v in self._admission_rejected_latency_events)

        return {
            "timestamp": time.time(),
            "in_flight": self.in_flight,
            "pool_active": pool_active,
            "pool_idle": pool_idle,
            "cumulative": {
                "total_count": self.total_count,
                "success_count": self.success_count,
                "pool_timeout_count": self.pool_timeout_count,
                "query_timeout_count": self.query_timeout_count,
                "error_count": self.error_count,
                "admission_rejected_count": self.admission_rejected_count,
            },
            "recent_latency_ms": {
                "p50": self._pct_ms(recent_latencies, 0.50),
                "p95": self._pct_ms(recent_latencies, 0.95),
                "p99": self._pct_ms(recent_latencies, 0.99),
                "sample_count": len(recent_latencies),
            },
            "recent_pool_wait_ms": {
                "p50": self._pct_ms(recent_pool_waits, 0.50),
                "p95": self._pct_ms(recent_pool_waits, 0.95),
                "sample_count": len(recent_pool_waits),
            },
            "recent_admission_rejected_latency_ms": {
                "p50": self._pct_ms(recent_admission_rejected_latencies, 0.50),
                "p95": self._pct_ms(recent_admission_rejected_latencies, 0.95),
                "sample_count": len(recent_admission_rejected_latencies),
            },
        }

    def _pct_ms(self, sorted_values: list[float], pct: float) -> float | None:
        v = self._percentile(sorted_values, pct)
        return round(v * 1000, 3) if v is not None else None


def prometheus_payload() -> bytes:
    return generate_latest()
