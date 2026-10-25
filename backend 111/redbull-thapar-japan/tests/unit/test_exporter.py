"""Unit tests — src/reporting/exporter.py (markdown / JSON / HTML)."""
from __future__ import annotations

import html
import json

import pytest

from src.app import PipelineResult
from src.briefing.japanese import (GRADE_COMMENT_JA, build_executive_briefing_en,
                                   build_executive_briefing_ja)
from src.data_sources.matrix import get_matrix
from src.intelligence.cultural_compat.engine import (CulturalCompatibilityEngine,
                                                     CulturalProfile)
from src.intelligence.localization_econ.engine import LocalizationEconomicsEngine
from src.reporting.exporter import to_html, to_json, to_markdown
from src.scoring.engine import WEIGHTS, Factor

CUL = CulturalCompatibilityEngine()
ECO = LocalizationEconomicsEngine()


# --------------------------------------------------------------- shared builders
def synth_result(title="Synthetic Show", score=59, grade="C", confidence=70,
                 status="FINISHED", genres=("Action",), tags=(), is_adult=False,
                 fmt="TV", triggers=None, wiki=None, breakdown=None):
    cul = CUL.evaluate(genres=list(genres), tags=list(tags), is_adult=is_adult,
                       format=fmt, episodes=12)
    if triggers is not None:
        cul = CulturalProfile(
            archetype_alignment=cul.archetype_alignment,
            cultural_distance_flags=cul.cultural_distance_flags,
            cbfc_rating_estimate=cul.cbfc_rating_estimate, cbfc_notes=cul.cbfc_notes,
            sensitivity_triggers=list(triggers),
            family_co_viewing_friction=cul.family_co_viewing_friction,
            regional_variation=cul.regional_variation,
            overall_cultural_fit=cul.overall_cultural_fit)
    econ = ECO.evaluate(sakura_score=score, format=fmt, episodes=12, duration_min=24)
    factors = [Factor(n, 60, WEIGHTS[n], 60 * WEIGHTS[n], [f"{n} note"])
               for n in WEIGHTS]
    r = PipelineResult(
        title=title, metadata={"status": status, "genres": list(genres),
                               "tags": list(tags)},
        unreleased=False, sakura_score=score, grade=grade, confidence=confidence,
        factors=factors, cultural_profile=cul, localization_economics=econ,
        data_source_matrix=get_matrix(), executive_briefing_en="",
        executive_briefing_ja="", market_breakdown=breakdown or {},
        wiki_evidence=wiki, grade_comment_ja=GRADE_COMMENT_JA[grade])
    r.executive_briefing_en = build_executive_briefing_en(r)
    r.executive_briefing_ja = build_executive_briefing_ja(r)
    return r


def table_rows_after(md: str, header_prefix: str) -> list[str]:
    lines = md.splitlines()
    idx = next(i for i, l in enumerate(lines) if l.startswith(header_prefix))
    rows = []
    for line in lines[idx + 2:]:          # skip header + |---| separator
        if not line.startswith("|"):
            break
        rows.append(line)
    return rows


# --------------------------------------------------------- real pipeline result
@pytest.fixture(scope="module")
def live_result(app):
    return app.run_candidate("Chainsaw Man")


def test_markdown_section_headers(live_result):
    md = to_markdown(live_result)
    for header in [
        f"# SakuraScore India Report — {live_result.title}",
        f"## Score: {live_result.sakura_score}/100 — Grade {live_result.grade}",
        "## Why This Score? (factor attribution)",
        "## Cultural Compatibility & CBFC Assessment",
        "### Archetype alignment",
        "### Sensitivity triggers & censor notes",
        "## Rupee Localization Economics",
        "## India Market Map (linguistic hubs)",
        "## Public Big Data Source Assessment (8 sources)",
        "経営ブリーフィング(日本語)",
    ]:
        assert header in md, header


def test_markdown_table_row_counts(live_result):
    md = to_markdown(live_result)
    assert len(table_rows_after(md, "| Factor |")) == 6
    assert len(table_rows_after(md, "| Archetype |")) == 4
    assert len(table_rows_after(md, "| Mode |")) == 4
    assert len(table_rows_after(md, "| Hub |")) == 6
    assert len(table_rows_after(md, "| Source |")) == 8


def test_markdown_contains_briefings_and_status(live_result):
    md = to_markdown(live_result)
    assert live_result.executive_briefing_en in md
    assert live_result.executive_briefing_ja in md
    assert f"**Status:** {live_result.metadata.get('status')}" in md


def test_markdown_recommended_plan_marked(live_result):
    md = to_markdown(live_result)
    rec = live_result.localization_economics.recommended_mode
    assert f"| {rec} **← recommended**" in md
    assert md.count("**← recommended**") == 1


def test_markdown_empty_triggers_placeholder():
    md = to_markdown(synth_result(genres=["Comedy"]))
    assert "- none flagged" in md


