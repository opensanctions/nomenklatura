import redis
import logging
from typing import Union
from functools import cache
from redis.client import Redis
from fakeredis import FakeStrictRedis

from nomenklatura import settings

log = logging.getLogger(__name__)


@cache
def get_redis() -> "Redis[bytes]":
    """Return a Redis connection configured from the environment."""
    if settings.TESTING or not len(settings.REDIS_URL.strip()):
        log.info("Using in-memory key-value store...")
        return FakeStrictRedis(decode_responses=False)
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
