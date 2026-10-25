# Repository Evaluation & Engine Decision

**SakuraScore India — Simulation & Research Subsystem**

- Commits inspected (isolated read-only checkouts under `/home/z/my-project/upstream/`):
  - **MiroFish** `7657031ac01184afe2cb220f5ee3545573b5e843` (2026-10-02) — AGPL-3.0
  - **OASIS** (`camel-ai/oasis`) `8607dba82d73f7bfc371b3beafe57cc844687be2` (2026-10-19) — Apache-2.0
  - **Agent-Reach** (`Panniantong/Agent-Reach`) `beabda7486e9a666360b18cdb5c0e759c2c4d20f` (2026-10-23, v1.6.0) — MIT
- Environment facts that drive the decision: **Python 3.12.15** runtime; **no LLM API keys** available (no `OPENAI_API_KEY` or equivalents); 24-hour hackathon deadline.
- Full evidence dossiers: `/home/z/my-project/agent-reports/task-3-{a,b,c}-*.md`.

---

## 1. Classification summary

| Repository | Classification | One-line rationale |
|---|---|---|
| MiroFish | **Reference only** | AGPL-3.0 + mandatory Zep Cloud SaaS + no determinism + Twitter/Reddit-only verbs; excellent architecture patterns worth copying |
| OASIS | **Defer** (adapter path documented) | Apache-2.0 is fine, but pinned `python <3.12` (our runtime is 3.12.15), no keyless LLM mode, no seeding, custom actions need a 3-file fork |
| Agent-Reach | **Adapt** (later, not needed for P0) | MIT, read-only, refuse-don't-bypass posture, credential-free channels; ideal future evidence pipeline; no caching layer so we persist provenance ourselves |
| sakura-abm (ours) | **Integrate now** | Zero dependencies, zero credentials, fully seeded, paired-design, India-segment-native; honestly labelled a simplified scenario model |

## 2. Option analysis (Part 4 of the project brief)

### Option A — MiroFish integration: REJECTED for P0 (evidence)

*Advantages claimed:* existing workflow, agent generation, orchestration, reporting — all verified present.

*Decisive concerns (verified in source):*

1. **Licence:** AGPL-3.0. Any copied/vendored code forces share-alike on SakuraScore; network-service clause (§13) applies to modified deployments. Calling it as a separate service is the safer boundary but needs organiser sign-off — not a 24-hour conversation.
2. **Credentials:** `ZEP_API_KEY` mandatory (`backend/app/config.py:69-72`), `ZEP_API_URL` explicitly rejected — no self-hosted escape hatch. Plus `LLM_API_KEY` with real budget (per-agent-per-round LLM calls × 2 platforms).
3. **Determinism:** zero `random.seed` in `backend/` (grep-verified); unseeded activation sampling (`run_parallel_simulation.py:1040-1090`); LLM sampling at temp 0.7; no variance machinery. **Our core deliverable — a defensible paired dub-vs-baseline comparison — is impossible on single unseeded runs.**
4. **Action space:** 6 Twitter + 13 Reddit verbs; SakuraScore verbs (discover / view_info / express_interest / share / respond-to-language-scenario) do not exist and would require forking OASIS.
5. **Localisation:** activity schedules and prompts hardcode Chinese habits ("考虑中国人作息"); persona fallbacks hardcode `country:"中国"`.
6. **Dead control surface:** `stance`, `sentiment_bias`, `influence_weight` are generated but never consumed at runtime — scenarios could only be encoded indirectly in seed documents.

### Option B — Independent OASIS integration: DEFERRED (evidence)

*What OASIS actually is (verified):* a client-server social-media sandbox. `SocialAgent` subclasses camel-ai's `ChatAgent` (`oasis/social_agent/agent.py:55`); actions are 29 LLM tool-stubs on a `SocialAction` object (`oasis/social_agent/agent_action.py:28-61`); a single `Platform` server persists to SQLite (16 tables) and mediates visibility via recommenders (`oasis/social_platform/recsys.py` — torch/sentence-transformers imports at lines 25–29). A timestep is `env.step()` with `asyncio.gather` concurrency (`oasis/environment/env.py:136-198`).

*Decisive concerns (verified):*

1. **Python constraint:** `pyproject.toml:25` = `python = ">=3.10.0,<3.12"`. pip refuses install on our 3.12.15 runtime. Locked dep `unstructured==0.13.7` is also `<3.12`. Fixable only with a 3.10/3.11 venv.
2. **No keyless mode:** no mock/synthetic LLM backend exists (`oasis/testing/` is a DB pretty-printer); CI itself injects `OPENAI_API_KEY` for the entire pytest run (`.github/workflows/python-app.yml:35-38`). With zero API keys in our environment, no experiment can run.
3. **No seeding:** zero hits for `random.seed|np.random.seed|torch.manual_seed|default_rng` repo-wide; `model_random_seed` appears only in docstrings. Reproducibility = action journaling (`trace` table), not re-execution.
4. **Custom actions need a coordinated 3-file fork** (`typing.py:17-49`, `platform.py:147-158`, `agent_action.py:28-61`) — no plugin registry.
5. **Weight:** importing `platform.py` pulls torch + sentence-transformers (~3–5 GB CPU wheels).

