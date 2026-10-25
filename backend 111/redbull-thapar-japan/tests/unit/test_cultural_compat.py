"""Unit tests — src/intelligence/cultural_compat/engine.py.

Includes an independent re-implementation of the documented rules (the
"model") used to cross-check >=20 hand-built cases end to end.
"""
from __future__ import annotations

import pytest

from src.intelligence.cultural_compat.engine import (ADULT_GENRES, ADULT_TAGS,
                                                     ARCHETYPES,
                                                     COVIEW_FRICTION_GENRES,
                                                     COVIEW_FRICTION_TAGS,
                                                     HIGH_RISK_TAGS,
                                                     MILD_RISK_GENRES,
                                                     MODERATE_RISK_TAGS,
                                                     REGION_GENRE_DELTAS,
                                                     CulturalCompatibilityEngine)

E = CulturalCompatibilityEngine()
VALID_RATINGS = {"U", "U/A 7+", "U/A 13+", "A risk / U/A 16+", "A (Adults Only)"}
RELIGION_TRIGGER = ("religious/mythological imagery — review for "
                    "community-sensitivity edits")


def ev(genres=(), tags=(), is_adult=False, fmt="TV", episodes=None):
    return E.evaluate(genres=list(genres), tags=list(tags), is_adult=is_adult,
                      format=fmt, episodes=episodes)


# ------------------------------------------------- independent reference model
def model(genres, tags, is_adult, fmt=""):
    genres = list(genres)
    names = [t for t, _ in tags]
    ranks = dict(tags)
    alignment = {}
    for aid, spec in ARCHETYPES.items():
        g_hits = sum(1 for g in spec["genres"] if g in genres)
        t_hits = sum(1 for t in names if t in spec["tags"])
        alignment[aid] = min(35 + 18 * min(g_hits, 2) + 12 * min(t_hits, 3), 100)
    # rating ladder
    triggers = []
    if is_adult or any(g in ADULT_GENRES for g in genres) or \
            any(t in ADULT_TAGS and ranks.get(t, 50) >= 55 for t in names):
        rating = "A (Adults Only)"
        triggers.append("adult/sexual content — direct CBFC 'A' territory")
    else:
        high = [t for t in names if t in HIGH_RISK_TAGS and ranks.get(t, 50) >= 45]
        mod = [t for t in names if t in MODERATE_RISK_TAGS and ranks.get(t, 50) >= 35]
        if high:
            rating = "A risk / U/A 16+"
            triggers.extend(HIGH_RISK_TAGS[t] for t in high)
        elif mod:
            rating = "U/A 13+"
            triggers.extend(MODERATE_RISK_TAGS[t] for t in mod)
        else:
            rating = "U" if {"Kids", "Slice of Life", "Comedy"} & set(genres) else "U/A 7+"
        mild = [g for g in genres if g in MILD_RISK_GENRES]
        if mild and rating not in ("A (Adults Only)", "A risk / U/A 16+"):
            triggers.extend(f"{g} themes" for g in mild)
            if rating == "U":
                rating = "U/A 7+"
    if "Religion" in names or "Mythology" in names:
        triggers.append(RELIGION_TRIGGER)
    # friction
    fr = 0
    for t in names:
        fr = min(100, fr + COVIEW_FRICTION_TAGS.get(t, 0)
                 * (1 if ranks.get(t, 50) >= 50 else 0.5))
    for g in genres:
        fr = min(100, fr + COVIEW_FRICTION_GENRES.get(g, 0))
    if fmt == "MOVIE" and fr < 20:
        fr = max(0, fr - 5)
    friction = int(fr)
    # regional
    regional = {}
    for g in genres:
        for hub, d in REGION_GENRE_DELTAS.get(g, {}).items():
            regional[hub] = regional.get(hub, 0) + d
    regional = {k: v for k, v in regional.items() if v != 0}
    # flags + overall
    flags = []
    if rating.startswith("A"):
        flags.append("certification restricts broadcast & co-viewing")
    if friction >= 40:
        flags.append("high family co-viewing friction for the Hindi belt")
    if "Ecchi" in genres:
        flags.append("ecchi content complicates localization pitch")
    top = max(alignment.values())
    rs = 0 if rating.startswith("A") else 70 if rating == "U/A 13+" else 85
    maxabs = max([abs(v) for v in regional.values()], default=0)
    sign = 1 if any(v > 0 for v in regional.values()) else -1
    overall = int(0.45 * top + 0.25 * (100 - friction) + 0.15 * rs
                  + 0.15 * (50 + maxabs * sign))
    return {"alignment": alignment, "rating": rating,
            "triggers": sorted(set(triggers)), "friction": friction,
            "regional": regional, "flags": flags,
            "overall": max(0, min(100, overall))}


