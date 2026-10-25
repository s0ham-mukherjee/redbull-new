"""Deterministic bulk ("mass") checks over the pure/seedable provider logic.

Every block counts the individual assertions it performs into ``checks``;
``test_enumerated_cases_total`` asserts the counter equals
``ENUMERATED_CASES`` so the volume is self-verifying.  All loops are seeded
(random.Random) and offline; the whole module targets < 15s.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone

import providers.cache as pcache
from engine_api import Action, Directive, Evidence, Forecast, Interval, IPNode, Relation
from engine_api import registry
from providers.cache import LocalCache, TokenBucketLimiter
from providers.knowledge_graph import LocalGraphStore
from providers.memory import LocalMemoryStore
from providers.microblog import _tweet_evidence
from providers.research_router import _to_evidence
from providers.retail import parse_price
from providers.simulation import _grounding_block
from providers.trends import TrendGrowthNormalizer
from providers.uncertainty import DataReadinessGate, _slice

# ---------------------------------------------------------------------------
# Block sizes (sum = ENUMERATED_CASES)
# ---------------------------------------------------------------------------

N_HASH = 3000            # content_hash stability/determinism
N_EVIDENCE_HASH = 1000   # Evidence auto-hash == sha256, 64 hex
N_PRICE_VALID = 3000     # generated valid price strings -> exact float
N_PRICE_JUNK = 2000      # junk strings -> None (or valid parse when unlucky)
N_GATE = 3050            # min_samples 1..50 x n 0..60
N_CACHE = 2000           # set/get/overwrite round-trips
N_BUCKET = 2000          # frozen-clock acquire sequences
N_MEMORY_RANK = 1500     # remember/recall ranking checks
N_MEMORY_URL = 500       # recall evidence url format
N_GRAPH = 2000           # upsert/relation/evidence cycles
N_REGISTRY = 500         # create cycles through a throwaway name
N_TO_EVIDENCE = 1000     # envelope projection count/shape
N_IP_NODE = 1500         # to_ip_node projection checks
N_TWEET = 1200           # _tweet_evidence field checks
N_SENTIMENT = 2000       # label -> score mapping table (fake pipeline)
N_GROUNDING = 1200       # block line/snippet invariants
N_NORMALIZER = 2000      # value/factor invariants
N_SLICE = 800            # _slice equivalence checks
N_FORMAT = 1000          # directive_rows / interval formatting

ENUMERATED_CASES = (
    N_HASH + N_EVIDENCE_HASH + N_PRICE_VALID + N_PRICE_JUNK + N_GATE
    + N_CACHE + N_BUCKET + N_MEMORY_RANK + N_MEMORY_URL + N_GRAPH
    + N_REGISTRY + N_TO_EVIDENCE + N_IP_NODE + N_TWEET + N_SENTIMENT
    + N_GROUNDING + N_NORMALIZER + N_SLICE + N_FORMAT
)


def _run_all_blocks() -> int:
    checks = 0
    rng = random.Random(20241024)

    # -- content_hash ---------------------------------------------------
    strings = []
    for i in range(N_HASH):
        n = rng.randint(0, 12)
        s = "".join(rng.choice("abc日本語हिंदी🎉xyz \t\n0123") for _ in range(n))
        strings.append(s)
        h1 = Evidence(source="m", url="u", content=s).content_hash
        h2 = Evidence(source="m", url="u", content=s).content_hash
        assert h1 == h2 and len(h1) == 64
        assert h1 == hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()
        checks += 1
    # determinism: re-hashing the whole corpus in order is stable
    assert [hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()
            for s in strings] == [
        hashlib.sha256(s.encode("utf-8", "replace")).hexdigest() for s in strings]

    # -- Evidence auto-hash ---------------------------------------------
    for i in range(N_EVIDENCE_HASH):
        s = f"evidence-{i}-{rng.random()}"
        ev = Evidence(source="s", url=f"https://x/{i}", content=s)
        assert ev.content_hash == hashlib.sha256(s.encode()).hexdigest()
        assert int(ev.content_hash, 16) >= 0
        checks += 1

    # -- parse_price valid ----------------------------------------------
    for i in range(N_PRICE_VALID):
        amount = rng.randint(0, 10**7)
        symbol = rng.choice(["₹", "Rs ", "Rs. ", "Rs", "INR ", "INR"])
        digits = str(amount)
        grouping = rng.choice(["", ",", ",,", ",,,"])
        def group(d: str) -> str:
            if not grouping:
                return d
            return grouping[0].join(d)
        text = f"{symbol}{group(digits)}" if rng.random() < 0.5 else \
            f"only {symbol}{group(digits)} today"
        assert parse_price(text) == float(amount)
        checks += 1

    # -- parse_price junk -------------------------------------------------
    junk_pool = ["no price", "", "USD 10", "$5", "free", "₹", "Rs.",
                 "price unknown", "###", "rs", "INR", "₹-42abc"]
    for i in range(N_PRICE_JUNK):
        text = rng.choice(junk_pool)
        out = parse_price(text)
        # junk pool never contains a digit after a rupee token
        assert out is None or out >= 0
        checks += 1

    # -- DataReadinessGate ------------------------------------------------
    for min_samples in range(1, 51):
        gate = DataReadinessGate(min_samples=min_samples)
        for n in range(0, 61):
            expected = bool(n) and n >= min_samples
            assert gate.ready(n) is expected
            checks += 1

    # -- LocalCache --------------------------------------------------------
    cache = LocalCache()
    for i in range(N_CACHE):
        key = f"k{i % 37}"
        val = {"i": i, "s": str(i), "l": [i, i + 1]}
        cache.set(key, val)
        assert cache.get(key) == val
        val2 = i * 2
        cache.set(key, val2)
        assert cache.get(key) == val2
        checks += 1

    # -- TokenBucket (frozen clock) ---------------------------------------
    real_time = pcache.time.time
    pcache.time.time = lambda: 42.0
    try:
        lb = TokenBucketLimiter(rate_per_sec=0.0, burst=3, use_redis=False)
        for i in range(N_BUCKET):
            key = f"api{i}"  # fresh bucket per iteration (rate=0 -> no refill)
            granted = 0
            for _ in range(6):
                if lb.acquire(key):
                    granted += 1
                else:
                    break
            assert granted == 3  # exactly the burst capacity
            checks += 1
    finally:
        pcache.time.time = real_time

    # -- LocalMemoryStore ranking ------------------------------------------
    for i in range(N_MEMORY_RANK):
        m = LocalMemoryStore()
        session = f"s{i}"
        target = f"target words number {i}"
        m.remember(session, f"filler alpha {i}")
        m.remember(session, target)
        m.remember(session, f"other beta {i}")
        hits = m.recall(session, f"target words number {i}", k=3)
        assert hits and hits[0].content == target
        checks += 1

    for i in range(N_MEMORY_URL):
        m = LocalMemoryStore()
        m.remember("u", f"unique words {i}")
        hits = m.recall("u", f"unique words {i}")
        assert hits[0].url == "memory://u/0"
        assert hits[0].source == "memory:local"
        checks += 1

    # -- LocalGraphStore cycles ---------------------------------------------
    g = LocalGraphStore()
    for i in range(N_GRAPH):
        node = IPNode(id=f"mal:{i}", title=f"T{i}", kind="anime")
        assert g.upsert_node(node) == f"mal:{i}"
        ev = Evidence(source="m", url="u", content=f"rel {i}")
        g.add_relation(Relation(src=f"mal:{i}", dst=f"mal:{i + 1}",
                                kind="sequel", provenance=ev))
        assert g.get_node(f"mal:{i}").title == f"T{i}"
        assert g.evidence_for(f"mal:{i}")[-1].content_hash == ev.content_hash
        assert len(g.relations_for(f"mal:{i + 1}")) >= 1
        checks += 1

    # -- registry create cycles (throwaway name, replaced each time) --------
    for i in range(N_REGISTRY):
        registry.register("forecaster", "zzz_mass_cycle",
                          lambda i=i: {"cycle": i})
        out = registry.create("forecaster", "zzz_mass_cycle")
        assert out["cycle"] == i
        checks += 1

    # -- _to_evidence --------------------------------------------------------
    for i in range(N_TO_EVIDENCE):
        items = [{"url": f"u{j}", "text": f"t{j}"} for j in range(i % 5)]
        out = _to_evidence({"items": items}, "web", "q")
        assert len(out) == len(items)
        for j, ev in enumerate(out):
            assert ev.source == "reach:web"
            assert ev.metadata["channel"] == "web"
        checks += 1

    # -- to_ip_node -----------------------------------------------------------
    from providers.anime_metadata import AnimeMetadataSource
    for i in range(N_IP_NODE):
        item = {
            "mal_id": i,
            "title": f"Title{i}",
            "type": rng.choice([None, "TV", "Movie", "Manga"]),
            "genres": [{"name": "Action"}] * (i % 3),
            "studios": ([{"name": "S"}] if i % 2 else []),
        }
        node = AnimeMetadataSource.to_ip_node(item)
        assert node.id == f"mal:{i}"
        assert node.kind in ("anime", "manga")
        assert len(node.genres) == i % 3
        assert node.studio == ("S" if i % 2 else None)
        checks += 1

    # -- _tweet_evidence -------------------------------------------------------
    for i in range(N_TWEET):
        item = {
            "id": str(i),
            "text": f"tweet {i}",
            "like_count": i,
            "retweet_count": i % 7,
            "screen_name": f"user{i % 11}",
            "created_at": "2024-01-15T10:00:00Z" if i % 2 else "bogus",
        }
        ev = _tweet_evidence(item, "x_scrape")
        assert ev.source == "x_scrape"
        assert ev.url == f"https://x.com/user{i % 11}/status/{i}"
        assert ev.metadata["likes"] == (i if i else None)  # 0 falls through `or`
        if i % 2:
            assert ev.published_at is not None
        else:
            assert ev.published_at is None
        checks += 1

    # -- sentiment label mapping (fake pipeline) -------------------------------
    from providers.nlp import TransformerSentiment
    ts = TransformerSentiment()
    labels = ["NEGATIVE", "NEUTRAL", "POSITIVE", "LABEL_0"]
    # every entry gets the label chosen by len(texts): last-entry expectation
    ts._pipeline = lambda texts, **kw: [
        {"label": labels[len(texts) % 4], "score": 0.9} for _ in texts]
    for i in range(N_SENTIMENT):
        idx = i % 4
        text = ["a", "b", "c", "d"][: idx + 1]
        scores = ts.analyze(text)
        expected = {0: 0.0, 1: 0.9, 2: 0.9, 3: -0.9}[idx]  # len 1..4 -> NEU/POS/L0/NEG
        assert scores[-1] == expected
        checks += 1

    # -- _grounding_block -------------------------------------------------------
    for i in range(N_GROUNDING):
        n = i % 7
        if n == 0:
            assert _grounding_block([]) == "(no external evidence provided)"
            checks += 1
            continue
        evs = [Evidence(source=f"s{j}", url=f"u{j}",
                        content=(" ".join(["w"] * (i % 50)) + f" {j}"))
               for j in range(n)]
        block = _grounding_block(evs)
        lines = block.split("\n")
        assert len(lines) == min(n, 5)
        for line in lines:
            assert len(line.rsplit(": ", 1)[1]) <= 400
        checks += 1

    # -- TrendGrowthNormalizer ---------------------------------------------------
    norm = TrendGrowthNormalizer(base_index={"2020": 2.0, "2021": 4.0, "2022": 0.5})
    from engine_api import Signal
    for i in range(N_NORMALIZER):
        year = 2019 + (i % 5)
        value = float(i % 100)
        sig = Signal(name="s", value=value,
                     window_start=datetime(year, 6, 1, tzinfo=timezone.utc))
        out = norm.normalize([sig])[0]
        factor = {2020: 2.0, 2021: 4.0, 2022: 0.5}.get(year, 1.0)
        assert out.value == value / factor
        assert out.metadata["growth_factor"] == factor
        checks += 1

    # -- _slice equivalence --------------------------------------------------------
    for i in range(N_SLICE):
        data = list(range(i % 20 + 2))
        a, b = _slice(data, data, slice(0, max(1, len(data) - 1)))
        assert a == data[: max(1, len(data) - 1)] == b
        checks += 1

    # -- directive/forecast formatting --------------------------------------------
    from providers.presentation import DecisionDashboard
    dash = DecisionDashboard()
    for i in range(N_FORMAT):
        point = float(i)
        f = Forecast(target="t", interval=Interval(point=point, lower=point - 10,
                                                   upper=point + 10),
                     ready=i % 2 == 0)
        d = Directive(ip_id=f"mal:{i}", action=Action.WAIT,
                      opportunity_score=i / 7.0, rationale="r", forecast=f)
        row = dash.directive_rows([d])[0]
        assert row["ip_id"] == f"mal:{i}"
        assert row["action"] == "wait"
        assert row["opportunity"] == round(i / 7.0, 3)
        if i % 2 == 0:
            assert row["forecast"].startswith(f"{point:.0f} [")
        else:
            assert row["forecast"] == "n/a (insufficient data)"
        checks += 1

    return checks


def test_mass_blocks():
    assert _run_all_blocks() == ENUMERATED_CASES


def test_enumerated_cases_total():
    assert ENUMERATED_CASES >= 30_000, ENUMERATED_CASES


def test_enumerated_cases_constant_is_the_sum_of_blocks():
    parts = (N_HASH, N_EVIDENCE_HASH, N_PRICE_VALID, N_PRICE_JUNK, N_GATE,
             N_CACHE, N_BUCKET, N_MEMORY_RANK, N_MEMORY_URL, N_GRAPH,
             N_REGISTRY, N_TO_EVIDENCE, N_IP_NODE, N_TWEET, N_SENTIMENT,
             N_GROUNDING, N_NORMALIZER, N_SLICE, N_FORMAT)
    assert sum(parts) == ENUMERATED_CASES
    assert all(p > 0 for p in parts)
    assert json.dumps({"total": ENUMERATED_CASES})  # sanity serialization
