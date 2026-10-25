"""Report exporters — Markdown, JSON, HTML.

Every format carries the full pipeline result: score attribution, cultural
compatibility & CBFC assessment, rupee localization economics, the 8-source
public-data evidence matrix, and the bilingual executive briefings.
"""
from __future__ import annotations

import html
import json

from src.app import PipelineResult
from src.intelligence.localization_econ.engine import format_inr


# --------------------------------------------------------------------------- md
def to_markdown(r: PipelineResult) -> str:
    loc, cul = r.localization_economics, r.cultural_profile
    unreleased_note = (" — UNRELEASED (zero Indian consumption history; scored on "
                       "pre-launch demand + structural features)" if r.unreleased else "")
    L = [
        f"# SakuraScore India Report — {r.title}",
        f"*Geek Pictures GEEK-PS-01 · Predicting Indian Market Potential for "
        f"Japanese Media Content*",
        "",
        f"## Score: {r.sakura_score}/100 — Grade {r.grade} "
        f"(confidence {r.confidence}/100)",
        f"**Status:** {r.metadata.get('status') or 'n/a'}{unreleased_note}",
        "",
        "## Why This Score? (factor attribution)",
        "| Factor | Value | Weight | Contribution | Rationale |",
        "|---|---|---|---|---|",
    ]
    for f in sorted(r.factors, key=lambda x: -x.contribution):
        L.append(f"| {f.name.replace('_',' ')} | {f.value:.0f}/100 | {f.weight:.2f} "
                 f"| {f.contribution:+.1f} | {'; '.join(f.rationale)} |")
    L += [
        "",
        "## Cultural Compatibility & CBFC Assessment",
        f"- **CBFC certification estimate:** {cul.cbfc_rating_estimate}",
        f"- **Family co-viewing friction:** {cul.family_co_viewing_friction}/100",
        f"- **Overall cultural fit:** {cul.overall_cultural_fit}/100",
        "",
        "### Archetype alignment",
        "| Archetype | Score | Why |",
        "|---|---|---|",
    ]
    for aid, a in cul.archetype_alignment.items():
        L.append(f"| {a['label']} | {a['score']}/100 | {'; '.join(a['why'])} |")
    L += ["", "### Sensitivity triggers & censor notes"]
    L += [f"- {t}" for t in cul.sensitivity_triggers] or ["- none flagged"]
    L += [f"- note: {n}" for n in cul.cbfc_notes]
    if cul.cultural_distance_flags:
        L += ["- flags: " + "; ".join(cul.cultural_distance_flags)]

    L += [
        "",
        "## Rupee Localization Economics",
        f"Content: {loc.content_type}, {loc.episodes} x {loc.minutes_per_ep} min "
        f"= {loc.total_minutes} minutes",
        "",
        "| Mode | Languages | Cost (INR) | Reach vs subs | INR per reach-unit |",
        "|---|---|---|---|---|",
    ]
    for p in loc.plans:
        star = " **← recommended**" if p.mode == loc.recommended_mode else ""
        L.append(f"| {p.mode}{star} | {', '.join(p.languages)} "
                 f"| {format_inr(p.cost_inr)} | {p.reach_multiplier:.2f}x "
                 f"| ₹{p.cost_per_reach_unit:,.0f} |")
    be = ("break-even ≈ "
          + (f"{loc.break_even_tickets:,} net tickets" if loc.break_even_tickets
             else f"{loc.break_even_views:,} stream views") if (loc.break_even_tickets or loc.break_even_views)
          else "n/a")
    L += ["", f"**Recommended: {loc.recommended_mode}** — {format_inr(loc.recommended_plan.cost_inr)}, "
          f"{loc.recommended_plan.reach_multiplier:.2f}x reach, {be}"
          + (f", payback ≈ {loc.payback_months} months." if loc.payback_months else ".")]
    L += [f"- assumption: {a}" for a in loc.assumptions]

    if r.market_breakdown:
        L += ["", "## India Market Map (linguistic hubs)",
              "| Hub | Population | Internet % | Median age | Cultural Δ | Demand index |",
              "|---|---|---|---|---|---|"]
        for hub, m in r.market_breakdown.items():
            L.append(f"| {hub} | {m['population']:,} | {m['internet_penetration_pct']} "
                     f"| {m['median_age']} | {m['cultural_delta']:+d} "
                     f"| {m['demand_index']}/100 |")

    L += ["", "## Public Big Data Source Assessment (8 sources)",
          "| Source | Status | Relevance | Reliability | Bias | Noise | Mitigation |",
          "|---|---|---|---|---|---|---|"]
    for s in r.data_source_matrix:
        L.append(f"| {s['name']} | {s['status']} | {s['relevance']} | {s['reliability']} "
                 f"| {s['bias']} | {s['noise']} | {s['mitigation']} |")

    L += ["", "---", r.executive_briefing_en, "", "## 経営ブリーフィング(日本語)", "",
          "```", r.executive_briefing_ja, "```"]
    return "\n".join(L)