HAND_BUILT = [
    # (genres, tags, is_adult, format) — 24 cases spanning the rule space
    ([], [], False, "TV"),
    (["Action"], [], False, "TV"),
    (["Comedy"], [], False, "TV"),
    (["Kids"], [], False, "TV"),
    (["Slice of Life"], [], False, "TV"),
    (["Action", "Sports", "Drama"], [("Training", 80), ("Martial Arts", 60)], False, "TV"),
    (["Hentai"], [], False, "TV"),
    (["Erotica"], [], False, "TV"),
    (["Ecchi"], [], False, "TV"),
    (["Action"], [], True, "TV"),
    ([], [("Nudity", 55)], False, "TV"),
    ([], [("Nudity", 54)], False, "TV"),
    (["Action"], [("Gore", 45)], False, "TV"),
    (["Action"], [("Gore", 44)], False, "TV"),
    (["Action"], [("Violence", 35)], False, "TV"),
    (["Action"], [("Violence", 34)], False, "TV"),
    (["Horror", "Comedy"], [], False, "MOVIE"),
    (["Thriller"], [("Suicide", 80)], False, "TV"),
    (["Comedy", "Music", "Slice of Life"],
     [("Family", 60), ("Friendship", 70), ("Festival", 40)], False, "TV"),
    (["Sports", "Ecchi"], [], False, "TV"),
    (["Mecha", "Psychological"], [("War", 90), ("Death", 20)], False, "OVA"),
    (["Action", "Drama"], [("Duty", 90), ("Sacrifice", 75), ("Vengeance", 60),
                           ("Religion", 88)], False, "MOVIE"),
    (["Horror"], [("Gore", 90), ("Body Horror", 85), ("Cannibalism", 60),
                  ("Mythology", 70)], False, "TV"),
    (["Kids", "Slice of Life"], [("Alcohol", 49), ("Tobacco Use", 51)], False, "MOVIE"),
]


@pytest.mark.parametrize("genres,tags,is_adult,fmt", HAND_BUILT)
def test_hand_built_cases_match_independent_model(genres, tags, is_adult, fmt):
    p = ev(genres, tags, is_adult, fmt)
    m = model(genres, tags, is_adult, fmt)
    assert p.cbfc_rating_estimate == m["rating"]
    assert p.sensitivity_triggers == m["triggers"]
    assert p.family_co_viewing_friction == m["friction"]
    assert p.regional_variation == m["regional"]
    assert p.cultural_distance_flags == m["flags"]
    assert p.overall_cultural_fit == m["overall"]
    assert {k: v["score"] for k, v in p.archetype_alignment.items()} == m["alignment"]
    assert p.cbfc_rating_estimate in VALID_RATINGS
    assert 0 <= p.overall_cultural_fit <= 100
    assert 0 <= p.family_co_viewing_friction <= 100


# ---------------------------------------------------------------- CBFC ladder
@pytest.mark.parametrize("genre", sorted(ADULT_GENRES))
@pytest.mark.parametrize("is_adult", [False, True])
def test_adult_genre_forces_A(genre, is_adult):
    p = ev([genre], [], is_adult)
    assert p.cbfc_rating_estimate == "A (Adults Only)"
    assert "certification restricts broadcast & co-viewing" in p.cultural_distance_flags


