# Purpose: build and share Redis clients for the distributed rate-limit and replay stores.
# Responsibilities: construct a configured redis-py client from settings, support an in-process
#   "fakeredis://" scheme for tests, expose a health check, and never log connection secrets.
# Dependencies: redis-py (required); fakeredis (development/tests only, imported lazily).
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from redis import Redis
from redis.exceptions import RedisError

if TYPE_CHECKING:
    from app.config.settings import Settings

_FAKE_SCHEME = "fakeredis://"
# One shared fake server per URL so multiple clients (or simulated replicas) share state in-process.
# (state is kept in-process for the "fakeredis://" scheme only.)
_fake_servers: dict[str, Any] = {}
# Cache real/fake clients per (url, prefix) so each process reuses a single connection pool.
_clients: dict[tuple[str, str], RedisClient] = {}


class RedisClient(Protocol):
    """The subset of the redis-py client surface the stores rely on."""

    def ping(self) -> Any: ...
    def set(self, *args: Any, **kwargs: Any) -> Any: ...
    def get(self, name: Any) -> Any: ...
    def delete(self, *names: Any) -> Any: ...
    def zadd(self, *args: Any, **kwargs: Any) -> Any: ...
    def zrem(self, *args: Any, **kwargs: Any) -> Any: ...
    def scan_iter(self, *args: Any, **kwargs: Any) -> Any: ...
    def pipeline(self, *args: Any, **kwargs: Any) -> Any: ...


class RedisUnavailableError(Exception):
    """Raised when a required Redis dependency cannot be reached."""


def _build_fake(url: str) -> RedisClient:
    import fakeredis  # local dev/test dependency only

    server = _fake_servers.get(url)
    if server is None:
        server = fakeredis.FakeServer()
        _fake_servers[url] = server
    return fakeredis.FakeStrictRedis(server=server, decode_responses=True)


def build_redis_client(settings: Settings) -> RedisClient:
    """Return a shared Redis client for the process, honoring the fakeredis test scheme."""
    url = settings.redis_url
    if url is None:
        raise RedisUnavailableError("REDIS_URL is not configured")
    cache_key = (url, settings.redis_key_prefix)
    cached = _clients.get(cache_key)
    if cached is not None:
        return cached
    if url.startswith(_FAKE_SCHEME):
        client: RedisClient = _build_fake(url)
    else:
        client = Redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=settings.redis_socket_timeout_seconds,
            socket_connect_timeout=settings.redis_connect_timeout_seconds,
            health_check_interval=30,
        )
    _clients[cache_key] = client
    return client


def ping_redis(settings: Settings) -> None:
    """Verify Redis is reachable; raise RedisUnavailableError otherwise."""
    try:
        build_redis_client(settings).ping()
    except (RedisError, OSError) as error:
        raise RedisUnavailableError(type(error).__name__) from error


def redis_health(settings: Settings) -> dict[str, str]:
    """Return a safe health summary for the Redis dependency (no URL/secret disclosure)."""
    if not settings._redis_required:
        return {"status": "not_required"}
    try:
        ping_redis(settings)
    except RedisUnavailableError:
        return {"status": "unavailable"}
    return {"status": "ok"}


def reset_clients_for_tests() -> None:
    """Drop cached clients and fake servers between tests."""
    _clients.clear()
    _fake_servers.clear()
