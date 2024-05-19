import redis
from redis.client import Redis
from typing import Union
from functools import cache

from nomenklatura import settings


@cache
def get_redis() -> "Redis[bytes]":
    """Return a Redis connection configured from the environment."""
    db = redis.from_url(settings.REDIS_URL, decode_responses=False)
    # for kvrocks:
    if len(db.config_get("redis-cursor-compatible")):
        db.config_set("redis-cursor-compatible", "yes")
    return db


def close_redis() -> None:
    """Close the Redis connection."""
    get_redis().close()
    get_redis.cache_clear()


def b(s: str) -> bytes:
    """Encode a string to bytes."""
    return s.encode("utf-8")


def bv(s: Union[bytes, str, int, float]) -> bytes:
    """Decode bytes to a string."""
    return s  # type: ignore
