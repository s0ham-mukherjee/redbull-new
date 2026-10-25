"""Unit tests — src/intelligence/localization_econ/engine.py (exact INR math)."""
from __future__ import annotations

import pytest

from src.intelligence.localization_econ.engine import (DUB_MOVIE_PER_MIN_INR,
                                                       DUB_PER_EP_SERIES_INR,
                                                       MODE_LANGUAGES,
                                                       NET_REVENUE_PER_STREAM_VIEW_INR,
                                                       NET_TICKET_INR,
                                                       REACH_MULTIPLIERS,
                                                       SUBS_PER_MIN_INR,
                                                       LocalizationEconomicsEngine,
                                                       format_inr)

E = LocalizationEconomicsEngine()
MODES = ["subtitles_only", "hindi_dub", "three_language", "five_language"]
DUB_SERIES = DUB_PER_EP_SERIES_INR                      # 16_000
SUBS = SUBS_PER_MIN_INR                                 # 400
MOVIE_DUB = DUB_MOVIE_PER_MIN_INR                       # 8_000
EXTRA = 1 + 0.85 + 0.85 ** 2                            # 2.5725 3-lang chain
EXTRA5 = EXTRA + 0.85 ** 3 + 0.85 ** 4                  # 5-lang chain


def ev(score=60, fmt="TV", eps=None, dur=None):
    return E.evaluate(sakura_score=score, format=fmt, episodes=eps,
                      duration_min=dur)


def cost_of(x):
    return int(round(x))


# ------------------------------------------------------------------ constants
def test_reach_multiplier_constant_table():
    assert REACH_MULTIPLIERS == {"subtitles_only": 1.0, "hindi_dub": 1.55,
                                 "three_language": 1.85, "five_language": 2.2}


def test_mode_languages_constant_table():
    assert MODE_LANGUAGES == {
        "subtitles_only": ["all languages (subtitles)"],
        "hindi_dub": ["Hindi"],
        "three_language": ["Hindi", "Tamil", "Telugu"],
        "five_language": ["Hindi", "Tamil", "Telugu", "Bengali", "Marathi"],
    }


# ------------------------------------------------------------- series default
def test_series_default_cost_math():
    r = ev()  # episodes None -> 12, duration None -> 24
    assert (r.content_type, r.episodes, r.minutes_per_ep, r.total_minutes) == \
        ("series", 12, 24, 288)
    subs = SUBS * 288                                     # 115_200
    dub1 = DUB_SERIES * 12                                # 192_000
    expected = {
        "subtitles_only": cost_of(subs * 1.15),
        "hindi_dub": cost_of(dub1 + subs),
        "three_language": cost_of(dub1 * EXTRA + subs),
        "five_language": cost_of(dub1 * EXTRA5 + subs),
    }
    assert {p.mode: p.cost_inr for p in r.plans} == expected
    # spot integers (guard against silent constant changes)
    assert expected["subtitles_only"] == 132_480
    assert expected["hindi_dub"] == 307_200
    assert expected["three_language"] == 609_120
    assert expected["five_language"] == 827_257


def test_series_custom_eps_duration():
    r = ev(eps=13, dur=25)
    assert (r.episodes, r.minutes_per_ep, r.total_minutes) == (13, 25, 325)
    subs, dub1 = SUBS * 325, DUB_SERIES * 13
    got = {p.mode: p.cost_inr for p in r.plans}
    assert got["subtitles_only"] == cost_of(subs * 1.15)
    assert got["hindi_dub"] == cost_of(dub1 + subs)
    assert got["three_language"] == cost_of(dub1 * EXTRA + subs)
    assert got["five_language"] == cost_of(dub1 * EXTRA5 + subs)


def test_series_episode_cap_60():
    r = ev(eps=100)
    assert r.episodes == 60
    assert r.total_minutes == 60 * 24
    r2 = ev(eps=61)
    assert r2.episodes == 60
    r3 = ev(eps=60)
    assert r3.episodes == 60


