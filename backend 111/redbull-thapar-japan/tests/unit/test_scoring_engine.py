"""Unit tests — src/scoring/engine.py (ScoringEngine, grade_for, percentile).

All values hand-derived from the documented formulas:
  WEIGHTS sum 1.00; GRADES S>=80, A>=70, B>=60, C>=45, D>=0.
"""
from __future__ import annotations

import math

import pytest

from src.scoring.engine import (GENRE_AFFINITY, GRADES, WEIGHTS,
                                ScoringEngine, grade_for)

E = ScoringEngine()
PCT_50 = 100.0 * (50 + 0.5) / 101  # percentile of 50.0 within [0..100] float pool


# --------------------------------------------------------------------- helpers
def parts(conf=77, wiki=None, pop=None, fav=None, unrel=None):
    return {
        "wiki_vol_values": wiki if wiki is not None else [float(i) for i in range(101)],
        "popularity_values": pop if pop is not None else [float(i) for i in range(101)],
        "favourite_values": fav if fav is not None else [float(i) for i in range(101)],
        "unreleased_pop_values": unrel if unrel is not None else [10.0, 20.0, 30.0],
        "confidence": conf,
    }


def base_meta(**over):
    m = {"title_english": "Synthetic", "genres": ["Action"], "popularity": 50.0,
         "favourites": 50.0, "average_score": None}
    m.update(over)
    return m


def run(meta=None, wiki=None, trends=None, cultural_fit=62, reach=1.55,
        pre_launch=False, cp=None):
    return E.score_candidate(
        meta=meta if meta is not None else base_meta(),
        wiki=wiki, trends=trends if trends is not None else {"growth_2y_pct": None},
        cultural_fit=cultural_fit, reach_multiplier=reach,
        pre_launch=pre_launch, confidence_parts=cp if cp is not None else parts())


def fmap(res):
    return {f.name: f for f in res.factors}


# ------------------------------------------------------------------ grade_for
@pytest.mark.parametrize("score,grade", [
    (0, "D"), (1, "D"), (44, "D"), (45, "C"), (59, "C"), (60, "B"),
    (69, "B"), (70, "A"), (79, "A"), (80, "S"), (100, "S"),
    (-1, "D"), (-1000, "D"), (200, "S"), (10_000, "S"),
    (0.999, "D"), (44.999, "D"), (45.0, "C"), (45.001, "C"), (59.999, "C"),
    (60.0, "B"), (60.001, "B"), (69.999, "B"), (70.0, "A"), (70.001, "A"),
    (79.999, "A"), (80.0, "S"), (80.001, "S"), (99.999, "S"),
    (-0.001, "D"), (0.0, "D"),
])
def test_grade_for_boundaries(score, grade):
    assert grade_for(score) == grade


@pytest.mark.parametrize("score,grade", [
    (44 - 0.001, "D"), (44 + 0.001, "D"), (45 - 0.001, "D"), (45 + 0.001, "C"),
    (59 - 0.001, "C"), (59 + 0.001, "C"), (60 - 0.001, "C"), (60 + 0.001, "B"),
    (69 - 0.001, "B"), (69 + 0.001, "B"), (70 - 0.001, "B"), (70 + 0.001, "A"),
    (79 - 0.001, "A"), (79 + 0.001, "A"), (80 - 0.001, "A"), (80 + 0.001, "S"),
    (100 - 0.001, "S"), (100 + 0.001, "S"), (1 - 0.001, "D"), (1 + 0.001, "D"),
])
def test_grade_for_float_perturbations(score, grade):
    assert grade_for(score) == grade


def test_grade_for_nan_current_behaviour():
    # NaN fails every >= comparison and falls through the ladder to "D".
    assert grade_for(float("nan")) == "D"


def test_grades_table():
    assert GRADES == [(80, "S"), (70, "A"), (60, "B"), (45, "C"), (0, "D")]
    floors = [f for f, _ in GRADES]
    assert floors == sorted(floors, reverse=True)


