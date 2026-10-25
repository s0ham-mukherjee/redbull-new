# SakuraScore India — Simulation & Research Subsystem

**MiroFish-based AI simulation and research integration subsystem** (hackathon module).
Evaluates how Japanese media IPs might land with Indian audiences under different
release strategies — with evidence-traceable assumptions, a reproducible agent
simulation, and structured output for the SakuraScore scoring/frontend teams.

> **Value proposition:** *evidence → audience assumptions → agent simulation → paired scenario comparison → structured, labelled output* — zero credentials, zero dependencies, fully reproducible.

```
   Evidence (18 cited sources)          Audience segments (hypotheses, linked to evidence)
   data/evidence/*.json          ⟶      configs/*.json
                                          │
                                          ▼  run_simulation(config) -> result
                                 sakura-abm engine (deterministic, seeded, paired)
                                          │
                                          ▼
        results/*_output.json : scenarios · paired comparisons · assumptions ·
                                source_references · limitations · run_metadata
```

## What's here

| Path | Purpose |
|---|---|
| `src/sakurascore_sim/` | The subsystem (Python ≥3.10, **stdlib only**) |
| `src/sakurascore_sim/adapters/abm_engine.py` | `sakura-abm` — deterministic agent-based engine (the only implemented adapter; no dead stubs) |
| `src/sakurascore_sim/models.py` | Input contract + strict validation with stable error codes |
| `src/sakurascore_sim/simulation/{runner,scenarios,results}.py` | Orchestration, paired comparison logic, output contract |
| `src/sakurascore_sim/research/` | Source registry (terms/quality metadata) + evidence loader (no network I/O) |
| `configs/example_experiment.json` | Flagship experiment: *Demon Slayer: Infinity Castle* India — dubbing vs subs-only |
| `data/evidence/india_anime_evidence.json` | 18 curated, cited, labelled evidence items (retrieved 2026-10-24) |
| `schemas/` | JSON Schema v1.0 for input & output (authoritative validators are in code) |
| `scripts/run_experiment.py` | CLI: run an experiment, emit JSON + judge-readable markdown summary |
| `tests/` | 65 tests: contract errors, reproducibility, paired monotonicity, WOM ablation, output labelling + 22 greenlight tests (parser, tensor invariants, quant coherence, determinism) |
| `results/` | Actual outputs of the shipped experiment (JSON + markdown) |
| `docs/` | Deep-dive documentation (below) |

## Bun runtime — TypeScript port, API server, live dashboard

The sakura-abm engine has a **line-faithful TypeScript port** running natively on Bun —
same seeds, same RNG stream, same numbers (verified: 15 bun tests / 1,117 assertions,
including bit-exact MT19937 parity with `python.random` and the identical config hash).

```bash
bun install                      # no-op (zero npm dependencies)
bun test src/                    # 15 tests: parity, monotonicity, reproducibility, failure envelopes
bun run dev                      # http://localhost:8787 — dashboard + live API
bun run sim:cli -- --summary     # run the shipped experiment from the CLI
```

| Endpoint | What it does |
|---|---|
| `GET /` | the dot-matrix dashboard from `public/` (self-verifies against the live engine) |
| `GET /api/v1/ci` | competitive-intelligence battle map data (10 vendors · 45 repos · 12 risks · demo script) |
| `GET /api/v1/personas` | 40-agent roster (head-line seed): draws, R5 states base vs dub, grounding |
| `GET /api/v1/memo` | decision memo: 3 recommendations + named dissent + uncertainty, all cited |
| `GET /api/v1/report` | 10-section market-entry report, kind-tagged, export-ready |
| `GET /api/v1/status` | lane statuses (ok/blocked/failed per CI risks), missing creds, backend contract |
| `POST /api/v1/analyze` | `{title}` → same audience model, new IP, fresh paired-seed run |
| `GET /api/v1/pipeline/catalog` / `/search?q=` | the real python pipeline's AniList catalog (1,352 titles) + autocomplete |
| `GET /api/v1/pipeline/analyze?title=` | **the real backend**: data aggregation → signals → scoring → cultural compatibility → rupee localization economics → hub demand map → bilingual briefings (persistent python worker over stdio) |
| `POST /api/v1/greenlight` | **concept terminal**: `{concept}` (script / character design / any Japanese-media pitch) → parse → 1.3k-title catalog tensor kNN comparables → real-pipeline structural score → cohort LOO calibration → 20k-path antithetic Monte Carlo → VaR/CVaR/Sharpe/Kelly → 32-state demand map |
| `GET /api/v1/greenlight/presets` | sample concepts + the P0→P4 roadmap payload |
| `POST /api/v1/run-params` | live lab run: `{dub_lift, word_of_mouth_boost, announcement_boost, seeds, title}` → envelope + per-seed paired deltas |
| `GET /api/v1/sweep` | sensitivity sweep: `?param=dub_lift&from=1&to=2.2&steps=7` → robustness curve, every point a full paired run |
| `GET /api/v1/health` | engine + bun status |
| `GET /api/v1/run-example` | runs the shipped experiment **live in bun** |
| `POST /api/v1/run` | POST any experiment config → full labelled result envelope |

