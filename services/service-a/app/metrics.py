import time

from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Standard Prometheus surface, exposed at /metrics for any external tooling.
REQUEST_LATENCY = Histogram(
    "service_a_request_latency_seconds",
    "End-to-end request latency, including retries against Service B",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
IN_FLIGHT = Gauge("service_a_in_flight_requests", "Requests currently being handled")
TIMEOUTS = Counter(
    "service_a_timeouts_total",
    "Requests where every attempt against Service B timed out",
)
UPSTREAM_ERRORS = Counter(
    "service_a_upstream_errors_total",
    "Requests where Service B returned a 5xx on every attempt",
)
ERRORS = Counter("service_a_errors_total", "Requests that errored for other reasons")
SUCCESSES = Counter("service_a_successes_total", "Requests that succeeded")
RETRIES = Counter(
    "service_a_retries_total", "Retry attempts made against Service B"
)
RETRY_SUCCESSES = Counter(
    "service_a_retry_successes_total",
    "Requests that succeeded only after at least one retry",
)
SHORT_CIRCUITS = Counter(
    "service_a_short_circuits_total",
    "Requests failed fast by the circuit breaker without reaching Service B",
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
        self.timeout_count = 0
        self.upstream_error_count = 0
        self.error_count = 0
        self.retry_count = 0
        self.retry_success_count = 0
        self.short_circuit_count = 0
        # Each entry: (timestamp, latency_seconds)
        self._latency_events: list[tuple[float, float]] = []
        # Tracked separately so open_state_latency_p95 can confirm the
        # breaker is failing fast (near-zero) rather than blending it into
        # the overall latency distribution.
        self._short_circuit_latency_events: list[tuple[float, float]] = []

    def request_started(self) -> None:
        self.in_flight += 1
        IN_FLIGHT.set(self.in_flight)

    def request_finished(
        self, latency_seconds: float, outcome: str, retries: int
    ) -> None:
        self.in_flight -= 1
        IN_FLIGHT.set(self.in_flight)

        now = time.monotonic()
        self.total_count += 1
        self._latency_events.append((now, latency_seconds))
        REQUEST_LATENCY.observe(latency_seconds)

        if retries:
            self.retry_count += retries
            RETRIES.inc(retries)

        if outcome == "success":
            self.success_count += 1
            SUCCESSES.inc()
            if retries:
                self.retry_success_count += 1
                RETRY_SUCCESSES.inc()
        elif outcome == "timeout":
            self.timeout_count += 1
            TIMEOUTS.inc()
        elif outcome == "upstream_error":
            self.upstream_error_count += 1
            UPSTREAM_ERRORS.inc()
        elif outcome == "short_circuited":
            self.short_circuit_count += 1
            SHORT_CIRCUITS.inc()
            self._short_circuit_latency_events.append((now, latency_seconds))
        elif outcome == "error":
            self.error_count += 1
            ERRORS.inc()

        self._trim(now)

    def _trim(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._latency_events and self._latency_events[0][0] < cutoff:
            self._latency_events.pop(0)
        while (
            self._short_circuit_latency_events
            and self._short_circuit_latency_events[0][0] < cutoff
        ):
            self._short_circuit_latency_events.pop(0)

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

    def snapshot(self) -> dict:
        now = time.monotonic()
        self._trim(now)

        recent_latencies = sorted(v for _, v in self._latency_events)
        recent_short_circuit_latencies = sorted(
            v for _, v in self._short_circuit_latency_events
        )

        return {
            "timestamp": time.time(),
            "in_flight": self.in_flight,
            "cumulative": {
                "total_count": self.total_count,
                "success_count": self.success_count,
                "timeout_count": self.timeout_count,
                "upstream_error_count": self.upstream_error_count,
                "error_count": self.error_count,
                "retry_count": self.retry_count,
                "retry_success_count": self.retry_success_count,
                "short_circuit_count": self.short_circuit_count,
            },
            "recent_latency_ms": {
                "p50": self._pct_ms(recent_latencies, 0.50),
                "p95": self._pct_ms(recent_latencies, 0.95),
                "p99": self._pct_ms(recent_latencies, 0.99),
                "sample_count": len(recent_latencies),
            },
            "recent_short_circuit_latency_ms": {
                "p95": self._pct_ms(recent_short_circuit_latencies, 0.95),
                "sample_count": len(recent_short_circuit_latencies),
            },
        }

    def _pct_ms(self, sorted_values: list[float], pct: float) -> float | None:
        v = self._percentile(sorted_values, pct)
        return round(v * 1000, 3) if v is not None else None


def prometheus_payload() -> bytes:
    return generate_latest()