# ----------------------------------------------------------------- percentile
def test_percentile_empty_pool_returns_50():
    assert E.percentile([], 42.0) == 50.0
    assert E.percentile([], -1e9) == 50.0
    assert E.percentile([], 1e9) == 50.0


def test_percentile_single_element():
    assert E.percentile([42.0], 42.0) == 50.0
    assert E.percentile([42.0], 41.0) == 0.0
    assert E.percentile([42.0], 43.0) == 100.0


def test_percentile_ties_mid_rank():
    assert E.percentile([1, 2, 2, 3], 2) == 50.0            # below=1, eq=2
    assert E.percentile([1, 2, 2, 3], 1) == 12.5
    assert E.percentile([1, 2, 2, 3], 3) == 87.5
    assert E.percentile([5, 5, 5, 5], 5) == 50.0            # all tied


def test_percentile_below_all_above_all():
    assert E.percentile([10.0, 20.0, 30.0], 5.0) == 0.0
    assert E.percentile([10.0, 20.0, 30.0], 35.0) == 100.0
    assert E.percentile([-5.0, 0.0, 5.0], -10.0) == 0.0


def test_percentile_negative_values():
    assert E.percentile([-30.0, -20.0, -10.0], -20.0) == 50.0
    assert E.percentile([-30.0, -20.0, -10.0], -25.0) == pytest.approx(33.333333, abs=1e-4)


def test_percentile_nan_in_pool_current_behaviour():
    # NaN counts toward len() but never as below/equal.
    assert E.percentile([1.0, float("nan"), 3.0], 2.0) == pytest.approx(100.0 / 3)


def test_percentile_range_bounds():
    for pool in ([0.0], [1.0, 2.0], list(range(-50, 50))):
        for x in (-100.0, 0.0, 1.0, 49.0, 1e6):
            assert 0.0 <= E.percentile(pool, x) <= 100.0


# ------------------------------------------------------------ weights & shape
def test_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)
    assert WEIGHTS == {
        "india_demand": 0.25, "global_fandom": 0.20, "momentum": 0.14,
        "cultural_fit": 0.14, "localization_reach": 0.14, "genre_fit": 0.13,
    }


def test_factors_shape_names_order_weights():
    res = run()
    assert [f.name for f in res.factors] == list(WEIGHTS)
    for f in res.factors:
        assert f.weight == WEIGHTS[f.name]
        assert 0 <= f.value <= 100
        assert f.contribution == pytest.approx(f.value * f.weight)
    assert isinstance(res.sakura_score, int)
    assert isinstance(res.confidence, int)
    assert 0 <= res.sakura_score <= 100


# ------------------------------------------------- factor 1: india_demand
@pytest.mark.parametrize("wiki,expected", [
    # (wiki, expected int india_demand) with trends growth None -> 0.20*50 leg
    ({"avg_daily_last30": 50.0, "momentum_90d_vs_prior90": 0.25,
      "has_hindi_wiki": True},
     int(0.40 * PCT_50 + 0.25 * 62.5 + 0.15 * 100 + 0.20 * 50)),         # 60
    ({"avg_daily_last30": 50.0, "momentum_90d_vs_prior90": 0.25,
      "has_hindi_wiki": False},
     int(0.40 * PCT_50 + 0.25 * 62.5 + 0.15 * 30 + 0.20 * 50)),         # 55
    ({"avg_daily_last30": 50.0, "momentum_90d_vs_prior90": None,
      "has_hindi_wiki": True},
     int(0.40 * PCT_50 + 0.15 * 100 + 0.20 * 50)),                      # 55
    ({"avg_daily_last30": 50.0, "momentum_90d_vs_prior90": "",
      "has_hindi_wiki": True},
     int(0.40 * PCT_50 + 0.15 * 100 + 0.20 * 50)),                      # 55
    ({"avg_daily_last30": 50.0, "momentum_90d_vs_prior90": 5.0,
      "has_hindi_wiki": True},
     int(0.40 * PCT_50 + 0.25 * 100 + 0.15 * 100 + 0.20 * 50)),         # 80
    ({"avg_daily_last30": 50.0, "momentum_90d_vs_prior90": -5.0,
      "has_hindi_wiki": True},
     int(0.40 * PCT_50 + 0.25 * 0 + 0.15 * 100 + 0.20 * 50)),           # 55
    # no-wiki branch: 0.55*35 baseline (deliberate data penalty)
    (None, int(0.55 * 35 + 0.20 * 50)),                                 # 29
    ({}, int(0.55 * 35 + 0.20 * 50)),                                   # 29
    ({"avg_daily_last30": 0, "momentum_90d_vs_prior90": 0.5,
      "has_hindi_wiki": True}, int(0.55 * 35 + 0.20 * 50)),             # 29 falsy volume
])
def test_india_demand_wiki_variants(wiki, expected):
    res = run(wiki=wiki)
    assert fmap(res)["india_demand"].value == expected


