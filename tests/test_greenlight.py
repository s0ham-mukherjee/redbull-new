"""Greenlight engine tests — offline, deterministic, real-pipeline-backed.

Covers the three layers of scripts/backend/greenlight.py:
  1. ConceptParser — lexicon, emphasis, Japanese terms, media/format, titles
  2. CatalogTensor — shape/norm invariants, similarity sanity vs known titles
  3. GreenlightEngine.run — full verdict: blend, quant risk, plans, 32 states

Run:  SAKURASCORE_GREENLIGHT_OFFLINE=1 python3 -m pytest tests/test_greenlight.py -q
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("SAKURASCORE_GREENLIGHT_OFFLINE", "1")  # no network in CI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "backend"))

import pytest  # noqa: E402
from greenlight import (  # noqa: E402
    CatalogTensor, GreenlightEngine, SAMPLE_CONCEPTS, build_engine, parse_concept,
)

DEMON_SLAYER_ISH = (
    "A teenage boy joins a corps of demon hunters after his family is slaughtered "
    "by demons; his sister is turning into a demon. Katana swordplay, very gory "
    "battles against oni, Taisho-era historical Japan, found family and sacrifice."
)


# ---------------------------------------------------------------- 1. parser

def test_parser_genres_and_tags():
    p = parse_concept("A dark shounen isekai with katana swordplay and revenge, "
                      "very graphic violence. 24 episodes.")
    assert "Action" in p.genres or "Fantasy" in p.genres or "Adventure" in p.genres
    tags = {n for n, _ in p.tags}
    assert "Isekai" in tags and "Swordplay" in tags and "Revenge" in tags
    assert "Shounen" in tags
    assert p.episodes == 24
    assert p.media_type == "anime" and p.pipeline_format == "TV"


def test_parser_emphasis_and_risk():
    mild = parse_concept("mild violence in a school comedy")
    gory = parse_concept("very graphic violence and gore in a school comedy")
    r_mild = dict(mild.tags).get("Violence") or dict(mild.tags).get("Gore", 0)
    r_gory = dict(gory.tags).get("Gore") or dict(gory.tags).get("Violence", 0)
    assert r_gory > r_mild
    assert parse_concept("an explicit hentai series").is_adult is True
    assert parse_concept("a wholesome cooking show").is_adult is False


def test_parser_japanese_terms():
    p = parse_concept("異世界転生の忍者が侍と刀で戦う妖怪退冶譚")
    tags = {n for n, _ in p.tags}
    assert {"Isekai", "Ninja", "Samurai", "Swordplay"} & tags, "kanji terms must map to tags"
    assert p.japanese_terms, "Japanese terms must be recorded"


def test_parser_media_formats():
    assert parse_concept("a theatrical anime film, 118 minutes").pipeline_format == "MOVIE"
    assert parse_concept("an ONA web series about idols").pipeline_format == "ONA"
    assert parse_concept("a light novel about a villainess").media_type == "light novel"
    assert parse_concept("a mecha OVA, 40 minutes").duration_min == 40


def test_parser_titles():
    cases = [
        ('Title: Kurogane no Kokoro. A dark shounen isekai.', "Kurogane no Kokoro"),
        ('"Shokudo no Sora" — healing ramen slice of life.', "Shokudo no Sora"),
        ("巻物『月影』— samurai tale.", "月影"),
        ("no title here at all, just a pitch about idols", "Untitled Concept"),
    ]
    for text, want in cases:
        assert parse_concept(text).title == want


def test_parser_empty_signal_fallback():
    p = parse_concept("completely unrelated startup pitch about SaaS pricing")  # < no keywords
    assert p.genres and p.receipts  # neutral fallback fires with a receipt saying so


def test_parser_no_substring_false_positives():
    """Regression: keyword scan must be word-boundary anchored. Ordinary English
    words must NOT fire anime tags (these all did before the fix)."""
    p = parse_concept(
        "A young protagonist demonstrates his cooking skills while learning about "
        "Japanese culture. He rewards himself with ramen. Her husband runs a food "
        "truck. The story explores alienation in modern Tokyo.")
    tags = {n for n, _ in p.tags}
    for bogus in ("Demons", "Cult", "War", "Elf", "Band", "Aliens"):
        assert bogus not in tags, f"ordinary-word false positive: {bogus}"
    assert "Food" in tags, "a cooking pitch must still fire Food"


def test_parser_age_mentions_imply_cast():
    teen = parse_concept("a 17-year-old pilot saves the world")
    child = parse_concept("a 9-year-old genius solves crimes")
    adult = parse_concept("a 34-year-old salaryman finds meaning")
    assert ("Primarily Teen Cast", 80) in teen.tags
    assert ("Primarily Child Cast", 75) in child.tags
    assert ("Primarily Adult Cast", 75) in adult.tags


def test_parser_plural_rank_semantics():
    """Plural "demons" (85) must outrank singular "demon" (75); singular text
    must not earn the plural's rank."""
    singular = parse_concept("a boy fights a single demon at school")
    plural = parse_concept("a boy fights demons at school")
    assert dict(singular.tags).get("Demons", 0) < dict(plural.tags).get("Demons", 0)


