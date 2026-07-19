# Purpose: verify the distributed rate-limit and replay backends behave correctly and safely.
# Responsibilities: exercise key construction, atomic budget enforcement, TTLs, nonce single-use
#   across simulated replicas, timestamp skew, and Redis-outage fail-closed/open policy. These run
#   against an in-process fakeredis server (no external Redis required).
from __future__ import annotations

import fakeredis
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services.rate_limit import (
    InMemoryRateLimiter,
    RedisRateLimiter,
    rate_limit_key,
)
from app.services.replay import RedisReplayStore, ReplayError, ReplayGuard


def _clients(count: int) -> list[fakeredis.FakeStrictRedis]:
    """Return ``count`` clients that share one server (each models a separate app replica)."""
    server = fakeredis.FakeServer()
    return [fakeredis.FakeStrictRedis(server=server, decode_responses=True) for _ in range(count)]


class _BrokenClient:
    """A client whose every operation raises, to exercise Redis-outage policy."""

    def pipeline(self, *args: object, **kwargs: object) -> _BrokenClient:
        return self

    def zremrangebyscore(self, *a: object, **k: object) -> None: ...
    def zadd(self, *a: object, **k: object) -> None: ...
    def zcard(self, *a: object, **k: object) -> None: ...
    def expire(self, *a: object, **k: object) -> None: ...

    def execute(self) -> list[int]:
        raise RedisConnectionError("down")

    def set(self, *a: object, **k: object) -> bool:
        raise RedisConnectionError("down")

    def zrem(self, *a: object, **k: object) -> None:
        raise RedisConnectionError("down")

    def scan_iter(self, *a: object, **k: object) -> list[str]:
        raise RedisConnectionError("down")


# -- key construction -----------------------------------------------------------------------------


def test_rate_limit_key_includes_all_scopes() -> None:
    key = rate_limit_key(
        endpoint="monitoring:ingest", organization_id="org1", actor="key9", resource="plan7"
    )
    assert key == "monitoring:ingest:org1:key9:plan7"


def test_rate_limit_key_fills_missing_scopes() -> None:
    assert rate_limit_key(endpoint="e", organization_id="o") == "e:o:-:-"


# -- atomic limit behavior ------------------------------------------------------------------------


def test_redis_limiter_enforces_budget() -> None:
    client = _clients(1)[0]
    limiter = RedisRateLimiter(client, prefix="t", fail_open=False)
    allowed = [limiter.allow("k", 3) for _ in range(5)]
    assert allowed == [True, True, True, False, False]


def test_redis_limiter_rejected_request_does_not_consume_slot() -> None:
    client = _clients(1)[0]
    limiter = RedisRateLimiter(client, prefix="t", fail_open=False)
    limiter.allow("k", 1)
    assert limiter.allow("k", 1) is False
    # The rejected calls must not have grown the window beyond the single accepted request.
    (rkey,) = list(client.scan_iter(match="t:rl:*"))
    assert client.zcard(rkey) == 1


def test_two_instances_share_rate_limit_state() -> None:
    a_client, b_client = _clients(2)
    a = RedisRateLimiter(a_client, prefix="t", fail_open=False)
    b = RedisRateLimiter(b_client, prefix="t", fail_open=False)
    accepted = sum(
        1 for limiter in (a, b, a, b, a, b) if limiter.allow("shared", 3)
    )
    assert accepted == 3


# -- TTL behavior ---------------------------------------------------------------------------------


def test_redis_limiter_sets_ttl_on_key() -> None:
    client = _clients(1)[0]
    RedisRateLimiter(client, prefix="t", fail_open=False).allow("k", 5)
    (rkey,) = list(client.scan_iter(match="t:rl:*"))
    assert 0 < client.ttl(rkey) <= 61


def test_redis_limiter_window_expires_with_clock() -> None:
    client = _clients(1)[0]
    now = [1000.0]
    limiter = RedisRateLimiter(client, prefix="t", fail_open=False, clock=lambda: now[0])
    assert limiter.allow("k", 1) is True
    assert limiter.allow("k", 1) is False
    now[0] += 61  # advance past the 60s window; stale members are pruned on the next call
    assert limiter.allow("k", 1) is True


# -- outage policy --------------------------------------------------------------------------------


def test_redis_limiter_fail_closed_denies_on_outage() -> None:
    limiter = RedisRateLimiter(_BrokenClient(), prefix="t", fail_open=False)
    assert limiter.allow("k", 100) is False


def test_redis_limiter_fail_open_allows_on_outage() -> None:
    limiter = RedisRateLimiter(_BrokenClient(), prefix="t", fail_open=True)
    assert limiter.allow("k", 100) is True


# -- replay store ---------------------------------------------------------------------------------


def _guard(store: RedisReplayStore, now: float = 1000.0) -> ReplayGuard:
    return ReplayGuard(store, window_seconds=300, clock=lambda: now)


def test_replay_nonce_accepted_once_then_rejected() -> None:
    store = RedisReplayStore(_clients(1)[0], prefix="t", fail_open=False)
    guard = _guard(store)
    guard.check("n1", "1000", scope="org")
    with pytest.raises(ReplayError) as info:
        guard.check("n1", "1000", scope="org")
    assert info.value.status_code == 409


def test_replay_nonce_rejected_across_instances() -> None:
    a_client, b_client = _clients(2)
    worker_a = _guard(RedisReplayStore(a_client, prefix="t", fail_open=False))
    worker_b = _guard(RedisReplayStore(b_client, prefix="t", fail_open=False))
    worker_a.check("shared-nonce", "1000", scope="org")
    with pytest.raises(ReplayError) as info:
        worker_b.check("shared-nonce", "1000", scope="org")
    assert info.value.status_code == 409


def test_replay_same_nonce_different_scope_allowed() -> None:
    store = RedisReplayStore(_clients(1)[0], prefix="t", fail_open=False)
    guard = _guard(store)
    guard.check("n1", "1000", scope="orgA")
    guard.check("n1", "1000", scope="orgB")  # distinct organization scope: not a replay


def test_replay_rejects_timestamp_outside_skew() -> None:
    store = RedisReplayStore(_clients(1)[0], prefix="t", fail_open=False)
    guard = _guard(store, now=1000.0)
    with pytest.raises(ReplayError) as info:
        guard.check("n1", "500", scope="org")  # 500s old, window is 300s
    assert info.value.status_code == 400


def test_replay_requires_nonce_and_timestamp() -> None:
    store = RedisReplayStore(_clients(1)[0], prefix="t", fail_open=False)
    guard = _guard(store)
    with pytest.raises(ReplayError):
        guard.check(None, "1000", scope="org")
    with pytest.raises(ReplayError):
        guard.check("n1", None, scope="org")


def test_replay_fail_closed_treats_outage_as_replay() -> None:
    guard = _guard(RedisReplayStore(_BrokenClient(), prefix="t", fail_open=False))
    with pytest.raises(ReplayError):
        guard.check("n1", "1000", scope="org")


def test_replay_fail_open_allows_on_outage() -> None:
    guard = _guard(RedisReplayStore(_BrokenClient(), prefix="t", fail_open=True))
    guard.check("n1", "1000", scope="org")  # degrades to allow


def test_in_memory_limiter_still_available() -> None:
    limiter = InMemoryRateLimiter(clock=lambda: 0.0)
    assert [limiter.allow("k", 2) for _ in range(3)] == [True, True, False]