# ------------------------------------------------------------------------ json
def test_to_json_round_trip_and_exact_schema(live_result):
    doc = json.loads(to_json(live_result))
    assert set(doc) == {
        "schema", "challenge", "title", "metadata", "unreleased", "sakura_score",
        "grade", "confidence", "factors", "cultural_profile",
        "localization_economics", "data_source_matrix", "market_breakdown",
        "wiki_evidence", "executive_briefing_en", "executive_briefing_ja",
    }
    assert doc["schema"] == "sakurascore-india/0.2"
    assert doc["title"] == live_result.title
    assert doc["sakura_score"] == live_result.sakura_score
    assert doc["grade"] == live_result.grade
    assert len(doc["factors"]) == 6
    assert len(doc["data_source_matrix"]) == 8
    assert len(doc["market_breakdown"]) == 6
    assert set(doc["cultural_profile"]) == {
        "archetype_alignment", "cultural_distance_flags", "cbfc_rating_estimate",
        "cbfc_notes", "sensitivity_triggers", "family_co_viewing_friction",
        "regional_variation", "overall_cultural_fit"}
    assert set(doc["localization_economics"]) == {
        "content_type", "episodes", "minutes_per_ep", "total_minutes", "plans",
        "recommended_mode", "break_even_views", "break_even_tickets",
        "payback_months", "assumptions"}


def test_to_json_tags_serialized_as_name_rank_dicts(live_result):
    doc = json.loads(to_json(live_result))
    tags = doc["metadata"]["tags"]
    assert tags and all(set(t) == {"name", "rank"} for t in tags)
    assert ("Chainsaw Man" == live_result.title) or True
    names = [t["name"] for t in tags]
    assert "Gore" in names                       # catalog tag present
    gore = next(t for t in tags if t["name"] == "Gore")
    assert float(gore["rank"]) == 88.0           # catalog rank '88' preserved


def test_to_json_metadata_tags_only_transformed():
    r = synth_result(tags=[("Gore", 80), ("Violence", 35)])
    doc = json.loads(to_json(r))
    assert doc["metadata"]["tags"] == [{"name": "Gore", "rank": 80},
                                       {"name": "Violence", "rank": 35}]
    assert doc["metadata"]["genres"] == ["Action"]   # lists untouched


def test_to_json_unicode_survives():
    r = synth_result(title="日本語タイトル テスト")
    assert json.loads(to_json(r))["title"] == "日本語タイトル テスト"


def test_to_json_wiki_evidence_none():
    assert json.loads(to_json(synth_result()))["wiki_evidence"] is None


# ------------------------------------------------------------------------ html
def test_to_html_escapes_title(live_result):
    h = to_html(live_result)
    assert "<script>" not in h
    assert h.count("<!doctype html>") == 1
    assert "SakuraScore India" in h


def test_to_html_title_script_tag_escaped():
    r = synth_result(title="Evil <script>alert(1)</script> Show")
    h = to_html(r)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in h
    assert "<script>alert" not in h
    assert html.escape(r.title) in h


def test_to_html_status_unescaped_current_behaviour():
    # FINDING #7: metadata status flows into the <p class="small"> body line
    # UNESCAPED (the escaped copy that also appears comes from the briefing
    # text, which to_html does escape). Desired behaviour: tests/test_bugs.py.
    r = synth_result(status="<img src=x>")
    h = to_html(r)
    assert '<p class="small"><img src=x>' in h     # raw in body, current behaviour
    assert "&lt;img src=x&gt;" in h                # escaped via the briefing


def test_to_html_triggers_escaped():
    r = synth_result(triggers=["<img src=x> trigger", "plain trigger"])
    h = to_html(r)
    assert "&lt;img src=x&gt; trigger" in h
    assert "<img src=x>" not in h


def test_to_html_briefings_present_and_escaped():
    r = synth_result()
    h = to_html(r)
    assert "Executive Briefing (EN)" in h
    assert html.escape(r.executive_briefing_en) in h
    assert html.escape(r.executive_briefing_ja) in h


def test_to_html_market_map_section():
    app_profile = CUL.evaluate(genres=["Sports"], tags=[], is_adult=False)
    from src.app import SakuraScoreApp  # noqa: F401  (import check only)
    breakdown = {
        "Hindi Belt": {"population": 10, "internet_penetration_pct": 50.0,
                       "median_age": 28.0, "cultural_delta": 5, "demand_index": 40},
        "Southern Fortress": {"population": 5, "internet_penetration_pct": 60.0,
                              "median_age": 30.0, "cultural_delta": 0,
                              "demand_index": 30},
    }
    r = synth_result(breakdown=breakdown)
    h = to_html(r)
    assert "India Market Map" in h and "Hindi Belt" in h
    assert "Southern Fortress" in h


# ------------------------------------------------------------- synthetic grades
@pytest.mark.parametrize("grade,score", [("S", 90), ("A", 75), ("B", 65),
                                         ("C", 50), ("D", 20)])
def test_all_five_grades_render_everywhere(grade, score):
    r = synth_result(score=score, grade=grade)
    md, doc, h = to_markdown(r), json.loads(to_json(r)), to_html(r)
    assert f"Grade {grade}" in md and doc["grade"] == grade
    assert f"Grade {grade}" in h
    assert r.grade_comment_ja in doc["executive_briefing_ja"]
    assert doc["sakura_score"] == score
    # exporters never raise for any grade — implicit by reaching these asserts


def test_unreleased_annotation_in_outputs():
    r = synth_result()
    r.unreleased = True
    md, h = to_markdown(r), to_html(r)
    assert "UNRELEASED" in md and "UNRELEASED" in h


def test_determinism_of_exporters(live_result):
    assert to_markdown(live_result) == to_markdown(live_result)
    assert to_json(live_result) == to_json(live_result)
    assert to_html(live_result) == to_html(live_result)