@pytest.mark.parametrize("growth,expected_extra", [
    (None, 0.20 * 50), (0, 0.20 * 50), (10, 0.20 * 60), (50, 0.20 * 100),
    (200, 0.20 * 100), (-10, 0.20 * 40), (-60, 0.20 * 0), (-200, 0.20 * 0),
    (49.9, 0.20 * 99.9), (50.1, 0.20 * 100),
])
def test_india_demand_trends_clamp(growth, expected_extra):
    res = run(wiki=None, trends={"growth_2y_pct": growth})
    assert fmap(res)["india_demand"].value == int(0.55 * 35 + expected_extra)


def test_india_demand_momentum_clamp_current_behaviour_nan():
    # NaN momentum: min(1, nan) -> 1 in CPython, i.e. MAX acceleration (bug #1).
    res = run(wiki={"avg_daily_last30": 50.0, "momentum_90d_vs_prior90": float("nan"),
                    "has_hindi_wiki": True})
    assert fmap(res)["india_demand"].value == int(0.40 * PCT_50 + 0.25 * 100 + 0.15 * 100 + 0.20 * 50)  # 80


def test_india_demand_rationale_nonempty():
    for wiki in (None, {"avg_daily_last30": 50.0, "momentum_90d_vs_prior90": 0.25,
                        "has_hindi_wiki": False}):
        assert fmap(run(wiki=wiki))["india_demand"].rationale


def test_india_demand_hindi_rationale_mentions_hindi():
    res = run(wiki={"avg_daily_last30": 50.0, "momentum_90d_vs_prior90": 0.25,
                    "has_hindi_wiki": True})
    assert any("Hindi" in r for r in fmap(res)["india_demand"].rationale)


# ------------------------------------------------- factor 2: global_fandom
@pytest.mark.parametrize("avg,bump", [
    (None, None), (0, None), (67, -8), (68, 0), (69, 0), (74, 0), (75, 8),
    (76, 8), (79, 8), (80, 15), (100, 15),
])
def test_global_fandom_average_score_bumps(avg, bump):
    res = run(meta=base_meta(average_score=avg))
    f = fmap(res)["global_fandom"]
    base = int(PCT_50 * 0.55 + PCT_50 * 0.45) if bump is None else \
        int(min(100, max(0, PCT_50 + bump)))
    assert f.value == base


def test_global_fandom_pop_fav_mix():
    res = run(meta=base_meta(popularity=100.0, favourites=0.0))
    # pop pct = 100*100.5/101; fav pct = 100*0.5/101
    exp = int(0.55 * (100 * 100.5 / 101) + 0.45 * (100 * 0.5 / 101))
    assert fmap(res)["global_fandom"].value == exp


def test_global_fandom_rationale_has_two_lines():
    r = fmap(run())["global_fandom"].rationale
    assert len(r) >= 2 and any("popularity" in x for x in r) \
        and any("favourites" in x for x in r)


def test_global_fandom_missing_pop_fav_defaults_to_zero():
    res = run(meta={"title_english": "Bare", "genres": []})
    # both percentiles of 0 in [0..100] pool = 100*0.5/101
    assert fmap(res)["global_fandom"].value == int(100 * 0.5 / 101)


