"""Property tests — pipeline-level invariants (exporters, market map, determinism)."""
from __future__ import annotations

import html
import json

from hypothesis import given, settings
from hypothesis import strategies as st

from src.app import PipelineResult, SHOWCASE_ALIASES, SakuraScoreApp
from src.briefing.japanese import (GRADE_COMMENT_JA, build_executive_briefing_en,
                                   build_executive_briefing_ja)
from src.data_sources.matrix import get_matrix
from src.intelligence.cultural_compat.engine import CulturalCompatibilityEngine
from src.intelligence.localization_econ.engine import LocalizationEconomicsEngine
from src.reporting.exporter import to_html, to_json, to_markdown
from src.scoring.engine import WEIGHTS, Factor

CUL = CulturalCompatibilityEngine()
ECO = LocalizationEconomicsEngine()

TITLE_ALPHABET = "abcXYZ019 -_/&<>\"'日本語₹é."


def synth_result(title: str, score: int = 59) -> PipelineResult:
    cul = CUL.evaluate(genres=["Action"], tags=[], is_adult=False,
                       format="TV", episodes=12)
    econ = ECO.evaluate(sakura_score=score, format="TV", episodes=12,
                        duration_min=24)
    factors = [Factor(n, 60, WEIGHTS[n], 60 * WEIGHTS[n], [f"{n} note"])
               for n in WEIGHTS]
    r = PipelineResult(
        title=title, metadata={"status": "FINISHED", "tags": [("Gore", 80)]},
        unreleased=False, sakura_score=score, grade="C", confidence=70,
        factors=factors, cultural_profile=cul, localization_economics=econ,
        data_source_matrix=get_matrix(), executive_briefing_en="",
        executive_briefing_ja="", market_breakdown={}, wiki_evidence=None,
        grade_comment_ja=GRADE_COMMENT_JA["C"])
    r.executive_briefing_en = build_executive_briefing_en(r)
    r.executive_briefing_ja = build_executive_briefing_ja(r)
    return r


titles = st.text(alphabet=TITLE_ALPHABET, min_size=1, max_size=30)


@settings(max_examples=60, deadline=None)
@given(title=titles, score=st.integers(min_value=0, max_value=100))
def test_exporters_never_raise_and_schema_stable(title, score):
    r = synth_result(title, score)
    doc = json.loads(to_json(r))
    assert doc["schema"] == "sakurascore-india/0.2"
    assert set(doc) == {"schema", "challenge", "title", "metadata", "unreleased",
                        "sakura_score", "grade", "confidence", "factors",
                        "cultural_profile", "localization_economics",
                        "data_source_matrix", "market_breakdown", "wiki_evidence",
                        "executive_briefing_en", "executive_briefing_ja"}
    assert doc["title"] == title and doc["sakura_score"] == score
    assert len(doc["factors"]) == 6 and len(doc["data_source_matrix"]) == 8
    assert to_markdown(r)  # non-empty, no exception
    assert to_html(r)


@settings(max_examples=60, deadline=None)
@given(title=titles)
def test_to_html_contains_escaped_title(title):
    h = to_html(synth_result(title))
    assert html.escape(title) in h
    if "<" in title:
        # the raw angle-bracket payload must not appear as an unescaped tag
        # (title only enters the shell + escaped briefings)
        for chunk in title.split("<")[1:]:
            assert f"<{chunk.split('>')[0]}>" not in h or html.escape(title) in h


@settings(max_examples=60, deadline=None)
@given(title=titles)
def test_to_markdown_contains_title(title):
    assert title in to_markdown(synth_result(title))


@settings(max_examples=60, deadline=None)
@given(title=titles)
def test_to_json_round_trips_unicode_title(title):
    assert json.loads(to_json(synth_result(title)))["title"] == title


# ------------------------------------------------------------ real-app properties
HUB_NAMES = {"Hindi Belt", "Southern Fortress", "Western Metros", "Eastern Hub",
             "Northeast", "Northern Fringe"}


@settings(max_examples=50, deadline=None)
@given(reach=st.floats(min_value=0, max_value=3),
       genre=st.sampled_from(["Sports", "Ecchi", "Kids", "Action", "Horror"]),
       friction_tag=st.sampled_from([None, "Gore", "Explicit Sex"]))
def test_market_breakdown_invariants(app, reach, genre, friction_tag):
    tags = [(friction_tag, 80)] if friction_tag else []
    cul = app.cultural.evaluate(genres=[genre], tags=tags, is_adult=False,
                                format="TV", episodes=12)
    b = app.market_breakdown(cul, reach, 50)
    assert set(b) == HUB_NAMES
    total = int(app.states["population_2011_census"].sum())
    assert sum(m["population"] for m in b.values()) == total
    for hub, m in b.items():
        assert 0 <= m["demand_index"] <= 100, hub
        assert 0 <= m["internet_penetration_pct"] <= 100
        assert m["population"] > 0
    demands = [m["demand_index"] for m in b.values()]
    assert demands == sorted(demands, reverse=True)


@settings(max_examples=30, deadline=None)
@given(idx=st.integers(min_value=0, max_value=len(SHOWCASE_ALIASES) - 1))
def test_run_candidate_determinism(app, idx):
    alias = list(SHOWCASE_ALIASES)[idx]
    a = app.run_candidate(alias)
    b = app.run_candidate(alias)
    assert a.sakura_score == b.sakura_score
    assert a.grade == b.grade
    assert a.confidence == b.confidence
    assert [(f.name, f.value, f.contribution) for f in a.factors] == \
        [(f.name, f.value, f.contribution) for f in b.factors]
    assert a.market_breakdown == b.market_breakdown
    assert a.executive_briefing_en == b.executive_briefing_en
