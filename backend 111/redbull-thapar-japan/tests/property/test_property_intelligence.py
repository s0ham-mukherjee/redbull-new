"""Property tests — cultural compatibility & localization economics invariants."""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.intelligence.cultural_compat.engine import (ADULT_GENRES, ADULT_TAGS,
                                                     ARCHETYPES,
                                                     COVIEW_FRICTION_TAGS,
                                                     HIGH_RISK_TAGS,
                                                     MILD_RISK_GENRES,
                                                     MODERATE_RISK_TAGS,
                                                     REGION_GENRE_DELTAS,
                                                     CulturalCompatibilityEngine)
from src.intelligence.localization_econ.engine import (REACH_MULTIPLIERS,
                                                       LocalizationEconomicsEngine,
                                                       format_inr)

CUL = CulturalCompatibilityEngine()
ECO = LocalizationEconomicsEngine()
VALID_RATINGS = {"U", "U/A 7+", "U/A 13+", "A risk / U/A 16+", "A (Adults Only)"}

GENRE_POOL = sorted(set(ADULT_GENRES) | set(MILD_RISK_GENRES)
                    | set(REGION_GENRE_DELTAS)
                    | {"Action", "Comedy", "Drama", "Kids", "Slice of Life",
                       "Sports", "Adventure", "Music", "Fantasy", "Sci-Fi"})
TAG_POOL = sorted(set(HIGH_RISK_TAGS) | set(MODERATE_RISK_TAGS)
                  | set(ADULT_TAGS) | set(COVIEW_FRICTION_TAGS)
                  | {"Religion", "Mythology", "Family", "Training", "Duty"})

genres_s = st.lists(st.sampled_from(GENRE_POOL), max_size=4)
tags_s = st.lists(st.tuples(st.sampled_from(TAG_POOL),
                            st.integers(min_value=0, max_value=100)),
                  max_size=4)
RANKS = {t: r for t, r in
         [(name, rank) for name in TAG_POOL for rank in (0, 100)]}


@settings(max_examples=100, deadline=None)
@given(genres=genres_s, tags=tags_s, is_adult=st.booleans(),
       fmt=st.sampled_from(["TV", "MOVIE", "OVA", "movie", ""]))
def test_cultural_engine_invariants(genres, tags, is_adult, fmt):
    p = CUL.evaluate(genres=genres, tags=tags, is_adult=is_adult, format=fmt)
    assert p.cbfc_rating_estimate in VALID_RATINGS
    assert 0 <= p.family_co_viewing_friction <= 100
    assert 0 <= p.overall_cultural_fit <= 100
    assert set(p.archetype_alignment) == set(ARCHETYPES)
    for spec in p.archetype_alignment.values():
        assert 0 <= spec["score"] <= 100
    assert p.sensitivity_triggers == sorted(set(p.sensitivity_triggers))
    assert isinstance(p.cultural_distance_flags, list)
    for hub, delta in p.regional_variation.items():
        assert delta != 0, "zero-deltas are dropped"


@settings(max_examples=100, deadline=None)
@given(genres=genres_s, tags=tags_s, is_adult=st.booleans(),
       fmt=st.sampled_from(["TV", "MOVIE"]))
def test_cultural_engine_determinism(genres, tags, is_adult, fmt):
    a = CUL.evaluate(genres=genres, tags=tags, is_adult=is_adult, format=fmt)
    b = CUL.evaluate(genres=genres, tags=tags, is_adult=is_adult, format=fmt)
    assert a == b


@settings(max_examples=60, deadline=None)
@given(genres=genres_s, tags=tags_s)
def test_overall_fit_bounds_match_formula(genres, tags):
    p = CUL.evaluate(genres=genres, tags=tags, is_adult=False, format="TV")
    top = max(v["score"] for v in p.archetype_alignment.values())
    rs = (0 if p.cbfc_rating_estimate.startswith("A")
          else 70 if p.cbfc_rating_estimate == "U/A 13+" else 85)
    sign = 1 if any(v > 0 for v in p.regional_variation.values()) else -1
    maxabs = max([abs(v) for v in p.regional_variation.values()], default=0)
    expected = int(0.45 * top + 0.25 * (100 - p.family_co_viewing_friction)
                   + 0.15 * rs + 0.15 * (50 + maxabs * sign))
    assert p.overall_cultural_fit == max(0, min(100, expected))