When served by bun, the dashboard's RUN RECORD shows `LIVE RUN · BUN  bun x.y.z · N ms · hash ✓ · numbers ✓` —
the browser re-runs the whole model through bun on every page load and checks it matches the
embedded numbers. Opened as a plain file, it falls back to the embedded (identical) data.

| Path | Purpose |
|---|---|
| `src/engine/mt19937.ts` | bit-exact CPython Mersenne Twister (init_by_array, genrand_res53, _randbelow) |
| `src/engine/engine.ts` | sakura-abm port: BA graph, population draw, fixed-slot round loop |
| `src/engine/{compare,output,validate}.ts` | paired comparison, output contract, error codes |
| `src/run_simulation.ts` | `runSimulation(config) -> envelope` (dict-in/dict-out, never throws) |
| `src/server.ts` | Bun.serve dashboard + API · `src/cli.ts` CLI |
| `tests/fixtures/` | python-generated parity fixtures (`parity:regen` regenerates) |

## p14 Greenlight — the concept terminal (script → India verdict)

The only pane where you bring something that *doesn't exist yet*. Paste a script excerpt,
a character design, a logline — any Japanese-media pitch (anime, manga, light novel,
visual novel, game, live-action, tokusatsu; kanji/kana/romaji terms parse natively) —
and the concept is scored through the same machinery that scores real catalog titles:

```
concept text ─ConceptParser─▶ genres + tags + format + demographics + 日本語 receipts
                                   │
live catalog (1.3k titles) ──▶ CatalogTensor 1365×205 float32 (India-affinity weighted,
                                   │  norms precomputed, C-contiguous)
                                   ▼
                    cosine similarity = ONE BLAS matvec → top-10 comparables
                                   │
              ┌────────────────────┴───────────────────┐
              ▼                                        ▼
 real pipeline on the concept            real pipeline on each comparable
 (meta_override → cultural fit,          (cached → cohort score distribution)
  CBFC, rupee economics, two-pass)
              └────────────────────┬───────────────────┘
                                   ▼
        cohort leave-one-out calibration (empirical-Bayes shrinkage λ,
        blend weight fitted per-concept on the cohort's own LOO error)
                                   ▼
        QUANT: 20,000-path antithetic Monte Carlo (normal + Student-t₄ mixture)
        → E/σ, VaR₅, CVaR₅, P(grade), Sharpe (rf 6.5% India G-sec), Kelly f*,
        P(profit), 4-plan localization frontier
                                   ▼
        32-state India demand model (census 2011 + 2024 internet/age estimates,
        per-state dub-language fit) + live AniList trending cross-match
```