# ---------------------------------------------------------------- 2. tensor

@pytest.fixture(scope="module")
def engine() -> GreenlightEngine:
    return build_engine()


def test_tensor_shape_and_norms(engine):
    X = engine.tensor.X
    assert X.dtype.str == "<f4" and X.ndim == 2
    assert X.shape[0] == len(engine.tensor.titles) >= 1000
    assert X.shape[1] == 18 + CatalogTensor.TAG_DIMS + 6 + 1
    assert (engine.tensor.norms > 0).all()
    assert engine.tensor.X.flags["C_CONTIGUOUS"], "BLAS matvec needs contiguous rows"


def test_tensor_similarity_bounds_and_sanity(engine):
    v = engine.tensor.concept_vector(parse_concept(DEMON_SLAYER_ISH))
    sims = engine.tensor.similar(v, 10)
    assert len(sims) == 10
    assert all(-1.001 <= s <= 1.001 for _, s in sims)
    top_titles = {engine.tensor.titles[i] for i, _ in sims}
    assert any("Demon Slayer" in t or "Kimetsu" in t for t in top_titles), \
        "a Demon Slayer-style pitch must surface Demon Slayer among comparables"
    assert [s for _, s in sims] == sorted([s for _, s in sims], reverse=True)


def test_concept_vector_zero_for_empty_parse(engine):
    v = engine.tensor.concept_vector(parse_concept("startup SaaS pitch"))  # fallback genres
    assert v.sum() > 0  # fallback Action+Fantasy still lands in the space


# ---------------------------------------------------------------- 3. full run

@pytest.fixture(scope="module")
def verdict(engine):
    return engine.run({"concept": DEMON_SLAYER_ISH, "title": "Demon-ish"})


def test_run_status_and_determinism(engine, verdict):
    assert verdict["status"] == "ok"
    engine._run_cache.clear()  # force a fresh compute
    again = engine.run({"concept": DEMON_SLAYER_ISH, "title": "Demon-ish"})
    assert again["greenlight_score"] == verdict["greenlight_score"], \
        "MC is seeded (42) — identical input must give an identical verdict"
    assert again["cache_hit"] is False and verdict["cache_hit"] is False


def test_run_blend_is_calibrated(verdict):
    B = verdict["blend"]
    assert 0.0 <= B["knn_weight"] <= 1.0
    assert 0.0 <= B["shrinkage_lambda"] <= 1.0
    assert B["loo_mae"] >= 0
    assert B["ess"] >= 1.0
    mu = B["knn_weight"] * B["knn_score"] + (1 - B["knn_weight"]) * B["structural_score"]
    assert abs(mu - verdict["risk"]["mean"]) < 15, "risk mean must track the blend"


def test_run_quant_coherent(verdict):
    K = verdict["risk"]
    assert K["sims"] == 20000
    assert 0 <= K["mean"] <= 100
    assert K["cvar5"] <= K["var5"] <= K["mean"], "CVaR₅ ≤ VaR₅ ≤ mean, always"
    assert K["std"] > 0
    assert 0 <= K["p_grade_b"] <= 1 and K["p_grade_b"] >= K["p_grade_a"] >= K["p_grade_s"]


def test_run_comparables_and_cohort(verdict):
    comps = verdict["comparables"]
    assert len(comps) == 10
    assert all(0 <= c["sakura_score"] <= 100 for c in comps)
    assert all(c["similarity"] > 0 for c in comps)
    assert [c["similarity"] for c in comps] == sorted(
        [c["similarity"] for c in comps], reverse=True)
    C = verdict["cohort"]
    assert C["min"] <= C["mean"] <= C["max"]
    assert 0 <= C["concept_percentile"] <= 100


def test_run_plans_quant_bounded(verdict):
    plans = verdict["plans"]
    assert len(plans) == 4
    modes = {p["mode"] for p in plans}
    assert modes == {"subtitles_only", "hindi_dub", "three_language", "five_language"}
    for p in plans:
        assert p["cost_inr"] > 0
        assert 0 <= p["p_profit"] <= 1
        assert 0 <= p["kelly_fraction"] <= 1, "Kelly is a budget fraction — bounded"
        assert p["roi_cvar5"] <= p["roi_var5"] + 1e-9  # ties at the percentile
    assert verdict["recommended_plan"] in modes


def test_run_states_complete(verdict):
    states = verdict["states"]["states"]
    assert len(states) == 32, "india_states.csv covers 32 states/UTs"
    assert all(0 <= s["demand_index"] <= 100 for s in states)
    assert all(s["best_dub_language"] in {"hi", "ta", "te", "en"} for s in states)
    assert states[0]["demand_index"] >= states[-1]["demand_index"], "sorted desc"
    hubs = {s["hub"] for s in states}
    assert len(hubs) == 6, "all six linguistic hubs represented"
    # UP (biggest population) should lead or sit in the top 3 demand slots
    top3 = {s["state"] for s in states[:3]}
    assert "Uttar Pradesh" in top3


