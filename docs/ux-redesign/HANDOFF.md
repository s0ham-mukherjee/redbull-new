# Handoff

## Locations

- **Original (untouched):** `/Users/apple/Desktop/sakurascore-simulation/sakurascore-simulation` — branch `main`, still deployed at https://sakurascore-india.vercel.app. Nothing on `main` changed for this redesign.
- **Redesign (this work):** `/Users/apple/Desktop/sakurascore-simulation/sakurascore-writer-ux` — a git worktree on branch **`greenlight-writer-first-ux`**, one commit ahead of `main`. Only `public/index.html` + `docs/ux-redesign/**` changed. Not pushed, not deployed (per instructions).

## Run it

```bash
cd sakurascore-writer-ux
bun run dev                 # http://localhost:8787 (or PORT=8789 to run beside the original)
bun test src/engine.test.ts src/lab.test.ts          # 22 parity tests
SAKURASCORE_GREENLIGHT_OFFLINE=1 python3 -m pytest tests/ -q --ignore=tests/e2e.py   # 68 tests
python3 -m pytest tests/e2e.py -q                     # 16 browser tests (server must be up on :8787)
```

Note: `backend 111/redbull-thapar-japan/modules/external` in the worktree is a symlink into the original checkout (the 6.4 GB clones are gitignored and not in the repo); without it only the module-inventory count degrades — the pipeline and greenlight engines run entirely from tracked source.

## What was implemented

A writer-first Greenlight brief: verdict-first hierarchy, plain-language translations of every score, "What to do next" derived from real fields, comparables with franchise dedup, audience/creative/business/confidence sections, and all previous research preserved behind a single disclosure. Full detail: IMPLEMENTATION_NOTES.md; reasoning: UX_AUDIT.md + REDESIGN_PLAN.md; preservation map: CONTENT_INVENTORY.md.

## Merging

The branch is a clean, single-file code change plus docs. To adopt: `git merge greenlight-writer-first-ux` (or cherry-pick the commit) on `main`, then redeploy. The old presentation is fully recoverable from history; no migration needed.

## Outstanding / next steps

- Dynamic brief prose is English-only (titles/chrome are bilingual) — a JP prose pass would need translated sentence templates.
- The rest of the site (analyst pages) intentionally untouched; if writers also live on Overview, a similar calm pass could follow the same pattern.
- Real writer usability sessions recommended once merged — current validation is heuristic + automated.
