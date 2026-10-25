# MiroFish Reverse-Engineering Report

**SakuraScore India — Simulation & Research Subsystem (Task 3-a deliverable)**

- **Repository inspected:** https://github.com/666ghj/MiroFish — *"A Simple and Universal Swarm Intelligence Engine, Predicting Anything"*
- **Isolated checkout:** `/home/z/my-project/upstream/MiroFish` (read-only reference; not linked into our build)
- **Exact commit inspected:** `7657031ac01184afe2cb220f5ee3545573b5e843` (2026-10-02, "chore: update Star History (#832)")
- **Licence:** **GNU AGPL-3.0** (network-service clause §13 applies if code is copied or offered as a modified network service)
- **Method:** static source reading only. No upstream code executed, no dependencies installed. All claims below were verified against the checked-out source; secondary verification of load-bearing claims was done independently by the subsystem coordinator.
- **Full evidence dossier:** `/home/z/my-project/agent-reports/task-3-a-mirofish.md` (~3,900 words, line-level citations)

---

## 1. Executive summary

MiroFish is a **Flask + Vue 3 web product wrapped around the camel-ai OASIS library** (`camel-oasis==0.2.5`, pinned in `backend/requirements.txt` lines 22–23 — verified). It is *not* a fork or vendored copy of OASIS: the simulation loop lives in three CLI scripts under `backend/scripts/` that import `oasis` directly, while MiroFish's own code provides document→knowledge-graph preparation (via **Zep Cloud SaaS**), LLM-generated agent personas, subprocess orchestration, and an LLM-generated report pipeline.

For SakuraScore India the decisive findings are:

1. **Two mandatory external credentials** — `ZEP_API_KEY` (Zep Cloud only; self-hosting explicitly rejected at `backend/app/config.py:71-72`) and `LLM_API_KEY` (any OpenAI-compatible endpoint).
2. **Not deterministic** — zero `random.seed` usage in `backend/` (verified by grep); unseeded `random.uniform/random.sample/random.random` drive agent activation (`run_parallel_simulation.py:1040-1090`); LLM sampling at temperature 0.7; no run-to-run variance machinery anywhere. **A paired dub-vs-baseline comparison is therefore not defensible on MiroFish.**
3. **Action space is Twitter/Reddit-native** (6 Twitter + 13 Reddit actions) — it cannot express SakuraScore verbs like *discover / express_interest / respond-to-dub-availability* without forking OASIS itself.
4. The engine loop is cleanly invocable standalone (the runner scripts import no Flask), but everything that differentiates MiroFish (personas, config generation, reporting) is coupled to Zep Cloud and LLM spend.

Verdict for our subsystem: **Reference only** (architecture patterns + runner-loop reference), *not* an integration target within the 24-hour window. Details in `REPOSITORY_EVALUATION.md`.

---

## 2. System architecture (verified)

### 2.1 Stack

| Layer | Technology | Evidence |
|---|---|---|
| Backend | **Flask** (≥3.0), app factory | `backend/app/__init__.py :: create_app` registers blueprints `/api/graph`, `/api/simulation`, `/api/report`; entry `backend/run.py :: main` (port `FLASK_PORT`, default 5001) |
| Frontend | Vue 3 + Vite SPA (d3, vue-i18n, axios) | `frontend/package.json`; wizard steps `frontend/src/components/Step1GraphBuild.vue … Step5Interaction.vue` |
| Deployment | **Single** Docker container (`ghcr.io/666ghj/mirofish:latest`, ports 3000+5001) | `docker-compose.yml` — no DB/cache/queue services |
| Persistence | **File-based**: project JSON + extracted text (`backend/app/models/project.py :: ProjectManager`), `state.json`/`run_state.json`, per-platform **SQLite** DBs owned by OASIS (`twitter_simulation.db`, `reddit_simulation.db`), action JSONL (`backend/scripts/action_logger.py :: PlatformActionLogger`), reports under `backend/app/services/report_agent.py :: ReportManager.REPORTS_DIR` | verified |
| Task tracking | In-memory dict (lost on restart) | `backend/app/models/task.py :: TaskManager` |
| Knowledge graph | **Zep Cloud (SaaS)** via `zep-cloud==3.25.0` | `backend/requirements.txt:17`; client `backend/app/utils/zep.py :: get_zep_client` |