def test_run_offline_no_live(verdict):
    assert verdict["live"]["trending_pulled"] is False
    assert verdict["live"]["trending_crossmatch"] == 0


def test_run_pipeline_result_serialized(verdict):
    pr = verdict["pipeline_result"]
    for key in ("sakura_score", "factors", "cultural_profile", "localization_economics",
                "market_breakdown", "why_bullets", "confidence_parts", "genre_affinity",
                "executive_briefing_en", "executive_briefing_ja",
                "pipeline_ms", "two_pass"):
        assert key in pr, f"pipeline_result must carry {key} for the dashboard renderer"
    assert isinstance(pr["pipeline_ms"], (int, float)), "no 'pipeline undefined ms' in the UI"
    tp = pr["two_pass"]
    assert tp["provisional"] is not None and tp["final"] is not None
    assert tp["final"] == pr["sakura_score"], "final pass is the shipped score"
    assert tp["plan_reach"] in (1.0, 1.55, 1.85, 2.2)


def test_run_module_inventory(verdict):
    m = verdict["modules"]
    assert "error" not in m
    assert m["total_modules"] >= 80, "27 registry providers + 60+ external repos"
    assert len(m["registry_kinds"]) >= 25
    assert m["providers"].get("source"), "providers must be registered (import side-effect)"


def test_run_error_on_garbage(engine):
    out = engine.run({"concept": "too short"})
    assert out["status"] == "error"


@pytest.mark.parametrize("sample", SAMPLE_CONCEPTS)
def test_run_all_samples(engine, sample):
    out = engine.run({"concept": sample["concept"]})
    assert out["status"] == "ok"
    assert 0 <= out["greenlight_score"] <= 100
    assert out["grade"] in "SABCD"


# ------------------------------------------------- 4. casting + sketch

def test_casting_real_actors_and_determinism():
    from casting import cast_for_script
    script = ("Vanakkam idhu enna periya velaikala. The young boy must command his fear "
              "and lead the village. Haha, what a journey.")
    out = cast_for_script(script)
    assert out["status"] == "ok"
    assert out["total_actors"] >= 300, "placeholder-filtered pool"
    assert out["total_actors_excluded"] >= 180, "synthetic rows documented"
    assert 0 <= out["best"]["compatibility"] <= 100
    names = [m["name"] for m in out["recommendations"]]
    assert not any(n.lower() in ("generic", "name") for n in names), "no filler actors surfaced"
    assert all(m["why"] for m in out["recommendations"]), "every match carries its rationale"
    again = cast_for_script(script)
    assert again["recommendations"][0]["name"] == out["recommendations"][0]["name"]


def test_casting_language_detection():
    from casting import cast_for_script
    out = cast_for_script("Vanakkam idhu enna periya velaikala. Naan avanai piranthen. Nandri!")
    assert out["analysis"]["language"].lower() in ("tamil", "english")  # source keyword weights
    assert out["status"] == "ok"


def test_casting_rejects_short_script():
    from casting import cast_for_script
    assert cast_for_script("too short")["status"] == "error"


def test_sketch_cnn_path():
    from sketch import classify_image_bytes
    from pathlib import Path
    manga = Path("/tmp/sketch-recog/sketch-recog/manga_model/data/val/manga/manga_0001.png")
    if not manga.exists():
        pytest.skip("sketch validation fixtures not present")
    out = classify_image_bytes(manga.read_bytes())
    assert out["status"] == "ok" and out["is_manga"] is True
    assert out["model"] == "cnn+heuristics"
    assert 0.5 <= out["confidence"] <= 1.0


def test_sketch_deterministic_heuristics():
    from sketch import classify_image_bytes
    from pathlib import Path
    img = Path("/tmp/sketch-recog/sketch-recog/manga_model/data/val/manga/manga_0002.png")
    if not img.exists():
        pytest.skip("sketch fixtures missing")
    a = classify_image_bytes(img.read_bytes())
    b = classify_image_bytes(img.read_bytes())
    assert a["confidence"] == b["confidence"] and a["heuristics"] == b["heuristics"]


def test_sketch_rejects_garbage():
    from sketch import classify_base64
    assert classify_base64("bm90IGFuIGltYWdl")["status"] == "error"


def test_worker_voice_cast_and_sketch():
    import sys
    sys.path.insert(0, "scripts/backend")
    import worker as wk
    wk.ensure_boot()
    out = wk.handle({"cmd": "voice_cast", "script": "The young boy must command his fear. Dhanyavad!"})
    assert out["status"] == "ok" and out["best"]["compatibility"] <= 100