@pytest.mark.parametrize("is_adult", [False, True])
def test_nonadult_genre_with_is_adult_flag(is_adult):
    assert ev(["Action"], [], is_adult).cbfc_rating_estimate == \
        ("A (Adults Only)" if is_adult else "U/A 7+")


@pytest.mark.parametrize("tag", sorted(ADULT_TAGS))
@pytest.mark.parametrize("rank", [34, 35, 44, 45, 54, 55, 56, 100])
def test_adult_tag_rank_gate(tag, rank):
    p = ev(["Action"], [(tag, rank)], False)
    assert p.cbfc_rating_estimate == ("A (Adults Only)" if rank >= 55 else "U/A 7+")


def test_adult_tag_default_rank_50_is_not_adult():
    # rank defaults matter: ADULT_TAGS below 55 never trigger 'A' by themselves
    assert ev(["Comedy"], [("Nudity", 50)], False).cbfc_rating_estimate == "U"


@pytest.mark.parametrize("tag", sorted(HIGH_RISK_TAGS))
@pytest.mark.parametrize("rank", [34, 35, 36, 44, 45, 46, 54, 55, 56])
def test_high_risk_tag_rank_gate(tag, rank):
    p = ev(["Action"], [(tag, rank)], False)
    assert p.cbfc_rating_estimate == ("A risk / U/A 16+" if rank >= 45 else "U/A 7+")


@pytest.mark.parametrize("tag", sorted(MODERATE_RISK_TAGS))
@pytest.mark.parametrize("rank", [34, 35, 36, 44, 45, 46, 54, 55, 56])
def test_moderate_tag_rank_gate(tag, rank):
    p = ev(["Action"], [(tag, rank)], False)
    assert p.cbfc_rating_estimate == ("U/A 13+" if rank >= 35 else "U/A 7+")


def test_high_risk_beats_moderate():
    p = ev(["Action"], [("Gore", 80), ("Violence", 80)], False)
    assert p.cbfc_rating_estimate == "A risk / U/A 16+"
    assert "graphic gore" in p.sensitivity_triggers
    # CURRENT BEHAVIOUR: the moderate-risk branch is an elif — moderate triggers
    # are NOT emitted once a high-risk tag sets the 16+ rating.
    assert "violence" not in p.sensitivity_triggers


def test_adult_beats_everything():
    p = ev(["Action"], [("Gore", 100), ("Violence", 100), ("Nudity", 100)], False)
    assert p.cbfc_rating_estimate == "A (Adults Only)"


@pytest.mark.parametrize("genres,expected", [
    (["Kids"], "U"), (["Slice of Life"], "U"), (["Comedy"], "U"),
    (["Comedy", "Action"], "U"), (["Action"], "U/A 7+"), ([], "U/A 7+"),
    (["Sports"], "U/A 7+"), (["Kids", "Ecchi"], "A (Adults Only)"),
])
def test_U_vs_UA7_by_genre(genres, expected):
    assert ev(genres, [], False).cbfc_rating_estimate == expected


@pytest.mark.parametrize("genres,tag_name,expected", [
    (["Horror"], None, "U/A 7+"),          # already U/A 7+ — stays
    (["Horror", "Comedy"], None, "U/A 7+"),  # demoted from U
    (["Thriller", "Kids"], None, "U/A 7+"),  # demoted from U
    (["Psychological", "Comedy"], None, "U/A 7+"),
    (["Horror"], "Violence", "U/A 13+"),       # no demotion from 13+
    (["Thriller"], "Gore", "A risk / U/A 16+"),  # no demotion on A-track
])
def test_mild_risk_demotion_only_from_U(genres, tag_name, expected):
    tags = [(tag_name, 80)] if tag_name else []
    p = ev(genres, tags, False)
    assert p.cbfc_rating_estimate == expected