### 2.2 Architecture diagram

```
                       +---------------------------- single Docker container ---------------------------+
 Browser --HTTP 3000-->| Vue3 SPA --axios polling (1.5-30s)--> Flask :5001                              |
                       |                                        |                                       |
 user docs (pdf/md/txt)--> ProjectManager (files + JSON on disk)                                  |
                       |        | chunks 500/50            OntologyGenerator (LLM, temp 0.3)            |
                       |        v                                 |                                       |
                       |   GraphBuilderService ---batch API---> ZEP CLOUD (SaaS; ZEP_API_KEY)          |
                       |   (graph.create, set_ontology,          * entity/relationship extraction      |
                       |    add_text_batches)                      happens INSIDE Zep                 |
                       |        ^  graph.search (read)                                                  |
                       |        |                                                                       |
                       |   SimulationManager.prepare_simulation:                                        |
                       |     ZepEntityReader.filter_defined_entities -> one agent per entity            |
                       |     OasisProfileGenerator -> reddit_profiles.json / twitter_profiles.csv       |
                       |     SimulationConfigGenerator -> simulation_config.json                        |
                       |        |                                                                       |
                       |   SimulationRunner.start_simulation ---subprocess--->                           |
                       |        backend/scripts/run_{twitter,reddit,parallel}_simulation.py             |
                       |          imports oasis (camel-oasis==0.2.5) + camel.models.ModelFactory        |
                       |          oasis.make(agent_graph, platform, database_path=..., semaphore=30)    |
                       |          round 0: ManualAction(CREATE_POST) injection of initial_posts         |
                       |          loop: stochastic activation -> {agent: LLMAction()} -> env.step       |
                       |        <sim_dir>/{platform}_simulation.db (SQLite ground truth)                |
                       |        <sim_dir>/{platform}/actions.jsonl (action_logger)                      |
                       |        IPC files ipc_commands/ <-> ipc_responses/ (interview, close_env)       |
                       |   monitor thread tails actions.jsonl -> run_state.json -> GET /run-status      |
                       |   ReportAgent (ReAct; tools: insight_forge / panorama_search / quick_search    |
                       |    [Zep reads] + interview_agents [live IPC]) -> uploads/reports/<id>/         |
                       +--------------------------------------------------------------------------------+
```

### 2.3 LLM connectivity (two distinct paths)

1. **OpenAI SDK path** — ontology, persona generation, simulation-config generation, report agent. Env: `LLM_API_KEY`, `LLM_BASE_URL` (default `https://api.openai.com/v1`), `LLM_MODEL_NAME` (default `gpt-4o-mini`); `.env.example` recommends Alibaba DashScope `qwen-plus`. Optional `LLM_BOOST_*` trio for the second parallel platform run (`backend/app/config.py:27-30`).
2. **camel-ai path (the agents)** — runner scripts copy `LLM_*` into `OPENAI_API_KEY`/`OPENAI_API_BASE_URL` and call `camel.models.ModelFactory.create(ModelPlatformType.OPENAI, ...)` (`backend/scripts/run_parallel_simulation.py :: create_model`, lines 984–1037).

---

## 3. Input pipeline (A)

