"""Unit tests — src/briefing/japanese.py (EN/JA briefings over fake results)."""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from src.briefing.japanese import (GRADE_COMMENT_JA, build_executive_briefing_en,
                                   build_executive_briefing_ja)
from src.data_sources.matrix import get_matrix
from src.intelligence.cultural_compat.engine import CulturalCompatibilityEngine
from src.intelligence.localization_econ.engine import LocalizationEconomicsEngine
from src.scoring.engine import WEIGHTS, Factor

CUL = CulturalCompatibilityEngine()
ECO = LocalizationEconomicsEngine()
MATRIX = get_matrix()
LIVE = sum(1 for s in MATRIX if s["status"] == "live")   # 5

FACTOR_JA = {
    "india_demand": "インド需要シグナル", "global_fandom": "グローバル人気",
    "momentum": "勢い(トレンド)", "cultural_fit": "文化的適合性",
    "localization_reach": "ローカライズ到達度", "genre_fit": "ジャンル適合度",
}
MODE_JA = {"subtitles_only": "字幕のみ", "hindi_dub": "ヒンディー語吹替",
           "three_language": "3言語吹替(印・タミル・テルグ)",
           "five_language": "5言語吹替(+ベンガル・マラーティ)"}


def make_factors(**values):
    vals = {"india_demand": 60, "global_fandom": 50, "momentum": 55,
            "cultural_fit": 62, "localization_reach": 45, "genre_fit": 85}
    vals.update(values)
    return [Factor(n, v, WEIGHTS[n], v * WEIGHTS[n], [f"{n} rationale"])
            for n, v in vals.items()]


def fake_result(title="Test Title", score=75, grade="A", confidence=80,
                status="FINISHED", factors=None, cul=None, loc=None,
                matrix=MATRIX):
    return SimpleNamespace(
        title=title, sakura_score=score, grade=grade, confidence=confidence,
        metadata={"status": status},
        factors=factors if factors is not None else make_factors(),
        cultural_profile=cul if cul is not None else CUL.evaluate(
            genres=["Action"], tags=[], is_adult=False, format="TV", episodes=12),
        localization_economics=loc if loc is not None else ECO.evaluate(
            sakura_score=score, format="TV", episodes=12, duration_min=24),
        data_source_matrix=matrix,
    )


# ---------------------------------------------------------------------- basics
@pytest.mark.parametrize("grade,score", [("S", 90), ("A", 75), ("B", 65),
                                         ("C", 50), ("D", 20)])
def test_briefings_all_five_grades(grade, score):
    r = fake_result(score=score, grade=grade)
    en, ja = build_executive_briefing_en(r), build_executive_briefing_ja(r)
    assert isinstance(en, str) and isinstance(ja, str)
    assert "Test Title" in en and "Test Title" in ja
    assert f"{score}/100" in en and f"{score}/100" in ja
    assert f"Grade {grade}" in en and f"グレード {grade}" in ja
    assert f"Confidence {r.confidence}/100" in en


@pytest.mark.parametrize("grade", ["S", "A", "B", "C", "D"])
def test_ja_briefing_contains_grade_comment(grade):
    ja = build_executive_briefing_ja(fake_result(grade=grade))
    assert GRADE_COMMENT_JA[grade] in ja


def test_grade_comment_ja_covers_exactly_five_grades():
    assert set(GRADE_COMMENT_JA) == {"S", "A", "B", "C", "D"}
    assert all(isinstance(v, str) and v for v in GRADE_COMMENT_JA.values())


@pytest.mark.parametrize("factor_name", sorted(WEIGHTS))
def test_factor_ja_mapping_covers_all_six(factor_name):
    # make the target factor the top contributor so it appears in the top-3 list
    factors = make_factors(**{factor_name: 100})
    factors = [Factor(f.name, 1 if f.name != factor_name else 100, f.weight,
                      f.weight * (1 if f.name != factor_name else 100), f.rationale)
               for f in factors]
    ja = build_executive_briefing_ja(fake_result(factors=factors))
    assert FACTOR_JA[factor_name] in ja
    assert f"{FACTOR_JA[factor_name]}(100/100)" in ja


@pytest.mark.parametrize("score,mode", [(80, "five_language"), (60, "three_language"),
                                        (45, "hindi_dub"), (20, "subtitles_only")])
def test_mode_ja_mapping_covers_all_four(score, mode):
    r = fake_result(score=score)
    assert r.localization_economics.recommended_mode == mode
    ja = build_executive_briefing_ja(r)
    assert f"方式:**{MODE_JA[mode]}**" in ja
    en = build_executive_briefing_en(r)
    assert f"Mode: **{mode}**" in en


# ------------------------------------------------------------------ break-even
def test_break_even_tickets_movie():
    r = fake_result(loc=ECO.evaluate(sakura_score=60, format="MOVIE"))
    en = build_executive_briefing_en(r)
    ja = build_executive_briefing_ja(r)
    assert "net tickets" in en
    assert "純チケット" in ja
    assert "stream views" not in en


