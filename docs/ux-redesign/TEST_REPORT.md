# Test Report

Environment: worktree `sakurascore-writer-ux` (branch `greenlight-writer-first-ux`), original untouched at `sakurascore-simulation` on `main`. Redesign served at http://localhost:8789, original at http://localhost:8787 for side-by-side comparison.

## Commands executed and results

| Check | Command | Result |
|---|---|---|
| Bun engine parity (hash pinned) | `bun test src/engine.test.ts src/lab.test.ts` | **22 pass, 0 fail** (1,147 assertions; shipped config hash unchanged) |
| Python suite (parser, tensor, quant, determinism, module inventory) | `SAKURASCORE_GREENLIGHT_OFFLINE=1 python3 -m pytest tests/ -q --ignore=tests/e2e.py` | **68 pass, 0 fail** (after the worktree symlink fix; 1 env-related failure found and fixed, see IMPLEMENTATION_NOTES) |
| E2E browser suite against the redesign | patched `tests/e2e.py` → `BASE=http://localhost:8789` | **16 pass, 0 fail** (router ×14 routes, interactions, axe-core a11y scans, performance, network audit) |
| Writer-task validation (Playwright, heuristic) | task script, 8 task categories | **8 pass** (task 1 initially "failed" on a case-sensitivity artifact — `.lbl` renders CSS-uppercased; content verified present, check corrected. No app defect.) |
| JS console/page errors across all validation runs | Playwright listeners | **0 errors** |
| Mobile (390×844) | Playwright | full verdict flows, **0 px horizontal overflow** |
| Content preservation | DOM queries on the rendered page | research disclosure contains: 32 state rows + 6 hub chips, ≥20 receipt rows, all four structural-report labels (`Score receipt`, `Cultural compatibility`, `Localization economics`, `Executive briefing` EN+日本語), quant stat cards, full 9-column plan table, module inventory, roadmap — all `checkVisibility() = true` when open |

## Information-preservation audit

Every inventory item (CONTENT_INVENTORY.md) verified present on the rendered page: Level 1 items in the brief, Level 2 inline or as badges, Level 3 inside the one-click disclosure. Nothing deleted; backend contract byte-identical (greenlight python tests pin the schema).

## Not executed / limitations

- No live writer interviews (none available) — validation is heuristic + automated, per the brief's honesty requirement.
- Lighthouse not re-run (original score is on record in the main repo; no JS-weight changes were made — render payload identical, one fewer full-panel render on first paint).
- iOS/Safari real-device testing not available; Chromium headless used for the mobile viewport check.
