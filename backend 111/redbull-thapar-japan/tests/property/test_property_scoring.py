"""Property tests — scoring engine invariants (hypothesis)."""
from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from src.scoring.engine import GENRE_AFFINITY, WEIGHTS, ScoringEngine, grade_for

E = ScoringEngine()
VALID_GRADES = {"S", "A", "B", "C", "D"}

scores = st.floats(min_value=0, max_value=100)
scores_wide = st.floats()   # unbounded: NaN/inf allowed


@given(scores)
def test_grade_for_always_valid(scores):
    assert grade_for(scores) in VALID_GRADES


@given(st.tuples(scores, scores))
def test_grade_for_monotone_non_decreasing(pair):
    a, b = sorted(pair)
    order = ["D", "C", "B", "A", "S"]
    assert order.index(grade_for(a)) <= order.index(grade_for(b))


@given(scores_wide)
def test_grade_for_never_raises_on_any_float(scores):
    assert grade_for(scores) in VALID_GRADES | {"D"}


@given(st.lists(st.integers(-1000, 1000), max_size=30), st.integers(-1100, 1100))
def test_percentile_bounds(pool, x):
    p = E.percentile([float(v) for v in pool], float(x))
    assert 0.0 <= p <= 100.0


@given(st.lists(st.floats(-1e6, 1e6, allow_nan=False), min_size=1, max_size=30),
       st.lists(st.floats(-1e6, 1e6, allow_nan=False), min_size=1, max_size=10))
def test_percentile_monotone_in_x(pool, queries):
    for a, b in zip(sorted(queries), sorted(queries)[1:]):
        assert E.percentile(pool, a) <= E.percentile(pool, b)


@given(st.lists(st.floats(allow_nan=False), max_size=0),
       st.floats(allow_nan=False))
def test_percentile_empty_pool_is_50(_empty, x):
    assert E.percentile([], x) == 50.0


# ------------------------------------------------------- score_candidate inputs
known_genres = st.sampled_from(sorted(GENRE_AFFINITY))
genre_lists = st.lists(st.one_of(known_genres,
                                 st.text(min_size=1, max_size=12)),
                       max_size=5)
momentum = st.one_of(st.none(), st.just(""),
                     st.floats(min_value=-5, max_value=5, allow_nan=False))
wiki = st.one_of(
    st.none(),
    st.fixed_dictionaries({
        "avg_daily_last30": st.floats(min_value=0, max_value=5_000,
                                      allow_nan=False),
        "momentum_90d_vs_prior90": momentum,
        "has_hindi_wiki": st.booleans()}))
trends = st.fixed_dictionaries({
    "keyword": st.sampled_from(["anime", "solo leveling", "unknown"]),
    "growth_2y_pct": st.one_of(st.none(), st.floats(min_value=-200, max_value=200))})
metas = st.fixed_dictionaries({
    "title_english": st.just("Property Title"),
    "genres": genre_lists,
    "popularity": st.floats(min_value=0, max_value=1e6, allow_nan=False),
    "favourites": st.floats(min_value=0, max_value=1e6, allow_nan=False),
    "average_score": st.one_of(st.none(), st.integers(min_value=0, max_value=100))})
pools = st.fixed_dictionaries({
    "wiki_vol_values": st.lists(st.floats(0, 100, allow_nan=False), max_size=20),
    "popularity_values": st.lists(st.floats(0, 100, allow_nan=False), max_size=20),
    "favourite_values": st.lists(st.floats(0, 100, allow_nan=False), max_size=20),
    "unreleased_pop_values": st.lists(st.floats(0, 100, allow_nan=False), max_size=20),
    "confidence": st.just(50)})


@settings(max_examples=100, deadline=None)
@given(meta=metas, wiki=wiki, trends=trends,
       cultural_fit=st.integers(min_value=0, max_value=100),
       reach=st.floats(min_value=0, max_value=3),
       pre_launch=st.booleans(), cp=pools)
