"""Mass enumeration — engine-level sweeps (scoring, cultural fit, mass lookup).

Companion of test_mass_enumeration.py; together they enumerate >= 55,000 cases.
"""
from __future__ import annotations

import random

from src.app import SHOWCASE_ALIASES, _norm
from src.intelligence.cultural_compat.engine import CulturalCompatibilityEngine
from src.scoring.engine import GENRE_AFFINITY, WEIGHTS, ScoringEngine

SCORING_CASES = 2_500
CULTURAL_FIT_CASES = 2_500
LOOKUP_ALIASES = 5
LOOKUP_RELEASED = 40
LOOKUP_UNRELEASED = 10

ENUMERATED_CASES = SCORING_CASES + CULTURAL_FIT_CASES + \
    LOOKUP_ALIASES + LOOKUP_RELEASED + LOOKUP_UNRELEASED

S = ScoringEngine()
CUL = CulturalCompatibilityEngine()

GENRE_POOL = sorted(GENRE_AFFINITY) + ["Unknown Genre A", "Unknown Genre B", ""]
TAG_POOL = ["Gore", "Violence", "Nudity", "Alcohol", "Family", "Training",
            "Religion", "Mythology", "Nope", "Explicit Sex"]


def _fail(failures, counter, msg):
    if len(failures) < 25:
        failures.append(f"#{counter}: {msg}")


# ---------------------------------------------------- ScoringEngine sweeps
def test_mass_score_candidate():
    rng = random.Random(90210)
    counter = 0
    failures = []
    for _ in range(SCORING_CASES):
        meta = {
            "title_english": "Mass Candidate",
            "genres": rng.sample(GENRE_POOL, rng.randint(0, 4)),
            "popularity": rng.uniform(0, 100_000),
            "favourites": rng.uniform(0, 100_000),
            "average_score": rng.choice([None, 0, 60, 67, 68, 75, 80, 95]),
        }
        wiki = rng.choice([None, {
            "avg_daily_last30": rng.choice([0.0, rng.uniform(0, 5000)]),
            "momentum_90d_vs_prior90": rng.choice(
                [None, "", rng.uniform(-2, 2)]),
            "has_hindi_wiki": rng.random() < 0.5}])
        trends = {"keyword": "anime",
                  "growth_2y_pct": rng.choice([None, rng.uniform(-200, 200)])}
        cp = {
            "wiki_vol_values": [float(rng.randint(0, 100))
                                for _ in range(rng.randint(0, 15))],
            "popularity_values": [float(rng.randint(0, 100))
                                  for _ in range(rng.randint(0, 15))],
            "favourite_values": [float(rng.randint(0, 100))
                                 for _ in range(rng.randint(0, 15))],
            "unreleased_pop_values": [float(rng.randint(0, 100))
                                      for _ in range(rng.randint(0, 15))],
            "confidence": rng.randint(0, 100),
        }
        kwargs = dict(meta=meta, wiki=wiki, trends=trends,
                      cultural_fit=rng.randint(0, 100),
                      reach_multiplier=rng.uniform(0, 3),
                      pre_launch=rng.random() < 0.5, confidence_parts=cp)
        counter += 1
        a = S.score_candidate(**kwargs)
        b = S.score_candidate(**kwargs)
        if a != b:
            _fail(failures, counter, "non-deterministic")
        if not (0 <= a.sakura_score <= 100):
            _fail(failures, counter, f"score {a.sakura_score} out of bounds")
        if a.grade not in {"S", "A", "B", "C", "D"}:
            _fail(failures, counter, f"grade {a.grade!r}")
        if [f.name for f in a.factors] != list(WEIGHTS):
            _fail(failures, counter, "factor names/order broken")
        for f in a.factors:
            if not (0 <= f.value <= 100):
                _fail(failures, counter, f"{f.name}={f.value} out of bounds")
            if f.weight != WEIGHTS[f.name]:
                _fail(failures, counter, f"{f.name} weight mismatch")
        if abs(a.sakura_score - sum(f.contribution for f in a.factors)) > 1:
            _fail(failures, counter, "score deviates from weighted sum by >1")
    assert counter == SCORING_CASES == 2_500
    assert not failures, failures