def test_mild_triggers_added_below_A_track_only():
    below = ev(["Horror", "Comedy"], [], False)          # U -> U/A 7+
    assert "Horror themes" in below.sensitivity_triggers
    mod = ev(["Horror"], [("Violence", 80)], False)      # 13+
    assert "Horror themes" in mod.sensitivity_triggers
    high = ev(["Horror"], [("Gore", 80)], False)         # A-track
    assert "Horror themes" not in high.sensitivity_triggers


@pytest.mark.parametrize("genres,tags", [
    ([], []),                                   # U/A 7+
    (["Comedy"], []),                           # U
    (["Action"], [("Violence", 80)]),           # U/A 13+
    (["Action"], [("Gore", 80)]),               # A risk / U/A 16+
    (["Hentai"], []),                           # A (Adults Only)
    (["Action"], []),                           # U/A 7+ (demoted from nothing)
])
def test_religion_mythology_trigger_at_every_rating(genres, tags):
    for rel_tag in ("Religion", "Mythology"):
        p = ev(genres, tags + [(rel_tag, 90)], False)
        assert RELIGION_TRIGGER in p.sensitivity_triggers
    # and it is the only addition for an otherwise clean title
    clean = ev(["Comedy"], [], False).sensitivity_triggers
    withrel = ev(["Comedy"], [("Religion", 90)], False).sensitivity_triggers
    assert set(withrel) - set(clean) == {RELIGION_TRIGGER}


def test_triggers_sorted_and_deduped():
    tags = [("Gore", 90), ("Gore", 90), ("Violence", 90), ("Suicide", 90)]
    p = ev(["Action"], tags, False)
    assert p.sensitivity_triggers == sorted(set(p.sensitivity_triggers))


# -------------------------------------------------------------------- friction
@pytest.mark.parametrize("tag,rank,expected", [
    ("Gore", 50, 30), ("Gore", 49, 15),          # rank>=50 full, <50 half
    ("Nudity", 55, 40), ("Nudity", 54, 40), ("Nudity", 49, 20),
    ("Alcohol", 100, 12), ("Tobacco Use", 49, 5),
    ("Unknown Tag", 90, 0),
])
def test_friction_tag_rank_weighting(tag, rank, expected):
    assert ev([], [(tag, rank)], False).family_co_viewing_friction == expected


@pytest.mark.parametrize("genres,expected", [
    (["Hentai"], 80), (["Ecchi"], 35), (["Erotica"], 60), (["Horror"], 15),
    (["Psychological"], 8), (["Thriller"], 8), (["Action"], 0), ([], 0),
])
def test_friction_genre_table(genres, expected):
    assert ev(genres, [], False).family_co_viewing_friction == expected


def test_friction_accumulates_and_caps_at_100():
    tags = [("Explicit Sex", 60), ("Sexual Violence", 60), ("Nudity", 60),
            ("Ecchi", 60), ("Gore", 60)]
    assert ev([], tags, False).family_co_viewing_friction == 100


def test_friction_accumulation_full_and_half_mix():
    # full 30 (Gore@50) + half 12.5 (Suicide@49: 35*0.5) + genre 15 (Horror)
    p = ev(["Horror"], [("Gore", 50), ("Suicide", 49)], False)
    assert p.family_co_viewing_friction == int(30 + 17.5 + 15)


@pytest.mark.parametrize("fmt,expected", [
    ("MOVIE", 7),    # 12 - 5 (single-sitting discount when friction<20)
    ("movie", 12),   # CURRENT BEHAVIOUR: case-sensitive compare -> no discount
    ("TV", 12), ("", 12), ("OVA", 12),
])
def test_friction_movie_discount_case_sensitivity(fmt, expected):
    assert ev([], [("Alcohol", 60)], False, fmt).family_co_viewing_friction == expected


