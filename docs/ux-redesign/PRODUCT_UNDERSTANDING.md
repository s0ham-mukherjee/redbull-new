# Product Understanding — what this app actually is

*Written from a full read of the repository plus live use of the running app. This is the redesign copy's working document; the original project is untouched at `sakurascore-simulation/` (branch `main`).*

## What the product does

SakuraScore India evaluates **Japanese entertainment IPs against the Indian market**. One engine stack, three layers:

1. **sakura-abm** — a deterministic, seeded agent-based audience simulation (TypeScript + Python, bit-exact parity, 40 agents on a Barabási–Albert network). Answers "does regional-language dubbing change simulated engagement?" via paired seeds.
2. **The scoring pipeline** (Python) — scores *real* catalog titles (1,365 anime from a live AniList pull) on India demand, global fandom, momentum, cultural fit and localization economics, with CBFC rating estimates and rupee cost models.
3. **Greenlight** — the concept terminal. A writer pastes a *new* concept (script, logline, character design — English or Japanese). The concept is parsed into AniList feature space, matched against the catalog tensor, scored structurally by the real pipeline, calibrated against its 10 nearest catalog neighbours, and risk-adjusted with a 20,000-path Monte Carlo (VaR₅/CVaR₅/Sharpe/Kelly).

Delivered as a single-page dashboard (14 routed sections, dot-matrix aesthetic, EN/日本語 toggle) served by Bun locally and deployed fully serverless on Vercel (Node function for the TS engine, Python function for pipeline + greenlight).

## Who uses it

- **The writer** (primary user of Greenlight): has a concept — a script, a character, a premise — and needs to know *is this viable for India, for whom, what should I lean into, what will get me in trouble, is it worth my time.* They think in stories and comparable shows, not in shrinkage lambdas.
- **The analyst/founder** (primary user of the other 13 pages): wants the simulation receipts, the competitive intelligence, the scoring math, the sensitivity sweeps.

## Greenlight's role

Greenlight is the **front door for creative input** and the only page where the user brings something that doesn't exist yet. The backend response (unchanged in this redesign — `sakurascore-greenlight/1.0`) contains: concept parse (genres/tags/demographics/media type/Japanese terms/receipts), greenlight score + grade, the blend + LOO calibration, quant risk block, 10 comparables with live pipeline scores and live AniList trending, cohort stats, all four localization plans with ROI/Sharpe/Kelly, 32-state demand model, module inventory, roadmap, and the full structural pipeline result (cultural profile with Indian archetypes, CBFC estimate, co-viewing friction, econ plans, hub demand, bilingual briefings).

## The writer's actual workflow (observed, from the shipped presets and controls)

1. Arrives with text (paste or file upload — txt/md/fountain).
2. Runs it, waits ~1–10 s.
3. Reads the result — **currently a 6,800-pixel wall of 8 dense panels + the full pipeline report**.
4. Tries to answer: *is this good? for whom? what now?*

Steps 3–4 are where the product fails the writer today. Everything they need is *somewhere* on that page, but it is organised by **internal pipeline stage** (parse → tensor → cohort → quant → states → modules → roadmap → structural), not by the writer's questions.

## Technical constraints (preserved by this redesign)

- Single-file dashboard (`public/index.html`, vanilla JS, no framework, zero npm deps in the browser).
- The greenlight HTTP contract and every computed field stays byte-identical — **this redesign changes presentation only** (one render function + CSS + the input card markup). No backend, API, or data-contract changes.
- The dot-matrix design tokens (dot typeface, ink/canvas/signal colours) are the product's identity and are retained; the redesign uses them more calmly.
- Tests: 22 bun parity tests, 68 python tests (25 greenlight), 14 e2e Playwright browser tests. All must stay green.

## Uncertainties

- No live writer interviews were available; the writer model is inferred from the product's own positioning (concept terminal for Japanese-media pitches), the shipped sample concepts, and the feedback that the page is "too overwhelming for writers."
