"""Executive briefings — English and Japanese, generated from PipelineResult.

The Japanese briefing targets Tokyo studio executives and licensing leads:
concise, score-led, with localization strategy and risk in business Japanese.
"""
from __future__ import annotations

from src.intelligence.localization_econ.engine import format_inr


def _grade_comment_ja(grade: str) -> str:
    return {
        "S": "極めて高いポテンシャル — 最優先で展開検討すべきタイトル",
        "A": "高いポテンシャル — 多言語展開を推奨",
        "B": "中堅ポテンシャル — コスト配分の最適化が鍵",
        "C": "ニッチ志向 — 字幕配信とコア層攻略を推奨",
        "D": "現時点での展開は慎重検討が必要",
    }[grade]


def build_executive_briefing_en(r) -> str:
    loc = r.localization_economics
    cul = r.cultural_profile
    top = sorted(r.factors, key=lambda f: -f.contribution)[:3]
    lines = [
        f"# Executive Briefing — {r.title}",
        "",
        f"**SakuraScore: {r.sakura_score}/100 (Grade {r.grade})** · "
        f"Confidence {r.confidence}/100 · {r.metadata.get('status', '')}",
        "",
        "## Headline",
        f"{r.title} scores {r.sakura_score}/100 for Indian market potential. "
        f"The score is driven primarily by: "
        + "; ".join(f"{f.name.replace('_', ' ')} ({f.value:.0f}/100)" for f in top)
        + ".",
        "",
        "## Localization strategy (recommended)",
        f"- Mode: **{loc.recommended_mode}** ({', '.join(loc.recommended_plan.languages)})",
        f"- Estimated cost: **{format_inr(loc.recommended_plan.cost_inr)}** "
        f"for {loc.total_minutes} content-minutes",
        f"- Reach vs subtitles-only: **{loc.recommended_plan.reach_multiplier:.2f}x**",
        f"- Break-even: " + (
            f"{loc.break_even_tickets:,} net tickets" if loc.break_even_tickets
            else f"{loc.break_even_views:,} stream views" if loc.break_even_views
            else "n/a"),
        "" if loc.payback_months is None else f"- Indicative payback: ~{loc.payback_months} months",
        "",
        "## Cultural & regulatory",
        f"- CBFC estimate: **{cul.cbfc_rating_estimate}**",
        f"- Family co-viewing friction: {cul.family_co_viewing_friction}/100",
        f"- Strongest archetype: {max(cul.archetype_alignment.items(), key=lambda kv: kv[1]['score'])[1]['label']}",
        f"- Flags: {', '.join(cul.cultural_distance_flags) or 'none'}",
        "",
        "## Key risks",
        "\n".join(f"- {t}" for t in (cul.sensitivity_triggers[:4] or ["None flagged"])) ,
        "",
        "## Data confidence",
        f"Score built from {sum(1 for s in r.data_source_matrix if s['status'] == 'live')} live "
        f"public sources ({len(r.data_source_matrix)} assessed); confidence "
        f"{r.confidence}/100. Full evidence audit in the report.",
    ]
    return "\n".join(lines)


def build_executive_briefing_ja(r) -> str:
    """日本語エグゼクティブブリーフィング (Tokyo licensing leads)."""
    loc = r.localization_economics
    cul = r.cultural_profile
    top = sorted(r.factors, key=lambda f: -f.contribution)[:3]
    factor_ja = {
        "india_demand": "インド需要シグナル",
        "global_fandom": "グローバル人気",
        "momentum": "勢い(トレンド)",
        "cultural_fit": "文化的適合性",
        "localization_reach": "ローカライズ到達度",
        "genre_fit": "ジャンル適合度",
    }
    mode_ja = {
        "subtitles_only": "字幕のみ",
        "hindi_dub": "ヒンディー語吹替",
        "three_language": "3言語吹替(印・タミル・テルグ)",
        "five_language": "5言語吹替(+ベンガル・マラーティ)",
    }
    rating_ja = {
        "U": "U(全年齢)", "U/A 7+": "U/A 7+(7歳以上・保護者同伴推奨)",
        "U/A 13+": "U/A 13+(13歳以上推奨)",
        "U/A 16+": "U/A 16+(16歳以上推奨)",
    }.get(cul.cbfc_rating_estimate, cul.cbfc_rating_estimate)

    lines = [
        f"# 経営ブリーフィング(日本語)— {r.title}",
        "",
        f"**サクラスコア:{r.sakura_score}/100(グレード {r.grade})** · "
        f"データ信頼度 {r.confidence}/100 · {GRADE_COMMENT_JA[r.grade]}",
        "",
        "## エグゼクティブサマリー",
        f"{r.title} のインド市場ポテンシャルは **{r.sakura_score}/100**。"
        "スコアを牽引しているのは: "
        + "、".join(f"{factor_ja.get(f.name, f.name)}({f.value:.0f}/100)" for f in top)
        + "。",
        "",
        "## 推奨ローカライズ戦略",
        f"- 方式:**{mode_ja.get(loc.recommended_mode, loc.recommended_mode)}**",
        f"- 概算費用:**{format_inr(loc.recommended_plan.cost_inr)}**"
        f"(コンテンツ {loc.total_minutes} 分ベース)",
        f"- 字幕のみ比の到達倍率:**{loc.recommended_plan.reach_multiplier:.2f}倍**",
        ("損益分岐:純チケット " + f"{loc.break_even_tickets:,} 枚") if loc.break_even_tickets
        else ("損益分岐:配信視聴 " + f"{loc.break_even_views:,} 回") if loc.break_even_views
        else "損益分岐:計算不可",
        "" if loc.payback_months is None else f"- 回収目安:約 {loc.payback_months} ヶ月",
        "",
        "## 文化的適合と規制(CBFC)",
        f"- 映画検定(CBFC)推定:{rating_ja}",
        f"- ファミリー視聴(親子共視)への摩擦:{cul.family_co_viewing_friction}/100",
        f"- 最も適合する文化的原型:{max(cul.archetype_alignment.items(), key=lambda kv: kv[1]['score'])[1]['label']}",
        "",
        "## 主要リスク",
        "\n".join(f"- {t}" for t in (cul.sensitivity_triggers[:4] or ["大きなリスク要因は検出されていません"])),
        "",
        "## データ透明性",
        f"公開ビッグデータ {len(r.data_source_matrix)} ソースを評価(うち "
        f"{sum(1 for s in r.data_source_matrix if s['status'] == 'live')} が稼働中)。"
        "ソースごとの信頼性・バイアス・緩和策はレポート Evidence Audit を参照。",
    ]
    return "\n".join(lines)


GRADE_COMMENT_JA = {
    "S": "極めて高いポテンシャル — 最優先で展開検討すべきタイトル",
    "A": "高いポテンシャル — 多言語展開を推奨",
    "B": "中堅ポテンシャル — コスト配分の最適化が鍵",
    "C": "ニッチ志向 — 字幕配信とコア層攻略を推奨",
    "D": "現時点での展開は慎重検討が必要",
}