# ------------------------------------------------------------------------ json
def to_json(r: PipelineResult) -> str:
    doc = {
        "schema": "sakurascore-india/0.2",
        "challenge": "Geek Pictures GEEK-PS-01",
        "title": r.title,
        "metadata": {k: (v if not isinstance(v, (list, tuple)) or k != "tags" else
                         [{"name": n, "rank": rk} for n, rk in v])
                     for k, v in r.metadata.items()},
        "unreleased": r.unreleased,
        "sakura_score": r.sakura_score,
        "grade": r.grade,
        "confidence": r.confidence,
        "factors": [{"name": f.name, "value": f.value, "weight": f.weight,
                     "contribution": f.contribution, "rationale": f.rationale}
                    for f in r.factors],
        "cultural_profile": {
            "archetype_alignment": r.cultural_profile.archetype_alignment,
            "cultural_distance_flags": r.cultural_profile.cultural_distance_flags,
            "cbfc_rating_estimate": r.cultural_profile.cbfc_rating_estimate,
            "cbfc_notes": r.cultural_profile.cbfc_notes,
            "sensitivity_triggers": r.cultural_profile.sensitivity_triggers,
            "family_co_viewing_friction": r.cultural_profile.family_co_viewing_friction,
            "regional_variation": r.cultural_profile.regional_variation,
            "overall_cultural_fit": r.cultural_profile.overall_cultural_fit,
        },
        "localization_economics": {
            "content_type": r.localization_economics.content_type,
            "episodes": r.localization_economics.episodes,
            "minutes_per_ep": r.localization_economics.minutes_per_ep,
            "total_minutes": r.localization_economics.total_minutes,
            "plans": [vars(p) for p in r.localization_economics.plans],
            "recommended_mode": r.localization_economics.recommended_mode,
            "break_even_views": r.localization_economics.break_even_views,
            "break_even_tickets": r.localization_economics.break_even_tickets,
            "payback_months": r.localization_economics.payback_months,
            "assumptions": r.localization_economics.assumptions,
        },
        "data_source_matrix": r.data_source_matrix,
        "market_breakdown": r.market_breakdown,
        "wiki_evidence": r.wiki_evidence,
        "executive_briefing_en": r.executive_briefing_en,
        "executive_briefing_ja": r.executive_briefing_ja,
    }
    return json.dumps(doc, ensure_ascii=False, indent=2, default=str)


# ----------------------------------------------------------------------- html
_HTML_SHELL = """<!doctype html>
<html><head><meta charset="utf-8"><title>SakuraScore India — {title}</title>
<style>
body{{font-family:'Segoe UI',system-ui,sans-serif;margin:0;background:#faf7fb;color:#231826}}
.hero{{background:linear-gradient(120deg,#5b2a86,#e0447c);color:#fff;padding:28px 36px}}
.hero h1{{margin:0 0 4px}} .hero p{{margin:0;opacity:.9}}
.badge{{display:inline-block;background:rgba(255,255,255,.18);border:1px solid
 rgba(255,255,255,.4);border-radius:999px;padding:4px 12px;font-size:.8em;margin-top:8px}}
main{{padding:24px 36px;max-width:1080px;margin:auto}}
.score{{font-size:52px;font-weight:800;color:#5b2a86}}
table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:.92em}}
th,td{{border:1px solid #e3d7ea;padding:7px 10px;text-align:left;vertical-align:top}}
th{{background:#f3e9f8}}
.bar{{background:#e0447c;height:10px;border-radius:6px}}
section{{margin:26px 0}} h2{{color:#5b2a86;border-bottom:2px solid #f0d9e6;padding-bottom:6px}}
.pill{{background:#f3e9f8;border-radius:999px;padding:2px 10px;margin:2px;display:inline-block;font-size:.85em}}
.ja{{background:#fff8f0;border:1px solid #f0e0c8;border-radius:10px;padding:16px;white-space:pre-wrap}}
.small{{color:#7a6b83;font-size:.85em}}
</style></head><body>
<div class="hero"><h1>🌸 SakuraScore India</h1>
<p>Geek Pictures GEEK-PS-01 · Predicting Indian Market Potential for Japanese Media Content</p>
<span class="badge">{title} — Grade {grade} · confidence {conf}/100</span></div>
<main>{body}</main></body></html>"""