def test_score_candidate_invariants(meta, wiki, trends, cultural_fit, reach,
                                    pre_launch, cp):
    res = E.score_candidate(meta=meta, wiki=wiki, trends=trends,
                            cultural_fit=cultural_fit, reach_multiplier=reach,
                            pre_launch=pre_launch, confidence_parts=cp)
    # score & factor bounds
    assert 0 <= res.sakura_score <= 100
    assert res.grade in VALID_GRADES
    assert 0 <= res.confidence <= 100
    assert [f.name for f in res.factors] == list(WEIGHTS)
    for f in res.factors:
        assert 0 <= f.value <= 100, f.name
        assert f.weight == WEIGHTS[f.name]
        assert f.contribution == f.value * f.weight
    # score == round(sum of contributions) within 1
    assert abs(res.sakura_score - sum(f.contribution for f in res.factors)) <= 1
    # tier notes only pre-launch
    assert bool(res.tier_notes) == pre_launch


@settings(max_examples=100, deadline=None)
@given(meta=metas, wiki=wiki, trends=trends,
       cultural_fit=st.integers(min_value=0, max_value=100),
       reach=st.floats(min_value=0, max_value=3),
       pre_launch=st.booleans(), cp=pools)
def test_score_candidate_determinism(meta, wiki, trends, cultural_fit, reach,
                                     pre_launch, cp):
    kwargs = dict(meta=meta, wiki=wiki, trends=trends, cultural_fit=cultural_fit,
                  reach_multiplier=reach, pre_launch=pre_launch,
                  confidence_parts=cp)
    a = E.score_candidate(**kwargs)
    b = E.score_candidate(**kwargs)
    assert a == b
    assert a.sakura_score == b.sakura_score and a.grade == b.grade


@settings(max_examples=100, deadline=None)
@given(genres=genre_lists)
def test_genre_fit_bounds_for_arbitrary_genres(genres):
    res = E.score_candidate(
        meta={"genres": genres, "popularity": 0, "favourites": 0},
        wiki=None, trends={"growth_2y_pct": None}, cultural_fit=50,
        reach_multiplier=1.0, pre_launch=False,
        confidence_parts={"wiki_vol_values": [], "popularity_values": [],
                          "favourite_values": [], "unreleased_pop_values": [],
                          "confidence": 50})
    g = {f.name: f.value for f in res.factors}["genre_fit"]
    assert 0 <= g <= 100
    if not genres:
        assert g == 55
    else:
        affs = [GENRE_AFFINITY.get(x, 55) for x in genres]
        assert g == int(0.6 * max(affs) + 0.4 * (sum(affs) / len(affs)))


@settings(max_examples=100, deadline=None)
@given(mom=st.floats(min_value=-10, max_value=10, allow_nan=False))
def test_momentum_factor_bounds_for_any_momentum(mom):
    wiki = {"avg_daily_last30": 100.0, "momentum_90d_vs_prior90": mom,
            "has_hindi_wiki": False}
    res = E.score_candidate(
        meta={"genres": [], "popularity": 0, "favourites": 0}, wiki=wiki,
        trends={"growth_2y_pct": None}, cultural_fit=50, reach_multiplier=1.0,
        pre_launch=False,
        confidence_parts={"wiki_vol_values": [0.0, 100.0],
                          "popularity_values": [0.0],
                          "favourite_values": [0.0],
                          "unreleased_pop_values": [0.0], "confidence": 50})
    m = {f.name: f.value for f in res.factors}["momentum"]
    clamped = max(-1.0, min(1.0, mom))
    expected = int(max(0, min(100, 0.6 * 75.0 + 0.4 * (50 + 50 * clamped))))
    assert m == expected


@settings(max_examples=50, deadline=None)
@given(growth=st.floats(min_value=-200, max_value=200, allow_nan=False))
def test_india_demand_trends_leg_clamped(growth):
    res = E.score_candidate(
        meta={"genres": [], "popularity": 0, "favourites": 0}, wiki=None,
        trends={"growth_2y_pct": growth}, cultural_fit=50, reach_multiplier=1.0,
        pre_launch=False,
        confidence_parts={"wiki_vol_values": [], "popularity_values": [],
                          "favourite_values": [], "unreleased_pop_values": [],
                          "confidence": 50})
    assert {f.name: f.value for f in res.factors}["india_demand"] == \
        int(0.55 * 35 + 0.20 * max(0, min(100, 50 + growth)))
