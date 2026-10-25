"""LocalCache + TokenBucketLimiter edge cases (all in-process, use_redis=False).

Time-dependent behavior is tested with a monkeypatched clock in the
providers.cache namespace; no real Redis and no real sleeping.
"""

from __future__ import annotations

import sys
import threading

import pytest

import providers.cache as pcache
from engine_api.protocols import Cache, RateLimiter
from providers._bootstrap import ProviderError
from providers.cache import LocalCache, TokenBucketLimiter


# ---------------------------------------------------------------------------
# LocalCache
# ---------------------------------------------------------------------------


def test_local_cache_missing_key_returns_none():
    assert LocalCache().get("nope") is None


@pytest.mark.parametrize("value", [
    "plain str",
    42,
    -3.75,
    True,
    False,
    [1, 2, 3],
    {"nested": {"a": [1, "x", None]}},
    None,  # stored None round-trips as None (indistinguishable from missing)
])
def test_local_cache_set_get_round_trip(value):
    c = LocalCache()
    c.set("k", value)
    assert c.get("k") == value
    assert c.get("k") == c.get("k")  # repeated gets stable


def test_local_cache_keys_independent():
    c = LocalCache()
    c.set("a", 1)
    c.set("b", 2)
    assert c.get("a") == 1 and c.get("b") == 2