1. **Upload + ontology** — `POST /api/graph/ontology/generate` → `backend/app/api/graph.py :: generate_ontology` (line 265). Text extracted by `backend/app/utils/file_parser.py :: FileParser.extract_text` (PyMuPDF for PDF); ontology generated by LLM (`backend/app/services/ontology_generator.py`, `ONTOLOGY_SYSTEM_PROMPT` line 48, temperature 0.3). The user's natural-language prediction question (`simulation_requirement`) is captured here.
2. **Graph build** — `POST /api/graph/build` → `graph.py :: build_graph` (line 448) → `backend/app/services/graph_builder.py :: GraphBuilderService.build_graph_async`: chunk 500/50, `client.graph.create`, `set_ontology`, `add_text_batches` (batch 350). **Entity/relationship extraction is performed inside Zep Cloud**, not in MiroFish code.
3. **Create simulation** — `POST /api/simulation/create` → `backend/app/api/simulation.py :: create_simulation` (line 195) → `<sim_dir>/state.json`.
4. **Prepare agent world model** — `POST /api/simulation/prepare` → `backend/app/services/simulation_manager.py :: SimulationManager.prepare_simulation` (line 244): filter Zep entities (`backend/app/services/zep_entity_reader.py :: ZepEntityReader.filter_defined_entities`), one OASIS agent per entity, and `backend/app/services/simulation_config_generator.py :: SimulationConfigGenerator.generate_config` (line 244) writes `simulation_config.json` (time config, per-agent activity configs, event config incl. `initial_posts`, hard-coded `PlatformConfig`s).

---

## 4. Agent generation (B)

| Aspect | Finding | Evidence |
|---|---|---|
| Agent schema | `OasisAgentProfile` dataclass: bio, persona (~2000 chars), karma/followers, age, gender, mbti, country, profession, topics, provenance | `backend/app/services/oasis_profile_generator.py :: OasisAgentProfile` (lines 80–202); platform serializers `to_reddit_format()` / `to_twitter_format()` |
| Population size | **One agent per filtered Zep entity** — no default count in code | `simulation_manager.py` line 305 (`filtered.filtered_count`) |
| Persona generation | LLM JSON generation, temp 0.7 → 0.5 → 0.3 retries, JSON repair, rule-based fallback with hardcoded archetypes; **Chinese system prompt** + locale suffix | `_generate_profile_with_llm` (line 540), `_build_individual_persona_prompt` (line 721), fallback `_generate_profile_rule_based` (line 818) |
| Behaviour config | `AgentActivityConfig`: `activity_level`, `posts_per_hour`, `active_hours`, `response_delay_*`, `sentiment_bias`, `stance`, `influence_weight` — LLM-generated per agent (batches of 15) | `backend/app/services/simulation_config_generator.py` lines 53–81, `_generate_agent_configs_batch` (line 815) |
| **Dead parameters** | **Only `activity_level` and `active_hours` are consumed at runtime.** `stance`, `sentiment_bias`, `influence_weight`, `posts_per_hour`, `comments_per_hour` are written to config but never read by any runner script (grep-verified). Opinion steering via config is impossible. | grep over `backend/scripts/` |
| Segments | No first-class demographic-segment API; "segments" = implicit Zep entity types; initial posts assigned by type matching | `SimulationConfigGenerator._assign_initial_post_agents` (line 730) |
| Programmatic control | Good: engine consumes flat files, so hand-written profiles + config can bypass Zep/LLM prep entirely | §7 of the full dossier |

---

## 5. Simulation engine (C/D) — the decisive section

**The engine is a CLI script, not a library.** `run_parallel_simulation.py` / `run_twitter_simulation.py` / `run_reddit_simulation.py` import `oasis` and `camel.models` plus a local `action_logger` — **no `app.*`/Flask imports** (import block lines 67–174).

Environment construction (`run_parallel_simulation.py :: run_twitter_simulation` line 1101 / `run_reddit_simulation` line 1293):

1. `create_model(...)` → camel `ModelFactory.create(ModelPlatformType.OPENAI, ...)`
2. `generate_twitter_agent_graph(...)` / `generate_reddit_agent_graph(...)` — OASIS constructors from the profile files
3. `oasis.make(agent_graph, platform=oasis.DefaultPlatformType.TWITTER/REDDIT, database_path=<platform>_simulation.db, semaphore=30)` (lines 1155–1160 / 1346–1351)
4. `await env.reset()`

**Round loop** (lines 1228–1279 / 1427–1478):