# ------------------------------------------- cultural overall-fit sweeps
def test_mass_cultural_overall_fit():
    rng = random.Random(4242)
    genre_pool = ["Action", "Comedy", "Horror", "Ecchi", "Sports", "Kids",
                  "Slice of Life", "Mecha", "Fantasy", "Psychological", "Drama"]
    tag_pool = ["Gore", "Violence", "Nudity", "Suicide", "Family", "Training",
                "Religion", "Gore", "Explicit Sex", "Alcohol", "Cannibalism"]
    counter = 0
    failures = []
    for _ in range(CULTURAL_FIT_CASES):
        genres = rng.sample(genre_pool, rng.randint(0, 3))
        tags = [(t, rng.randint(0, 100))
                for t in rng.sample(tag_pool, rng.randint(0, 4))]
        counter += 1
        p = CUL.evaluate(genres=genres, tags=tags, is_adult=rng.random() < 0.1,
                         format=rng.choice(["TV", "MOVIE", "movie", "OVA"]),
                         episodes=rng.choice([None, 1, 12, 100]))
        q = CUL.evaluate(genres=genres, tags=tags,
                         is_adult=rng.random() < 0.1,
                         format="TV", episodes=None)
        if not (0 <= p.overall_cultural_fit <= 100):
            _fail(failures, counter, f"overall {p.overall_cultural_fit} out of bounds")
        if not (0 <= p.family_co_viewing_friction <= 100):
            _fail(failures, counter, "friction out of bounds")
        if len(p.archetype_alignment) != 4:
            _fail(failures, counter, "archetype count != 4")
        if any(not (0 <= v["score"] <= 100) for v in p.archetype_alignment.values()):
            _fail(failures, counter, "archetype score out of bounds")
        if p.cbfc_rating_estimate not in {"U", "U/A 7+", "U/A 13+",
                                          "A risk / U/A 16+", "A (Adults Only)"}:
            _fail(failures, counter, f"rating {p.cbfc_rating_estimate!r}")
    assert counter == CULTURAL_FIT_CASES == 2_500
    assert not failures, failures


# ------------------------------------------------------- mass lookup (real data)
def test_mass_lookup_resolves(app):
    titles = list(SHOWCASE_ALIASES)                                  # 5 aliases
    released = app.released_top(40)                                  # 40 released
    unreleased = app.catalog.loc[
        app.catalog["status"] == "NOT_YET_RELEASED", "title_english"
    ].dropna().head(LOOKUP_UNRELEASED).tolist()                      # 10 unreleased
    counter = 0
    failures = []

    def check(title, expect_norm_equal):
        nonlocal counter
        counter += 1
        row = app.lookup(title)
        if row is None:
            _fail(failures, counter, f"{title!r} did not resolve")
            return
        got = row["title_english"]
        if not isinstance(got, str) or not got:
            _fail(failures, counter, f"{title!r} resolved to empty title")
        if expect_norm_equal and _norm(str(got)) != _norm(title):
            _fail(failures, counter, f"{title!r} resolved to {got!r} (norm mismatch)")

    for alias in titles:
        check(alias, expect_norm_equal=False)
    for t in released:
        check(t, expect_norm_equal=True)
    for t in unreleased:
        check(t, expect_norm_equal=True)

    assert len(titles) == LOOKUP_ALIASES
    assert len(released) == LOOKUP_RELEASED
    assert len(unreleased) == LOOKUP_UNRELEASED
    assert counter == LOOKUP_ALIASES + LOOKUP_RELEASED + LOOKUP_UNRELEASED == 55
    assert not failures, failures


def test_module_total():
    assert ENUMERATED_CASES == 2_500 + 2_500 + 5 + 40 + 10
    assert ENUMERATED_CASES == 5_055
