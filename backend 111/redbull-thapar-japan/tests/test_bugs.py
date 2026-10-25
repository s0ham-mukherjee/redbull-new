"""Bug documentation — desired-behaviour tests, all currently failing.

Each test is @pytest.mark.xfail(strict=True): it pins the DESIRED behaviour
from BACKEND_MAP.md FINDINGS (plus two new ones found while writing this
suite). The rest of the suite asserts CURRENT behaviour, so it stays green;
these tests go XPASS->failure the moment a bug is fixed, prompting an update.
"""
from __future__ import annotations

import pytest

from src.app import PipelineResult, SakuraScoreApp
from src.briefing.japanese import GRADE_COMMENT_JA, build_executive_briefing_en, \
    build_executive_briefing_ja
from src.data_sources.matrix import SOURCES, get_matrix
from src.intelligence.cultural_compat.engine import CulturalCompatibilityEngine
from src.intelligence.localization_econ.engine import LocalizationEconomicsEngine
from src.reporting.exporter import to_html
from src.scoring.engine import WEIGHTS, Factor, ScoringEngine

POOL = [float(i) for i in range(101)]
PARTS = {"wiki_vol_values": POOL, "popularity_values": POOL,
         "favourite_values": POOL, "unreleased_pop_values": [10.0, 20.0, 30.0],
         "confidence": 50}
NAN_WIKI = {"avg_daily_last30": 50.0, "momentum_90d_vs_prior90": float("nan"),
            "has_hindi_wiki": True}
META = {"title_english": "Bug Case", "genres": ["Action"], "popularity": 50.0,
        "favourites": 50.0, "average_score": None}


# ------------------------------------------------------------------ finding #1
@pytest.mark.xfail(strict=True, reason="FINDING #1: NaN momentum should be "
                   "neutral, not max acceleration "
                   "(src/scoring/engine.py:93 and :149)")
def test_bug1_nan_momentum_should_be_neutral():
    res = ScoringEngine().score_candidate(
        meta=META, wiki=NAN_WIKI, trends={"growth_2y_pct": None},
        cultural_fit=50, reach_multiplier=1.0, pre_launch=False,
        confidence_parts=PARTS)
    fmap = {f.name: f.value for f in res.factors}
    pct = 100.0 * 50.5 / 101
    assert fmap["india_demand"] == int(0.40 * pct + 0.25 * 50 + 0.15 * 100 + 0.20 * 50)
    assert fmap["momentum"] == int(0.6 * pct + 0.4 * 50)


# ------------------------------------------------------------------ finding #3
@pytest.mark.xfail(strict=True, reason="FINDING #3: meta_override path passes "
                   "meta=None so the +30 catalog confidence points are never "
                   "awarded (src/app.py:303)")
def test_bug3_override_confidence_should_include_catalog_points(app):
    r = app.run_candidate("QZQ Bug3 Title", meta_override={
        "title_english": "QZQ Bug3 Title", "status": "FINISHED",
        "genres": ["Action"], "tags": [], "popularity": 1, "favourites": 1})
    assert r.confidence == 63   # 8 (no wiki) + 15 (trends) + 10 (released) + 30


# ------------------------------------------------------------------ finding #4
@pytest.mark.xfail(strict=True, reason="FINDING #4: _trends_for keeps the LAST "
                   "substring hit; it should prefer the longest/most-specific "
                   "keyword (src/app.py:174-176)")
def test_bug4_trends_should_pick_longest_keyword(app):
    t = app._trends_for({}, "Anime Hindi Dub Solo Leveling Review")
    assert t["keyword"] == "anime hindi dub"   # longest match, not last


# ------------------------------------------------------------------ finding #5
@pytest.mark.xfail(strict=True, reason="FINDING #5: lookup('') substring-matches "
                   "everything and returns a row; it should return None "
                   "(src/app.py:139-143)")