*What would unlock it:* Python 3.10/3.11 venv + an OpenAI-compatible endpoint (key or self-hosted vLLM, cf. `examples/twitter_simulation_vllm.py:27-45`). A thin `OasisBackend` behind runtime probes (`find_spec("oasis")`, version check, endpoint detection) is the documented adapter path — deliberately **not stubbed** in our repo (no dead code). Honest effort estimate if unlocked: 7–15 h to a working scenario, leaving no slack.

### Option C — Lightweight custom simulation: **SELECTED** (with honest labelling)

Chosen because it is the only option that satisfies all P0 constraints *simultaneously*: runs on the available Python 3.12 runtime, needs zero credentials, is fully seeded/reproducible, and expresses SakuraScore's own verbs natively.

**What it is:** `sakura-abm` — a compact stochastic-threshold agent model over a preferential-attachment social graph, with segment-level hypotheses and explicit, named assumptions. Full specification: `SIMULATION_METHODOLOGY.md`.

**What it is NOT (must be stated whenever results are shown):** it is NOT equivalent to OASIS/MiroFish LLM-agent simulations — no natural-language personas, no emergent discourse, no recommendation-algorithm dynamics. It answers a narrower question well: *under stated assumptions, how does a release-strategy variable shift engagement across audience segments, and how confident can we be in the direction of that shift?*

### Decision rationale in one table

| Requirement | MiroFish | OASIS | sakura-abm |
|---|---|---|---|
| Runs in our env (Py 3.12, no keys) | ✗ | ✗ | ✓ |
| Reproducible / seeded A/B | ✗ | ✗ | ✓ (paired seeds) |
| SakuraScore action verbs | ✗ | fork needed | ✓ native |
| Licence-clean for our repo | AGPL risk | Apache-2.0 ✓ | n/a (original) |
| India segment control | indirect | personas only | ✓ first-class |
| LLM-grade emergent behaviour | ✓ | ✓ | ✗ (documented) |
| Hackathon risk | high | high | low |

## 3. Agent-Reach evaluation (Part 5)

Verified from source (`agent_reach/`): 14 channels; credential-free = `web` (Exa hosted search + Jina reader, `channels/web.py`), `youtube` (yt-dlp search/read/subtitles), `github`, `v2ex`, bilibili public; login-required = reddit/twitter/xiaohongshu/etc.; unified JSON envelope with provenance fields (`runtime/result.py :: make_item` — `title/url/author/published_at/text/raw`); layered rate-limit handling with cooldowns (`runtime/dispatch.py :: run_action`); **read-only by construction, refuses anti-bot circumvention** (`web.py :: _is_antibot_page` raises on Cloudflare challenges; `result.py` hints say "Stop automation… Do not switch backends").

Caveats: no response caching (we must persist envelopes ourselves); the optional CloakBrowser substrate is a non-MIT binary licence — excluded; v1.6 changelog admits 28/40 actions passed acceptance (our channels are among the tested ones).

**Adaptation plan (post-hackathon):** fixed query list → `agent-reach <channel> <action>` subprocess → parse JSON envelope → respect `retry_after_seconds`, never retry `PLATFORM_BLOCKED` → write append-only JSONL with `{query, retrieved_at, tool_version, commit}` provenance → feed through our `evidence_loader` validation. Estimated ~150 lines. Not required for P0 because the curated dataset (`data/evidence/india_anime_evidence.json`) already provides a small, traceable, permitted evidence base.

## 4. Additional tools considered

| Candidate area | Decision | Rationale |
|---|---|---|
| networkx (graph lib) | **Reject** (already available but unused) | 30-line deterministic BA graph in stdlib keeps the zero-dependency guarantee |
| pydantic / jsonschema runtime validation | **Reject** for runtime | Hand-rolled validator gives precise error codes with zero deps; JSON Schema files shipped for tooling interop |
| LightRAG / GraphRAG | **Reject** for P0 | Our evidence set is small and curated; a knowledge graph adds setup cost with no P0 payoff (P2 idea) |
| Experiment tracking (MLflow/W&B) | **Defer** | `run_metadata` + `config_hash` covers hackathon-level reproducibility |
| YouTube Data API v3 | **Adapt planned** | Official, quota-limited path for engagement metadata when credentials exist (`source_registry.py`) |

## 5. Consequences for the implemented design

1. `src/sakurascore_sim/adapters/` contains only the implemented engine (`abm_engine.py`) registered in `ENGINES` — no empty stubs.
2. Unknown `engine` values (e.g. `"oasis"`) fail with code `ENGINE_UNAVAILABLE` and a pointer to this document.
3. Every engine constant is a named, documented assumption surfaced in results (`assumptions[]`) — the antidote to MiroFish/OASIS-style hidden dynamics.
4. Evidence flows into results as `source_references[]` with URL + date + quality + observed/inferred labels; simulation metrics are always labelled `simulated`.
