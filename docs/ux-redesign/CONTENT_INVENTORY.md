# Content Inventory — every meaningful item and its destination

*Rule: presentation changes, not survival. "Behind the research disclosure" = one click from the brief, default collapsed, fully rendered on open. The backend response is unchanged, so preservation is verifiable against the JSON contract.*

## Level 1 — essential understanding (the brief, first screen)

| Information | Source field | Destination |
|---|---|---|
| Score + grade | `greenlight_score`, `grade` | **The verdict** — big number + plain-language meaning + honest one-line method note |
| Plain verdict paragraph | derived from score/grade/cohort/comparables | **The verdict** body prose |
| What to do next | derived: grade → develop/rework guidance, `recommended_plan`, CBFC, top state | **What to do next** (3 traceable bullets) |
| Concept identity | `concept.title`, `media_type`, `genres`, `demographics`, episodes | **At a glance** fact strip (chips = the writer's own words) |
| Comparables | `comparables[]` (title, score, similarity, live trending) | **It reads like…** — titles first, scores secondary, click = full drawer (unchanged) |
| Audience | `states.states[]` top rows, `states.hubs[]` | **Who it's for** — plain sentences ("core audience: the Hindi belt — UP, Maharashtra…"), top-6 state rows kept as compact list |
| What resonates | `pipeline_result.cultural_profile.archetype_alignment` | **What resonates** — archetype labels are already writer-readable ("Dharma & Duty (धर्म/कर्तव्य)…") |
| What to watch | `cultural_profile.cbfc_rating_estimate`, `sensitivity_triggers`, `family_co_viewing_friction` | **What to watch** — rating in plain words + triggers + what co-viewing friction means |
| Business picture | `plans[]`, `recommended_plan` | **The business picture** — 3 calm columns (plan, cost, odds it pays off) + one plain sentence for the recommendation |
| Confidence | `blend.loo_mae`, `risk.p_grade_*`, `risk.var5` | **How sure are we** — "typically off by ±N points", P(reaching B/A), worst-case in plain words |

## Level 2 — supporting context (in the brief, visually quiet)

| Information | Source field | Destination |
|---|---|---|
| Cohort position (concept vs comparables) | `cohort` | One sentence in "How sure are we" + mini strip |
| Japanese terms parsed | `concept.japanese_terms` | Small note in "At a glance" (only if present) |
| Two-pass structural story | `pipeline_result.two_pass` | Behind research disclosure (with the structural render) |
| Live trending cross-match | `comparables[].live_trending` | Badge on comparable rows ("trending now") — no separate panel |

## Level 3 — full research (behind "The full research" disclosure, one click)

| Information | Source field | Destination |
|---|---|---|
| Quant histogram + E/σ/VaR₅/CVaR₅ + P(grades) | `risk` | Research: Quant risk panel (unchanged internals, calmer chrome) |
| Monte-Carlo method note | `risk.method` | Same panel footnote |
| Full 32-state demand table | `states.states` (all) | Research: full state table (top-12 version retired — the full one is the authoritative view; brief keeps a plain-language summary) |
| Hub rollup chips | `states.hubs` | Research: with state table |
| Parse receipts (keyword → what it fired) | `concept.receipts` | Research: receipts table |
| Blend internals (λ, ESS, LOO-optimal weight) | `blend` | Research: calibration panel |
| Plan quant table (9 columns) | `plans[]` full fields | Research: full plans table (Sharpe/Kelly/VaR₅ columns live here) |
| Module inventory | `modules` | Research: inventory strip |
| Roadmap P0–P4 | presets payload `roadmap` | Research: roadmap |
| Structural pipeline report (factors, confidence parts, signals, cultural tables, econ assumptions, hub demand, evidence matrix, EN/JA briefings) | `pipeline_result` | Research: the existing `renderPipeline` output, unchanged |
| Timings/catalog size | `timings_ms` | Research footer line (also shown in the small `glMeta` header line, as today) |

## Removed from first view (not removed from product)

Nothing is deleted. Two items change *presentation*: the top-12 state list is superseded by the plain-language audience section + full table behind the disclosure; the nine-column plan table's first three columns are promoted to the brief as a calm three-column table, with the full table remaining in research.

## Verification

`tests/e2e.py` (14 browser tests) + a new task-validation script assert: brief sections render from real data, the disclosure opens, the full state table (32 rows), receipts, plan quant table, structural report and drawers all remain reachable and functional. Backend JSON contract untouched (68 python tests pin it).