**Why the blend:** a brand-new concept has zero popularity/wiki/trends signals, so its
raw pipeline score is structurally floored (by design — the pipeline refuses to invent
demand data). The greenlight verdict therefore blends two estimators: the *structural*
score (what the concept's content earns: cultural fit, CBFC, economics) and a
*comparable-cohort* kNN estimate (similarity-weighted pipeline scores of its ten nearest
catalog neighbours — i.e. **the scores the pipeline yields for real anime like this**).
Both the blend weight and a shrinkage factor are fitted on the cohort's own
leave-one-out error, so the confidence is empirical, not asserted.

**Quant-finance layer:** score uncertainty is propagated, not hidden — antithetic
variates halve sampler variance, a Student-t₄ mixture adds fat tails, and the
investment view runs a two-regime ROI model (launch vs niche outcome per path) across
all four localization plans, reporting Sharpe, Kelly f*, P(profit) and ROI VaR₅ so a
niche concept honestly shows five-language dubbing as a negative-Sharpe bet.

**Determinism & caching:** MC seeded at 42 (same concept → same verdict, test-pinned);
comparable scores cached per title, verdicts cached per concept, the catalog tensor
built once per worker boot (~0.5 s); a data refresh rebuilds both without a restart.

**Roadmap** (also rendered live in the pane, mapped to the repos already on disk):
- **P1 — semantic comparables:** sentence-transformers embeddings of real synopses
  (clone present) + indic_nlp_library/IndicTrans2 for Hinglish/Devanagari input
- **P2 — causal uplift:** EconML/dowhy causal estimate of dub-lift on comparable
  cohorts replacing the heuristic 1.55/1.85/2.2 reach multipliers; AIF360 fairness
  audit of the state demand model
- **P3 — forecasting + conformal gates:** darts/prophet state-demand forecasts,
  MAPIE conformal intervals published with every score, alibi-detect drift monitoring
  on the tensor
- **P4 — swarm validation + live evidence:** OASIS-style agent swarm reacts to the
  concept's pilot script; Agent-Reach retrieves live Reddit/YouTube comparable
  evidence; dgraph IP-similarity knowledge graph at scale

Run it: `bun run dev` → http://localhost:8787/#/greenlight — or
`SAKURASCORE_GREENLIGHT_OFFLINE=1 python3 scripts/backend/greenlight.py --selftest`.

## p07 Battle Map + p08 Demo Ops (competitive intelligence)

The dashboard ships a full CI command center built from `data/ci/*.csv` (sakurascore-ci
workspace, every row source-checked 2026-10-24): an 8-player × 15-dimension competitor
matrix with epistemic status chips (`VERIFIED` / `CLAIMED` / `VERIFIED-ABSENT` / `UNKNOWN`),
commercial comparables with published pricing ($8.9k–12.5k+/yr WTP), a 45-repo GitHub-API
landscape with P0–P3 calls, the 12-risk register, the A1–A10 24h build plan, the
three-minute demo script (money moment highlighted), and the OPEN LANE callout: no public
product combines India-anime evidence + per-claim provenance + multi-agent simulation +
quantified scenario A/B. Served data comes from bun (`/api/v1/ci`); the same JSON is
embedded for offline `file://` use.

## Deployment — GitHub (private) + Vercel (production)

**Live:** https://sakurascore-india.vercel.app — the full stack runs serverless:

- `public/index.html` — the dashboard (static, works offline for pages 01–09)
- `api/v1/[[...route]].ts` — **Node function** running the bit-exact TS engine
  (sim lab, personas, memo, report, status, sweeps — same `src/router.ts` as the
  local bun server; the shipped config hash verifies green in production)
- `api/py/index.py` — **Python function** running the real pipeline + greenlight
  engines (numpy + pandas via pyproject/uv), routed by rewrites from
  `/api/v1/pipeline/*` and `/api/v1/greenlight*`
- `api/_backend/` — a 9.8 MB serverless bundle of the backend source + processed
  CSVs, built by `scripts/prepare-vercel.sh` (the 6.4 G external clones and raw
  pulls stay out; git ignores the bundle, vercel ships it)

```bash
git clone https://github.com/Ehsas317/sakurascore-simulation && cd sakurascore-simulation
./scripts/prepare-vercel.sh        # build api/_backend from backend 111 source
vercel deploy --prod               # or: vercel --prod
bun run dev                        # local: full stack incl. the stdio python worker
```

The v2 polish pass (24 Oct 2026): Greenlight moved to #02 · the IP row is live
(pick any title → pipeline + abm) · EN/日本語 chrome toggle (header) · dynamic
provenance bar per page · sim-lab auto-run on slider release · diffusion speed
control (0.5–4×), loop mode and agent hover tooltips · personas sort/replay/
summary strip · greenlight file upload (txt/md/fountain + drag-drop) · per-page
explainers · 14 e2e browser tests, 68 python tests, 22 bun parity tests.

## Documentation

| Doc | Contents |
|---|---|
| [`docs/MIROFISH_ARCHITECTURE.md`](docs/MIROFISH_ARCHITECTURE.md) | Full reverse-engineering of MiroFish @ `7657031` (commit pinned): architecture diagram, input pipeline, agent generation, simulation loop, reporting, OASIS relationship, verified capabilities vs limitations — with file::function citations |
| [`docs/REPOSITORY_EVALUATION.md`](docs/REPOSITORY_EVALUATION.md) | MiroFish (reference only) vs OASIS (defer; python<3.12 + no keyless mode + no seeding) vs Agent-Reach (adapt) vs **sakura-abm (selected)** — evidence-based decision |
| [`docs/RESEARCH_SOURCE_MAP.md`](docs/RESEARCH_SOURCE_MAP.md) | Every source used/considered: access method, auth, terms posture, quality; data-access policy; planned Agent-Reach pipeline |
| [`docs/SIMULATION_METHODOLOGY.md`](docs/SIMULATION_METHODOLOGY.md) | Exact behavioural equations, RNG protocol, paired-seed design + monotonicity invariant, assumption register |
| [`docs/INTEGRATION_GUIDE.md`](docs/INTEGRATION_GUIDE.md) | Team contract: quickstart, mandatory/optional fields, output blocks, error codes, what's safe to show judges |
| [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) | All limitations + sensitivity-probing recipes (also embedded in every result) |

## Quickstart

```bash
python scripts/run_experiment.py     # ~100ms, no installs, no API keys
python -m pytest tests/ -q --ignore=tests/e2e.py  # 65 tests, <2s
```

```python
from sakurascore_sim import run_simulation
result = run_simulation(config)      # dict-in/dict-out; failures are structured, not raised
```

## The shipped experiment (headline, all SIMULATED)

*Question: does regional-language dubbing change simulated engagement?*
*Demon Slayer: Infinity Castle*, India audience model, 40 agents × 6 rounds,
5 paired seeds (42–46), identical marketing, 18 evidence sources:

| Metric (simulated) | Baseline JP+EN (counterfactual) | +HI/TA/TE dubs | Paired Δ (mean ± std) |
|---|---|---|---|
| Engagement rate | 49.0% | 60.5% | **+11.5pp ± 5.1pp (positive in 5/5 seeds)** |
| Reach rate | 68.5% | 74.0% | +5.5pp ± 3.7pp |
| Shares / discussions | 17.0 / 17.2 | 29.6 / 29.6 | +81.9% / +81.6% relative |

Mechanism sanity: lift concentrated in `regional-language-first` (+28.0pp) and
`film-event-audiences` (+15.0pp); exactly **zero** for `manga-first-readers`
(already high EN/JA fit). Full attribution in `results/*_output.json`
(`comparisons[].drivers`, `assumptions[]`).

**These are simulated outcomes of stated hypotheses — not forecasts.** See `docs/LIMITATIONS.md`.

## Why a custom engine (one paragraph)

MiroFish (AGPL-3.0) requires Zep Cloud + LLM credentials and is unseeded/non-deterministic — paired A/B scenarios are undefendable on it. OASIS (Apache-2.0) pins `python <3.12` (we run 3.12.15), has no keyless LLM mode and no seeding; custom actions need a 3-file fork. Agent-Reach (MIT) is excellent for *evidence retrieval* later, but the P0 needed a simulation core. `sakura-abm` trades LLM-grade emergent behaviour (documented) for determinism, paired-seed statistics, India-native segments and zero operational risk. Full analysis: `docs/REPOSITORY_EVALUATION.md`.

## Team contract (short version)

- Needs from you: a JSON config (IP + segments + scenarios + sim params). Mandatory/optional fields: `docs/INTEGRATION_GUIDE.md` §2.
- Returns: JSON result (status/ scenarios/ comparisons/ assumptions/ source_references/ limitations/ run_metadata). Failures: `simulation_status:"failed"` + error codes — never exceptions in default mode.
- Integration fixtures: the shipped config + evidence dataset are the sample dataset agreed for pre-real-data integration.
- Simulation results stay **separate** from opportunity scores unless we explicitly agree on a fusion contract.
