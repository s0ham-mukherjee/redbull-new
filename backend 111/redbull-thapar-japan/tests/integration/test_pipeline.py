"""Integration tests — real data end-to-end through SakuraScoreApp.run_candidate."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.app import SHOWCASE_ALIASES, _norm
from src.reporting.exporter import to_html, to_json, to_markdown
from src.scoring.engine import WEIGHTS

GRADES = {"S", "A", "B", "C", "D"}
HUBS = {"Hindi Belt", "Southern Fortress", "Western Metros", "Eastern Hub",
        "Northeast", "Northern Fringe"}


# ------------------------------------------------------------- showcase aliases
@pytest.mark.parametrize("alias", sorted(SHOWCASE_ALIASES))
def test_showcase_alias_end_to_end(app, alias):
    r = app.run_candidate(alias)
    assert r.title == SHOWCASE_ALIASES[alias]        # resolves to catalog title
    assert r.unreleased is True                      # India-premiere-pending
    assert 0 <= r.sakura_score <= 100 and r.grade in GRADES
    assert 0 <= r.confidence <= 100
    assert r.executive_briefing_en and r.executive_briefing_ja
    assert len(r.data_source_matrix) == 8
    assert set(r.market_breakdown) == HUBS
    assert r.metadata["title_english"] == SHOWCASE_ALIASES[alias]


# ------------------------------------------------------------ released top-10
def test_released_top10_full_pipeline(app):
    failures = []
    for i, title in enumerate(app.released_top(10)):
        r = app.run_candidate(title)
        if not (0 <= r.sakura_score <= 100):
            failures.append(f"{title}: score {r.sakura_score}")
        if r.grade not in GRADES:
            failures.append(f"{title}: grade {r.grade!r}")
        if not (0 <= r.confidence <= 100):
            failures.append(f"{title}: confidence {r.confidence}")
        names = [f.name for f in r.factors]
        if sorted(names) != sorted(WEIGHTS):
            failures.append(f"{title}: factor names {names}")
        if r.unreleased is not False:
            failures.append(f"{title}: released title flagged unreleased")
        # why_bullets sorted by contribution desc
        contribs = [float(b.split("=")[1].split("]")[0].replace("+", ""))
                    for b in r.why_bullets]
        if contribs != sorted(contribs, reverse=True):
            failures.append(f"{title}: why_bullets not sorted desc")
        try:
            md, doc, html = (to_markdown(r), json.loads(to_json(r)),
                             to_html(r))
            assert md and doc and html
        except Exception as exc:
            failures.append(f"{title}: exporter raised {exc!r}")
    assert not failures, failures


# ------------------------------------------------------------ meta_override path
def test_meta_override_full(app):
    r = app.run_candidate(
        "QZQ Unknown Original Series",
        meta_override={"title_english": "QZQ Unknown Original Series",
                       "format": "TV", "episodes": 12, "duration_min": 24,
                       "status": "FINISHED", "genres": ["Action", "Sports"],
                       "tags": [("Gore", 60)], "popularity": 50_000,
                       "favourites": 20_000, "average_score": 78,
                       "is_adult": False})
    assert r.title == "QZQ Unknown Original Series"
    assert 0 <= r.sakura_score <= 100 and r.grade in GRADES
    assert r.metadata["genres"] == ["Action", "Sports"]
    # CURRENT BEHAVIOUR (finding #3): override path passes meta=None to
    # _confidence -> never earns the +30 catalog points. Desired: test_bugs.py.
    assert r.confidence == 33
    assert set(r.market_breakdown) == HUBS
    assert r.executive_briefing_en and r.executive_briefing_ja


def test_meta_override_minimal_empty_dict_current_behaviour(app):
    # CURRENT BEHAVIOUR (new finding C): `elif meta_override:` treats an EMPTY
    # dict as missing, so the setdefault defaults never run and the call raises
    # instead of scoring with defaults. Desired behaviour: tests/test_bugs.py.
    with pytest.raises(ValueError, match="not in catalog"):
        app.run_candidate("QZQ Bare Override", meta_override={})


def test_meta_override_one_key_gets_defaults(app):
    # any non-empty dict triggers the setdefault defaults for the other keys
    r = app.run_candidate("QZQ Bare Override", meta_override={"status": "FINISHED"})
    assert r.title == "QZQ Bare Override"
    assert r.metadata["format"] == "TV"
    assert r.metadata["popularity"] == 0 and r.metadata["favourites"] == 0
    assert r.metadata["genres"] == [] and r.metadata["tags"] == []
    assert r.metadata["is_adult"] is False
    assert 0 <= r.sakura_score <= 100
    assert {f.name for f in r.factors} == set(WEIGHTS)


def test_unknown_title_without_override_raises(app):
    with pytest.raises(ValueError, match="not in catalog"):
        app.run_candidate("QZQ Definitely Not In Catalog 12345")


def test_override_vs_catalog_confidence_delta(app):
    # the same fully-specified metadata scores 30 confidence points lower via
    # the override path than an equivalent catalog row would (finding #3)
    r = app.run_candidate("QZQ Conf Delta", meta_override={"status": "FINISHED"})
    assert r.confidence < 63        # 33 current; 63 with the +30 catalog points


# ------------------------------------------------------------------ determinism
def test_determinism_same_title_twice(app, sample_titles):
    for title in sample_titles:
        a = app.run_candidate(title)
        b = app.run_candidate(title)
        assert a.sakura_score == b.sakura_score, title
        assert a.grade == b.grade, title
        assert [(f.name, f.value) for f in a.factors] == \
            [(f.name, f.value) for f in b.factors], title


# ------------------------------------------------------------- unreleased catalog
def test_not_yet_released_catalog_title(app):
    row = app.catalog.loc[app.catalog["status"] == "NOT_YET_RELEASED",
                          "title_english"].dropna()
    assert len(row) > 0, "catalog has no NOT_YET_RELEASED rows"
    title = row.iloc[0]
    r = app.run_candidate(title)
    assert r.unreleased is True
    assert r.metadata["status"] == "NOT_YET_RELEASED"
    # pre-launch tier note is produced by the scoring pass; PipelineResult does
    # not carry tier_notes (computed but dropped — see report), so we re-derive
    # it from the engine contract:
    res = app.scoring.score_candidate(
        meta=r.metadata, wiki=r.wiki_evidence,
        trends=app._trends_for(r.metadata, r.title),
        cultural_fit=r.cultural_profile.overall_cultural_fit,
        reach_multiplier=r.localization_economics.recommended_plan.reach_multiplier,
        pre_launch=True,
        confidence_parts={"wiki_vol_values": app.wiki_vol_values,
                          "popularity_values": app.popularity_values,
                          "favourite_values": app.favourite_values,
                          "unreleased_pop_values": app.unreleased_pop_values,
                          "confidence": r.confidence})
    assert res.tier_notes and "Unreleased title" in res.tier_notes[0]


def test_unreleased_note_reaches_markdown(app):
    row = app.catalog.loc[app.catalog["status"] == "NOT_YET_RELEASED",
                          "title_english"].dropna()
    r = app.run_candidate(row.iloc[0])
    assert "UNRELEASED" in to_markdown(r)


# ---------------------------------------------------------------- smoke sanity
def test_smoke_chainsaw_man(app):
    r = app.run_candidate("Chainsaw Man")
    assert r.sakura_score == 71 and r.grade == "A" and r.confidence == 90
    doc = json.loads(to_json(r))
    assert doc["sakura_score"] == 71 and doc["grade"] == "A"
    assert len(doc["factors"]) == 6


def test_every_sample_title_runs(app, sample_titles):
    for title in sample_titles:
        r = app.run_candidate(title)
        assert isinstance(r.title, str) and r.title
        assert 0 <= r.confidence <= 100
        assert len(r.data_source_matrix) == 8
        assert set(r.market_breakdown) == HUBS
