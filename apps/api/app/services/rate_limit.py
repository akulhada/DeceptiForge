# Purpose: enforce request rate limits, either per-process (development) or shared across replicas.
# Responsibilities: define the RateLimiter interface, keep an in-memory sliding-window limiter for
#   development/tests, add a Redis-backed sliding-window limiter that coordinates across workers,
#   and select the active backend from settings. Keys carry organization/actor/endpoint/resource
#   scope and every Redis key is given a TTL. Dependencies: settings, redis_support.
from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterable
from typing import Protocol

from redis.exceptions import RedisError

from app.config.settings import Settings, get_settings
from app.services.redis_support import RedisClient, build_redis_client

_WINDOW_SECONDS = 60.0


def rate_limit_key(
    *,
    endpoint: str,
    organization_id: object,
    actor: object | None = None,
    resource: object | None = None,
) -> str:
    """Build a scoped limiter key from the parts that should share (or not share) a budget."""
    parts: Iterable[object] = (endpoint, organization_id, actor or "-", resource or "-")
    return ":".join(str(part) for part in parts)


class RateLimiter(Protocol):
    """Allow or deny an action identified by ``key`` within a per-minute budget."""

    def allow(self, key: str, limit_per_minute: int) -> bool: ...

    def clear(self) -> None: ...


class InMemoryRateLimiter:
    """In-process, per-key sliding-window limiter (single worker only)."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._clock = clock or time.monotonic

    def allow(self, key: str, limit_per_minute: int) -> bool:
        if limit_per_minute <= 0:
            return True
        now = self._clock()
        window = self._hits[key]
        while window and now - window[0] > _WINDOW_SECONDS:
            window.popleft()
        if len(window) >= limit_per_minute:
            return False
        window.append(now)
        return True

    def clear(self) -> None:
        self._hits.clear()


class RedisRateLimiter:
    """Distributed sliding-window limiter backed by a Redis sorted set per key.

    Each request is a unique member scored by timestamp. A single MULTI/EXEC transaction prunes the
    window, records the request, reads the count, and refreshes the TTL, so concurrent workers see a
    consistent budget. Rejected requests remove their own member so a denial does not use a slot.
    """

    def __init__(
        self,
        client: RedisClient,
        *,
        prefix: str,
        fail_open: bool,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._client = client
        self._prefix = f"{prefix}:rl:"
        self._fail_open = fail_open
        self._clock = clock or time.time

    def allow(self, key: str, limit_per_minute: int) -> bool:
        if limit_per_minute <= 0:
            return True
        now = self._clock()
        rkey = f"{self._prefix}{key}"
        member = f"{now:.6f}:{secrets.token_hex(6)}"
        try:
            pipe = self._client.pipeline(transaction=True)
            pipe.zremrangebyscore(rkey, 0, now - _WINDOW_SECONDS)
            pipe.zadd(rkey, {member: now})
            pipe.zcard(rkey)
            pipe.expire(rkey, int(_WINDOW_SECONDS) + 1)
            count = pipe.execute()[2]
        except (RedisError, OSError):
            return self._fail_open
        if int(count) > limit_per_minute:
            try:
                self._client.zrem(rkey, member)
            except (RedisError, OSError):
                pass
            return False
        return True

    def clear(self) -> None:
        try:
            for rkey in self._client.scan_iter(match=f"{self._prefix}*"):
                self._client.delete(rkey)
        except (RedisError, OSError):
            pass


def build_rate_limiter(settings: Settings) -> RateLimiter:
    if settings.rate_limit_backend == "redis":
        return RedisRateLimiter(
            build_redis_client(settings),
            prefix=settings.redis_key_prefix,
            fail_open=settings.redis_fail_mode == "open",
        )
    return InMemoryRateLimiter()


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Return the process-wide limiter, building it from settings on first use."""
    global _limiter
    if _limiter is None:
        _limiter = build_rate_limiter(get_settings())
    return _limiter


def reset_rate_limiter() -> None:
    """Clear and drop the cached limiter (used between tests and on settings reload)."""
    global _limiter
    if _limiter is not None:
        _limiter.clear()
    _limiter = None
