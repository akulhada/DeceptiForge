# Purpose: reject replayed or stale monitoring requests across all workers.
# Responsibilities: define the ReplayStore interface, keep an in-process store for dev/tests,
#   add a Redis store that atomically reserves each nonce (SET NX EX) so a nonce accepted by one
#   worker is rejected by every other, and enforce a timestamp clock-skew bound. Nonce keys are
#   scoped by organization/monitor and always carry a TTL. Dependencies: settings, redis_support.
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from redis.exceptions import RedisError

from app.config.settings import Settings, get_settings
from app.services.redis_support import RedisClient, build_redis_client


class ReplayError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _scope_key(scope: str, nonce: str) -> str:
    return f"{scope}:{nonce}"


class ReplayStore(Protocol):
    """Reserve a nonce for ``ttl_seconds``; return True if newly reserved, False if already seen."""

    def reserve(self, key: str, ttl_seconds: int) -> bool: ...

    def clear(self) -> None: ...


class InMemoryReplayStore:
    """Single-process nonce store; not shared across workers."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._seen: dict[str, float] = {}
        self._clock = clock or time.time

    def reserve(self, key: str, ttl_seconds: int) -> bool:
        now = self._clock()
        for existing, expiry in list(self._seen.items()):
            if expiry < now:
                del self._seen[existing]
        if key in self._seen:
            return False
        self._seen[key] = now + ttl_seconds
        return True

    def clear(self) -> None:
        self._seen.clear()


class RedisReplayStore:
    """Distributed nonce store using an atomic SET NX EX reservation."""

    def __init__(self, client: RedisClient, *, prefix: str, fail_open: bool) -> None:
        self._client = client
        self._prefix = f"{prefix}:replay:"
        self._fail_open = fail_open

    def reserve(self, key: str, ttl_seconds: int) -> bool:
        try:
            created = self._client.set(f"{self._prefix}{key}", "1", nx=True, ex=ttl_seconds)
        except (RedisError, OSError):
            # Fail closed rejects the request (treated as not-reserved) unless configured open.
            return self._fail_open
        return bool(created)

    def clear(self) -> None:
        try:
            for rkey in self._client.scan_iter(match=f"{self._prefix}*"):
                self._client.delete(rkey)
        except (RedisError, OSError):
            pass


class ReplayGuard:
    """Enforce nonce single-use and timestamp skew using a pluggable ReplayStore."""

    def __init__(
        self,
        store: ReplayStore,
        *,
        window_seconds: int = 300,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._store = store
        self._window = window_seconds
        self._clock = clock or time.time

    def check(self, nonce: str | None, timestamp: str | None, *, scope: str = "global") -> None:
        if not nonce or not timestamp:
            raise ReplayError(400, "monitoring requires a nonce and timestamp")
        try:
            event_time = float(timestamp)
        except ValueError:
            raise ReplayError(400, "invalid timestamp") from None
        now = self._clock()
        if abs(now - event_time) > self._window:
            raise ReplayError(400, "timestamp outside the allowed clock skew")
        # TTL slightly exceeds the skew window so a nonce cannot be reused while still valid.
        if not self._store.reserve(_scope_key(scope, nonce), self._window + 1):
            raise ReplayError(409, "replayed nonce")

    def clear(self) -> None:
        self._store.clear()


def build_replay_store(settings: Settings) -> ReplayStore:
    if settings.replay_backend == "redis":
        return RedisReplayStore(
            build_redis_client(settings),
            prefix=settings.redis_key_prefix,
            fail_open=settings.redis_fail_mode == "open",
        )
    return InMemoryReplayStore()


_guard: ReplayGuard | None = None


def get_replay_guard() -> ReplayGuard:
    """Return the process-wide replay guard, building it from settings on first use."""
    global _guard
    if _guard is None:
        settings = get_settings()
        _guard = ReplayGuard(
            build_replay_store(settings),
            window_seconds=settings.monitoring_timestamp_skew_seconds,
        )
    return _guard


def reset_replay_guard() -> None:
    """Clear and drop the cached replay guard (used between tests and on settings reload)."""
    global _guard
    if _guard is not None:
        _guard.clear()
    _guard = None