@pytest.mark.parametrize("tags,expected_no_discount", [
    ([("Suicide", 50)], 35),        # friction>=20 -> no MOVIE discount
    ([("Gore", 50)], 30),
])
def test_friction_movie_discount_only_below_20(tags, expected_no_discount):
    assert ev([], tags, False, "MOVIE").family_co_viewing_friction == expected_no_discount


def test_friction_movie_floor_at_zero():
    assert ev([], [], False, "MOVIE").family_co_viewing_friction == 0  # max(0, -5)


# -------------------------------------------------------------------- regional
@pytest.mark.parametrize("genres,expected", [
    (["Sports"], {"Southern Fortress": 8, "Western Metros": 4}),
    (["Sports", "Mecha"], {"Southern Fortress": 14, "Western Metros": 12}),
    # Sports +8/-; Ecchi -8 SF: SF sums to 0 and is dropped, but HB -12 stays
    (["Sports", "Ecchi"], {"Western Metros": 4, "Hindi Belt": -12}),
    (["Ecchi"], {"Hindi Belt": -12, "Southern Fortress": -8}),
    (["Action"], {}),                                # unknown genre -> no deltas
    ([], {}),
    (["Horror"], {"Hindi Belt": 5, "Eastern Hub": 6}),
    (["Kids", "Slice of Life", "Iyashikei"], {"Hindi Belt": 14 - 6 - 5, "Eastern Hub": 5}),
])
def test_regional_deltas_sum_and_zero_drop(genres, expected):
    assert ev(genres, [], False).regional_variation == expected


def test_regional_duplicate_genre_counts_twice():
    assert ev(["Sports", "Sports"], [], False).regional_variation == \
        {"Southern Fortress": 16, "Western Metros": 8}


def test_all_regional_deltas_reference_hubs():
    for g, deltas in REGION_GENRE_DELTAS.items():
        for hub in deltas:
            assert hub in {"Hindi Belt", "Southern Fortress", "Western Metros",
                           "Eastern Hub", "Northeast", "Northern Fringe"}, (g, hub)


# ---------------------------------------------------------------------- flags
@pytest.mark.parametrize("genres,tags,is_adult,flags", [
    # Hentai: A rating + genre friction 80 -> cert + friction flags
    (["Hentai"], [], False,
     ["certification restricts broadcast & co-viewing",
      "high family co-viewing friction for the Hindi belt"]),
    # 'A risk / U/A 16+' also startswith('A') -> cert flag; friction 30 < 40
    (["Action"], [("Gore", 80)], False,
     ["certification restricts broadcast & co-viewing"]),
    (["Action"], [], False, []),
    ([], [("Sexual Violence", 80)], False,
     ["certification restricts broadcast & co-viewing",
      "high family co-viewing friction for the Hindi belt"]),
    # Ecchi: A rating + genre friction 35 < 40 -> cert + ecchi flags only
    (["Ecchi"], [], False,
     ["certification restricts broadcast & co-viewing",
      "ecchi content complicates localization pitch"]),
    ([], [("Gore", 80)], False,
     ["certification restricts broadcast & co-viewing"]),
])
def test_flag_rules(genres, tags, is_adult, flags):
    assert ev(genres, tags, is_adult).cultural_distance_flags == flags


# ------------------------------------------------------------------- archetypes
@pytest.mark.parametrize("genres,tags,expected", [
    ([], [], {"dharma_duty": 35, "guru_shishya": 35, "parivaar": 35, "sahavas": 35}),
    (["Action"], [], {"dharma_duty": 53, "guru_shishya": 53, "parivaar": 35, "sahavas": 35}),
    # parivaar/sahavas: 2 genre hits (+36) + 3 tag hits (+36) = 107 -> capped 100;
    # guru_shishya: no genre hit + School tag only -> 47
    (["Slice of Life", "Comedy", "Drama", "Kids", "Music"],
     [("Family", 80), ("Friendship", 80), ("School", 80), ("Festival", 80), ("Teamwork", 80)],
     {"dharma_duty": 53, "guru_shishya": 47, "parivaar": 100, "sahavas": 100}),
])
def test_archetype_scoring(genres, tags, expected):
    p = ev(genres, tags, False)
    got = {k: v["score"] for k, v in p.archetype_alignment.items()}
    assert got == expected
    assert set(p.archetype_alignment) == set(ARCHETYPES)