# ------------------------------------------------- factor 3: momentum
@pytest.mark.parametrize("mom,expected", [
    (0.25, int(0.6 * PCT_50 + 0.4 * 62.5)),                 # 55
    (None, int(0.6 * PCT_50 + 0.4 * 50)),                   # 50
    ("", int(0.6 * PCT_50 + 0.4 * 50)),                     # 50
    (5.0, int(0.6 * PCT_50 + 0.4 * 100)),                   # 70
    (-5.0, int(0.6 * PCT_50 + 0.4 * 0)),                    # 30
    (float("nan"), int(0.6 * PCT_50 + 0.4 * 100)),          # NaN -> clamp +1 (bug #1)
])
def test_momentum_released_with_wiki(mom, expected):
    res = run(wiki={"avg_daily_last30": 50.0, "momentum_90d_vs_prior90": mom,
                    "has_hindi_wiki": False})
    assert fmap(res)["momentum"].value == expected


@pytest.mark.parametrize("wiki,expected", [
    (None, int(0.6 * (100 * 0.5 / 101) + 0.4 * 50)),        # no wiki -> base pct of 0
    ({"avg_daily_last30": 100.0, "momentum_90d_vs_prior90": None,
      "has_hindi_wiki": False}, int(0.6 * (100 * 100.5 / 101) + 0.4 * 50)),
])
def test_momentum_released_no_momentum(wiki, expected):
    assert fmap(run(wiki=wiki))["momentum"].value == expected


def test_momentum_prelaunch_path():
    # percentile of pop within the unreleased pool (pool [10,20,30], pop=20 -> 50)
    res = run(pre_launch=True, meta=base_meta(popularity=20.0))
    assert fmap(res)["momentum"].value == 50
    res2 = run(pre_launch=True, meta=base_meta(popularity=31.0))
    assert fmap(res2)["momentum"].value == 100  # above every pool member
    res3 = run(pre_launch=True, meta=base_meta(popularity=5.0))
    assert fmap(res3)["momentum"].value == 0    # below every pool member
    # empty unreleased pool -> percentile 50
    res4 = run(pre_launch=True, cp=parts(unrel=[]))
    assert fmap(res4)["momentum"].value == 50


def test_momentum_prelaunch_note_in_tier_notes():
    res = run(pre_launch=True)
    assert res.tier_notes and "Unreleased title" in res.tier_notes[0]
    assert run(pre_launch=False).tier_notes == []


def test_momentum_rationale_text_by_level():
    hi = fmap(run(wiki={"avg_daily_last30": 100.0, "momentum_90d_vs_prior90": 0.9,
                        "has_hindi_wiki": False}))["momentum"].rationale[0]
    lo = fmap(run(wiki={"avg_daily_last30": 0.0, "momentum_90d_vs_prior90": -0.9,
                        "has_hindi_wiki": False}))["momentum"].rationale[0]
    assert hi == "sustained post-release attention on Wikipedia"
    assert lo == "attention below catalog median"


# ------------------------------------------------- factor 4: genre_fit
@pytest.mark.parametrize("genres,expected", [
    (["Action"], 85),
    (["Sports"], 80),
    (["Hentai"], 0),
    (["Ecchi"], 15),
    ([], 55),
    (["NotARealGenre"], 55),
    (["Action", "NotARealGenre"], int(0.6 * 85 + 0.4 * (85 + 55) / 2)),   # 79
    (["Action", "Sports"], int(0.6 * 85 + 0.4 * 82.5)),                   # 84
    (["Hentai", "Action"], int(0.6 * 85 + 0.4 * 42.5)),                   # 68
])
def test_genre_fit_values(genres, expected):
    assert fmap(run(meta=base_meta(genres=genres)))["genre_fit"].value == expected


def test_genre_fit_rationale_filters_low_and_high_affinity():
    r = fmap(run(meta=base_meta(genres=["Hentai", "Action", "Romance"])))["genre_fit"].rationale
    assert any("Hentai" in x for x in r)      # affinity 0 listed
    assert any("Action" in x for x in r)      # affinity >= 70 listed
    assert not any("Romance" in x for x in r)  # mid affinity (60) omitted
    # CURRENT BEHAVIOUR: genres with only mid affinities produce an EMPTY rationale
    # (transparency gap — see tests/test_bugs.py::test_new_genre_rationale_empty).
    assert fmap(run(meta=base_meta(genres=["Romance"])))["genre_fit"].rationale == []