def test_local_cache_ttl_expiry_with_frozen_clock(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(pcache.time, "time", lambda: clock["now"])
    c = LocalCache()
    c.set("k", "v", ttl=10)
    assert c.get("k") == "v"  # well before expiry
    clock["now"] = 1005.0
    assert c.get("k") == "v"  # still before expiry
    clock["now"] = 1009.9
    assert c.get("k") == "v"  # just before expiry
    clock["now"] = 1010.0
    assert c.get("k") == "v"  # exactly at expiry -> strict > means still valid
    clock["now"] = 1010.5
    assert c.get("k") is None  # past expiry
    # expired key is deleted from the store
    assert "k" not in c._data


def test_local_cache_ttl_zero_means_no_expiry(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(pcache.time, "time", lambda: clock["now"])
    c = LocalCache()
    c.set("k", "v", ttl=0)  # 0 is falsy -> no expiry
    clock["now"] = 10**9
    assert c.get("k") == "v"


def test_local_cache_ttl_none_means_no_expiry(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(pcache.time, "time", lambda: clock["now"])
    c = LocalCache()
    c.set("k", "v", ttl=None)
    clock["now"] = 10**9
    assert c.get("k") == "v"


def test_local_cache_negative_ttl_expires_immediately(monkeypatch):
    clock = {"now": 100.0}
    monkeypatch.setattr(pcache.time, "time", lambda: clock["now"])
    c = LocalCache()
    c.set("k", "v", ttl=-5)  # negative is truthy -> expiry in the past
    assert c.get("k") is None


def test_local_cache_overwrite_updates_value_and_ttl(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(pcache.time, "time", lambda: clock["now"])
    c = LocalCache()
    c.set("k", "first", ttl=100)
    c.set("k", "second", ttl=5)
    assert c.get("k") == "second"
    clock["now"] = 6.0
    assert c.get("k") is None  # the *new* ttl applies


def test_local_cache_overwrite_can_clear_ttl(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(pcache.time, "time", lambda: clock["now"])
    c = LocalCache()
    c.set("k", "first", ttl=5)
    c.set("k", "second")  # no ttl -> persistent now
    clock["now"] = 10**6
    assert c.get("k") == "second"


def test_local_cache_thread_safety_smoke():
    c = LocalCache()
    errors = []

    def worker(tid: int) -> None:
        try:
            for i in range(100):
                key = f"t{tid}-{i}"
                c.set(key, tid * 1000 + i)
                got = c.get(key)
                if got != tid * 1000 + i:
                    errors.append((tid, i, got))
        except Exception as exc:  # pragma: no cover
            errors.append((tid, "crash", exc))

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    for tid in range(8):
        for i in range(100):
            assert c.get(f"t{tid}-{i}") == tid * 1000 + i


def test_local_cache_satisfies_cache_protocol():
    assert isinstance(LocalCache(), Cache)


# ---------------------------------------------------------------------------
# TokenBucketLimiter
# ---------------------------------------------------------------------------


def test_token_bucket_burst_defaults_to_max_one_rate():
    assert TokenBucketLimiter(rate_per_sec=3.0, use_redis=False)._capacity == 3.0
    assert TokenBucketLimiter(rate_per_sec=0.5, use_redis=False)._capacity == 1.0
    assert TokenBucketLimiter(rate_per_sec=0.0, use_redis=False)._capacity == 1.0


def test_token_bucket_explicit_burst_honored():
    assert TokenBucketLimiter(rate_per_sec=10, burst=2, use_redis=False)._capacity == 2.0
    assert TokenBucketLimiter(rate_per_sec=1, burst=25, use_redis=False)._capacity == 25.0


def test_token_bucket_acquire_true_while_tokens_false_when_drained(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(pcache.time, "time", lambda: clock["now"])
    lb = TokenBucketLimiter(rate_per_sec=0.0, burst=3, use_redis=False)
    assert lb.acquire("k") is True
    assert lb.acquire("k") is True
    assert lb.acquire("k") is True
    assert lb.acquire("k") is False  # drained, no refill (rate=0)
    assert lb.acquire("k") is False


def test_token_bucket_refill_over_time(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(pcache.time, "time", lambda: clock["now"])
    lb = TokenBucketLimiter(rate_per_sec=2.0, burst=2, use_redis=False)
    assert lb.acquire("k") and lb.acquire("k")
    assert lb.acquire("k") is False
    clock["now"] = 0.5  # 1 token refilled
    assert lb.acquire("k") is True
    assert lb.acquire("k") is False  # only half->1 token was available
    clock["now"] = 1.5  # 2 more tokens (capped at capacity 2)
    assert lb.acquire("k") and lb.acquire("k")
    assert lb.acquire("k") is False


def test_token_bucket_refill_capped_at_capacity(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(pcache.time, "time", lambda: clock["now"])
    lb = TokenBucketLimiter(rate_per_sec=100.0, burst=2, use_redis=False)
    lb.acquire("k"); lb.acquire("k")
    assert lb.acquire("k") is False
    clock["now"] = 60.0  # an hour of refill cannot exceed capacity
    assert lb.acquire("k") is True
    assert lb.acquire("k") is True
    assert lb.acquire("k") is False


def test_token_bucket_cost_greater_than_tokens_returns_false(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(pcache.time, "time", lambda: clock["now"])
    lb = TokenBucketLimiter(rate_per_sec=0.0, burst=2, use_redis=False)
    assert lb.acquire("k", cost=3) is False  # 3 > capacity 2
    assert lb.acquire("k", cost=2) is True
    assert lb.acquire("k", cost=0.5) is False  # drained


def test_token_bucket_cost_zero_always_true(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(pcache.time, "time", lambda: clock["now"])
    lb = TokenBucketLimiter(rate_per_sec=0.0, burst=1, use_redis=False)
    lb.acquire("k")  # drain
    assert lb.acquire("k", cost=0) is True  # zero-cost always granted (current)


def test_token_bucket_negative_cost_returns_true_when_drained(monkeypatch):
    # CURRENT behavior (see test_bugs.py: negative cost should be rejected).
    clock = {"now": 0.0}
    monkeypatch.setattr(pcache.time, "time", lambda: clock["now"])
    lb = TokenBucketLimiter(rate_per_sec=0.0, burst=1, use_redis=False)
    lb.acquire("k")  # drain
    assert lb.acquire("k", cost=-10) is True


def test_token_bucket_different_keys_independent(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(pcache.time, "time", lambda: clock["now"])
    lb = TokenBucketLimiter(rate_per_sec=0.0, burst=1, use_redis=False)
    assert lb.acquire("jikan") is True
    assert lb.acquire("jikan") is False
    assert lb.acquire("youtube") is True  # separate bucket
    assert lb.acquire("youtube") is False


def test_token_bucket_wait_succeeds_when_capacity_available():
    lb = TokenBucketLimiter(rate_per_sec=10, burst=5, use_redis=False)
    assert lb.wait("k") is None  # immediate, no sleeping


def test_token_bucket_wait_raises_provider_error_after_timeout(monkeypatch):
    clock = {"now": 100.0}

    def advancing_time() -> float:
        clock["now"] += 1.0  # every look at the clock moves it forward
        return clock["now"]

    monkeypatch.setattr(pcache.time, "time", advancing_time)
    monkeypatch.setattr(pcache.time, "sleep", lambda s: None)  # never really sleep
    lb = TokenBucketLimiter(rate_per_sec=0.0, burst=1, use_redis=False)
    assert lb.acquire("k") is True  # drain the only token, rate=0 -> no refill
    with pytest.raises(ProviderError, match="rate limit timeout"):
        lb.wait("k", timeout=0.2)


def test_token_bucket_use_redis_with_failing_import_falls_back(monkeypatch, no_redis_env):
    # sys.modules entry None makes `import redis` raise ImportError inside the
    # constructor -> must silently fall back to the in-process bucket.
    monkeypatch.setitem(sys.modules, "redis", None)
    lb = TokenBucketLimiter(rate_per_sec=5, use_redis=True)
    assert lb._redis is None
    assert lb.acquire("k") is True  # in-process path works


def test_token_bucket_use_redis_unreachable_server_falls_back(no_redis_env):
    # Real redis-py is installed but the port is closed offline -> silent
    # fallback to the in-process bucket (no raise at construction or use).
    lb = TokenBucketLimiter(rate_per_sec=5, redis_url="redis://127.0.0.1:1/0",
                            use_redis=True)
    assert lb._redis is None
    assert lb.acquire("k") is True


def test_token_bucket_satisfies_rate_limiter_protocol():
    assert isinstance(TokenBucketLimiter(use_redis=False), RateLimiter)


def test_local_cache_via_registry(reg):
    c = reg.create("cache", "local")
    c.set("x", 1, ttl=60)
    assert c.get("x") == 1
    assert isinstance(c, Cache)


def test_token_bucket_via_registry(reg):
    lb = reg.create("limiter", "token_bucket", rate_per_sec=100, use_redis=False)
    assert lb.acquire("zzz_registry_key") is True
    assert isinstance(lb, RateLimiter)