def to_html(r: PipelineResult) -> str:
    loc, cul = r.localization_economics, r.cultural_profile
    b: list[str] = []
    b.append(f'<section><div class="score">{r.sakura_score}<span '
             f'style="font-size:22px;color:#7a6b83">/100 — Grade {r.grade}</span></div>'
             f'<p class="small">{r.metadata.get("status") or ""}'
             f'{" · UNRELEASED — scored on pre-launch demand" if r.unreleased else ""}</p>'
             + "".join(f'<div style="display:flex;gap:8px;align-items:center;margin:4px 0">'
                       f'<div style="width:150px" class="small">{f.name.replace("_"," ")}</div>'
                       f'<div style="flex:1;background:#f3e9f8;border-radius:6px">'
                       f'<div class="bar" style="width:{f.value}%"></div></div>'
                       f'<div class="small">{f.value:.0f}</div></div>' for f in
                       sorted(r.factors, key=lambda x: -x.contribution))
             + "".join(f'<p class="small">{" · ".join(f.rationale)}</p>'
                       for f in sorted(r.factors, key=lambda x: -x.contribution))
             + "</section>")

    b.append('<section><h2>Cultural Compatibility & CBFC</h2>'
             f'<p><span class="pill">CBFC estimate: {cul.cbfc_rating_estimate}</span>'
             f'<span class="pill">co-viewing friction: {cul.family_co_viewing_friction}/100</span>'
             f'<span class="pill">overall cultural fit: {cul.overall_cultural_fit}/100</span></p>'
             "<table><tr><th>Archetype</th><th>Score</th><th>Why</th></tr>"
             + "".join(f"<tr><td>{html.escape(a['label'])}</td><td>{a['score']}</td>"
                       f"<td>{html.escape('; '.join(a['why']))}</td></tr>"
                       for a in cul.archetype_alignment.values())
             + "</table>"
             + "".join(f'<span class="pill">⚠ {html.escape(t)}</span>'
                       for t in cul.sensitivity_triggers)
             + "</section>")

    b.append('<section><h2>Rupee Localization Economics</h2>'
             f'<p class="small">{loc.content_type}: {loc.episodes} × {loc.minutes_per_ep} '
             f'min = {loc.total_minutes} min</p>'
             "<table><tr><th>Mode</th><th>Languages</th><th>Cost</th><th>Reach</th></tr>"
             + "".join(f"<tr><td>{p.mode}{' ← recommended' if p.mode == loc.recommended_mode else ''}</td>"
                       f"<td>{html.escape(', '.join(p.languages))}</td>"
                       f"<td>{format_inr(p.cost_inr)}</td><td>{p.reach_multiplier:.2f}x</td></tr>"
                       for p in loc.plans)
             + "</table>"
             + (f"<p>Break-even ≈ <b>{loc.break_even_tickets:,}</b> net tickets"
                if loc.break_even_tickets else
                f"<p>Break-even ≈ <b>{loc.break_even_views:,}</b> stream views"
                if loc.break_even_views else "")
             + (f" · payback ≈ {loc.payback_months} months</p>" if loc.payback_months else "</p>")
             + "</section>")

    if r.market_breakdown:
        b.append('<section><h2>India Market Map — linguistic hubs</h2>'
                 "<table><tr><th>Hub</th><th>Population</th><th>Internet %</th>"
                 "<th>Median age</th><th>Cultural Δ</th><th>Demand</th></tr>"
                 + "".join(f"<tr><td>{hub}</td><td>{m['population']:,}</td>"
                           f"<td>{m['internet_penetration_pct']}</td><td>{m['median_age']}</td>"
                           f"<td>{m['cultural_delta']:+d}</td>"
                           f"<td><div class='bar' style='width:{m['demand_index']}%'></div></td></tr>"
                           for hub, m in r.market_breakdown.items())
                 + "</table></section>")

    b.append('<section><h2>Public Big Data Source Assessment (8 sources)</h2>'
             "<table><tr><th>Source</th><th>Status</th><th>Relevance</th><th>Reliability</th>"
             "<th>Bias → Mitigation</th></tr>"
             + "".join(f"<tr><td>{s['name']}</td><td>{s['status']}</td>"
                       f"<td>{s['relevance']}</td><td>{s['reliability']}</td>"
                       f"<td class='small'>{html.escape(s['bias'])}<br>→ "
                       f"{html.escape(s['mitigation'])}</td></tr>"
                       for s in r.data_source_matrix)
             + "</table></section>")

    b.append('<section><h2>Executive Briefing (EN)</h2><pre style="white-space:pre-wrap">'
             + html.escape(r.executive_briefing_en) + "</pre></section>")
    b.append('<section><h2>経営ブリーフィング(日本語)</h2><div class="ja">'
             + html.escape(r.executive_briefing_ja) + "</div></section>")

    return _HTML_SHELL.format(title=html.escape(r.title), grade=r.grade,
                              conf=r.confidence, body="\n".join(b))