@pytest.mark.parametrize("zero_kw", ["eps", "dur"])
def test_series_zero_falls_back_to_default_current_behaviour(zero_kw):
    # FINDING #6: `or` treats explicit 0 as missing.
    r = ev(eps=0) if zero_kw == "eps" else ev(dur=0)
    if zero_kw == "eps":
        assert (r.episodes, r.minutes_per_ep) == (12, 24)
    else:
        assert (r.episodes, r.minutes_per_ep) == (12, 24)


# ---------------------------------------------------------------- movie plans
def test_movie_default_105min():
    r = ev(fmt="MOVIE")
    assert (r.content_type, r.episodes, r.minutes_per_ep, r.total_minutes) == \
        ("movie", 1, 105, 105)
    expected = {
        "subtitles_only": cost_of(SUBS * 105 * 1.15),
        "hindi_dub": cost_of(MOVIE_DUB * 105),
        "three_language": cost_of(MOVIE_DUB * 105 * EXTRA),
        "five_language": cost_of(MOVIE_DUB * 105 * EXTRA5),
    }
    assert {p.mode: p.cost_inr for p in r.plans} == expected


def test_movie_custom_duration_and_episode_ignore():
    r = ev(fmt="MOVIE", eps=12, dur=130)   # episodes forced to 1 for movies
    assert (r.episodes, r.minutes_per_ep, r.total_minutes) == (1, 130, 130)
    assert {p.mode: p.cost_inr for p in r.plans}["hindi_dub"] == cost_of(MOVIE_DUB * 130)
    r0 = ev(fmt="MOVIE", dur=0)            # 0 -> default 105 (finding #6)
    assert r0.total_minutes == 105


@pytest.mark.parametrize("fmt", ["movie", "MOVIE", "Movie"])
def test_movie_format_case_insensitive_prefix(fmt):
    assert ev(fmt=fmt).content_type == "movie"


@pytest.mark.parametrize("fmt", ["TV", "OVA", "tv", "ONA", "TV_SHORT", "SPECIAL", ""])
def test_series_format_variants(fmt):
    assert ev(fmt=fmt).content_type == "series"


def test_format_none_is_series():
    assert ev(fmt=None).content_type == "series"


# ------------------------------------------------------------ plan list shape
def test_plans_order_and_fields():
    for r in (ev(), ev(fmt="MOVIE")):
        assert [p.mode for p in r.plans] == MODES
        for p in r.plans:
            assert p.languages == MODE_LANGUAGES[p.mode]
            assert p.reach_multiplier == REACH_MULTIPLIERS[p.mode]
            assert isinstance(p.cost_inr, int) and p.cost_inr >= 0
            assert p.cost_per_reach_unit == round(p.cost_inr / p.reach_multiplier, 2)
            assert p.cost_per_reach_unit > 0


def test_cost_per_reach_unit_rounding():
    r = ev()
    p = next(p for p in r.plans if p.mode == "hindi_dub")
    assert p.cost_per_reach_unit == round(307_200 / 1.55, 2)


def test_costs_strictly_increase_with_mode_depth():
    r = ev()
    costs = [p.cost_inr for p in r.plans]
    assert costs == sorted(costs) and len(set(costs)) == 4


# --------------------------------------------------------------- recommendation
@pytest.mark.parametrize("score,mode", [
    (0, "subtitles_only"), (39, "subtitles_only"), (39.9, "subtitles_only"),
    (40, "hindi_dub"), (40.001, "hindi_dub"), (54, "hindi_dub"), (54.9, "hindi_dub"),
    (55, "three_language"), (55.001, "three_language"), (71, "three_language"),
    (71.9, "three_language"),
    (72, "five_language"), (72.001, "five_language"), (100, "five_language"),
    (-10, "subtitles_only"),
])
def test_recommendation_boundaries(score, mode):
    r = ev(score=score)
    assert r.recommended_mode == mode
    assert r.recommended_plan.mode == mode


