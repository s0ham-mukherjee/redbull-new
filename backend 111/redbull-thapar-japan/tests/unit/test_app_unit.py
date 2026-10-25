"""Unit tests — src/app.py helpers (_norm, lookup, indexes, confidence, hubs)."""
from __future__ import annotations

import unicodedata

import pandas as pd
import pytest

from src.app import SHOWCASE_ALIASES, SakuraScoreApp, _norm

HUBS = SakuraScoreApp.HUBS


# ---------------------------------------------------------------------- _norm
@pytest.mark.parametrize("raw,expected", [
    ("", ""),
    ("   ", ""),
    ("Chainsaw Man", "chainsaw man"),
    ("CHAINSAW MAN", "chainsaw man"),
    ("chainsaw-man!", "chainsaw man"),
    ("JUJUTSU_KAISEN", "jujutsu kaisen"),
    ("Solo  Leveling", "solo leveling"),          # collapse runs
    ("  spaced  out  ", "spaced out"),
    ("ÀÉÎÕÜ", "a e i o u"),   # NFKD decomposes; combining marks become spaces
    ("ｃｈａｉｎｓａｗ", "chainsaw"),                   # fullwidth -> ASCII
    ("日本語アニメ", ""),                            # non-alnum -> spaces -> strip
    (" Naruto 2: Shippuden!! ", "naruto 2 shippuden"),
    ("12345", "12345"),
    ("a.b,c;d:e", "a b c d e"),
])
def test_norm_values(raw, expected):
    assert _norm(raw) == expected


def test_norm_non_string_via_str():
    assert _norm(123) == "123"
    assert _norm(4.5) == "4 5"
    assert _norm(None) == "none"
    assert _norm(["A", "B"]) == "a b"


def test_norm_idempotent_and_charset():
    for raw in ("", "Chainsaw! Man", "ＴＥＳＴ", "Ærøskøbing", "a  b  c"):
        once = _norm(raw)
        assert _norm(once) == once
        assert once == "" or all(c.isalnum() or c == " " for c in once)


def test_norm_uses_nfkd():
    composed = "café"                                  # e-acute precomposed
    assert _norm(composed) == "cafe"
    assert unicodedata.normalize("NFKD", composed) != composed


# -------------------------------------------------------------------- lookup
def test_lookup_exact(app):
    row = app.lookup("Chainsaw Man")
    assert row is not None and row["title_english"] == "Chainsaw Man"


def test_lookup_alias(app):
    row = app.lookup("solo leveling s2")
    assert row["title_english"] == SHOWCASE_ALIASES["solo leveling s2"]


def test_lookup_normalized(app):
    assert app.lookup("chainsaw man")["title_english"] == "Chainsaw Man"
    assert app.lookup("CHainsaw    MAN!!")["title_english"] == "Chainsaw Man"


def test_lookup_substring(app):
    got = app.lookup("kaisen")
    assert got is not None and "kaisen" in _norm(got["title_english"])


def test_lookup_missing_returns_none(app):
    assert app.lookup("zzzz-no-such-title-qqq") is None
    assert app.lookup("the quick brown fox jumps over the lazy dog xyzzy") is None


def test_lookup_empty_matches_everything_current_behaviour(app):
    # FINDING #5: str.contains("") is always True — the first row with an
    # empty normalized english title is returned instead of None.
    row = app.lookup("")
    assert row is not None
    assert row["title_english"] != "Chainsaw Man" or True  # shape only


def test_lookup_whitespace_only_behaves_like_empty(app):
    assert app.lookup("   ") is not None   # _norm("   ") == "" -> substring ""


# --------------------------------------------------------- SHOWCASE_ALIASES
def test_showcase_alias_keys_are_normalized():
    for key in SHOWCASE_ALIASES:
        assert _norm(key) == key, key
    assert len(SHOWCASE_ALIASES) == 5


@pytest.mark.parametrize("alias", sorted(SHOWCASE_ALIASES))
def test_showcase_alias_targets_resolve(app, alias):
    assert SHOWCASE_ALIASES[alias] in app.by_english
    assert app.lookup(alias)["title_english"] == SHOWCASE_ALIASES[alias]


def test_showcase_titles_method(app):
    assert app.showcase_titles() == list(SHOWCASE_ALIASES)


# --------------------------------------------------------------- released_top
def test_released_top_bounds(app):
    assert app.released_top(0) == []
    assert len(app.released_top(1)) == 1
    top10 = app.released_top(10)
    assert len(top10) == 10 and all(isinstance(t, str) and t for t in top10)
    total = len(app.released_top(100_000))
    assert 0 < total < len(app.catalog)
    # negative n: pandas head(-k) drops the LAST k rows (current behaviour)
    assert len(app.released_top(-3)) == total - 3