def test_break_even_views_series():
    r = fake_result(loc=ECO.evaluate(sakura_score=60, format="TV"))
    en = build_executive_briefing_en(r)
    ja = build_executive_briefing_ja(r)
    assert "stream views" in en
    assert "配信視聴" in ja


def test_break_even_neither():
    base = ECO.evaluate(sakura_score=60, format="TV")
    loc = dataclasses.replace(base, break_even_views=None,
                              break_even_tickets=None, payback_months=None)
    en = build_executive_briefing_en(fake_result(loc=loc))
    ja = build_executive_briefing_ja(fake_result(loc=loc))
    assert "Break-even: n/a" in en
    assert "損益分岐:計算不可" in ja


def test_payback_none_vs_int():
    movie = fake_result(loc=ECO.evaluate(sakura_score=60, format="MOVIE"))
    assert movie.localization_economics.payback_months is None
    assert "payback" not in build_executive_briefing_en(movie)
    series = fake_result(loc=ECO.evaluate(sakura_score=60, format="TV"))
    assert isinstance(series.localization_economics.payback_months, int)
    assert "Indicative payback" in build_executive_briefing_en(series)


# ------------------------------------------------------- triggers / flags / live
def test_empty_triggers_placeholder():
    r = fake_result(cul=CUL.evaluate(genres=["Comedy"], tags=[], is_adult=False))
    en = build_executive_briefing_en(r)
    ja = build_executive_briefing_ja(r)
    assert "None flagged" in en
    assert "大きなリスク要因は検出されていません" in ja


def test_triggers_listed_and_capped_at_four():
    # moderate tags all emit triggers (unlike high-risk, which is an elif branch)
    tags = [("Violence", 80), ("War", 80), ("Suicide", 80), ("Drugs", 80),
            ("Alcohol", 80), ("Death", 80)]
    cul = CUL.evaluate(genres=["Action"], tags=tags, is_adult=False)
    assert len(cul.sensitivity_triggers) == 6
    en = build_executive_briefing_en(fake_result(cul=cul))
    risks = en.split("## Key risks")[1].split("## Data confidence")[0]
    # trigger lines are capped at 4; CBFC notes are also bulleted in this section
    assert len([l for l in risks.splitlines() if l.startswith("- ")]) == 4


def test_empty_flags_shows_none():
    r = fake_result(cul=CUL.evaluate(genres=["Comedy"], tags=[], is_adult=False))
    assert "Flags: none" in build_executive_briefing_en(r)
    flagged = fake_result(cul=CUL.evaluate(genres=["Hentai"], tags=[], is_adult=False))
    assert "certification restricts broadcast" in build_executive_briefing_en(flagged)


def test_live_source_count_math():
    assert LIVE == 5 and len(MATRIX) == 8
    en = build_executive_briefing_en(fake_result())
    ja = build_executive_briefing_ja(fake_result())
    assert f"Score built from {LIVE} live public sources ({len(MATRIX)} assessed)" in en
    assert f"公開ビッグデータ {len(MATRIX)} ソースを評価(うち {LIVE} が稼働中)" in ja


def test_status_line_in_en_briefing():
    assert "RELEASING" in build_executive_briefing_en(fake_result(status="RELEASING"))
    assert "NOT_YET_RELEASED" in build_executive_briefing_en(
        fake_result(status="NOT_YET_RELEASED"))


def test_cultural_section_contents():
    cul = CUL.evaluate(genres=["Sports"], tags=[("Training", 80)], is_adult=False)
    en = build_executive_briefing_en(fake_result(cul=cul))
    assert "CBFC estimate" in en
    assert f"Family co-viewing friction: {cul.family_co_viewing_friction}/100" in en
    assert "Strongest archetype" in en


def test_ja_cultural_section_translates_rating():
    for genres, rating_ja in [
        (["Comedy"], "U(全年齢)"),
        (["Action"], "U/A 7+(7歳以上・保護者同伴推奨)"),
        (["Action"], None),  # same as above id
    ][:2]:
        cul = CUL.evaluate(genres=genres, tags=[], is_adult=False)
        ja = build_executive_briefing_ja(fake_result(cul=cul))
        assert "映画検定(CBFC)推定:" in ja
        assert rating_ja in ja
    cul13 = CUL.evaluate(genres=["Action"], tags=[("Violence", 80)], is_adult=False)
    assert "U/A 13+(13歳以上推奨)" in build_executive_briefing_ja(fake_result(cul=cul13))
    culA = CUL.evaluate(genres=["Hentai"], tags=[], is_adult=False)
    assert "A (Adults Only)" in build_executive_briefing_ja(fake_result(cul=culA))


def test_localization_strategy_lines_en():
    r = fake_result()
    en = build_executive_briefing_en(r)
    assert "Localization strategy (recommended)" in en
    assert "Reach vs subtitles-only" in en
    assert "₹" in en  # format_inr applied to recommended cost


def test_determinism():
    r = fake_result()
    assert build_executive_briefing_en(r) == build_executive_briefing_en(r)
    assert build_executive_briefing_ja(r) == build_executive_briefing_ja(r)
