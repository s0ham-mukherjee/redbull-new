"""Exhaustive unit/edge tests for engine_api.types.

Every frozen dataclass, every default, hash semantics (including unicode and
lone surrogates), the Action enum and utcnow.
"""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime, timezone

import pytest

from engine_api import (
    Action,
    AgentTurn,
    Directive,
    Document,
    EvaluationResult,
    Evidence,
    Forecast,
    Interval,
    IPNode,
    Persona,
    Query,
    Relation,
    Scenario,
    Signal,
    SimulationReport,
    content_hash,
    utcnow,
)

FROZEN_DATACLASSES = [
    ("Query", lambda: Query(text="t")),
    ("Evidence", lambda: Evidence(source="s", url="u", content="c")),
    ("Document", lambda: Document(url="u", text="t")),
    ("Signal", lambda: Signal(name="n", value=1.0)),
    ("IPNode", lambda: IPNode(id="i", title="t")),
    ("Relation", lambda: Relation(src="a", dst="b", kind="sequel")),
    ("Interval", lambda: Interval(point=1.0, lower=0.0, upper=2.0)),
    ("Forecast", lambda: Forecast(target="t", interval=Interval(point=1, lower=0, upper=2))),
    ("Directive", lambda: Directive(ip_id="i", action=Action.WAIT,
                                    opportunity_score=0.5, rationale="r")),
    ("Persona", lambda: Persona(id="p1")),
    ("Scenario", lambda: Scenario(id="sc", ip_id="i", prompt="p")),
    ("AgentTurn", lambda: AgentTurn(agent_id="a", stance="pro", text="t")),
    ("SimulationReport", lambda: SimulationReport(scenario_id="sc", seed=0, turns=())),
    ("EvaluationResult", lambda: EvaluationResult(passed=True, score=1.0)),
]


@pytest.mark.parametrize("name,make", FROZEN_DATACLASSES, ids=[n for n, _ in FROZEN_DATACLASSES])
def test_frozen_dataclass_rejects_setattr(name, make):
    obj = make()
    field_name = next(iter(f.name for f in dataclasses.fields(obj)))
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, field_name, "mutated")


@pytest.mark.parametrize("name,make", FROZEN_DATACLASSES, ids=[n for n, _ in FROZEN_DATACLASSES])
def test_dataclasses_are_frozen_and_hashable_identity(name, make):
    obj = make()
    assert dataclasses.is_dataclass(obj)
    # a fresh build reproduces every deterministic field (auto-timestamp
    # fields like retrieved_at/crawled_at differ per instance by design)
    clone = make()
    for f in dataclasses.fields(obj):
        if f.name.endswith("_at"):
            continue
        assert getattr(obj, f.name) == getattr(clone, f.name), f.name


# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------


def test_content_hash_known_vector_matches_hashlib():
    assert content_hash("sakura") == hashlib.sha256(b"sakura").hexdigest()
    assert content_hash("") == hashlib.sha256(b"").hexdigest()