def test_recommended_plan_is_one_of_plans():
    r = ev(score=63)
    assert r.recommended_plan in r.plans


# ------------------------------------------------------------------ break-even
def test_series_break_even_math_exact():
    r = ev(score=60)  # three_language rec: cost 609_120
    assert r.break_even_tickets is None
    assert r.break_even_views == cost_of(609_120 / NET_REVENUE_PER_STREAM_VIEW_INR)
    assert r.break_even_views == 676_800
    monthly = {"five_language": 2_600_000, "three_language": 1_400_000,
               "hindi_dub": 700_000, "subtitles_only": 280_000}["three_language"]
    assert r.payback_months == max(1, cost_of(609_120 / (monthly * 0.9)))
    assert r.payback_months == 1


@pytest.mark.parametrize("score,mode,monthly", [
    (80, "five_language", 2_600_000),
    (60, "three_language", 1_400_000),
    (45, "hindi_dub", 700_000),
    (20, "subtitles_only", 280_000),
])
def test_series_payback_each_mode(score, mode, monthly):
    r = ev(score=score)
    assert r.recommended_mode == mode
    assert r.payback_months == max(
        1, cost_of(r.recommended_plan.cost_inr / (monthly * 0.9)))


def test_payback_max_one_floor():
    # minimal series (1 ep x 1 min): subs-only cost 460 -> payback floored at 1
    r = ev(score=0, eps=1, dur=1)
    assert r.recommended_mode == "subtitles_only"
    assert r.recommended_plan.cost_inr == cost_of(SUBS * 1 * 1.15)  # 460
    assert r.payback_months == 1
    assert r.break_even_views == cost_of(460 / 0.9)  # 511


def test_movie_break_even_tickets_exact():
    r = ev(score=60, fmt="MOVIE")  # three_language cost = 8000*105*2.5225
    cost = r.recommended_plan.cost_inr
    assert cost == cost_of(MOVIE_DUB * 105 * EXTRA)  # 2_118_900
    assert r.break_even_views is None
    assert r.payback_months is None
    assert r.break_even_tickets == cost_of(cost / NET_TICKET_INR)


def test_movie_has_no_payback_and_series_has_no_tickets():
    assert ev(fmt="MOVIE").break_even_views is None
    assert ev(fmt="MOVIE").payback_months is None
    assert ev().break_even_tickets is None
    assert isinstance(ev().payback_months, int)


def test_assumptions_documented():
    for r in (ev(), ev(fmt="MOVIE")):
        assert len(r.assumptions) == 4
        assert all(isinstance(a, str) and a for a in r.assumptions)


# ------------------------------------------------------------------ format_inr
@pytest.mark.parametrize("amount,expected", [
    (0, "₹0"),
    (1, "₹1"),
    (999, "₹999"),
    (99_999, "₹99,999"),
    (1_00_000, "₹1.0 L"),          # exactly 1 lakh
    (1_50_000, "₹1.5 L"),
    (99_99_999, "₹100.0 L"),       # just under 1 crore rounds up to 100.0 L
    (1_00_00_000, "₹1.00 Cr"),     # exactly 1 crore
    (1_23_45_678, "₹1.23 Cr"),
    (99_99_99_999, "₹100.00 Cr"),   # 99.99.. Cr rounds up in the .2f format
    (-5_000, "₹-5,000"),           # negative: comma branch, no L/Cr
    (-1_00_00_000, "₹-10,000,000"),
    (123_456, "₹1.2 L"),
])
def test_format_inr_boundaries(amount, expected):
    assert format_inr(amount) == expected


def test_format_inr_float_truncates():
    assert format_inr(150_000.9) == "₹1.5 L"
    assert format_inr(99_999.99) == "₹99,999"


def test_format_inr_str_input_via_int():
    assert format_inr("460") == "₹460"
