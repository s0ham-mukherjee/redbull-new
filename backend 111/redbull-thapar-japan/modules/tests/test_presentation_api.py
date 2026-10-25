"""FastAPI decision API (TestClient) + DecisionDashboard pure helpers."""

from __future__ import annotations

import sys
from datetime import datetime

import pytest

from engine_api import Action, Directive, Evidence, Forecast, Interval, available
from providers._bootstrap import ProviderError
from providers.presentation import DecisionDashboard, create_decision_api

EXPECTED_PAIRS = {
    ("source", "anime_metadata"), ("source", "reddit"), ("source", "youtube"),
    ("source", "reach_reddit"), ("source", "retail"),
    ("extractor", "web_page"), ("router", "multi_channel"),
    ("store", "local_graph"), ("store", "dgraph"),
    ("memory", "local"), ("memory", "zep"),
    ("timeseries", "search_trends"), ("timeseries", "wiki_pageviews"),
    ("sentiment", "transformer"), ("text", "indic"),
    ("uncertainty", "conformal_regressor"), ("gate", "data_readiness"),
    ("simulator", "oasis_swarm"), ("simulator", "mirofish_service"),
    ("evaluator", "factual_consistency"), ("scheduler", "prefect"),
    ("cache", "local"), ("cache", "redis"), ("limiter", "token_bucket"),
    ("normalizer", "trend_growth"), ("app", "decision_api"),
    ("ui", "decision_dashboard"),
}


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    return TestClient(create_decision_api())


@pytest.fixture()
def capture_client():
    """App whose engine_fetch records (kind, name, query) and returns nothing."""
    from fastapi.testclient import TestClient
    calls = []

    def engine_fetch(kind, name, query):
        calls.append((kind, name, query))
        return []

    return TestClient(create_decision_api(engine_fetch=engine_fetch)), calls


# ---------------------------------------------------------------------------
# /health and /capabilities
# ---------------------------------------------------------------------------


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_capabilities_equals_available_and_contains_all_27(client):
    resp = client.get("/capabilities")
    assert resp.status_code == 200
    caps = resp.json()
    assert caps == available()
    registered = {(k, n) for k, names in caps.items() for n in names}
    assert EXPECTED_PAIRS <= registered, f"missing: {sorted(EXPECTED_PAIRS - registered)}"
    assert len(EXPECTED_PAIRS) == 27


# ---------------------------------------------------------------------------
# /research
# ---------------------------------------------------------------------------


def test_research_without_engine_fetch_is_503(client):
    resp = client.post("/research", json={"provider": "youtube", "text": "x"})
    assert resp.status_code == 503
    assert "engine did not attach" in resp.json()["detail"]


def test_research_with_engine_fetch_empty_result(capture_client):
    tc, calls = capture_client
    resp = tc.post("/research", json={"provider": "youtube", "text": "naruto"})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"count": 0, "evidence": []}
    assert len(calls) == 1
    kind, name, query = calls[0]
    assert kind == "source" and name == "youtube"
    from engine_api import Query
    assert isinstance(query, Query) and query.text == "naruto"


