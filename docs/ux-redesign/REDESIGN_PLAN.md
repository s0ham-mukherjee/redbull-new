# Redesign Plan — Greenlight as a writer's brief

## The mental model shift

Today the page is organised the way **our pipeline works** (parse → tensor → cohort → quant → states → modules → structural). The redesign organises it the way **a writer thinks**:

> *Is my idea good? → What should I do? → What is it, in one line? → What is it like? → Who's it for? → What should I lean into, what will bite me? → What's the business reality? → How sure are you? → (only if I want) show me everything.*

## The new page structure

```
┌ input (calm) ──────────────────────────────────────────────┐
│ paste your concept…                     [ Greenlight ▶ ]    │
│ example chips · options (title/format/eps) · file · chars  │
└─────────────────────────────────────────────────────────────┘

┌ THE VERDICT ───────────────────────────────────────────────┐
│  52/100 · Grade C — "Niche, but workable with the right    │
│  scope"                                                    │
│  A short paragraph: what was judged, against what, and     │
│  what that means for the writer. One honest method line.   │
│                                                            │
│  WHAT TO DO NEXT                                           │
│  · develop/rework guidance from grade + plan               │
│  · the one constraint that matters (CBFC)                  │
│  · where the audience is                                   │
└────────────────────────────────────────────────────────────┘

  At a glance     — the writer's own words (format, genres,
                    demographics, eps, 日本語 note)
  It reads like…  — comparables: title-led, click for drawer
  Who it's for    — plain-language audience + 6 state rows
  What resonates  — Indian archetypes, translated to craft
  What to watch   — CBFC + triggers + co-viewing, plain words
  The business    — 3-column calm table + one recommendation
                    sentence
  How sure are we — ±error in points, P(grades), worst case

┌ THE FULL RESEARCH ▸ (disclosure, default closed) ──────────┐
│ quant risk · full 32-state table · parse receipts ·        │
│ calibration internals · full plan quant table · module     │
│ inventory · roadmap · the complete structural pipeline     │
│ report (factors, cultural tables, econ, briefings)         │
└────────────────────────────────────────────────────────────┘
```

## Language rules

- Lead sentences answer a question; sections are titled with the writer's question ("Who it's for", not "State-wise demand prediction").
- Numbers get units and meaning: "typically off by ±6 points", "a 5-in-100 chance the score lands below 40", "₹6.1 L upfront; 99% of scenarios turn a profit".
- Internal vocabulary (λ, ESS, antithetic, kNN, tensor, CBFC-as-acronym) appears only inside the research disclosure, or is translated once.
- Grade meanings are presentation, not new logic: S exceptional · A strong · B promising · C niche-but-workable · D high-risk/rework. Map derives from the existing grade thresholds.

## Visual approach (same design tokens, calmer use)

- Typography carries the hierarchy: one verdict headline, section titles in sentence case, readable 13–14px body prose, quiet small notes. Chip noise reduced to the concept's own vocabulary.
- Hairline boxes only around the two anchors (verdict card, research disclosure); brief sections separated by whitespace + headings, not cards.
- Colour: signal pink reserved for the verdict score, links and the "trending" badge; everything else ink/canvas.
- Dotbars remain inside research tables where comparison is the job.

## Alternatives considered

1. **Tabbed brief vs scrolling brief** — tabs hide the narrative; a brief should read top-to-bottom. Chosen: single scroll with a sticky-free calm structure (~1,800 px to "How sure", vs 6,781 px today).
2. **Deleting the quant/states/structural panels** — rejected: they're the product's intelligence and its receipts (audit P6). They move, they don't die.
3. **Multi-page split (brief page + research page)** — rejected: the SPA has no per-page state for this; a disclosure keeps everything one click away without a route/UX contract change.
4. **Rewording the backend briefings and shipping those** — the pipeline's EN/JA briefings stay as research artifacts; the verdict paragraph is written for *this* page's context (concept + comparables + plans together), which the backend briefing doesn't have.

## Implementation scope (what changes, what cannot)

- `public/index.html` only: the Greenlight input card markup, one new `renderGreenlight` (+ small helpers: plain-grade mapping, sentence builders from real fields), brief CSS, and a disclosure toggle. `renderPipeline` reused unchanged inside the disclosure.
- Backend, HTTP contract, worker, engines, tests: **zero changes**.
- i18n: the new section titles carry `data-en`/`data-ja` like the rest of the chrome; deep research content stays English (as today).
