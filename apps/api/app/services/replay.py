# Purpose: reject replayed or stale monitoring requests.
# Responsibilities: enforce a per-nonce single-use window and a timestamp clock-skew bound. This is
#   an in-process guard (single worker); production needs shared state. Dependencies: stdlib only.
# FUTURE_HARDENING: back the nonce store with Redis and add signed monitor request bodies.
from __future__ import annotations

import time
from collections.abc import Callable


class ReplayError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class ReplayGuard:
    def __init__(
        self, *, window_seconds: int = 300, clock: Callable[[], float] | None = None
    ) -> None:
        self._window = window_seconds
        self._seen: dict[str, float] = {}
        self._clock = clock or time.time

    def check(self, nonce: str | None, timestamp: str | None) -> None:
        if not nonce or not timestamp:
            raise ReplayError(400, "monitoring requires a nonce and timestamp")
        try:
            event_time = float(timestamp)
        except ValueError:
            raise ReplayError(400, "invalid timestamp") from None
        now = self._clock()
        if abs(now - event_time) > self._window:
            raise ReplayError(400, "timestamp outside the allowed clock skew")
        for key, expiry in list(self._seen.items()):
            if expiry < now:
                del self._seen[key]
        if nonce in self._seen:
            raise ReplayError(409, "replayed nonce")
        self._seen[nonce] = now + self._window

    def clear(self) -> None:
        self._seen.clear()


replay_guard = ReplayGuard()