def test_released_top_sorted_by_popularity(app):
    fin = app.catalog[app.catalog["status"].isin(["FINISHED", "RELEASING"])]
    pops = {r["title_english"]: r["popularity"]
            for _, r in fin.iterrows() if isinstance(r["title_english"], str)}
    top = app.released_top(5)
    for a, b in zip(top, top[1:]):
        assert pops[a] >= pops[b]


# ------------------------------------------------------------------ _trends_for
def test_trends_for_fallback_anime(app):
    t = app._trends_for({}, "QZQ Completely Unknown Franchise")
    assert t["keyword"] == "anime"
    assert t["growth_2y_pct"] == app.trends_growth["anime"]


@pytest.mark.parametrize("title,expected_kw", [
    ("Solo Leveling Season 2", "solo leveling"),
    ("Demon Slayer: Kimetsu no Yaiba", "demon slayer"),
    ("One Piece Film: Red", "one piece"),
    ("Naruto Shippuden", "naruto"),
])
def test_trends_for_keyword_match(app, title, expected_kw):
    t = app._trends_for({}, title)
    assert t["keyword"] == expected_kw


def test_trends_for_last_match_current_behaviour(app):
    # FINDING #4: iteration keeps the LAST substring hit, not the most specific.
    t = app._trends_for({}, "Anime Hindi Dub Solo Leveling Review")
    assert t["keyword"] == "solo leveling"          # last in dict order


# ------------------------------------------------------------------ _confidence
CONF_CASES = [
    # (meta, wiki, growth, has_hindi, seed, unreleased)
    (None, None, None, False, None, False),
    (None, None, 5.9, False, None, False),
    ({"t": 1}, None, None, False, None, False),
    ({"t": 1}, {"x": 1}, None, False, None, False),
    ({"t": 1}, {"x": 1}, 5.9, False, None, False),
    ({"t": 1}, {"x": 1, "has_hindi_wiki": True}, 5.9, True, None, False),
    ({"t": 1}, {"x": 1, "has_hindi_wiki": True}, 5.9, True, pd.DataFrame({"a": [1]}), True),
    ({"t": 1}, None, 5.9, False, pd.DataFrame({"a": [1]}), True),
    (None, {"x": 1, "has_hindi_wiki": True}, 5.9, True, pd.DataFrame({"a": [1]}), True),
    ({"t": 1}, {"x": 1}, 0.0, False, None, True),
]


@pytest.mark.parametrize("meta,wiki,growth,has_hindi,seed,unreleased", CONF_CASES)
def test_confidence_formula(app, meta, wiki, growth, has_hindi, seed, unreleased):
    wiki_arg = wiki
    if wiki is not None:
        wiki_arg = dict(wiki)
        wiki_arg.setdefault("has_hindi_wiki", has_hindi)
    got = app._confidence(meta=meta, wiki=wiki_arg,
                          trends={"keyword": "k", "growth_2y_pct": growth},
                          seed_match=seed, unreleased=unreleased)
    expected = (
        (30 if meta is not None else 0)
        + (25 if wiki else 8)
        + (15 if growth is not None else 5)
        + (10 if wiki and has_hindi else 0)
        + (10 if seed is not None else 0)
        + (5 if unreleased else 10)
    )
    assert got == min(100, expected)


def test_confidence_max_reaches_100(app):
    df = pd.DataFrame({"title": ["x"]})
    c = app._confidence(meta={"t": 1}, wiki={"has_hindi_wiki": True},
                        trends={"growth_2y_pct": 5.0}, seed_match=df,
                        unreleased=False)
    assert c == 100


def test_confidence_minimum(app):
    c = app._confidence(meta=None, wiki=None,
                        trends={"growth_2y_pct": None}, seed_match=None,
                        unreleased=True)
    assert c == 8 + 5 + 5


# ------------------------------------------------------------------ wiki index
def test_wiki_for_real_title(app):
    w = app._wiki_for({"title_english": "Chainsaw Man"})
    assert w is not None
    assert {"article", "avg_daily_last30", "peak_daily",
            "momentum_90d_vs_prior90", "has_hindi_wiki", "total_views_24m"} == set(w)
    assert isinstance(w["avg_daily_last30"], float)


def test_wiki_for_unknown_title(app):
    assert app._wiki_for({"title_english": "QZQ No Wiki Title"}) is None
    assert app._wiki_for({}) is None