# --------------------------------------------------------------- econ properties
formats_s = st.sampled_from(["TV", "MOVIE", "movie", "OVA", "ONA", ""])
MODE_ORDER = list(REACH_MULTIPLIERS)


@settings(max_examples=100, deadline=None)
@given(score=st.integers(min_value=0, max_value=100),
       fmt=formats_s,
       eps=st.integers(min_value=1, max_value=200),
       dur=st.integers(min_value=1, max_value=200))
def test_econ_core_invariants(score, fmt, eps, dur):
    r = ECO.evaluate(sakura_score=score, format=fmt, episodes=eps, duration_min=dur)
    assert r.total_minutes > 0 and r.episodes >= 1 and r.minutes_per_ep >= 1
    assert [p.mode for p in r.plans] == MODE_ORDER
    assert r.recommended_mode in MODE_ORDER
    for p in r.plans:
        assert isinstance(p.cost_inr, int) and p.cost_inr > 0
        assert p.reach_multiplier == REACH_MULTIPLIERS[p.mode]
        assert p.cost_per_reach_unit == round(p.cost_inr / p.reach_multiplier, 2)
    if r.content_type == "movie":
        assert r.break_even_views is None and r.payback_months is None
        assert r.break_even_tickets >= 0
    else:
        assert r.break_even_tickets is None
        assert r.break_even_views >= 0
        assert r.payback_months is None or r.payback_months >= 1


@settings(max_examples=60, deadline=None)
@given(fmt=st.sampled_from(["TV", "OVA", "movie"]),
       eps=st.integers(min_value=1, max_value=59),
       dur=st.integers(min_value=1, max_value=120))
def test_costs_strictly_increase_with_episodes_and_duration(fmt, eps, dur):
    is_movie = fmt.upper() == "MOVIE"
    a = ECO.evaluate(sakura_score=50, format=fmt, episodes=eps, duration_min=dur)
    b = ECO.evaluate(sakura_score=50, format=fmt, episodes=eps + 1,
                     duration_min=dur)
    c = ECO.evaluate(sakura_score=50, format=fmt, episodes=eps,
                     duration_min=dur + 1)
    for pa, pb in zip(a.plans, b.plans):
        if is_movie:
            assert pb.cost_inr == pa.cost_inr   # movie episodes are forced to 1
        else:
            assert pb.cost_inr > pa.cost_inr
    for pa, pc in zip(a.plans, c.plans):
        assert pc.cost_inr > pa.cost_inr


@settings(max_examples=80, deadline=None)
@given(score=st.integers(min_value=0, max_value=99))
def test_recommendation_monotone_in_score(score):
    a = ECO.evaluate(sakura_score=score, format="TV", episodes=12, duration_min=24)
    b = ECO.evaluate(sakura_score=score + 1, format="TV", episodes=12, duration_min=24)
    ia = MODE_ORDER.index(a.recommended_mode)
    ib = MODE_ORDER.index(b.recommended_mode)
    assert ib >= ia
    # documented tier boundaries
    expected = ("five_language" if score >= 72 else "three_language"
                if score >= 55 else "hindi_dub" if score >= 40 else "subtitles_only")
    assert a.recommended_mode == expected


@settings(max_examples=40, deadline=None)
@given(amount=st.integers(min_value=-10 ** 9, max_value=10 ** 9))
def test_format_inr_never_raises_and_contains_rupee_sign(amount):
    out = format_inr(amount)
    assert isinstance(out, str) and out.startswith("₹")


@settings(max_examples=40, deadline=None)
@given(amount=st.integers(min_value=0, max_value=10 ** 9))
def test_format_inr_non_negative_branches(amount):
    out = format_inr(amount)
    if amount >= 1_00_00_000:
        assert out.endswith(" Cr")
    elif amount >= 1_00_000:
        assert out.endswith(" L")
    else:
        assert "Cr" not in out and " L" not in out
