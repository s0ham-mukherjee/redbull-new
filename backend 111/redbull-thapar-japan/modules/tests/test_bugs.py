"""Known bugs, encoded as strict xfails.

Every test in this file describes the DESIRED behavior and is expected to
FAIL against the current production code (``xfail(strict=True)``).  When a
bug is fixed the test will XPASS and turn the suite red, forcing the
expectation to be updated.  All other tests in the suite assert the CURRENT
behavior, so the suite stays green.

Findings #2 and #8 come from BACKEND_MAP.md; the rest were found while
writing this test-suite (file:line references below).
"""

from __future__ import annotations

import numpy as np
import pytest

from engine_api import Query
from providers.cache import TokenBucketLimiter
from providers.memory import LocalMemoryStore
from providers.microblog import _tweet_evidence
from providers.trends import SearchTrendSource
from providers.uncertainty import ConformalRegressor


# ---------------------------------------------------------------------------
# BACKEND_MAP finding #2 — microblog.py:44
#   `"retweets": item.get("retweet_count") or item.get("retweet_count")`
#   The same key is written twice; the second expression was almost
#   certainly meant to be a fallback metric (e.g. item["retweets"]).
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="microblog.py:44 duplicate dict key; "
                                       "retweets should fall back to a secondary metric")
def test_tweet_evidence_retweets_should_fall_back_to_retweets_key():
    item = {"id": "1", "text": "t", "retweets": 9}  # no retweet_count
    ev = _tweet_evidence(item, "x_scrape")
    assert ev.metadata["retweets"] == 9  # desired: fallback picks it up


# ---------------------------------------------------------------------------
# BACKEND_MAP finding #8 — memory.py:47
#   `scored[: max(1, k)]` -> recall(k=0) returns one entry instead of none.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="memory.py:47 max(1, k); recall(k=0) "
                                       "should return an empty list")
def test_local_memory_recall_k_zero_should_return_empty():
    m = LocalMemoryStore()
    m.remember("s", "alpha beta")
    assert m.recall("s", "alpha beta", k=0) == []


# ---------------------------------------------------------------------------
# NEW — trends.py:79  `keyword = keywords[0]`
#   regional() guards only the empty *frame*, not the empty *keywords* list;
#   Query(text="") with a non-empty frame crashes with IndexError instead of
#   the actionable ProviderError that series() raises for the same input.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="trends.py:79 unguarded keywords[0]; empty "
                                       "query text should raise ProviderError")
def test_trends_regional_empty_text_should_raise_provider_error():
    import pandas as pd

    src = SearchTrendSource()
    src._client = lambda: _FakeRegionalClient(
        pd.DataFrame({"": [1.0]}, index=["MH"]))
    with pytest.raises(Exception, match="at least one keyword") as exc_info:
        src.regional(Query(text=""))
    assert not isinstance(exc_info.value, IndexError)


class _FakeRegionalClient:
    def __init__(self, frame):
        self.frame = frame

    def build_payload(self, keywords, **kw):
        pass

    def interest_by_region(self, **kw):
        return self.frame


# ---------------------------------------------------------------------------
# NEW — anime_metadata.py:89  `prev.get("entry", [{}])[0]`
#   An adaptation relation whose "entry" list is EMPTY (observed shape from
#   the Jikan API for removed/merged entries) raises IndexError instead of
#   leaving adaptation_of as None.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="anime_metadata.py:89 empty entry list "
                                       "should yield adaptation_of=None, not IndexError")
def test_to_ip_node_adaptation_with_empty_entry_list_should_be_none():
    from providers.anime_metadata import AnimeMetadataSource
    node = AnimeMetadataSource.to_ip_node({
        "mal_id": 1, "title": "X",
        "related": [{"relation": "Adaptation", "entry": []}],
    })
    assert node.adaptation_of is None


# ---------------------------------------------------------------------------
# NEW — uncertainty.py:68-71  confidence-changed error path
#   The error handler re-runs ``self.__init__(...)`` purely to update the
#   stored confidence, which also resets ``self._model`` to None.  The fitted
#   model is destroyed even though the user only asked for an alpha the
#   estimator was not fitted for.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="uncertainty.py:68 rejected alpha must not "
                                       "destroy the fitted model")
def test_conformal_state_should_survive_confidence_mismatch():
    rng = np.random.default_rng(77)
    X = rng.uniform(0, 10, size=(60, 1))
    y = 3 * X[:, 0] + rng.normal(0, 0.1, 60)
    m = ConformalRegressor(confidence_level=0.9)
    m.fit(X, y)
    try:
        m.interval(X, alpha=0.5)
    except Exception:
        pass  # the ProviderError itself is expected and asserted elsewhere
    # desired: the original fit still works with the original alpha
    intervals = m.interval(X, alpha=0.10)
    assert len(intervals) == 60


# ---------------------------------------------------------------------------
# NEW — cache.py:127-131  TokenBucketLimiter.acquire with negative cost
#   `if tokens >= cost` succeeds for any negative cost, so a caller passing
#   cost<0 is always granted (and can even inflate the stored token count).
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="cache.py:127 negative cost should be "
                                       "rejected instead of always granted")
def test_token_bucket_negative_cost_should_be_rejected():
    import providers.cache as pcache
    real_time = pcache.time.time
    pcache.time.time = lambda: 100.0
    try:
        lb = TokenBucketLimiter(rate_per_sec=0.0, burst=1, use_redis=False)
        lb.acquire("k")  # drain
        with pytest.raises(ValueError):
            lb.acquire("k", cost=-10)
    finally:
        pcache.time.time = real_time