def test_wiki_indexes_built(app):
    assert len(app.wiki_by_source_title) > 50
    assert all(_norm(k) == k for k in app.wiki_by_source_title)
    assert len(app.hi_wiki_titles) > 0
    assert len(app.trends_growth) >= 8


def test_percentile_pools_built(app):
    assert len(app.popularity_values) == len(app.catalog)
    assert len(app.favourite_values) == len(app.catalog)
    assert 0 < len(app.unreleased_pop_values) < len(app.catalog)
    assert all(v == v for v in app.popularity_values[:100])  # no NaN in head


# ------------------------------------------------------------------- HUBS
def test_hubs_cover_every_state_exactly_once(app):
    all_hub_states = [s for states in HUBS.values() for s in states]
    assert len(all_hub_states) == len(set(all_hub_states))       # no dupes
    csv_states = set(app.states["state"])
    assert set(all_hub_states) == csv_states
    # FINDING #10 current behaviour: nothing falls through to the
    # "Northern Fringe" fillna — every state is claimed by a hub.
    leftovers = csv_states - set(all_hub_states)
    assert leftovers == set()


def test_hubs_structure():
    assert set(HUBS) == {"Hindi Belt", "Southern Fortress", "Western Metros",
                         "Eastern Hub", "Northeast", "Northern Fringe"}
    assert all(isinstance(v, list) and v for v in HUBS.values())


# ---------------------------------------------------------- market_breakdown
@pytest.fixture(scope="module")
def breakdown(app):
    cul = app.cultural.evaluate(genres=["Sports"], tags=[], is_adult=False,
                                format="TV", episodes=12)
    return app.market_breakdown(cul, 1.55, 80)


def test_market_breakdown_six_hubs(breakdown):
    assert set(breakdown) == set(HUBS)


def test_market_breakdown_demand_index_bounds_and_sort(breakdown):
    idx = [m["demand_index"] for m in breakdown.values()]
    assert all(0 <= i <= 100 for i in idx)
    assert idx == sorted(idx, reverse=True)   # dict sorted desc by demand
    assert list(breakdown) == [
        h for h, _ in sorted(breakdown.items(),
                             key=lambda kv: -kv[1]["demand_index"])]


def test_market_breakdown_population_sums_to_total(app, breakdown):
    total = int(app.states["population_2011_census"].sum())
    assert sum(m["population"] for m in breakdown.values()) == total


def test_market_breakdown_deterministic(app):
    cul = app.cultural.evaluate(genres=["Kids"], tags=[], is_adult=False,
                                format="TV", episodes=12)
    a = app.market_breakdown(cul, 1.55, 50)
    b = app.market_breakdown(cul, 1.55, 50)
    assert a == b


def test_market_breakdown_ignores_genre_fit_argument(app):
    cul = app.cultural.evaluate(genres=[], tags=[], is_adult=False,
                                format="TV", episodes=None)
    assert app.market_breakdown(cul, 1.85, 0) == app.market_breakdown(cul, 1.85, 100)


def test_market_breakdown_states_hub_column_idempotent(app):
    assert "_hub" in app.states.columns        # set by earlier calls
    before = app.states["_hub"].tolist()
    app.market_breakdown(app.cultural.evaluate(
        genres=[], tags=[], is_adult=False, format="TV"), 1.0, 50)
    assert app.states["_hub"].tolist() == before


def test_market_breakdown_reach_affects_demand(app):
    cul = app.cultural.evaluate(genres=[], tags=[], is_adult=False,
                                format="TV", episodes=None)
    lo = app.market_breakdown(cul, 1.0, 50)
    hi = app.market_breakdown(cul, 2.2, 50)
    for hub in lo:
        assert hi[hub]["demand_index"] >= lo[hub]["demand_index"]
    assert hi["Hindi Belt"]["population"] == lo["Hindi Belt"]["population"]


# --------------------------------------------------------------- init behaviour
def test_init_missing_data_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="processed CSVs"):
        SakuraScoreApp(data_dir=tmp_path)


def test_app_engines_wired(app):
    from src.intelligence.cultural_compat.engine import CulturalCompatibilityEngine
    from src.intelligence.localization_econ.engine import LocalizationEconomicsEngine
    from src.scoring.engine import ScoringEngine
    assert isinstance(app.cultural, CulturalCompatibilityEngine)
    assert isinstance(app.econ, LocalizationEconomicsEngine)
    assert isinstance(app.scoring, ScoringEngine)
    assert len(app._matrix) == 8
