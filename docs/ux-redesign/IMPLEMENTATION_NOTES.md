# Implementation Notes

## What changed (and what deliberately did not)

**One tracked file changed: `public/index.html`.** The backend, HTTP contract, worker, engines, tests and every other page are byte-identical to `main`. The greenlight response schema (`sakurascore-greenlight/1.0`) is untouched — this is a presentation-layer redesign.

### 1. Input card — calmer
- The three structured inputs (title / format / episodes) moved behind an `Options` disclosure; auto-detection keeps working, so most writers never open it.
- Placeholder rewritten to speak to the writer ("Paste your concept…"), the methodology hint replaced with one plain sentence, both bilingual (`data-en`/`data-ja`).
- Presets, file upload, drag-drop, char counter, clear button: unchanged and functional.

### 2. `renderGreenlight` — rewritten as the writer's brief
Single constrained reading column (`.gl-brief`, max 900 px), sections in the writer's question order:

1. **The verdict** — score + grade + a plain-prose paragraph (what you pitched, nearest neighbours, what the number means) + one honest method line + **What to do next** (3 bullets derived from grade, recommended plan, CBFC and top demand hub — every bullet traceable to response fields).
2. **At a glance** — the concept's own vocabulary as chips (media, genres, demographics, 日本語 terms).
3. **It reads like…** — comparables, title-led; **new: franchise deduplication** (the catalog carries each franchise's seasons as separate rows; the old page could say "The Seven Deadly Sins" three times in a row). Drawer per comparable unchanged.
4. **Who it's for** — one plain sentence on hub concentration + the six strongest states with demand dotbars and dub-language notes.
5. **What resonates** — the Indian archetype alignment translated to craft language (label + description + score), from `cultural_profile.archetype_alignment`.
6. **What to watch** — CBFC estimate, triggers, and co-viewing friction with its plain meaning; regional skew when present.
7. **The business picture** — a three-column table (plan / investment / odds) + one recommendation sentence with real numbers.
8. **How sure are we** — the LOO error, centre of range, 1-in-20 worst case, P(grade), cohort position — in sentences, not stats.
9. **The full research** — one `<details>` disclosure (default closed, one click): quant histogram + risk stats, the full nine-column plan economics table, all 32 states, calibration internals, parse receipts, module inventory, roadmap, and the complete structural pipeline report via the unchanged `renderPipeline` (still `setLast=false`).

### 3. Translation helpers (all presentation, no logic change)
`GRADE_MEANING` (S/A/B/C/D → plain verdicts matching the existing thresholds), `PLAN_PLAIN` (mode → plain release description), `FRICTION_PLAIN` (score → co-viewing meaning), `ordinal` (percentile phrasing).

## Bugs found and fixed during implementation

- **Franchise duplication in comparables** (pre-existing, surfaced by the brief's prose): fixed with `baseName` dedup for both the prose and the display list. Full 10-comparable set still drives the research/timings claims.
- **Worktree environment**: the initial `backend 111` symlink landed inside the git checkout, hiding `modules/external` (62 repos, gitignored) from the module-inventory test. Fixed by linking `modules/external` directly; 68/68 python tests pass in the copy.

## Known limitations

- Dynamic brief prose is English-only (section titles, verdict note and all chrome are bilingual via the header toggle, as before).
- Grade meanings are interpretations of the existing thresholds for presentation; the score/grade values themselves are untouched.