def test_archetype_cap_at_100():
    genres = ["Slice of Life", "Comedy", "Drama", "Kids", "Action", "Adventure",
              "Sports", "Music"]
    tags = [(t, 80) for t in ("Duty", "Honour", "Sacrifice",          # dharma
                              "Mentor", "Training", "Coming of Age",  # guru
                              "Family", "Parenthood", "Friendship",   # parivaar
                              "Festival", "School", "Music")]         # sahavas
    p = ev(genres, tags, False)
    assert all(v["score"] == 100 for v in p.archetype_alignment.values())


def test_archetype_metadata_fields():
    p = ev(["Sports"], [("Training", 70)], False)
    for spec in p.archetype_alignment.values():
        assert spec["label"] and spec["desc"] and spec["why"]
    assert any("genres" in w for w in p.archetype_alignment["guru_shishya"]["why"])
    assert p.archetype_alignment["dharma_duty"]["why"] == ["no direct thematic match"]


# ------------------------------------------------------------------- overall fit
@pytest.mark.parametrize("genres,tags,is_adult,fmt", HAND_BUILT)
def test_overall_fit_formula_recomputed(genres, tags, is_adult, fmt):
    p = ev(genres, tags, is_adult, fmt)
    m = model(genres, tags, is_adult, fmt)
    overall = int(
        0.45 * max(v["score"] for v in p.archetype_alignment.values())
        + 0.25 * (100 - p.family_co_viewing_friction)
        + 0.15 * (0 if p.cbfc_rating_estimate.startswith("A")
                  else 70 if p.cbfc_rating_estimate == "U/A 13+" else 85)
        + 0.15 * (50 + max([abs(v) for v in p.regional_variation.values()], default=0)
                  * (1 if any(v > 0 for v in p.regional_variation.values()) else -1)))
    assert p.overall_cultural_fit == max(0, min(100, overall))
    assert p.overall_cultural_fit == m["overall"]


def test_overall_fit_clamps():
    # friction 100 + A rating + no deltas + no archetype hits -> floor area
    p = ev([], [("Explicit Sex", 100), ("Sexual Violence", 100)], False)
    assert p.overall_cultural_fit == int(0.45 * 35 + 0.25 * 0 + 0.15 * 0 + 0.15 * 50)
    # maximum: archetype 100, friction 0, U rating, +delta
    genres = ["Sports", "Action", "Adventure", "Comedy", "Music"]
    tags = [(t, 90) for t in ("Mentor", "Training", "Coming of Age")]
    p2 = ev(genres, tags, False)
    assert p2.overall_cultural_fit == int(0.45 * 100 + 0.25 * 100 + 0.15 * 85
                                          + 0.15 * (50 + 8))


# ---------------------------------------------------------------- determinism
@pytest.mark.parametrize("genres,tags,is_adult,fmt", HAND_BUILT[:12])
def test_determinism(genres, tags, is_adult, fmt):
    a = ev(genres, tags, is_adult, fmt)
    b = ev(genres, tags, is_adult, fmt)
    assert a == b
    assert a.archetype_alignment == b.archetype_alignment
    assert a.sensitivity_triggers == b.sensitivity_triggers
    assert a.regional_variation == b.regional_variation
    assert a.cultural_distance_flags == b.cultural_distance_flags
    assert a.overall_cultural_fit == b.overall_cultural_fit


def test_episodes_argument_is_accepted_and_ignored():
    assert ev(["Action"], [], False, "TV", 12) == ev(["Action"], [], False, "TV", 400)
