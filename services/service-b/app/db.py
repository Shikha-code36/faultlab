import os

import asyncpg

DB_HOST = os.environ.get("DB_HOST", "toxiproxy")
DB_PORT = int(os.environ.get("DB_PORT", "5433"))
DB_USER = os.environ.get("DB_USER", "brinkline")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "brinkline")
DB_NAME = os.environ.get("DB_NAME", "brinkline")

POOL_MIN_SIZE = int(os.environ.get("POOL_MIN_SIZE", "5"))
POOL_MAX_SIZE = int(os.environ.get("POOL_MAX_SIZE", "10"))

# Seconds to wait for a free connection before giving up.
POOL_ACQUIRE_TIMEOUT = float(os.environ.get("POOL_ACQUIRE_TIMEOUT", "2.0"))

# Seconds to wait for the query itself to finish once a connection is held.
QUERY_TIMEOUT = float(os.environ.get("QUERY_TIMEOUT", "2.0"))


async def create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        min_size=POOL_MIN_SIZE,
        max_size=POOL_MAX_SIZE,
    )


def pool_config() -> dict:
    return {
        "pool_min_size": POOL_MIN_SIZE,
        "pool_max_size": POOL_MAX_SIZE,
        "pool_acquire_timeout": POOL_ACQUIRE_TIMEOUT,
        "query_timeout": QUERY_TIMEOUT,
        "db_host": DB_HOST,
        "db_port": DB_PORT,
    }
