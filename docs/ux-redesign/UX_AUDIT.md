# UX Audit — why Greenlight overwhelms a writer

*Original audited live at http://localhost:8787/#/greenlight (branch `main`, commit 3b682a0) with the shipped "Isekai revenge drama" preset. Result height: 6,781 px. Issues ranked by impact on the writer.*

## P1 — The verdict doesn't speak (cognitive, structural)

**Observed:** the first panel leads with `52 GRADE C`, then immediately dives into estimator internals: *"verdict = 73% comparable-cohort estimate (53.4, shrunk λ=0.565 · ESS 9.6) + 27% structural pipeline score (25) — blend weight fitted on the cohort's own leave-one-out error."*

**Why it hurts:** the writer's first question is *"is my idea good?"* and the first sentence answers it with a statistics lecture. "λ=0.565 · ESS 9.6" is our methodology, not their answer. A writer cannot act on a shrinkage factor.

**Fix:** lead with a plain-language verdict paragraph (what the score is, how it was judged in one honest sentence, what it means for them), and move the calibration story to a "how sure are we" section in human terms ("when we test this method on shows like yours, it's typically off by ±6 points").

## P2 — Panels are ordered by pipeline stage, not by the writer's questions (structural, cognitive)

**Observed order:** verdict → comparables + cohort maths → quant risk + plan table → states + module inventory + roadmap → full structural pipeline report. The creative guidance (cultural archetypes, CBFC, what resonates) is buried at the *bottom*, inside the structural pipeline render, below ~5,000 px of scroll.

**Why it hurts:** a writer's natural questions are *who's this for → what's it like (comps) → what should I lean into / avoid → what's the business picture → how sure are you.* The current order inverts this: methodology first, creative meaning last.

**Fix:** reorder into a brief: Verdict → What to do next → At a glance → It reads like… (comparables) → Who it's for (audience in plain words) → What resonates / what to watch (cultural + CBFC) → The business picture (one calm table + plain sentences) → How sure are we → *then* all research behind one disclosure.

## P3 — Everything is equally loud (visual)

**Observed:** 20+ tag chips on the first screen; four "big number" cards; nine-column plan table (`plan cost reach E[12m views] E[ROI] sharpe P(profit) ROI VaR₅ kelly`); pink dotbars everywhere; every panel has equal visual weight with hairline boxes.

**Why it hurts:** nothing is secondary, so nothing is primary. The chips are our parse output, not the writer's vocabulary. The plan table mixes three currencies (₹, multipliers, probabilities) in nine unlabeled-for-humans columns.

**Fix:** one clear typographic scale for the brief (headline verdict, section titles, body, small notes); chips only where they carry the writer's own words (genres); the research tables keep their density but live behind the disclosure where density is *expected*.

## P4 — No next action (cognitive, interaction)

**Observed:** the page ends with… more panels. Nothing tells the writer what to *do*.

**Fix:** a short, data-derived "What to do next" block right under the verdict (develop / rework guidance from the grade, the plan recommendation, the CBFC constraint, and the audience focus) — every bullet traceable to a field in the response, nothing invented.

## P5 — The input card competes with the output (visual, minor)

**Observed:** title/format/episodes inputs, four buttons, a 240-character hint sentence and three preset chips — all visible before anything happens.

**Fix:** calm it down — textarea + one primary button + presets; the rest behind an "Options" disclosure. Shorten the hint.

## P6 — Research is not deletable, only moveable (information integrity)

**Observed:** quant histogram, full 32-state table, parse receipts, module inventory, roadmap, and the full structural pipeline report are all genuinely valuable to the analyst and to a writer who wants to go deeper.

**Why it matters:** the fix is NOT to delete these. They move behind a single clearly-labelled disclosure ("The full research"), one click away, default-closed after the brief but fully functional. The e2e tests and the drawer interactions keep working.

## Non-issues (checked and left alone)

- The rest of the site (Sim Lab, Diffusion, Evidence, Battle Map…) is the analyst surface and is dense *by design* with explainers added in v2; the writer's journey is Overview → Greenlight. Scope kept to Greenlight + its input card.
- Load time, error states, offline fallbacks, and the JP/EN toggle are all sound (verified by the existing e2e suite).
- Accessibility: axe-core scans pass with 0 critical violations on the original; the redesign must keep that bar (checked in TEST_REPORT).