def test_genre_affinity_table_bounds():
    for g, v in GENRE_AFFINITY.items():
        assert 0 <= v <= 100, g
    assert GENRE_AFFINITY["Action"] == 85
    assert GENRE_AFFINITY["Hentai"] == 0


# ------------------------------------------------- factor 5: cultural_fit
@pytest.mark.parametrize("cf", [0, 1, 50, 99, 100])
def test_cultural_fit_passthrough(cf):
    assert fmap(run(cultural_fit=cf))["cultural_fit"].value == cf
    assert fmap(run(cultural_fit=cf))["cultural_fit"].contribution == pytest.approx(cf * 0.14)


# ------------------------------------------------- factor 6: localization_reach
@pytest.mark.parametrize("rm,expected", [
    (1.0, 0), (1.55, 45), (2.2, 100), (0.0, 0), (5, 100), (-3, 0),
    (0.5, 0), (1.6, 50), (2.0, 83), (1.2, 16),
])
def test_localization_reach_clamp(rm, expected):
    assert fmap(run(reach=rm))["localization_reach"].value == expected


def test_localization_reach_rationale_contains_multiplier():
    assert "1.55x" in fmap(run(reach=1.55))["localization_reach"].rationale[0]


# ------------------------------------------------------------- score assembly
def test_score_equals_rounded_weighted_sum():
    res = run(wiki={"avg_daily_last30": 50.0, "momentum_90d_vs_prior90": 0.25,
                    "has_hindi_wiki": True}, trends={"growth_2y_pct": 10})
    raw = sum(f.contribution for f in res.factors)
    assert res.sakura_score == int(round(raw))
    assert res.grade == grade_for(res.sakura_score)
    # hand-computed spot value: india 62, fandom 50, momentum 55, cultural 62,
    # reach 45, genre 85 -> 15.5+10+7.7+8.68+6.3+11.05 = 59.23 -> 59 (C)
    assert res.sakura_score == 59
    assert res.grade == "C"


def test_score_extremes():
    # cultural_fit and localization_reach are direct passthroughs -> drive 0/100
    low = run(cultural_fit=0, reach=0.0, wiki=None, trends={"growth_2y_pct": None})
    high = run(cultural_fit=100, reach=2.2,
               wiki={"avg_daily_last30": 100.0, "momentum_90d_vs_prior90": 1.0,
                     "has_hindi_wiki": True}, trends={"growth_2y_pct": 200},
               meta=base_meta(popularity=100.0, favourites=100.0,
                              average_score=100, genres=["Action"]))
    assert fmap(low)["cultural_fit"].value == 0
    assert fmap(low)["localization_reach"].value == 0
    for f in high.factors:
        assert f.value >= 45, f.name
    assert 0 <= low.sakura_score <= high.sakura_score <= 100


def test_confidence_passthrough():
    for conf in (0, 33, 77, 100):
        assert run(cp=parts(conf=conf)).confidence == conf


def test_score_candidate_determinism():
    args = dict(meta=base_meta(), wiki={"avg_daily_last30": 50.0,
                                        "momentum_90d_vs_prior90": 0.25,
                                        "has_hindi_wiki": True},
                trends={"growth_2y_pct": 10}, cultural_fit=62,
                reach_multiplier=1.55, pre_launch=False, confidence_parts=parts())
    a, b = E.score_candidate(**args), E.score_candidate(**args)
    assert a == b
    assert [(f.name, f.value) for f in a.factors] == [(f.name, f.value) for f in b.factors]


def test_every_factor_rationale_nonempty_except_genre_gap():
    res = run(wiki={"avg_daily_last30": 50.0, "momentum_90d_vs_prior90": 0.25,
                    "has_hindi_wiki": True}, trends={"growth_2y_pct": 10},
              meta=base_meta(genres=["Action"]))
    for f in res.factors:
        assert f.rationale, f.name