def test_research_with_two_evidences_row_shape():
    from fastapi.testclient import TestClient
    evs = [
        Evidence(source="s1", url="https://a", content="alpha", title="A"),
        Evidence(source="s2", url="https://b", content="beta"),
    ]
    tc = TestClient(create_decision_api(engine_fetch=lambda k, n, q: evs))
    resp = tc.post("/research", json={"provider": "x"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    rows = body["evidence"]
    assert len(rows) == 2
    for row, ev in zip(rows, evs):
        assert set(row) == {"source", "url", "title", "content_hash", "retrieved_at"}
        assert row["source"] == ev.source
        assert row["url"] == ev.url
        assert row["title"] == ev.title
        assert row["content_hash"] == ev.content_hash
        assert len(row["content_hash"]) == 64
        datetime.fromisoformat(row["retrieved_at"])  # ISO-8601 round-trips


def test_research_keyerror_maps_to_404():
    from fastapi.testclient import TestClient

    def boom(kind, name, query):
        raise KeyError("no provider registered for kind='source' name='ghost'")

    tc = TestClient(create_decision_api(engine_fetch=boom))
    resp = tc.post("/research", json={"provider": "ghost"})
    assert resp.status_code == 404
    assert "ghost" in resp.json()["detail"]


def test_research_valueerror_maps_to_502():
    from fastapi.testclient import TestClient

    def boom(kind, name, query):
        raise ValueError("upstream exploded")

    tc = TestClient(create_decision_api(engine_fetch=boom))
    resp = tc.post("/research", json={"provider": "youtube"})
    assert resp.status_code == 502
    assert "upstream exploded" in resp.json()["detail"]


def test_research_missing_provider_is_422(capture_client):
    tc, calls = capture_client
    resp = tc.post("/research", json={"text": "hi"})
    assert resp.status_code == 422
    assert calls == []


def test_research_defaults_kind_source_limit_10_extra_empty(capture_client):
    tc, calls = capture_client
    resp = tc.post("/research", json={"provider": "youtube"})
    assert resp.status_code == 200
    kind, name, query = calls[0]
    assert kind == "source"
    assert name == "youtube"
    assert query.text == ""
    assert query.region is None
    assert query.limit == 10
    assert query.extra == {}


def test_research_field_mapping(capture_client):
    tc, calls = capture_client
    resp = tc.post("/research", json={
        "kind": "timeseries", "provider": "search_trends",
        "text": "naruto", "region": "IN", "limit": 3, "extra": {"geo": "IN"},
    })
    assert resp.status_code == 200
    kind, name, query = calls[0]
    assert (kind, name) == ("timeseries", "search_trends")
    assert query.text == "naruto"
    assert query.region == "IN"
    assert query.limit == 3
    assert query.extra == {"geo": "IN"}


@pytest.mark.parametrize("limit", [-3, 0, 10**12])
def test_research_limit_bounds_accepted_by_model_current_behavior(limit):
    # ints with no pydantic bounds: negative/zero/huge all pass through
    from fastapi.testclient import TestClient
    calls = []

    def fetch(kind, name, query):
        calls.append(query)
        return []

    tc = TestClient(create_decision_api(engine_fetch=fetch))
    resp = tc.post("/research", json={"provider": "x", "limit": limit})
    assert resp.status_code == 200
    assert calls[0].limit == limit


def test_research_extra_not_shared_between_requests(capture_client):
    tc, calls = capture_client
    tc.post("/research", json={"provider": "x", "extra": {"a": 1}})
    tc.post("/research", json={"provider": "x", "extra": {"b": 2}})
    tc.post("/research", json={"provider": "x"})
    extras = [query.extra for _, _, query in calls]
    assert extras == [{"a": 1}, {"b": 2}, {}]
    assert extras[0] is not extras[1]


def test_research_extra_non_dict_is_422(capture_client):
    tc, _ = capture_client
    resp = tc.post("/research", json={"provider": "x", "extra": ["not", "a", "dict"]})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# app factory
# ---------------------------------------------------------------------------


def test_custom_title_appears_in_app_title():
    app = create_decision_api(title="My Custom Decision API")
    assert app.title == "My Custom Decision API"
    assert create_decision_api().title == "SakuraScore Engine API"


def test_app_via_registry(reg):
    app = reg.create("app", "decision_api")
    from fastapi.testclient import TestClient
    assert TestClient(app).get("/health").json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# DecisionDashboard.directive_rows
# ---------------------------------------------------------------------------


def _directive(forecast=None, action=Action.PILOT, score=0.77777, ip="mal:1"):
    return Directive(ip_id=ip, action=action, opportunity_score=score,
                     rationale="r", forecast=forecast)


READY_FORECAST = Forecast(
    target="box_office_inr",
    interval=Interval(point=1_000_000.5, lower=700_000.4, upper=1_400_000.6),
    n_calibration_samples=44, ready=True,
)
NOT_READY_FORECAST = Forecast(
    target="box_office_inr",
    interval=Interval(point=1, lower=0, upper=2),
    ready=False, reason="only 3 historical target samples",
)


def test_directive_rows_forecast_none():
    rows = DecisionDashboard().directive_rows([_directive(forecast=None)])
    assert rows[0]["forecast"] == "n/a (insufficient data)"


def test_directive_rows_forecast_ready_formatted():
    rows = DecisionDashboard().directive_rows([_directive(forecast=READY_FORECAST)])
    assert rows[0]["forecast"] == "1000000 [700000, 1400001]"
    assert rows[0]["forecast"].startswith("1000000 [")


def test_directive_rows_forecast_not_ready_is_na():
    rows = DecisionDashboard().directive_rows([_directive(forecast=NOT_READY_FORECAST)])
    assert rows[0]["forecast"] == "n/a (insufficient data)"


@pytest.mark.parametrize("action,expected", [
    (Action.PILOT, "pilot"), (Action.INVESTIGATE, "investigate"),
    (Action.WAIT, "wait"), (Action.ABSTAIN, "abstain"),
])
def test_directive_rows_action_enum_to_value(action, expected):
    rows = DecisionDashboard().directive_rows([_directive(action=action)])
    assert rows[0]["action"] == expected


def test_directive_rows_opportunity_rounded_three_decimals():
    rows = DecisionDashboard().directive_rows([_directive(score=0.1234567)])
    assert rows[0]["opportunity"] == 0.123
    assert rows[0]["opportunity"] == round(0.1234567, 3)


def test_directive_rows_exact_keys_and_empty_list():
    dash = DecisionDashboard()
    assert dash.directive_rows([]) == []
    rows = dash.directive_rows([_directive()])
    assert set(rows[0]) == {"ip_id", "action", "opportunity", "forecast", "rationale"}
    assert rows[0]["ip_id"] == "mal:1"
    assert rows[0]["rationale"] == "r"


def test_directive_rows_order_preserved():
    ds = [_directive(ip=f"mal:{i}", score=i / 10) for i in range(5)]
    rows = DecisionDashboard().directive_rows(ds)
    assert [r["ip_id"] for r in rows] == [f"mal:{i}" for i in range(5)]


def test_directive_rows_via_registry(reg):
    dash = reg.create("ui", "decision_dashboard")
    rows = dash.directive_rows([_directive()])
    assert rows[0]["action"] == "pilot"


# ---------------------------------------------------------------------------
# render_* without streamlit
# ---------------------------------------------------------------------------


def test_render_directives_raises_without_streamlit(monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit", None)  # import -> ImportError
    with pytest.raises(ProviderError, match="streamlit unavailable"):
        DecisionDashboard().render_directives([_directive()])


def test_render_evidence_raises_without_streamlit(monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit", None)
    with pytest.raises(ProviderError, match="streamlit unavailable"):
        DecisionDashboard().render_evidence([Evidence(source="s", url="u", content="c")])


def test_render_directives_empty_list_also_needs_streamlit(monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit", None)
    with pytest.raises(ProviderError, match="streamlit unavailable"):
        DecisionDashboard().render_directives([])
