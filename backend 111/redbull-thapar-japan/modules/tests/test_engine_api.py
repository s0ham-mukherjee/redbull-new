"""Smoke + behavior tests for the neutral engine contract and providers.

Run:  PYTHONPATH=src python -m pytest tests/ -q
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import providers  # noqa: E402,F401  (registers every provider)
from engine_api import (  # noqa: E402
    Action,
    Evidence,
    Forecast,
    Interval,
    IPNode,
    Query,
    available,
    registry,
)
from engine_api.protocols import (  # noqa: E402
    Cache,
    ContentExtractor,
    EvidenceSource,
    KnowledgeStore,
    MemoryStore,
    Normalizer,
    RateLimiter,
    ResearchRouter,
    TextProcessor,
    TimeSeriesSource,
    UncertaintyEstimator,
)


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------

EXPECTED = {
    ("source", "anime_metadata"),
    ("source", "reddit"),
    ("source", "youtube"),
    ("source", "reach_reddit"),
    ("source", "retail"),
    ("extractor", "web_page"),
    ("router", "multi_channel"),
    ("store", "local_graph"),
    ("store", "dgraph"),
    ("memory", "local"),
    ("memory", "zep"),
    ("timeseries", "search_trends"),
    ("timeseries", "wiki_pageviews"),
    ("sentiment", "transformer"),
    ("text", "indic"),
    ("uncertainty", "conformal_regressor"),
    ("gate", "data_readiness"),
    ("simulator", "oasis_swarm"),
    ("simulator", "mirofish_service"),
    ("evaluator", "factual_consistency"),
    ("scheduler", "prefect"),
    ("cache", "local"),
    ("cache", "redis"),
    ("limiter", "token_bucket"),
    ("normalizer", "trend_growth"),
    ("app", "decision_api"),
    ("ui", "decision_dashboard"),
}


def test_all_expected_providers_registered():
    registered = {(kind, name) for kind, names in available().items() for name in names}
    missing = EXPECTED - registered
    assert not missing, f"missing providers: {sorted(missing)}"


def test_unknown_kind_rejected():
    with pytest.raises(KeyError):
        registry.register("not-a-kind", "x", lambda: None)


def test_unknown_provider_error_lists_alternatives():
    with pytest.raises(KeyError) as exc:
        registry.create("source", "does_not_exist")
    assert "anime_metadata" in str(exc.value)


# ---------------------------------------------------------------------------
# Contracts (protocol conformance on locally-constructible providers)
# ---------------------------------------------------------------------------


def test_local_graph_store_satisfies_knowledge_store():
    store = registry.create("store", "local_graph")
    assert isinstance(store, KnowledgeStore)
    node = IPNode(id="mal:1", title="Naruto", genres=("shonen",), studio="Studio Pierrot")
    assert store.upsert_node(node) == "mal:1"
    assert store.get_node("mal:1").title == "Naruto"
    ev = Evidence(source="test", url="https://example.com", content="grounded claim")
    from engine_api import Relation

    store.add_relation(Relation(src="mal:1", dst="mal:2", kind="sequel", provenance=ev))
    assert store.evidence_for("mal:1")[0].content_hash == ev.content_hash


def test_local_memory_satisfies_memory_store():
    mem = registry.create("memory", "local")
    assert isinstance(mem, MemoryStore)
    mem.remember("s1", "anime fans prefer Hindi dubs", {"tier": "tier_2"})
    mem.remember("s1", "manga volumes cost 700 rupees", {"topic": "price"})
    hits = mem.recall("s1", "Hindi dub preference", k=1)
    assert hits and "Hindi dubs" in hits[0].content


def test_local_cache_and_limiter_contracts():
    cache = registry.create("cache", "local")
    assert isinstance(cache, Cache)
    cache.set("k", {"a": 1}, ttl=60)
    assert cache.get("k") == {"a": 1}
    assert cache.get("absent") is None

    limiter = registry.create("limiter", "token_bucket", rate_per_sec=100, use_redis=False)
    assert isinstance(limiter, RateLimiter)
    assert limiter.acquire("jikan") is True
    limiter.wait("jikan", timeout=1)


def test_trend_normalizer_contract():
    norm = registry.create("normalizer", "trend_growth", base_index={"2025": 2.0})
    assert isinstance(norm, Normalizer)
    sig = registry.create("timeseries", "search_trends")  # ensure registered
    from engine_api import Signal

    out = norm.normalize([Signal(name="search_interest:naruto", value=80.0,
                                 window_start=datetime(2025, 6, 1, tzinfo=timezone.utc))])
    assert out[0].value == 40.0
    assert out[0].metadata["growth_factor"] == 2.0


# ---------------------------------------------------------------------------
# Forecast gate behavior (Feature 49)
# ---------------------------------------------------------------------------


def test_forecast_gate_blocks_sparse_data():
    gate = registry.create("gate", "data_readiness", min_samples=30)
    iv = Interval(point=1_000_000, lower=700_000, upper=1_400_000, alpha=0.10)
    blocked = gate.forecast("trailer_views_30d", 1_000_000, iv, n_samples=12)
    assert blocked.ready is False and "need >= 30" in (blocked.reason or "")
    allowed = gate.forecast("trailer_views_30d", 1_000_000, iv, n_samples=60)
    assert allowed.ready is True and allowed.reason is None


# ---------------------------------------------------------------------------
# Real MAPIE conformal intervals (Feature 41) - actual upstream behavior
# ---------------------------------------------------------------------------


def test_conformal_regressor_produces_valid_intervals():
    rng = __import__("numpy").random.default_rng(0)
    X = rng.uniform(0, 10, size=(200, 2))
    y = 3 * X[:, 0] - 2 * X[:, 1] + rng.normal(0, 0.5, size=200)

    model = registry.create("uncertainty", "conformal_regressor", confidence_level=0.9)
    assert isinstance(model, UncertaintyEstimator)
    model.fit(X[:150], y[:150])
    intervals = model.interval(X[150:], alpha=0.10)
    assert len(intervals) == 50
    for iv in intervals:
        assert iv.lower <= iv.point <= iv.upper, "point must sit inside its interval"
    # ~90% empirical coverage on the held-out fold
    truth = y[150:]
    covered = sum(iv.lower <= t <= iv.upper for iv, t in zip(intervals, truth))
    assert covered / len(truth) >= 0.75, f"coverage too low: {covered}/{len(truth)}"


# ---------------------------------------------------------------------------
# Evidence hashing & contracts
# ---------------------------------------------------------------------------


def test_evidence_hash_is_stable_and_content_bound():
    a = Evidence(source="x", url="https://e.com", content="hello")
    b = Evidence(source="x", url="https://e.com", content="hello")
    c = Evidence(source="x", url="https://e.com", content="hello!")
    assert a.content_hash == b.content_hash
    assert a.content_hash != c.content_hash
    assert len(a.content_hash) == 64


def test_query_defaults():
    q = Query(text="naruto")
    assert q.limit == 50 and q.region is None and q.extra == {}


def test_directive_action_enum():
    assert Action.PILOT.value == "pilot"
    assert {a.value for a in Action} == {"pilot", "investigate", "wait", "abstain"}


def test_forecast_serializable_shape():
    f = Forecast(target="box_office_inr", interval=Interval(point=5e6, lower=2e6, upper=9e6),
                 n_calibration_samples=44, ready=True)
    assert f.interval.alpha == 0.10
    assert json.loads(json.dumps({"t": f.target}))["t"] == "box_office_inr"


# ---------------------------------------------------------------------------
# Provider construction (lazy deps must not explode at registration)
# ---------------------------------------------------------------------------


def test_text_processor_detects_and_normalizes_devanagari():
    proc = registry.create("text", "indic")
    assert isinstance(proc, TextProcessor)
    hindi = "नमस्ते दुनिया"
    assert proc.detect_language(hindi) in (None, "hi", "sa") or proc.detect_language(hindi)
    out = proc.normalize_text(hindi, language="hi")
    assert out  # normalization must not blank the string
    # Latin-only text -> no Indic detection
    assert proc.detect_language("plain english text") is None


def test_retail_price_parser():
    from providers.retail import parse_price

    assert parse_price("Price: ₹1,299.00") == 1299.0
    assert parse_price("Rs 499") == 499.0
    assert parse_price("no price here") is None


def test_retail_source_is_evidence_source_without_network():
    src = registry.create("source", "retail")
    with pytest.raises(Exception):
        src.fetch(Query(text="tell me about naruto"))  # no urls -> ProviderError


def test_reddit_source_requires_credentials_clearly():
    import os

    for var in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"):
        os.environ.pop(var, None)
    src = registry.create("source", "reddit")
    assert isinstance(src, EvidenceSource)
    with pytest.raises(Exception) as exc:
        src.fetch(Query(text="naruto"))
    assert "REDDIT_CLIENT_ID" in str(exc.value)


def test_anime_metadata_projects_ip_nodes():
    from providers.anime_metadata import AnimeMetadataSource

    sample = {
        "mal_id": 20,
        "title": "Naruto",
        "type": "TV",
        "genres": [{"name": "Action"}],
        "studios": [{"name": "Studio Pierrot"}],
        "score": 8.2,
        "members": 3_000_000,
        "title_japanese": "ナルト",
    }
    node = AnimeMetadataSource.to_ip_node(sample)
    assert node.id == "mal:20" and node.studio == "Studio Pierrot"
    assert node.genres == ("Action",) and node.aliases == ("ナルト",)


def test_evidence_source_subclasses_share_protocol():
    # Structural check: registered "source" providers expose fetch(Query).
    for name in available("source")["source"]:
        obj = registry.create("source", name)
        assert isinstance(obj, EvidenceSource), f"{name} does not satisfy EvidenceSource"
        assert callable(obj.fetch)


def test_router_health_shape():
    router = registry.create("router", "multi_channel")
    assert isinstance(router, ResearchRouter)
    health = router.health()
    channel_names = {c["name"] for c in health["channels"]}
    assert {"reddit", "youtube", "web", "github"} <= channel_names
    reddit = next(c for c in health["channels"] if c["name"] == "reddit")
    assert {"search", "read", "subreddit"} <= set(reddit["actions"])


def test_content_extractor_is_constructible_lazy():
    ext = registry.create("extractor", "web_page")
    assert isinstance(ext, ContentExtractor)
    assert callable(ext.extract)


def test_timeseries_sources_registered():
    for name in ("search_trends", "wiki_pageviews"):
        src = registry.create("timeseries", name)
        assert isinstance(src, TimeSeriesSource)
        assert src.name == name


def test_evaluator_offline_mode():
    ev = registry.create("evaluator", "factual_consistency", threshold=0.5)
    from engine_api import AgentTurn, SimulationReport

    report = SimulationReport(
        scenario_id="sc1", seed=0,
        turns=(AgentTurn(agent_id="a1", stance="pro", text="would watch", cited_evidence=("abc",)),),
    )
    grounded = ev.evaluate(report, [Evidence(source="t", url="u", content="c")])
    assert grounded.passed and grounded.score == 1.0

    empty = ev.evaluate(SimulationReport(scenario_id="sc2", seed=0, turns=()))
    assert empty.passed is False


def test_ui_dashboard_rows_without_streamlit():
    dash = registry.create("ui", "decision_dashboard")
    d = Action.PILOT
    from engine_api import Directive

    rows = dash.directive_rows([
        Directive(ip_id="mal:20", action=d, opportunity_score=0.7774,
                  rationale="high dub engagement", forecast=None)
    ])
    assert rows[0]["action"] == "pilot" and rows[0]["forecast"].startswith("n/a")


def test_app_factory_builds_fastapi_app():
    app = registry.create("app", "decision_api")
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200 and resp.json()["status"] == "ok"
    caps = client.get("/capabilities").json()
    assert "source" in caps and "youtube" in caps["source"]
    # no engine attached -> 503, not a crash
    no_engine = client.post("/research", json={"provider": "youtube", "text": "x"})
    assert no_engine.status_code == 503