1. Round 0 "God view": `config.event_config.initial_posts` injected via `ManualAction(ActionType.CREATE_POST, ...)` (lines 1172–1207 / 1362–1406). `scheduled_events` exists in `EventConfig` (line 121) but is parsed empty (line 725) and **never consumed — mid-run scenario injection is NOT implemented.**
2. Simulated clock: `round_num * minutes_per_round`.
3. **Stochastic activation** — `get_active_agents_for_round` (lines 1040–1090): `target_count = int(random.uniform(min, max) * peak_multiplier)`; each agent passes `random.random() < activity_level` if its `active_hours` contain the current hour; `random.sample` selects the subset. **Unseeded.**
4. `{agent: LLMAction()}` → `await env.step(actions)` — every decision is delegated to OASIS/camel LLM agents.
5. `fetch_new_actions_from_db` (line 657) reads new SQLite `trace` rows by rowid cursor, filters `refresh/sign_up`, enriches context, appends to `actions.jsonl`.

**Supported actions (actual code lists):**

- Twitter (`TWITTER_ACTIONS`, lines 178–185): `CREATE_POST, LIKE_POST, REPOST, FOLLOW, DO_NOTHING, QUOTE_POST`
- Reddit (`REDDIT_ACTIONS`, lines 188–202): `LIKE_POST, DISLIKE_POST, CREATE_POST, CREATE_COMMENT, LIKE_COMMENT, DISLIKE_COMMENT, SEARCH_POSTS, SEARCH_USER, TREND, REFRESH, DO_NOTHING, FOLLOW, MUTE`
- `INTERVIEW`: manual IPC action only (filesystem `ipc_commands/` ↔ `ipc_responses/`), post-loop while the env stays alive (`ParallelIPCHandler.process_commands`, lines 1596–1633)

Interaction is **platform-mediated only** (posts/comments/likes through OASIS SQLite); no direct agent-to-agent messaging. MiroFish's own spread knobs (`PlatformConfig.viral_threshold`, `echo_chamber_strength`, recsys weights, lines 130–144) are generated but **never read** — diffusion dynamics live inside the OASIS dependency.

---

## 6. Reporting (E)

- `POST /api/report/generate` → `backend/app/services/report_agent.py :: ReportAgent.generate_report` (line 1576): LLM outline plan (`PLAN_SYSTEM_PROMPT`, line 552 — Chinese "future-prediction" persona), then per-section ReAct loops (`_generate_section_react`, line 1260; max 5 tool calls, 2 reflection rounds, temp 0.5).
- Tools (`backend/app/services/zep_tools.py`): `insight_forge` (line 943), `panorama_search` (line 1143), `quick_search` (line 1235) — all Zep graph reads — plus `interview_agents` (line 1270) driving live IPC interviews.
- Outputs: `outline.json`, per-section markdown/JSON, progress JSON, `agent_log.jsonl`, full report JSON+markdown under `backend/uploads/reports/<id>/`. **No backend charts**; frontend d3 graph panel only (`frontend/src/components/GraphPanel.vue`).
- Delivery: **HTTP polling only** (frontend `setInterval` 1.5–30s; no WebSocket/SSE in the SPA).
- **Uncertainty/variability is not measured anywhere.** One simulation_id = one run; report caching reuses completed reports unless `force_regenerate` (`backend/app/api/report.py` lines 214–231).

---

## 7. Dependencies, credentials, runtime

- **Python** ≥3.11,<3.13; `backend/requirements.txt`: `flask>=3.0.0`, `openai>=1.0.0`, `zep-cloud==3.25.0`, **`camel-oasis==0.2.5`**, **`camel-ai==0.2.78`**, `PyMuPDF`, `pydantic>=2`. `uv.lock` is authoritative.
- **Mandatory env:** `LLM_API_KEY` (+ optional `LLM_BASE_URL`/`LLM_MODEL_NAME`), `ZEP_API_KEY`. `Config.validate` (`backend/app/config.py:63-76`) **rejects `ZEP_API_URL`** — "MiroFish 仅连接 Zep Cloud" (self-hosted Zep impossible).
- **Minimal programmatic invocation (verified feasible):** `python backend/scripts/run_reddit_simulation.py --config <dir>/simulation_config.json --no-wait` with (1) hand-written OASIS-format profiles, (2) `simulation_config.json` (`time_config`, `agent_configs` with `activity_level`/`active_hours`, optional `event_config.initial_posts`), (3) `LLM_API_KEY`. No Flask, no Zep for the loop itself — but per-agent LLM cost scales as `active_agents × rounds × platforms`, and there is **no way to run without an LLM endpoint**.
- **Preparation services are app-coupled:** `OasisProfileGenerator` / `SimulationConfigGenerator` import Flask transitively (`app/utils/locale.py`) and need Zep for persona enrichment.