def test_bug5_empty_title_lookup_should_return_none(app):
    assert app.lookup("") is None
    assert app.lookup("   ") is None


# ------------------------------------------------------------------ finding #6
@pytest.mark.xfail(strict=True, reason="FINDING #6: `episodes or 12` / "
                   "`duration_min or 24` treat explicit 0 as missing "
                   "(src/intelligence/localization_econ/engine.py:83-87)")
def test_bug6_explicit_zero_should_not_fall_back_to_defaults():
    r = LocalizationEconomicsEngine().evaluate(
        sakura_score=50, format="TV", episodes=0, duration_min=0)
    assert r.episodes == 0
    assert r.minutes_per_ep == 0
    assert r.total_minutes == 0


# ------------------------------------------------------------------ finding #7
def _synth(status: str) -> PipelineResult:
    cul = CulturalCompatibilityEngine().evaluate(
        genres=["Action"], tags=[], is_adult=False, format="TV", episodes=12)
    econ = LocalizationEconomicsEngine().evaluate(
        sakura_score=50, format="TV", episodes=12, duration_min=24)
    factors = [Factor(n, 60, WEIGHTS[n], 60 * WEIGHTS[n], []) for n in WEIGHTS]
    r = PipelineResult(
        title="Bug Seven", metadata={"status": status}, unreleased=False,
        sakura_score=50, grade="C", confidence=50, factors=factors,
        cultural_profile=cul, localization_economics=econ,
        data_source_matrix=get_matrix(), executive_briefing_en="",
        executive_briefing_ja="", market_breakdown={}, wiki_evidence=None,
        grade_comment_ja=GRADE_COMMENT_JA["C"])
    r.executive_briefing_en = build_executive_briefing_en(r)
    r.executive_briefing_ja = build_executive_briefing_ja(r)
    return r


@pytest.mark.xfail(strict=True, reason="FINDING #7: to_html interpolates "
                   "metadata status (and other labels) unescaped "
                   "(src/reporting/exporter.py:178)")
def test_bug7_html_should_escape_status():
    h = to_html(_synth("<img src=x>"))
    assert "<img src=x>" not in h            # must not appear raw anywhere


# --------------------------------------------------- new finding A (rationale)
@pytest.mark.xfail(strict=True, reason="NEW: genre_fit rationale is empty when "
                   "every genre affinity is mid-range (16..69) — transparency "
                   "gap (src/scoring/engine.py:159-161)")
def test_new_a_genre_fit_rationale_should_never_be_empty():
    res = ScoringEngine().score_candidate(
        meta={"genres": ["Romance"], "popularity": 0, "favourites": 0},
        wiki=None, trends={"growth_2y_pct": None}, cultural_fit=50,
        reach_multiplier=1.0, pre_launch=False, confidence_parts=PARTS)
    assert {f.name: f.rationale for f in res.factors}["genre_fit"]


# --------------------------------------------------- new finding B (matrix aliasing)
@pytest.mark.xfail(strict=True, reason="NEW: get_matrix() hands out the live "
                   "__dict__ of each DataSource — callers can corrupt module "
                   "state (src/data_sources/matrix.py:113-115)")
def test_new_b_matrix_dicts_should_be_isolated_copies():
    try:
        m = get_matrix()
        m[0]["status"] = "hacked"
        assert SOURCES[0].status == "live"    # desired: isolated copy
    finally:
        SOURCES[0].status = "live"            # restore for the rest of the suite


# --------------------------------------------------- new finding C (empty override)
@pytest.mark.xfail(strict=True, reason="NEW: `elif meta_override:` treats an "
                   "empty override dict as missing, so defaults are never "
                   "applied (src/app.py:263)")
def test_new_c_empty_meta_override_should_apply_defaults(app):
    r = app.run_candidate("QZQ Bug C Title", meta_override={})
    assert r.title == "QZQ Bug C Title"
    assert r.metadata["format"] == "TV" and r.metadata["genres"] == []
