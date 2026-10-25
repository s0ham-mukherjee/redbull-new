"""Caching & rate limiting (upstream clone: redis/redis-py, MIT).

Exposed capabilities:
- ``cache`` / ``redis`` - response cache for API calls (Features 1/10/68).
- ``cache`` / ``local`` - TTL dict cache for offline/test runs.
- ``limiter`` / ``token_bucket`` - leaky-bucket throttling per upstream API
  key (Feature 68), Redis-backed when a server is available, else in-process.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from engine_api import provider

from ._bootstrap import ProviderError


class LocalCache:
    """Cache: process-local JSON-safe values with TTL."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float | None, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires, value = item
            if expires is not None and time.time() > expires:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        expires = time.time() + ttl if ttl else None
        with self._lock:
            self._data[key] = (expires, value)


class RedisCache:
    """Cache over a running Redis server (redis-py)."""

    def __init__(self, url: str | None = None, prefix: str = "sakura:") -> None:
        self._url = url or os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
        self._prefix = prefix
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import redis  # lazy upstream import
            except Exception as exc:
                raise ProviderError(f"redis-py unavailable: {exc}") from exc
            try:
                self._client = redis.Redis.from_url(self._url, decode_responses=True)
                self._client.ping()
            except Exception as exc:
                raise ProviderError(
                    f"cannot reach Redis at {self._url} (start it or set REDIS_URL): {exc}"
                ) from exc
        return self._client

    def get(self, key: str) -> Any | None:
        raw = self.client.get(self._prefix + key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        payload = json.dumps(value, ensure_ascii=False, default=str)
        if ttl:
            self.client.setex(self._prefix + key, ttl, payload)
        else:
            self.client.set(self._prefix + key, payload)


class TokenBucketLimiter:
    """RateLimiter: token bucket keyed by e.g. 'jikan', 'youtube', 'reddit'.

    Uses Redis (INCR + EXPIRE window) when available, otherwise an in-process
    bucket. ``wait`` blocks until capacity frees up.
    """

    def __init__(self, rate_per_sec: float = 3.0, burst: float | None = None,
                 redis_url: str | None = None, use_redis: bool = True) -> None:
        self._rate = float(rate_per_sec)
        self._capacity = float(burst if burst is not None else max(1.0, rate_per_sec))
        self._tokens: dict[str, float] = {}
        self._stamps: dict[str, float] = {}
        self._lock = threading.Lock()
        self._redis: Any = None
        if use_redis:
            try:
                import redis as redis_lib  # lazy upstream import
                url = redis_url or os.environ.get("REDIS_URL") or "redis://localhost:6379/0"
                client = redis_lib.Redis.from_url(url, decode_responses=True)
                client.ping()
                self._redis = client
            except Exception:
                self._redis = None  # fall back to in-process bucket

    def acquire(self, key: str, cost: float = 1.0) -> bool:
        if self._redis is not None:
            # Fixed-window counter via Redis.
            window_key = f"rl:{key}:{int(time.time() * self._rate)}"
            used = self._redis.incrby(window_key, int(cost) or 1)
            if used == 1:
                self._redis.expire(window_key, max(2, int(2.0 / self._rate) + 1))
            return float(used) <= self._capacity
        with self._lock:
            now = time.time()
            tokens = self._tokens.get(key, self._capacity)
            elapsed = now - self._stamps.get(key, now)
            tokens = min(self._capacity, tokens + elapsed * self._rate)
            self._stamps[key] = now
            if tokens >= cost:
                self._tokens[key] = tokens - cost
                return True
            self._tokens[key] = tokens
            return False

    def wait(self, key: str, cost: float = 1.0, timeout: float = 60.0) -> None:
        deadline = time.time() + timeout
        while not self.acquire(key, cost):
            if time.time() > deadline:
                raise ProviderError(f"rate limit timeout for {key!r} after {timeout}s")
            time.sleep(max(0.05, 1.0 / self._rate))


@provider("cache", "local")
def _local_cache_factory(**config: Any) -> LocalCache:
    return LocalCache(**config)


@provider("cache", "redis")
def _redis_cache_factory(**config: Any) -> RedisCache:
    return RedisCache(**config)


@provider("limiter", "token_bucket")
def _limiter_factory(**config: Any) -> TokenBucketLimiter:
    return TokenBucketLimiter(**config)


__all__ = ["LocalCache", "RedisCache", "TokenBucketLimiter"]
