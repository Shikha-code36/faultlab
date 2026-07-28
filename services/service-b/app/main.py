import asyncio
import random
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response

from . import db
from .metrics import Metrics, prometheus_payload

metrics = Metrics()

ITEM_COUNT = 5000


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
    return db.pool_config()


@app.get("/internal/snapshot")
async def internal_snapshot():
    pool = app.state.pool
    return metrics.snapshot(
        pool_active=pool.get_size() - pool.get_idle_size(),
        pool_idle=pool.get_idle_size(),
    )


@app.get("/metrics")
async def prometheus_metrics():
    return Response(content=prometheus_payload(), media_type="text/plain")


@app.get("/work")
async def work(id: int | None = None):
    item_id = id if id is not None else random.randint(1, ITEM_COUNT)

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