---

## 8. OASIS relationship (verified)

**MiroFish is a downstream consumer of camel-ai OASIS — a pinned pip dependency, not a fork.**
`backend/requirements.txt` lines 20–23 (`camel-oasis==0.2.5`); all runner scripts `import oasis` (lines 160–174); no vendored `oasis/` source tree exists. MiroFish's contributions around OASIS: Zep→profile generation, LLM config generation, subprocess lifecycle + JSONL monitoring, IPC interviews, Zep graph memory write-back (`backend/app/services/zep_graph_memory_updater.py :: ZepGraphMemoryUpdater`), ReAct report agent. The README's "thousands of agents" is a marketing phrase; scale is bounded by Zep entity count and LLM budget (`semaphore=30`).

---

## 9. Verified capabilities vs limitations

| Capability | Verified? | Evidence | SakuraScore note |
|---|---|---|---|
| Document → knowledge graph | Yes | `graph.py :: generate_ontology`; `graph_builder.py :: add_text_batches` | Extraction happens in Zep Cloud |
| 1 agent per entity | Yes | `simulation_manager.py :: prepare_simulation` | No sampling/segment quotas |
| LLM persona generation (+fallback) | Yes | `oasis_profile_generator.py` lines 540/818 | Chinese-first prompts; needs LLM |
| Stance/sentiment steering at runtime | **No** | fields defined (lines 53–81), unused by runners | Dead parameters |
| Round-0 event injection | Yes | `run_parallel_simulation.py` lines 1172–1207 | Only mechanism to seed a scenario |
| Mid-run scenario injection | **No** | `scheduled_events` never consumed | Would need OASIS fork |
| Action space | Yes | lines 178–202 | Twitter/Reddit verbs only — no SakuraScore verbs |
| Determinism / reproducibility | **No** | grep: zero `random.seed` in `backend/`; temp-0.7 sampling | Paired A/B comparisons confounded |
| Variance/uncertainty measurement | **No** | single run per simulation_id | Would need custom orchestration |
| Standalone engine invocation | Yes | runner scripts import no `app.*` | Best reuse seam |
| India-ready defaults | **No** | `TimeSimulationConfig` docstring "基于中国人作息习惯"; peak hours 19–22; fallback `country:"中国"` | Needs code/prompt edits |
| Licence compatibility | — | AGPL-3.0 `LICENSE` | Share-alike obligations on any copied code |

## 10. SakuraScore integration assessment

- **(a) Engine-as-library:** feasible via the runner CLIs with hand-written profiles, but the LLM bill and non-determinism remain, and SakuraScore verbs don't exist in the action space.
- **(b) Drive via API + docker:** workable end-to-end (upload seed docs → build graph → prepare → start → poll → report) but requires Zep Cloud + LLM budget; two scenario runs = two full projects with no paired/seeded comparison support; first-run latency (ontology → ingestion → prepare) can be tens of minutes.
- **(c) Most reusable assets:** the three runner scripts + `action_logger.py` (the actual loop); `OasisAgentProfile` serializers (as an OASIS profile schema reference); config dataclasses as schema reference. Least reusable: `report_agent.py` (Zep+Chinese-coupled), `graph_builder.py` (Zep-only), `simulation_runner.py` (app lifecycle).
- **(d) 24h verdict: MEDIUM** overall — SMALL for one UI demo run with pre-written seed docs; LARGE for a rigorous, reproducible, India-focused SakuraScore subsystem. Non-determinism alone disqualifies it for our paired dub-vs-baseline experiment.

**Bottom line:** reuse the *pattern* (OASIS dependency, runner-script separation, JSONL action logs, paired-file config) — not the MiroFish application.
