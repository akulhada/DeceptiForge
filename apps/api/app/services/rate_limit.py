# Purpose: provide a simple, single-process rate limiter for the MVP.
# Responsibilities: allow or deny an action by key within a per-minute budget using an in-memory
#   sliding window. This is intentionally not distributed. Dependencies: standard library only.
# FUTURE_HARDENING: production needs edge/distributed rate limiting (Redis or gateway); this
#   in-process limiter does not coordinate across workers or hosts.
from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

_WINDOW_SECONDS = 60.0


class RateLimiter:
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


rate_limiter = RateLimiter()
