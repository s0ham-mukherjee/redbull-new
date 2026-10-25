"""Agent-Reach router: _to_evidence projection, research/read params, health."""

from __future__ import annotations

import json

import pytest

from engine_api import Query
from engine_api.protocols import EvidenceSource, ResearchRouter
from providers._bootstrap import ProviderError
from providers.research_router import (
    MultiChannelResearchRouter,
    RedditDiscussionSource,
    _to_evidence,
)


# ---------------------------------------------------------------------------
# _to_evidence (pure)
# ---------------------------------------------------------------------------


def test_to_evidence_empty_items():
    assert _to_evidence({}, "web", "q") == []
    assert _to_evidence({"items": []}, "web", "q") == []
    assert _to_evidence({"items": None}, "web", "q") == []


def test_to_evidence_non_dict_item_wrapped():
    out = _to_evidence({"items": [42]}, "web", "q")
    assert len(out) == 1
    payload = json.loads(out[0].content)
    assert payload == {"value": 42}


def test_to_evidence_url_precedence():
    assert _to_evidence({"items": [{"url": "U"}]}, "c", "q")[0].url == "U"
    assert _to_evidence({"items": [{"link": "L"}]}, "c", "q")[0].url == "L"
    assert _to_evidence({"items": [{"target": "T"}]}, "c", "q")[0].url == "T"
    assert _to_evidence({"items": [{"url": "U", "link": "L", "target": "T"}]},
                        "c", "q")[0].url == "U"
    assert _to_evidence({"items": [{}]}, "c", "q")[0].url == ""


def test_to_evidence_title_precedence():
    item = {"title": "T", "name": "N"}
    assert _to_evidence({"items": [item]}, "c", "q")[0].title == "T"
    assert _to_evidence({"items": [{"name": "N"}]}, "c", "q")[0].title == "N"
    assert _to_evidence({"items": [{}]}, "c", "q")[0].title is None
    # falsy title (0/""/None) -> None
    assert _to_evidence({"items": [{"title": 0}]}, "c", "q")[0].title is None


def test_to_evidence_text_precedence():
    for key in ("text", "content", "body", "description"):
        ev = _to_evidence({"items": [{key: "VAL"}]}, "c", "q")[0]
        assert ev.content == "VAL"
    combined = {"text": "1", "content": "2", "body": "3", "description": "4"}
    assert _to_evidence({"items": [combined]}, "c", "q")[0].content == "1"


def test_to_evidence_empty_text_falls_through():
    # "" is falsy in the or-chain -> falls back to other fields / full JSON
    ev = _to_evidence({"items": [{"text": "", "content": "CC"}]}, "c", "q")[0]
    assert ev.content == "CC"
    ev2 = _to_evidence({"items": [{"text": ""}]}, "c", "q")[0]
    assert json.loads(ev2.content) == {"text": ""}


def test_to_evidence_no_text_uses_full_json():
    item = {"url": "u", "title": "t", "nums": [1, 2]}
    ev = _to_evidence({"items": [item]}, "c", "q")[0]
    assert json.loads(ev.content) == item


def test_to_evidence_non_str_text_is_str_coerced():
    ev = _to_evidence({"items": [{"text": 12345}]}, "c", "q")[0]
    assert ev.content == "12345"


def test_to_evidence_metadata_and_source():
    item = {"url": "https://x", "text": "body"}
    ev = _to_evidence({"items": [item]}, "reddit", "the query")[0]
    assert ev.source == "reach:reddit"
    assert ev.metadata["channel"] == "reddit"
    assert ev.metadata["query"] == "the query"
    assert ev.metadata["raw"] == item


def test_to_evidence_preserves_count_and_order():
    items = [{"url": str(i), "text": f"t{i}"} for i in range(5)]
    out = _to_evidence({"items": items}, "c", "q")
    assert len(out) == 5
    assert [ev.url for ev in out] == [str(i) for i in range(5)]


# ---------------------------------------------------------------------------
# MultiChannelResearchRouter.research / read (monkeypatched _run)
# ---------------------------------------------------------------------------


@pytest.fixture()
def router():
    r = MultiChannelResearchRouter()
    r._calls = []
    return r


def test_research_not_ok_error_code_and_message(router):
    router._run = lambda c, a, p: {"ok": False, "error": {"code": "X", "message": "boom"}}
    with pytest.raises(ProviderError) as exc:
        router.research(Query(text="q"))
    msg = str(exc.value)
    assert "X" in msg and "boom" in msg


