# Before / After

Screenshots in `screenshots/` — `before-*` captured from the original (localhost:8787, `main`), `after-*` from the redesign (localhost:8789, this branch), same preset ("Isekai revenge drama"), same 1440×950 viewport.

## The numbers

| Measure | Before | After |
|---|---|---|
| Result height to end of "How sure are we" | 6,781 px (everything forced) | **2,778 px** (−59%), research one click away |
| Panels with equal visual weight before the verdict's meaning | 8 + full pipeline report | 1 verdict card + 7 quiet sections |
| Time-to-meaning | read estimator maths first | first paragraph answers "is my idea good, what now" |
| Statistical vocabulary on first screen | λ, ESS, antithetic, VaR₅, Sharpe, Kelly… | plain sentences; the vocabulary lives in research |
| Next action | none stated | 3 derived, traceable bullets |

## What a writer sees now (in order)

**Before:** score card with estimator internals → 10-row comparable table → cohort percentile maths + parse receipts → MC histogram + 9-column plan table → 12-state table + module inventory + roadmap → the entire structural pipeline report.

**After:** *You pitched X as a 24-episode series. Its closest neighbours are A, B and C — and scored for India the way those shows score, it lands at 52/100: promising, worth developing with a clear angle…* → **What to do next** (release plan, content warning, audience focus) → at a glance → it reads like… → who it's for → what resonates → what to watch → the business picture → how sure are we → *the full research, one click*.

## What did NOT change

The engine, the data, the honesty. The research disclosure carries everything the old page showed — the same quant histogram, the same 32-state model, the same receipts, the same pipeline report — with the same drawers and interactions. The e2e suite (16 tests) and the python suite (68 tests) pass unchanged against the redesign.
