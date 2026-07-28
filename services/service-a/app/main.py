import asyncio
import random
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Response

from . import client
from .breaker import CircuitBreaker
from .metrics import Metrics, prometheus_payload

metrics = Metrics()
breaker = CircuitBreaker()

ITEM_COUNT = 5000


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(
        timeout=client.HTTP_TIMEOUT,
        # Default httpx limits (max_connections=100) apply the same timeout
        # to "waiting for a pool slot" as to the request itself -- under load
        # this makes A's own client pool the bottleneck instead of B's DB
        # pool, which is the resource this experiment actually studies.
        limits=httpx.Limits(max_connections=1000, max_keepalive_connections=100),
    )
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/internal/config")
async def internal_config():
    return client.client_config()


@app.get("/internal/snapshot")
async def internal_snapshot():
    return metrics.snapshot()


@app.get("/internal/breaker")
async def internal_breaker():
    return {"timestamp": time.time(), **breaker.snapshot()}


@app.get("/metrics")
async def prometheus_metrics():
    return Response(content=prometheus_payload(), media_type="text/plain")


@app.get("/work")
async def work(id: int | None = None):
    item_id = id if id is not None else random.randint(1, ITEM_COUNT)

    metrics.request_started()
    start = time.monotonic()
    outcome = "error"
    retries = 0

    try:
        response: httpx.Response | None = None
        last_exc: Exception | None = None
        short_circuited = False

        for attempt in range(client.MAX_ATTEMPTS):
            if attempt > 0:
                retries += 1
                if client.RETRY_POLICY == "backoff":
                    delay_ms = random.uniform(
                        client.RETRY_BACKOFF_MIN_MS, client.RETRY_BACKOFF_MAX_MS
                    )
                    await asyncio.sleep(delay_ms / 1000)

            if client.BREAKER_ENABLED and not await breaker.acquire():
                short_circuited = True
                break

            try:
                response = await app.state.http.get(
                    client.SERVICE_B_URL, params={"id": item_id}
                )
                forwarded_success = response.status_code < 500
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                response = None
                forwarded_success = False

            if client.BREAKER_ENABLED:
                await breaker.record(forwarded_success)

            if forwarded_success:
                break

        if short_circuited:
            outcome = "short_circuited"
            raise HTTPException(status_code=503, detail="circuit open")

        if response is None:
            outcome = "timeout"
            detail = str(last_exc) if last_exc else "upstream unavailable"
            raise HTTPException(status_code=504, detail=detail)

        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="item not found")
        if response.status_code >= 500:
            outcome = "upstream_error"
            raise HTTPException(status_code=response.status_code, detail="upstream error")
        if response.status_code != 200:
            outcome = "error"
            raise HTTPException(
                status_code=response.status_code, detail="unexpected upstream response"
            )

        outcome = "success"
        return response.json()
    except HTTPException:
        raise
    except Exception as exc:
        outcome = "error"
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        latency_seconds = time.monotonic() - start
        metrics.request_finished(latency_seconds, outcome, retries)