def test_research_ok_returns_evidence(router):
    router._run = lambda c, a, p: {"ok": True, "items": [{"url": "u", "text": "t"}]}
    out = router.research(Query(text="q"))
    assert len(out) == 1 and out[0].source == "reach:web"


def test_research_default_channel_action_params(router):
    captured = {}

    def fake_run(channel, action, params):
        captured.update(channel=channel, action=action, params=params)
        return {"ok": True, "items": []}

    router._run = fake_run
    router.research(Query(text="q", limit=3))
    assert captured["channel"] == "web"
    assert captured["action"] == "search"
    assert captured["params"] == {"query": "q", "limit": 3}


@pytest.mark.parametrize("limit,expected", [(100, 25), (25, 25), (26, 25), (3, 3),
                                            (0, 0), (-5, -5)])
def test_research_limit_capped_at_25(router, limit, expected):
    captured = {}

    def fake_run(channel, action, params):
        captured.update(params=params)
        return {"ok": True, "items": []}

    router._run = fake_run
    router.research(Query(text="q", limit=limit))
    assert captured["params"]["limit"] == expected  # min(limit, 25), no floor


def test_research_extra_params_merge_and_override(router):
    captured = {}

    def fake_run(channel, action, params):
        captured.update(params=params)
        return {"ok": True, "items": []}

    router._run = fake_run
    router.research(Query(text="q", limit=10,
                          extra={"params": {"limit": 7, "foo": "bar"}}))
    assert captured["params"] == {"query": "q", "limit": 7, "foo": "bar"}


def test_research_channel_and_action_overridable(router):
    captured = {}

    def fake_run(channel, action, params):
        captured.update(channel=channel, action=action)
        return {"ok": True, "items": []}

    router._run = fake_run
    router.research(Query(text="q", extra={"channel": "github", "action": "read"}))
    assert captured["channel"] == "github"
    assert captured["action"] == "read"


def test_read_uses_read_action_with_target(router):
    captured = {}

    def fake_run(channel, action, params):
        captured.update(channel=channel, action=action, params=params)
        return {"ok": True, "items": [{"target": "t", "text": "body"}]}

    router._run = fake_run
    out = router.read("reddit", "https://reddit.com/x")
    assert captured == {"channel": "reddit", "action": "read",
                        "params": {"target": "https://reddit.com/x"}}
    assert len(out) == 1
    assert out[0].metadata["query"] == "https://reddit.com/x"


def test_read_not_ok_raises(router):
    router._run = lambda c, a, p: {"ok": False, "error": {"code": "E", "message": "m"}}
    with pytest.raises(ProviderError):
        router.read("web", "https://x")


def test_run_unknown_channel_offline_lookup(router):
    # get_channel() is a pure registry lookup in the Agent-Reach clone
    with pytest.raises(ProviderError, match="unknown research channel"):
        router._run("zzz-definitely-not-a-channel", "search", {"query": "q"})


def test_router_satisfies_protocol(router):
    assert isinstance(router, ResearchRouter)


# ---------------------------------------------------------------------------
# health() against the real Agent-Reach clone (offline, import-only)
# ---------------------------------------------------------------------------


def test_health_shape():
    health = MultiChannelResearchRouter().health()
    channels = health["channels"]
    assert isinstance(channels, list) and channels
    for ch in channels:
        assert set(ch) == {"name", "actions", "available"}
        assert isinstance(ch["name"], str)
        assert isinstance(ch["actions"], list)
        assert all(isinstance(a, str) for a in ch["actions"])
        assert isinstance(ch["available"], bool)
    names = {ch["name"] for ch in channels}
    assert {"reddit", "youtube", "web", "github"} <= names


# ---------------------------------------------------------------------------
# RedditDiscussionSource
# ---------------------------------------------------------------------------


def test_reddit_discussion_constructor_offline():
    src = RedditDiscussionSource()
    assert src.name == "reach_reddit"
    assert isinstance(src, EvidenceSource)


def test_reddit_discussion_via_registry(reg):
    src = reg.create("source", "reach_reddit")
    assert isinstance(src, EvidenceSource)


def test_router_via_registry(reg):
    r = reg.create("router", "multi_channel", timeout=5.0)
    assert isinstance(r, MultiChannelResearchRouter)
    assert isinstance(r, ResearchRouter)
