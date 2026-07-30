import asyncio
import os
import random
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response

from . import db
from .admission import EwmaAdmission, InstantaneousAdmission
from .metrics import Metrics, prometheus_payload

metrics = Metrics()

ITEM_COUNT = 5000

# Experiment 004 only: optional per-request arrival trace, used to measure
# retry desynchronization at sub-second resolution -- the existing ~1Hz
# snapshot polling can't distinguish a synchronized retry burst from a
# spread-out one, since a 100-200ms backoff schedule lives entirely inside
# one polling bucket. Default off so Experiments 001-003 are unaffected.
# Deliberately kept separate from metrics.py's permanent counter/gauge/
# snapshot system -- this is an experiment-scoped trace, not a permanent
# part of Service B's instrumentation surface.
ENABLE_ARRIVAL_TRACE = os.environ.get("ENABLE_ARRIVAL_TRACE", "false").lower() == "true"
_arrival_trace_ns: list[int] = []

# Experiment 006 only: server-side admission control, gated before ever
# calling pool.acquire(). The signal is the pool's own instantaneous state
# (no idle connections free) -- the same quantity every experiment since
# 001 has used to define saturation -- not a proxy like in-flight request
# count. Deliberately does not touch pool.acquire()'s own timeout/queueing
# behavior for admitted requests: this is a decision made upstream of the
# resource, not a change to how the resource itself arbitrates contention.
# Default off so Experiments 001-005 are unaffected and this branch is a
# true no-op when disabled.
ADMISSION_CONTROL_ENABLED = os.environ.get("ADMISSION_CONTROL_ENABLED", "false").lower() == "true"

# Experiment 007: which signal drives the admission decision above --
# "instantaneous" (006's exact mechanism, the default) or "ewma" (a trailing
# exponentially-weighted estimate of pool utilization, half-life below).
# Isolates information freshness as the only variable relative to 006: same
# resource, same location, same threshold, different temporal character of
# the input. The half-life is a stated design choice (see Experiment 007's
# README for the derivation from measured request-service-time and warmup
# duration), not a value Experiment 007 is trying to optimize.
ADMISSION_CONTROL_MODE = os.environ.get("ADMISSION_CONTROL_MODE", "instantaneous")
ADMISSION_EWMA_HALF_LIFE_S = float(os.environ.get("ADMISSION_EWMA_HALF_LIFE_S", "2.0"))

_admission_controller = (
    EwmaAdmission(half_life_s=ADMISSION_EWMA_HALF_LIFE_S)
    if ADMISSION_CONTROL_MODE == "ewma"
    else InstantaneousAdmission()
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await db.create_pool()
    try:
        yield
    finally:
        await app.state.pool.close()


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/internal/config")
async def internal_config():
    config = db.pool_config()
    config["admission_control_enabled"] = ADMISSION_CONTROL_ENABLED
    config["admission_control_mode"] = ADMISSION_CONTROL_MODE
    config["admission_ewma_half_life_s"] = ADMISSION_EWMA_HALF_LIFE_S
    return config


@app.get("/internal/snapshot")
async def internal_snapshot():
    pool = app.state.pool
    return metrics.snapshot(
        pool_active=pool.get_size() - pool.get_idle_size(),
        pool_idle=pool.get_idle_size(),
        admission_ewma_utilization=_admission_controller.current_value(),
    )


@app.get("/metrics")
async def prometheus_metrics():
    return Response(content=prometheus_payload(), media_type="text/plain")


@app.get("/internal/arrival_trace")
async def internal_arrival_trace():
    return {
        "enabled": ENABLE_ARRIVAL_TRACE,
        "count": len(_arrival_trace_ns),
        "arrivals_ns": list(_arrival_trace_ns),
    }


@app.post("/internal/arrival_trace/reset")
async def internal_arrival_trace_reset():
    _arrival_trace_ns.clear()
    return {"enabled": ENABLE_ARRIVAL_TRACE, "count": len(_arrival_trace_ns)}


@app.get("/work")
async def work(id: int | None = None):
    item_id = id if id is not None else random.randint(1, ITEM_COUNT)

    if ENABLE_ARRIVAL_TRACE:
        _arrival_trace_ns.append(time.monotonic_ns())

    if ADMISSION_CONTROL_ENABLED:
        admission_check_start = time.monotonic()
        pool = app.state.pool
        pool_active = pool.get_size() - pool.get_idle_size()
        if _admission_controller.should_reject(pool_active, db.POOL_MAX_SIZE):
            metrics.admission_rejected(time.monotonic() - admission_check_start)
            raise HTTPException(status_code=503, detail="admission rejected: pool at capacity")

    metrics.request_started()
    start = time.monotonic()
    outcome = "error"
    pool_wait_seconds: float | None = None
    acquire_start = time.monotonic()

    try:
        # Acquiring a connection and running the query time out independently,
        # so a timeout here means the pool is exhausted (saturation), while a
        # timeout below means the query itself is slow (a slow DB) -- collapsing
        # the two loses exactly the causal distinction this lab exists to show.
        try:
            async with app.state.pool.acquire(
                timeout=db.POOL_ACQUIRE_TIMEOUT
            ) as conn:
                pool_wait_seconds = time.monotonic() - acquire_start
                try:
                    row = await asyncio.wait_for(
                        conn.fetchrow(
                            "SELECT id, name, value FROM items WHERE id = $1",
                            item_id,
                        ),
                        timeout=db.QUERY_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    outcome = "query_timeout"
                    raise HTTPException(status_code=504, detail="query timed out")
        except asyncio.TimeoutError:
            pool_wait_seconds = time.monotonic() - acquire_start
            outcome = "pool_timeout"
            raise HTTPException(status_code=503, detail="pool acquire timed out")

        if row is None:
            raise HTTPException(status_code=404, detail="item not found")

        outcome = "success"
        return {
            "id": row["id"],
            "name": row["name"],
            "value": float(row["value"]),
        }
    except HTTPException:
        raise
    except Exception as exc:
        outcome = "error"
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        latency_seconds = time.monotonic() - start
        metrics.request_finished(latency_seconds, outcome, pool_wait_seconds)
