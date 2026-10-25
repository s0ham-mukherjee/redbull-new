"""Property-based tests (hypothesis).

Profiles are registered in tests/conftest.py:
default=100 examples, thorough=300, exhaustive=1500, deadline=None.

No pytest fixtures are used inside @given tests (avoids the function-scoped
fixture health check); time patching is done manually with try/finally.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from hypothesis import given
from hypothesis import strategies as st

from engine_api import Evidence, IPNode, Query, Signal, content_hash
from engine_api.protocols import Cache
from providers.cache import LocalCache, TokenBucketLimiter
from providers.knowledge_graph import LocalGraphStore
from providers.memory import LocalMemoryStore
from providers.research_router import _to_evidence
from providers.retail import parse_price
from providers.simulation import _grounding_block
from providers.trends import TrendGrowthNormalizer
from providers.uncertainty import DataReadinessGate
from providers.microblog import _tweet_evidence

# -- shared strategies -------------------------------------------------------

text_st = st.text(alphabet=st.characters(min_codepoint=1, max_codepoint=0x2FFF),
                  max_size=64)
word_st = st.text(alphabet="abcdefghij", min_size=1, max_size=8)
words_st = st.lists(word_st, min_size=1, max_size=6).map(" ".join)
json_st = st.recursive(
    st.none() | st.booleans() | st.integers(-10**9, 10**9) | st.floats(allow_nan=False),
    lambda children: st.lists(children, max_size=4)
    | st.dictionaries(st.text(min_size=1, max_size=8), children, max_size=4),
    max_leaves=8,
)


# ---------------------------------------------------------------------------
# content_hash / Evidence
# ---------------------------------------------------------------------------


@given(text_st)
def test_content_hash_deterministic_and_hex(text):
    h1, h2 = content_hash(text), content_hash(text)
    assert h1 == h2 and len(h1) == 64
    int(h1, 16)


@given(text_st)
def test_content_hash_matches_hashlib_for_bmp_text(text):
    import hashlib
    assert content_hash(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()


@given(st.tuples(text_st, text_st))
def test_content_hash_injective_enough(pair):
    a, b = pair
    if a != b:
        assert content_hash(a) != content_hash(b)


@given(text_st)
def test_evidence_auto_hash_covers_content(text):
    ev = Evidence(source="s", url="u", content=text)
    assert ev.content_hash == content_hash(text)
    assert ev.content_hash != content_hash(text + "!")


# ---------------------------------------------------------------------------
# Registry round-trip (throwaway kind, single name)
# ---------------------------------------------------------------------------


@given(st.integers(-1000, 1000), st.text(min_size=0, max_size=10))
def test_registry_create_round_trip(n, s):
    from engine_api import registry
    marker = object()
    captured = {}

    def factory(**config):
        captured.update(config)
        return marker

    registry.register("tracker", "zzz_prop", factory)
    out = registry.create("tracker", "zzz_prop", n=n, s=s)
    assert out is marker
    assert captured == {"n": n, "s": s}


# ---------------------------------------------------------------------------
# LocalCache
# ---------------------------------------------------------------------------


@given(st.text(min_size=1, max_size=12), json_st)
def test_local_cache_set_get_round_trip(key, value):
    c = LocalCache()
    c.set(key, value)
    assert c.get(key) == value


@given(st.text(min_size=1, max_size=12), json_st, json_st)
def test_local_cache_overwrite_last_wins(key, v1, v2):
    c = LocalCache()
    c.set(key, v1)
    c.set(key, v2)
    assert c.get(key) == v2


@given(st.integers(1, 10_000), st.integers(0, 5000))
def test_local_cache_ttl_boundary(ttl, advance):
    real_time = time.time
    clock = {"t": 1000.0}
    time.time = lambda: clock["t"]
    try:
        c = LocalCache()
        c.set("k", "v", ttl=ttl)
        clock["t"] = 1000.0 + advance
        got = c.get("k")
        if advance > ttl:
            assert got is None
        else:  # strictly-before-or-equal still returns the value
            assert got == "v"
    finally:
        time.time = real_time


def test_local_cache_protocol_instance():
    assert isinstance(LocalCache(), Cache)


# ---------------------------------------------------------------------------
# TokenBucket conservation
# ---------------------------------------------------------------------------


@given(st.floats(min_value=0.5, max_value=8.0, allow_nan=False),
       st.floats(min_value=0.0, max_value=2.0, allow_nan=False),
       st.booleans())
def test_token_bucket_never_grants_more_than_capacity(rate, cost, drain_first):
    real_time = time.time
    time.time = lambda: 500.0  # frozen clock: no refill can happen
    try:
        lb = TokenBucketLimiter(rate_per_sec=rate, use_redis=False)  # burst=rate
        granted = 0.0
        if drain_first and lb.acquire("k"):
            granted += 1.0
        for _ in range(60):
            if lb.acquire("k", cost=cost):
                granted += cost
            else:
                break
        assert granted <= max(1.0, rate) + 1e-9
    finally:
        time.time = real_time


@given(st.floats(min_value=0.0, max_value=5.0, allow_nan=False))
def test_token_bucket_independent_keys(cost):
    real_time = time.time
    time.time = lambda: 7.0
    try:
        lb = TokenBucketLimiter(rate_per_sec=0.0, burst=1, use_redis=False)
        assert lb.acquire("a") is True
        # draining "a" must not affect a fresh key
        assert lb.acquire("b", cost=cost) is (cost <= 1.0)
    finally:
        time.time = real_time


# ---------------------------------------------------------------------------
# LocalMemoryStore ranking
# ---------------------------------------------------------------------------


@given(st.lists(words_st, min_size=1, max_size=5, unique=True),
       st.integers(1, 5))
def test_memory_recall_top_hit_has_max_overlap(entries, k):
    m = LocalMemoryStore()
    for idx, e in enumerate(entries):
        m.remember("s", e)
    query = entries[-1]  # exactly matches the last stored entry
    hits = m.recall("s", query, k=k)
    assert hits, "the exactly-matching entry must be recalled"
    top_words = set(hits[0].content.lower().split())
    query_words = set(query.lower().split())
    best_possible = max(len(set(e.lower().split()) & query_words) for e in entries)
    assert len(top_words & query_words) == best_possible


@given(words_st, st.dictionaries(st.text(min_size=1, max_size=6),
                                 st.integers(), max_size=4))
def test_memory_round_trip_metadata(text, metadata):
    m = LocalMemoryStore()
    m.remember("s", text, metadata)
    hits = m.recall("s", text)
    assert len(hits) == 1
    assert hits[0].content == text
    assert hits[0].metadata == metadata


# ---------------------------------------------------------------------------
# LocalGraphStore
# ---------------------------------------------------------------------------


@given(st.lists(st.text(alphabet="xyz", min_size=3, max_size=5), min_size=1,
                max_size=8, unique=True))
def test_graph_upsert_get_all_ids_round_trip(ids):
    g = LocalGraphStore()
    for nid in ids:
        g.upsert_node(IPNode(id=nid, title=f"title-{nid}"))
    assert g.all_ids() == sorted(ids)
    for nid in ids:
        assert g.get_node(nid).title == f"title-{nid}"


@given(st.text(alphabet="abc", min_size=1, max_size=5))
def test_graph_evidence_for_unknown_empty(node_id):
    assert LocalGraphStore().evidence_for(node_id) == []


# ---------------------------------------------------------------------------
# DataReadinessGate
# ---------------------------------------------------------------------------


@given(st.integers(1, 200), st.integers(0, 100), st.integers(0, 200))
def test_gate_ready_monotone_in_n(n, low, high):
    gate = DataReadinessGate(min_samples=low)
    # ready() is monotone in n for n >= 1 (n=0 is always False because of
    # the `bool(n_samples)` truthiness guard – see unit tests)
    if high >= n and gate.ready(n):
        assert gate.ready(high)
    assert gate.ready(0) is False


@given(st.integers(0, 300), st.integers(-3, 60))
def test_gate_forecast_echo_and_threshold(n, min_samples):
    gate = DataReadinessGate(min_samples=max(min_samples, 1))
    from engine_api import Interval
    f = gate.forecast("t", 0.0, Interval(point=0, lower=0, upper=1), n)
    assert f.n_calibration_samples == n
    assert f.ready == gate.ready(n)
    assert (f.reason is None) is f.ready


# ---------------------------------------------------------------------------
# parse_price
# ---------------------------------------------------------------------------


PRINTABLE_ALPHABET = (
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    " .,;:!?₹$%-_@#()'\"/\\\n\t"
)


@given(st.text(alphabet=PRINTABLE_ALPHABET, max_size=64))
def test_parse_price_never_raises(text):
    out = parse_price(text)
    assert out is None or out >= 0


@given(st.integers(min_value=0, max_value=10**9),
       st.lists(st.sampled_from([",", ""]), min_size=0, max_size=4).map("".join))
def test_parse_price_rupee_int_round_trip(n, sep):
    text = f"₹{sep.join(str(n))}"
    assert parse_price(text) == float(n)


@given(st.integers(min_value=1, max_value=10**6), st.integers(min_value=1, max_value=10**6))
def test_parse_price_first_match(a, b):
    assert parse_price(f"Rs {a} and Rs {b}") == float(a)


# ---------------------------------------------------------------------------
# _to_evidence
# ---------------------------------------------------------------------------


@given(st.lists(st.one_of(
    st.dictionaries(st.text(min_size=1, max_size=8), st.text(max_size=20), max_size=3),
    st.integers(), st.text(max_size=10)), max_size=10))
def test_to_evidence_preserves_count(items):
    out = _to_evidence({"items": items}, "web", "q")
    assert len(out) == len(items)


# ---------------------------------------------------------------------------
# _tweet_evidence robustness
# ---------------------------------------------------------------------------


@given(st.dictionaries(st.sampled_from(
        ["id", "text", "url", "created_at", "like_count", "retweet_count",
         "view_count", "screen_name", "username", "author", "_query"]),
        st.one_of(st.text(max_size=16), st.none()),
        max_size=6))
def test_tweet_evidence_never_raises(item):
    ev = _tweet_evidence(item, "x_prop")
    assert isinstance(ev.url, str) and ev.url
    assert isinstance(ev.content, str)


# ---------------------------------------------------------------------------
# TrendGrowthNormalizer
# ---------------------------------------------------------------------------


@given(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
       st.floats(min_value=1e-6, max_value=1000.0, allow_nan=False),
       st.integers(1900, 2100))
def test_normalizer_divides_by_factor(value, factor, year):
    norm = TrendGrowthNormalizer(base_index={str(year): factor})
    sig = Signal(name="n", value=value,
                 window_start=datetime(year, 3, 3, tzinfo=timezone.utc))
    out = norm.normalize([sig])
    assert out[0].value == value / factor
    assert out[0].name == "n:normalized"
    assert out[0].metadata["growth_factor"] == factor


@given(st.lists(st.tuples(st.floats(min_value=-100, max_value=100, allow_nan=False),
                          st.integers(1900, 2100)), min_size=0, max_size=10))
def test_normalizer_preserves_length_and_order(pairs):
    norm = TrendGrowthNormalizer(base_index={"2000": 2.0})
    sigs = [Signal(name=f"s{i}", value=v,
                   window_start=datetime(y, 1, 1, tzinfo=timezone.utc))
            for i, (v, y) in enumerate(pairs)]
    out = norm.normalize(sigs)
    assert len(out) == len(pairs)
    for s, (v, y) in zip(out, pairs):
        assert s.value == v / (2.0 if y == 2000 else 1.0)


# ---------------------------------------------------------------------------
# _grounding_block
# ---------------------------------------------------------------------------


@given(st.lists(st.text(alphabet="abc xyz\n\t", min_size=0, max_size=80), max_size=8))
def test_grounding_block_line_count_and_prefix(contents):
    evs = [Evidence(source="s", url="u", content=c) for c in contents]
    block = _grounding_block(evs)
    lines = block.split("\n") if evs else [block]
    if not evs:
        assert block == "(no external evidence provided)"
    else:
        assert len(lines) == min(len(evs), 5)
        for line in lines:
            assert line.startswith("- (s) u: ")
            snippet = line[len("- (s) u: "):]
            assert len(snippet) <= 400
            assert "\n" not in snippet and "  " not in snippet


# ---------------------------------------------------------------------------
# Query default isolation
# ---------------------------------------------------------------------------


@given(text_st)
def test_query_extra_isolated(text):
    q1, q2 = Query(text=text), Query(text=text)
    q1.extra["mutated"] = True
    assert q2.extra == {}
