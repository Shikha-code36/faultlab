import os

SERVICE_B_URL = os.environ.get("SERVICE_B_URL", "http://service-b:8000/work")

# Per-attempt timeout for the call to Service B.
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "2.0"))

# none: single attempt, no retry.
# immediate: one retry, fired right after the first attempt fails.
# backoff: one retry, delayed by a random value in [RETRY_BACKOFF_MIN_MS, RETRY_BACKOFF_MAX_MS].
RETRY_POLICY = os.environ.get("RETRY_POLICY", "none")
RETRY_BACKOFF_MIN_MS = float(os.environ.get("RETRY_BACKOFF_MIN_MS", "50"))
RETRY_BACKOFF_MAX_MS = float(os.environ.get("RETRY_BACKOFF_MAX_MS", "100"))

MAX_ATTEMPTS = 1 if RETRY_POLICY == "none" else 2

BREAKER_ENABLED = os.environ.get("BREAKER_ENABLED", "false").lower() == "true"


def client_config() -> dict:
    return {
        "service_b_url": SERVICE_B_URL,
        "http_timeout": HTTP_TIMEOUT,
        "retry_policy": RETRY_POLICY,
        "retry_backoff_min_ms": RETRY_BACKOFF_MIN_MS,
        "retry_backoff_max_ms": RETRY_BACKOFF_MAX_MS,
        "max_attempts": MAX_ATTEMPTS,
        "breaker_enabled": BREAKER_ENABLED,
    }
