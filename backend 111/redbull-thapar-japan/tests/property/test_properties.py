"""Property-based tests (Hypothesis) for the SakuraScore src pipeline engines.

18 properties over the pure engines: grading, percentiles, normalization,
cultural compatibility, localization economics, confidence accounting and
scoring determinism. Run with --hypothesis-profile={default,thorough,exhaustive}.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoring.engine import GENRE_AFFINITY, GRADES, ScoringEngine, grade_for  # noqa: E402
from src.intelligence.cultural_compat.engine import CulturalCompatibilityEngine  # noqa: E402
from src.intelligence.localization_econ.engine import LocalizationEconomicsEngine  # noqa: E402
from src.app import SakuraScoreApp, _norm  # noqa: E402

SE = ScoringEngine()
CUL = CulturalCompatibilityEngine()
ECON = LocalizationEconomicsEngine()

GENRES = sorted(GENRE_AFFINITY)
TAG_NAMES = ["Violence", "War", "Suicide", "Drugs", "Alcohol", "Death", "School",
             "Coming of Age", "Time Travel", "Mecha", "Iyashikei", "Romance"]

tag_lists = st.lists(st.tuples(st.sampled_from(TAG_NAMES), st.integers(0, 100)),
                     min_size=0, max_size=8)
genre_lists = st.lists(st.sampled_from(GENRES), min_size=0, max_size=6)


# --- grading ---------------------------------------------------------------

@settings(max_examples=200)
@given(score=st.floats(min_value=0, max_value=100, allow_nan=False))
def test_p01_grade_matches_table(score):
    expected = next(g for floor, g in GRADES if score >= floor)
    assert grade_for(score) == expected


@settings(max_examples=200)
@given(a=st.floats(min_value=0, max_value=100, allow_nan=False),
       b=st.floats(min_value=0, max_value=100, allow_nan=False))
def test_p02_grade_monotone(a, b):
    lo, hi = sorted([a, b])
    order = {g: i for i, (_, g) in enumerate(reversed(GRADES))}
    assert order[grade_for(lo)] <= order[grade_for(hi)]


# --- percentile ------------------------------------------------------------

@settings(max_examples=150)
@given(data=st.lists(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
                     min_size=1, max_size=60),
       x=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False))
def test_p03_percentile_bounds(data, x):
    p = SE.percentile(data, x)
    assert 0.0 <= p <= 100.0


@settings(max_examples=150)
@given(data=st.lists(st.integers(-500, 500), min_size=2, max_size=40))
def test_p04_percentile_exact_membership(data):
    member = float(data[0])
    pool = [float(v) for v in data]
    p = SE.percentile(pool, member)
    # mid-rank percentile of a pool member must lie between the strict-below
    # share and the at-or-below share (correct bound for duplicate-heavy pools)
    below = sum(1 for v in pool if v < member)
    eq = sum(1 for v in pool if v == member)
    lo = 100.0 * below / len(pool)
    hi = 100.0 * (below + eq) / len(pool)
    assert lo - 1e-9 <= p <= hi + 1e-9


@settings(max_examples=150)
@given(data=st.lists(st.floats(min_value=1, max_value=1e6, allow_nan=False), min_size=2, max_size=30),
       k=st.floats(min_value=0.5, max_value=4, allow_nan=False),
       x=st.floats(min_value=1, max_value=1e6, allow_nan=False))
def test_p05_percentile_scale_invariance(data, k, x):
    assert SE.percentile(data, x) == pytest.approx(SE.percentile([v * k for v in data], x * k))


# --- normalization ---------------------------------------------------------

@settings(max_examples=200)
@given(s=st.text(min_size=0, max_size=60))
def test_p06_norm_idempotent(s):
    assert _norm(s) == _norm(_norm(s))


@settings(max_examples=200)
@given(s=st.text(min_size=0, max_size=60))
def test_p07_norm_charset(s):
    import re
    assert re.fullmatch(r"[a-z0-9 ]*", _norm(s)), _norm(s)


# --- cultural compatibility -------------------------------------------------

@settings(max_examples=150)
@given(genres=genre_lists, tags=tag_lists, adult=st.booleans())
def test_p08_cultural_fit_bounds(genres, tags, adult):
    cul = CUL.evaluate(genres=genres, tags=tags, is_adult=adult, format="TV", episodes=12)
    assert 0 <= cul.overall_cultural_fit <= 100


@settings(max_examples=150)
@given(genres=genre_lists, tags=tag_lists, adult=st.booleans())
def test_p09_friction_bounds(genres, tags, adult):
    cul = CUL.evaluate(genres=genres, tags=tags, is_adult=adult, format="TV", episodes=12)
    assert 0 <= cul.family_co_viewing_friction <= 100


@settings(max_examples=150)
@given(genres=genre_lists, tags=tag_lists)
def test_p10_triggers_sorted_unique(genres, tags):
    cul = CUL.evaluate(genres=genres, tags=tags, is_adult=False, format="TV", episodes=12)
    assert cul.sensitivity_triggers == sorted(set(cul.sensitivity_triggers))


@settings(max_examples=150)
@given(genres=genre_lists, tags=tag_lists, adult=st.booleans())
def test_p11_cbfc_in_allowed_set(genres, tags, adult):
    allowed = {"U", "U/A 7+", "U/A 13+", "U/A 16+", "A risk / U/A 16+", "A (Adults Only)"}
    cul = CUL.evaluate(genres=genres, tags=tags, is_adult=adult, format="TV", episodes=12)
    assert cul.cbfc_rating_estimate in allowed


# --- localization economics -------------------------------------------------

@settings(max_examples=200)
@given(score=st.integers(0, 100), fmt=st.sampled_from(["TV", "MOVIE"]),
       episodes=st.integers(1, 60), duration=st.integers(1, 200))
def test_p12_econ_four_plans_fixed_reach(score, fmt, episodes, duration):
    e = ECON.evaluate(sakura_score=score, format=fmt, episodes=episodes, duration_min=duration)
    assert len(e.plans) == 4
    assert [p.reach_multiplier for p in e.plans] == [1.0, 1.55, 1.85, 2.2]


@settings(max_examples=200)
@given(score=st.integers(0, 100), fmt=st.sampled_from(["TV", "MOVIE"]),
       episodes=st.integers(1, 60), duration=st.integers(1, 200))
def test_p13_econ_costs_positive_and_ordered(score, fmt, episodes, duration):
    e = ECON.evaluate(sakura_score=score, format=fmt, episodes=episodes, duration_min=duration)
    costs = [p.cost_inr for p in e.plans]
    assert all(isinstance(c, int) and c > 0 for c in costs)
    assert costs == sorted(costs)


@settings(max_examples=200)
@given(score=st.integers(0, 100), fmt=st.sampled_from(["TV", "MOVIE"]),
       episodes=st.integers(1, 60), duration=st.integers(1, 200))
def test_p14_econ_recommended_mode_tier(score, fmt, episodes, duration):
    e = ECON.evaluate(sakura_score=score, format=fmt, episodes=episodes, duration_min=duration)
    expected = ("five_language" if score >= 72 else "three_language" if score >= 55
                else "hindi_dub" if score >= 40 else "subtitles_only")
    assert e.recommended_mode == expected


# --- confidence accounting ---------------------------------------------------

@settings(max_examples=150)
@given(meta=st.booleans(), wiki=st.booleans(), trends=st.booleans(),
       hindi=st.booleans(), seed=st.booleans(), released=st.booleans())
def test_p15_confidence_mirror_total(meta, wiki, trends, hindi, seed, released):
    class _W(dict):
        def get(self, k, d=None):
            if k == "has_hindi_wiki":
                return hindi
            return super().get(k, d)
    c = SakuraScoreApp._confidence(None, meta=meta if meta else None,
                    wiki=_W({"avg_daily_last30": 1.0, "has_hindi_wiki": hindi}) if wiki else None,
                    trends={"growth_2y_pct": 5.0} if trends else {},
                    seed_match=object() if seed else None,
                    unreleased=not released)
    manual = (30 if meta else 0) + (25 if wiki else 8) + (15 if trends else 5) \
        + (10 if (wiki and hindi) else 0) + (10 if seed else 0) + (10 if released else 5)
    assert c == min(100, manual)


# --- scoring determinism & arithmetic ----------------------------------------

meta_strategy = st.fixed_dictionaries({
    "title_english": st.sampled_from(["Alpha", "Beta", "Gamma"]),
    "format": st.sampled_from(["TV", "MOVIE", "OVA"]),
    "episodes": st.integers(1, 30),
    "duration": st.integers(3, 120),
    "status": st.sampled_from(["FINISHED", "RELEASING", "NOT_YET_RELEASED"]),
    "genres": genre_lists,
    "popularity": st.floats(0, 300000, allow_nan=False),
    "favourites": st.floats(0, 200000, allow_nan=False),
    "average_score": st.one_of(st.none(), st.floats(40, 95, allow_nan=False)),
    "is_adult": st.booleans(),
})


def _conf_parts():
    return {"wiki_vol_values": [10.0, 50.0, 250.0, 1000.0],
            "popularity_values": [100.0, 5000.0, 50000.0, 250000.0],
            "favourite_values": [10.0, 500.0, 5000.0, 20000.0],
            "unreleased_pop_values": [50.0, 900.0, 12000.0],
            "confidence": 80}


@settings(max_examples=120)
@given(meta=meta_strategy, wiki=st.booleans())
def test_p16_scoring_deterministic(meta, wiki):
    kw = dict(meta=meta,
              wiki={"avg_daily_last30": 120.0, "peak_daily": 900.0,
                    "momentum_90d_vs_prior90": 0.2, "has_hindi_wiki": False,
                    "total_views_24m": 1e5} if wiki else None,
              trends={"keyword": "anime", "growth_2y_pct": 12.0},
              cultural_fit=60, reach_multiplier=1.55, pre_launch=False,
              confidence_parts=_conf_parts())
    a = SE.score_candidate(**kw)
    b = SE.score_candidate(**kw)
    assert a.sakura_score == b.sakura_score and a.grade == b.grade


@settings(max_examples=120)
@given(meta=meta_strategy, wiki=st.booleans())
def test_p17_factor_contributions_sum_to_score(meta, wiki):
    r = SE.score_candidate(meta=meta,
                           wiki={"avg_daily_last30": 120.0, "peak_daily": 900.0,
                                 "momentum_90d_vs_prior90": 0.2, "has_hindi_wiki": False,
                                 "total_views_24m": 1e5} if wiki else None,
                           trends={"keyword": "anime", "growth_2y_pct": 12.0},
                           cultural_fit=60, reach_multiplier=1.55, pre_launch=False,
                           confidence_parts=_conf_parts())
    total = sum(f.contribution for f in r.factors)
    assert r.sakura_score == pytest.approx(round(total), abs=1.5)


@settings(max_examples=120)
@given(meta=meta_strategy, reach=st.sampled_from([1.0, 1.55, 1.85, 2.2]))
def test_p18_localization_reach_tracks_multiplier(meta, reach):
    r = SE.score_candidate(meta=meta,
                           wiki=None,
                           trends={"keyword": "anime", "growth_2y_pct": 0.0},
                           cultural_fit=60, reach_multiplier=reach, pre_launch=False,
                           confidence_parts=_conf_parts())
    lr = next(f for f in r.factors if f.name == "localization_reach")
    expected = 100 * (reach - 1) / (2.2 - 1)
    assert lr.value == pytest.approx(expected, abs=1.0)