@pytest.mark.parametrize("text", [
    "hello world",
    "こんにちは世界",
    "नमस्ते दुनिया",
    "🎉🦀",
    "mixed 日本語 with ASCII 123",
])
def test_content_hash_unicode_matches_hashlib_utf8(text):
    assert content_hash(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_content_hash_lone_surrogate_replaced():
    # Lone surrogates cannot be encoded as UTF-8; the 'replace' handler turns
    # them into b"?" — current (and desired) behavior.
    assert content_hash("\ud800") == hashlib.sha256(b"?").hexdigest()
    assert content_hash("a\udfffz") == hashlib.sha256(b"a?z").hexdigest()
    # Evidence construction with a lone surrogate must not raise.
    ev = Evidence(source="s", url="u", content="x\ud800y")
    assert len(ev.content_hash) == 64


@pytest.mark.parametrize("text", ["", "a", "hello", "データ", "\n\t mixed \t whitespace"])
def test_content_hash_shape_stable_and_sensitive(text):
    h1, h2 = content_hash(text), content_hash(text)
    assert h1 == h2
    assert len(h1) == 64
    int(h1, 16)  # pure hex
    assert h1 != content_hash(text + " ")


def test_content_hash_order_sensitive():
    assert content_hash("ab") != content_hash("ba")


# ---------------------------------------------------------------------------
# Evidence auto-hash
# ---------------------------------------------------------------------------


def test_evidence_auto_hash_is_sha256_of_content():
    ev = Evidence(source="s", url="u", content="payload")
    assert ev.content_hash == hashlib.sha256(b"payload").hexdigest()
    assert len(ev.content_hash) == 64


def test_evidence_hash_stable_across_instances_and_content_sensitive():
    a = Evidence(source="x", url="u", content="hello")
    b = Evidence(source="x", url="u", content="hello")
    c = Evidence(source="x", url="u", content="hello!")
    d = Evidence(source="OTHER", url="u", content="hello")  # only source differs
    assert a.content_hash == b.content_hash
    assert a.content_hash != c.content_hash
    # hash covers *content only* – different source/url do not change it
    assert a.content_hash == d.content_hash


def test_evidence_explicit_hash_preserved():
    ev = Evidence(source="s", url="u", content="c", content_hash="custom-hash")
    assert ev.content_hash == "custom-hash"


def test_evidence_explicit_empty_string_hash_recomputed():
    # the falsy explicit hash triggers auto-computation
    ev = Evidence(source="s", url="u", content="c", content_hash="")
    assert ev.content_hash == content_hash("c")


def test_evidence_retrieved_at_default_is_utc_now():
    before = utcnow()
    ev = Evidence(source="s", url="u", content="c")
    after = utcnow()
    assert before <= ev.retrieved_at <= after
    assert ev.retrieved_at.tzinfo is timezone.utc


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def test_query_defaults():
    q = Query(text="naruto")
    assert q.ip_id is None
    assert q.region is None
    assert q.languages == ()
    assert q.since is None
    assert q.limit == 50
    assert q.extra == {}


def test_query_extra_default_is_not_shared_between_instances():
    q1, q2 = Query(text="a"), Query(text="b")
    assert q1.extra == {} and q2.extra == {}
    assert q1.extra is not q2.extra
    q1.extra["k"] = 1
    assert q2.extra == {}
    assert q1.extra == {"k": 1}


def test_query_accepts_full_override():
    q = Query(text="t", ip_id="mal:1", region="IN", languages=("hi", "en"),
              since=datetime(2024, 1, 1, tzinfo=timezone.utc), limit=3,
              extra={"channel": "reddit"})
    assert q.ip_id == "mal:1" and q.region == "IN"
    assert q.languages == ("hi", "en") and q.limit == 3
    assert q.extra == {"channel": "reddit"}


# ---------------------------------------------------------------------------
# Remaining dataclass defaults
# ---------------------------------------------------------------------------


def test_document_defaults():
    d = Document(url="u", text="t")
    assert d.status == 200
    assert d.metadata == {}
    assert d.crawled_at.tzinfo is timezone.utc


def test_signal_defaults():
    s = Signal(name="n", value=1.5)
    assert s.region is None
    assert s.window_start is None and s.window_end is None
    assert s.source == ""
    assert s.metadata == {}


def test_ipnode_defaults():
    n = IPNode(id="i", title="t")
    assert n.kind == "anime"
    assert n.genres == () and n.studio is None and n.adaptation_of is None
    assert n.aliases == () and n.attributes == {}


def test_relation_default_provenance_none():
    r = Relation(src="a", dst="b", kind="adapted_from")
    assert r.provenance is None


def test_interval_default_alpha():
    iv = Interval(point=1.0, lower=0.5, upper=1.5)
    assert iv.alpha == pytest.approx(0.10)


def test_forecast_defaults():
    f = Forecast(target="t", interval=Interval(point=1, lower=0, upper=2))
    assert f.n_calibration_samples == 0
    assert f.ready is True
    assert f.reason is None


def test_directive_defaults():
    d = Directive(ip_id="i", action=Action.PILOT, opportunity_score=0.1, rationale="r")
    assert d.forecast is None
    assert d.evidence == ()


def test_agent_turn_defaults():
    t = AgentTurn(agent_id="a", stance="pro", text="t")
    assert t.cited_evidence == ()
    assert t.step == 0


def test_simulation_report_defaults():
    r = SimulationReport(scenario_id="sc", seed=7, turns=())
    assert r.demand_distribution == {}
    assert r.started_at is None and r.finished_at is None
    assert r.metadata == {}


def test_evaluation_result_defaults():
    e = EvaluationResult(passed=False, score=0.0)
    assert e.details == {}


def test_persona_defaults():
    p = Persona(id="p1")
    assert p.tier == "tier_2"
    assert p.location is None
    assert p.languages == ("hi",)
    assert p.preferred_formats == ("dub",)
    assert p.genres == ("shonen",)
    assert p.disposable_income_inr == 8000.0
    assert p.attributes == {}


def test_persona_attributes_default_not_shared():
    p1, p2 = Persona(id="a"), Persona(id="b")
    assert p1.attributes is not p2.attributes
    p1.attributes["k"] = 1
    assert p2.attributes == {}


def test_scenario_defaults():
    s = Scenario(id="sc", ip_id="i", prompt="p")
    assert s.price_points_inr == {}
    assert s.attributes == {}


# ---------------------------------------------------------------------------
# Action enum
# ---------------------------------------------------------------------------


def test_action_values_exact():
    assert Action.PILOT.value == "pilot"
    assert Action.INVESTIGATE.value == "investigate"
    assert Action.WAIT.value == "wait"
    assert Action.ABSTAIN.value == "abstain"


def test_action_values_unique_and_closed():
    values = [a.value for a in Action]
    assert len(values) == len(set(values)) == 4
    assert set(values) == {"pilot", "investigate", "wait", "abstain"}


def test_action_is_str_enum_and_lookup_by_value():
    assert isinstance(Action.PILOT, str)
    assert Action.PILOT == "pilot"
    assert Action("wait") is Action.WAIT
    with pytest.raises(ValueError):
        Action("nope")


# ---------------------------------------------------------------------------
# utcnow
# ---------------------------------------------------------------------------


def test_utcnow_is_tz_aware_utc():
    now = utcnow()
    assert now.tzinfo is timezone.utc
    assert now.utcoffset().total_seconds() == 0


def test_utcnow_monotonic_non_decreasing():
    t1 = utcnow()
    t2 = utcnow()
    assert t2 >= t1
