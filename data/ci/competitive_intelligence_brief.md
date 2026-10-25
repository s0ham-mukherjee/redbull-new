# SakuraScore India — Competitive Intelligence & Hackathon Strategy Brief

**Prepared:** 2026-10-24 (Asia/Shanghai) · **Analyst:** Qwen (CI/product strategy mode)
**Evidence standard:** every material claim carries a source URL and the date checked. Entries are tagged:
`[VERIFIED]` (inspected source), `[CLAIMED]` (vendor/team's own claim, not independently reproduced), `[UNKNOWN]`, `[SPECULATION]`.

> ⚠️ **Two honest caveats before anything else**
> 1. **The exact hackathon was not identified.** The team did not provide an event name, link, or participant list. Per the brief's own rule, **no competing teams are named or guessed**. Section B lists *publicly comparable* projects/products, clearly separated from "verified competitors in your event" (of which there are currently **zero — unknown event**).
> 2. **"100% accuracy" is not achievable** for competitive intelligence. What is guaranteed instead: no fabricated entities, every row sourced or marked unknown, and all SakuraScore capabilities marked `[CLAIMED-UNVERIFIED]` because **no SakuraScore code, repo, or demo was available in the workspace** (checked `/home/user` on 2026-10-24 — empty).

---

## A. Executive summary

1. **The idea-space is proven but crowded.** LLM-persona audience simulation is a fast-maturing commercial category: a vendor roundup dated Oct 2026 profiles **17 synthetic market-research tools**, several with *published validation benchmarks* (Aaru: Pearson 0.970 across answer shares over 186 studies; Artificial Societies: 86% distribution accuracy; Evidenza: 88% similarity; Simile builds on Stanford's 1,000-person agent-interview study, arXiv:2411.10109). [VERIFIED — source: getminds.ai roundup, 2026-10-16; note this blog is vendor-authored (Minds) and labels itself as such; individual vendor figures were not re-verified against each vendor.] Judges and investors have increasingly seen "AI personas answer your survey." **Generic persona simulation alone is no longer a differentiator.**
2. **Hackathon projects already demo this pattern well.** Three public Devpost projects are directly comparable in *form*: **Tunnel** (162–200+ AI personas, 3D globe, voice conversations with personas, "zero to insight in 30 seconds"), **The Boardroom** (5 incentive-driven agents debate a product decision, dissent logged, staged for projector legibility), and **Agentropolis** (thousands of agents on a live 3D Toronto map, event injection, join-as-avatar). [VERIFIED — Devpost pages inspected 2026-10-24.] Lesson: the *visual theater* of simulation is established. SakuraScore must win on **credibility and evidence**, not spectacle.
3. **No public product found combining our exact four elements.** In this search, nothing was found that combines (a) India-specific entertainment/anime market evidence, (b) evidence provenance linked into (c) multi-agent audience simulation with (d) baseline-vs-intervention scenario comparison. That is the open lane. [VERIFIED absence *in this search*; SPECULATION about the market as a whole — absence of evidence is not proof none exists.]
4. **Our two reference repos are verified, healthy, and strategically informative:**
   - **Agent-Reach** — MIT, ~101.5k stars, pushed 2026-10-23 (one day before this report), v1.6.0. YouTube is a *default, no-login* channel (video info, search, subtitles; transcription needs a Groq/OpenAI key). Reddit/Twitter require login and are marked optional/experimental; the project's own release record shows **Reddit was network-blocked during their acceptance testing**. [VERIFIED — GitHub repo + commit messages, 2026-10-24.]
   - **MiroFish** — **AGPL-3.0**, ~81.6k stars, backed/incubated by **Shanda Group**, simulation engine powered by **OASIS (camel-ai/oasis)**, uses **Zep Cloud** memory + GraphRAG, 5-step workflow (graph building → environment setup → simulation → ReportAgent → deep interaction), live demo hosted, README explicitly warns token consumption is high ("try simulations with fewer than 40 rounds first"). [VERIFIED — GitHub README, 2026-10-24.] **AGPL means: study the architecture, do NOT copy code into a project you'll pitch as commercial.**
5. **India market hook is strong and officially sourced:** Ormax OTT Audience Report 2026 (ormaxmedia.com, Sept 2026): India's OTT universe = **664.9M** (+11% YoY); Ormax's own social posts state anime audiences on Indian OTT **grew 32% in 2025-26**, behind only micro-dramas and K-dramas. [VERIFIED — ormaxmedia.com + Ormax LinkedIn/Instagram summaries, checked 2026-10-24.]
6. **Biggest judging risk:** a judge asking *"how do you know your simulated Indians are right?"* Every serious commercial comparable now answers with a validation number. SakuraScore's answer must be built, not improvised: **provenance + seed-variance + one historical backtest.** (See Sections E/G/H.)

---

## B. Verified comparable list (NOT confirmed hackathon competitors)

**Your actual event's competitors: UNKNOWN — event not provided.** The following are public comparables researched per the brief's fallback instruction.

### B1. Hackathon projects (public Devpost submissions)

| Project | Event | What it is | Status evidence | Source (checked 2026-10-24) |
|---|---|---|---|---|
| **Tunnel — AI Agents for Simulated Market Research** | Devpost (Auth0/Cohere/Vapi-adjacent hackathon, listing dated ~Sep 2025) | Test product ideas vs 162–200+ personas; 3D globe sentiment map; voice calls with personas; focus-group auto-targeting via reranking | Submission page w/ 8 screenshots + YouTube demo video [VERIFIED page; demo video not watched] | https://devpost.com/software/tunnel-dqv1k4 |
| **The Boardroom** | The Great Agent Hackathon (Bangalore, ended 2026-09-26) | 5 incentive-driven agents (Product/Finance/Legal/CS/Eng) debate a decision in 3 rounds via LangGraph; dissent explicitly logged; ElevenLabs voices; terminal UI designed for stage lighting | Full submission text incl. architecture + challenges [VERIFIED page] | https://devpost.com/software/the-boardroom |
| **Agentropolis** | GenAI Genesis 2026 (Devpost, ~Mar 2026) | Thousands of agents on 3D Mapbox Toronto; archetype→follower two-layer agent system; event injection (transit strike, heat wave); user joins as avatar; FastAPI+WebSockets+NeonDB | Submission page w/ screenshots + YouTube demo [VERIFIED page; video not watched] | https://devpost.com/software/agentropolis |
| **Multi Agent Hub** | Devpost (listing ~Jan 2026) | Deployable multi-agent hub | Gallery one-liner only [CLAIMED] | https://devpost.com/software/multi-agent-hub |

### B2. Commercial comparables (the "would a customer buy this instead?" set)

Figures below are **vendor-published** [CLAIMED] unless noted; compiled from an Oct-2026 roundup that states vendor pages were checked 2026-10-03/17 (source is vendor-authored — Minds; treat comparisons accordingly).

| Company | Category | Key published facts | Source (checked 2026-10-24) |
|---|---|---|---|
| **Parrot Analytics** | Entertainment demand measurement (incumbent) | "World's largest audience behavior dataset"; global demand rankings incl. anime | https://www.parrotanalytics.com/academy/learn-the-methodology-behind-demand-measurement |
| **Synthetic Users** | Synthetic interviews for product teams | From **$12,500/yr**; claims 85–92% "theme parity" | https://www.syntheticusers.com/ ; pricing page per roundup |
| **Yabble (→ YouGov Virtual Audiences)** | Virtual audiences / synthetic personas | From **$8,900/yr**; claims 90% "similarity of insight" (metric undefined); acquired/partnered into YouGov per roundup | https://www.yabble.com/blog/product-release-proprietary-data-for-virtual-audiences |
| **Evidenza** | Managed B2B synthetic research (Dentsu-distributed per third-party landscape article) | Results in 72h; claims 88% similarity across 100+ tests | https://www.evidenza.ai/ |
| **Aaru** | Enterprise population simulation | Claims Pearson 0.970 vs answer shares, 186 studies (largest published validation in category per roundup) | https://aaru.com/ |
| **Simile** | Behavior simulation (enterprise) | Built on research lineage of Stanford 1,000-person agent study (arXiv:2411.10109: agents reproduce 83–86% of human retest consistency) | https://www.simile.com/ ; https://arxiv.org/abs/2411.10109 |
| **Artificial Societies** | Networked persona simulation | Claims 86% distribution accuracy across 1,000 surveys | https://societies.ai/eval |
| **Qualtrics Edge Audiences** | Synthetic responses beside human panels | Claims 0.07 SD avg deviation on 8 Likert items | qualtrics.com/articles (per roundup) |

**Takeaway:** none of these is India-entertainment-specific; none offers *evidence-linked* agent outputs as a headline feature; several charge $9k–$12.5k+/yr — a hackathon-priced SakuraScore with India vertical depth has a clear wedge. [VERIFIED that none of the above advertise India-anime specialization, per their positioning pages checked 2026-10-24.]

### B3. Reference architectures (our stated references)

| Project | Verified facts | Implication for us |
|---|---|---|
| **MiroFish** (666ghj/MiroFish) | AGPL-3.0; ~81.6k stars; Shanda Group incubated; engine = OASIS; Zep Cloud memory; GraphRAG seed extraction; ReportAgent; live demo at 666ghj.github.io/mirofish-demo; last code push ~2026-07/10; high token cost warning | Copy *patterns* (seed→graph→persona→simulate→report→chat-with-agent), never code. Its "chat with any agent in the simulated world" is the interaction judges remember. |
| **Agent-Reach** (Panniantong/Agent-Reach) | MIT; ~101.5k stars; v1.6.0 (2026-10-23); channels: YouTube/Bilibili/GitHub/V2EX/web (default, no login), Reddit/LinkedIn/XHS/Xueqiu/Boss/Xiaoyuzhou (optional/login), Twitter/Facebook/Instagram (experimental); YouTube subtitles default, transcription needs Groq/OpenAI key; per-platform ordered fallback tool lists; Reddit blocked in maintainer's own acceptance env | Best-in-class for YouTube evidence (subtitles of Indian anime-review/dub channels). Do NOT plan a live Reddit demo as P0. |
| **OASIS** (camel-ai/oasis) | Apache-2.0; ~5.3k stars; active (pushed 2026-10-19); "one million agents" social simulation | The engine under MiroFish; usable directly under permissive license if we need scale — but scale is NOT our differentiator. |

---

## C. Repository intelligence (verified via GitHub API on 2026-10-24)

Full table with 40+ repos in **`data/opensource_repos.csv`**. Curation logic: *does this buy a demo-visible advantage in ≤24h?* Highlights:

**Multi-agent simulation** — `joonspk-research/generative_agents` (Apache-2.0, 22.3k★, **unmaintained since 2024-08** — read the paper, don't run the code), `camel-ai/oasis` (Apache-2.0, 5.3k★, active), `tsinghua-fib-lab/AgentSociety` (Apache-2.0, 1.4k★, active), `a16z-infra/ai-town` (MIT, 10.7k★), `sotopia-lab/sotopia` (MIT, 341★).

**LLM orchestration** — `langchain-ai/langgraph` (MIT, 43.8k★, pushed today) — the safest 24h choice for a deterministic scenario-comparison pipeline (The Boardroom used it); `567-labs/instructor` (MIT, 14.1k★) — **highest ROI repo for us**: pydantic-validated structured outputs = zero malformed-JSON demo failures and a natural home for `citation_id` fields; `BerriAI/litellm` (61.9k★, license NOASSERTION/custom — check terms) for provider fallback if a demo key rate-limits; `BoundaryML/baml` (Apache-2.0, 9.4k★); `stanfordnlp/dspy` (MIT, 38.8k★) — powerful but a *learning-curve trap* inside 24h.

**Data collection** — `Panniantong/Agent-Reach` (MIT, 101.5k★ — see above); `yt-dlp/yt-dlp` (Unlicense, 201k★, pushed 2026-10-23) for YouTube metadata/subtitle extraction if Agent-Reach's YouTube path misbehaves; `unclecode/crawl4ai` (Apache-2.0, 86.2k★) and `adbar/trafilatura` (Apache-2.0, 7k★) for clean article extraction (Ormax/industry pages); `scrapy` (BSD-3, 65k★) — **overkill for 24h, skip**; `praw-dev/praw` (BSD-2, 4.3k★) needs Reddit API credentials — **skip for demo, cache data instead**; `JustAnotherArchivist/snscrape` (GPL-3.0, **abandoned since 2023-11** — do not use); `GeneralMilk/pytrends` — **404 on GitHub API, canonical repo unverifiable today; Google Trends scraping is fragile — treat as P2 at most.**

**Research agents** — `assafelovic/gpt-researcher` (Apache-2.0, 30.3k★), `stanford-oval/storm` (MIT, 31.7k★, last push 2025-09) — pattern reference for cited-report generation.

**Analytics/visualization** — `plotly/dash` (MIT, 24.5k★) or `streamlit/streamlit` (Apache-2.0, 46.1k★) for the dashboard in hours; `evidence-dev/evidence` (MIT, 7.1k★) — SQL+markdown BI-as-code, excellent for *reproducible* scenario reports (a credibility story of its own); `apache/echarts` (Apache-2.0, 67.6k★) if we want a Tunnel-style animated map/globe without Three.js cost; `duckdb/duckdb` (MIT, 42.5k★) for the evidence store (queryable provenance table = demo moment: "SELECT the evidence behind this claim").

**Memory/RAG** — `mem0ai/mem0` (Apache-2.0, 67.7k★) or `getzep/zep` (Apache-2.0; MiroFish uses Zep Cloud) if agent memory is needed — for 24h, plain JSON state is enough; don't add infra.

**Traps to avoid in 24h:** `FoundationAgents/MetaGPT` (71k★ but last push 2026-01 — slowing, and its "software company" framing doesn't fit), `FlowiseAI/Flowise` (**archived=true per API** — dead for new builds), `microsoft/lida` (stale since 2024), dify/n8n (NOASSERTION/fair-code licenses + heavy infra).

---

## D. Competitor strengths & weaknesses (evidence-linked)

### Tunnel (closest hackathon comparable)
- **Strengths [CLAIMED, page-verified]:** speed theater ("zero to insight in 30s"), 162 unique personas with psychographics, 3D globe with color-coded sentiment, **voice conversations with rejecting personas**, shareable session URLs; disciplined engineering writeup (Zod validation, retry/backoff, rate-limit queueing).
- **Weaknesses [VERIFIED from their own page]:** personas are **synthetic-first, not evidence-linked** (no real data grounding per description); B2B/startup-idea validation focus — no entertainment vertical, no India depth; no scenario A/B comparison; no uncertainty quantification; "viral coefficient calculation" asserted without methodology; roadmap admits GPT-4 integration still pending at submission time.
- **Judging advantage they'd have:** visual wow + voice. **How we beat it:** every opinion on our screen traces to a real Indian-fandom artifact; we show *delta between scenarios* with variance, they show a sentiment globe.

### The Boardroom
- **Strengths [VERIFIED page]:** explicit modeling of *disagreement* (moderated rebuttal round), **named dissent logged** in the decision memo, RAG grounding for the Legal agent ("objections drawn from real constraints instead of invented ones"), projector-legibility engineering.
- **Weaknesses:** internal-decision personas (Finance/Legal), not *market audiences*; no data collection; no India/entertainment angle; no scenario quantification.
- **Steal-worthy pattern (technique, not branding):** dissent logging + "designed for stage lighting" contrast checks.

### Agentropolis
- **Strengths [VERIFIED page]:** two-layer archetype→follower agent system (cost control), **pre-fetching all agent context to avoid slow tool loops** (demo-latency lesson), event injection as live theater, user-joins-simulation.
- **Weaknesses:** urban sim, not market research; no evidence provenance; Toronto-centric.

### Commercial vendors (Synthetic Users / Evidenza / Aaru / Simile et al.)
- **Strengths [CLAIMED]:** published validation benchmarks; managed-service credibility; enterprise distribution (Evidenza via Dentsu per third-party article; Yabble via YouGov).
- **Weaknesses [VERIFIED positioning gap]:** horizontal, Western-centric panels; **no India-entertainment verticalization found**; prices ($8.9k–$12.5k+/yr) exclude the studios/labels/licensors SakuraScore would first serve; none advertise *per-claim evidence provenance* into simulated outputs.
- **Risk to us:** if a judge knows this space, they'll ask why SakuraScore isn't just "Synthetic Users for anime." Answer prepared in Section G.

### MiroFish (reference, potential "competitor" only in mindshare)
- **Strengths [VERIFIED]:** Shanda backing, 81k★ mindshare, full seed→simulate→report→chat pipeline, OASIS engine, live demo.
- **Weaknesses [VERIFIED from repo signals]:** AGPL-3.0 (commercial-hostile), code activity slowed (~3 months since last functional commit vs star-history bot commits), high token cost warning in its own README, generic "predict anything" positioning without vertical evidence base.
- **Opportunity:** SakuraScore = "MiroFish-pattern rigor, applied to a vertical, with per-claim evidence and India data" — and permissively licensed.

---

## E. Competitive gap analysis — where SakuraScore stands

**Current state: `[CLAIMED-UNVERIFIED]` across the board** (no code available to audit; workspace checked 2026-10-24). The matrix in `data/competitor_matrix.csv` marks every SakuraScore cell accordingly — **fix this before judging by making at least the P0 items demonstrably true.**

| Gap | Severity | Fix |
|---|---|---|
| No verified working implementation (nothing in workspace) | 🔴 Critical | Ship a thin end-to-end vertical slice: 1 IP → evidence pack → 12–20 personas → 2 scenarios → comparison report. Depth in one lane beats breadth in six. |
| No validation story vs commercial vendors' published benchmarks | 🔴 Critical | Seed-variance + one historical backtest (Section H, P1). |
| Live-data fragility (Reddit blocked even for Agent-Reach's maintainer; Twitter experimental) | 🟠 High | **Static evidence cache committed to repo**; live collection shown once on YouTube channel (default, no-login), everything else replays from cache. |
| Simulation spectacle already commoditized (Tunnel/Agentropolis globs & maps) | 🟠 High | Don't build 3D. Spend those hours on the provenance click-through (evidence → claim → scenario delta). |
| Cost blowup risk (MiroFish's own README warns) | 🟡 Medium | Cap: ≤20 personas × 2 scenarios × ≤3 rounds; batch + cache; LiteLLM fallback key. |
| AGPL contamination risk if MiroFish code copied | 🟡 Medium | Architecture-only reference; add a NOTICE in repo README stating influences (also good judging optics). |

**Features already common (do not spend time):** persona generation, sentiment coloring, chat-with-agent, LLM report generation, 3D visualization.
**Features competitors demo well (respect, don't copy):** voice personas (Tunnel), dissent logging (Boardroom), live event injection (Agentropolis).
**Features SakuraScore lacks (build the first two, skip the third):** per-claim provenance links; baseline-vs-intervention delta view with variance; real-user testimonials (impossible in 24h — skip).
**Open lane nobody addressed (in this search):** India regional-language dubbing strategy simulation grounded in collected evidence; historical backtest of an actual Indian anime launch; uncertainty/sensitivity reports as a first-class output.
**Too expensive/risky before judging:** 1M-agent scale (OASIS), live Twitter/Reddit pipelines, voice UI, 3D maps, custom crawlers, model fine-tuning.

---

## F. Hackathon judging strategy

**Event-specific criteria: UNKNOWN.** Reference criteria from a comparable 24h India agent hackathon that *has* ended (The Great Agent Hackathon, Bangalore, 2026-09-26; Freshworks-sponsored; [VERIFIED event page 2026-10-24]): **Innovation & Originality · Technical Execution · Use of AI/Agentic Design ("meaningful, not bolted on") · Relevance to Problem Statement**. Assume your event is similar; re-tune when you give me the actual rubric.

Mapping strategy to those four axes:
1. **Innovation:** not "agents simulate audiences" (common) but "**evidence-grounded, uncertainty-quantified scenario simulation for a specific vertical**" — the provenance click-through is the innovation moment.
2. **Technical execution:** deterministic LangGraph-style pipeline, instructor-validated schemas, DuckDB evidence store, cached fixtures, tests for the simulation reducer. Show the repo graph in one slide.
3. **Agentic design:** multi-stage agency with *verifiable handoffs* — Collector → Persona Builder → Simulator → Analyst → Report agent; each stage's output cites the previous stage's artifacts (this is the "not a chatbot" proof).
4. **Relevance/business:** frame the decision, not the tech: *"Should we license IP X for India, dub it in Hindi or Tamil, and release before or after Diwali?"* Price the alternative: traditional market research takes months/$50k+ (Tunnel's own framing) and Parrot-class panels are enterprise-priced.

**Credibility choreography (from demo research, Section D/G):** first working result on screen < 45s; projector-legible contrast (Boardroom's lesson); pre-fetch context so nothing hangs (Agentropolis's lesson); show one dissenting agent + variance bars (honesty reads as rigor); end on the decision memo with clickable citations.

---

## G. Three-minute demo script

Full timestamped script with narration + screen actions + fallbacks in **`data/demo_script.csv`**. Skeleton:

- **0:00–0:20 Hook (no slides needed):** "India's OTT universe just crossed 664.9 million. Anime audiences grew 32% last year — third-fastest format in the country (Ormax, 2026). A Japanese licensor's real question: *which IP, which language, which window?* Today that answer costs months of research. Watch us produce a decision-grade answer in three minutes — with receipts."
- **0:20–0:50 Evidence:** type IP name (pre-cached fixture, e.g. a Jujutsu Kaisen–class title). Collector agent shows 8–12 evidence cards **in real time from cache**: YouTube review/dub videos w/ subtitle snippets, Ormax stat, fandom threads. Every card has source+date. Click one → raw excerpt.
- **0:50–1:30 Personas from evidence, not imagination:** Persona builder shows 12–20 agents; each persona card lists *which evidence IDs shaped it* ("Persona #7: 24, Pune, Hindi-dub-first — grounded in E3, E9").
- **1:30–2:20 Scenario A/B (the money moment):** Baseline (sub-only release) vs Intervention (Hindi+Tamil dubs, Diwali-window). Side-by-side deltas: intent-to-watch, platform preference, willingness-to-pay — **with variance bars across 3 seeds** and one dissenting agent quote shown deliberately ("Agent 14 stays negative — here's why, and here's the evidence it cites").
- **2:20–2:50 Recommendation memo:** evidence-linked, uncertainty-flagged; click any recommendation line → the exact sources behind it.
- **2:50–3:00 Close:** "This wasn't a chatbot opinion. Every number is simulated, every simulation is grounded, every grounding is a link. If we had one more week, we'd backtest this against the 2024 Demon Slayer India release — the machinery for that is already in the repo." (Only say this if the backtest fixture exists; otherwise use the variance line.)

**Why slides can't do this:** the click-through from *simulated claim → persona → evidence card → source URL* is a live proof-of-work that a slide cannot fake — that's the answer to "how do we show it's more than a chatbot with charts."

---

## H. Section 7 answers (competitive advantage)

1. **Why not a general-purpose LLM?** A GPT/Claude chat gives one averaged opinion, no provenance, no distribution, no reproducibility. SakuraScore returns a *distribution* of grounded reactions, scenario deltas, variance across seeds, and per-claim sources — auditability an LLM chat cannot produce. [VERIFIED differentiator vs Tunnel/commercial claims pages checked 2026-10-24.]
2. **Why simulation for anime-in-India?** The decision is counterfactual ("what if we dub in Tamil and move the window?") — no dataset contains it. Simulation is the only way to price interventions pre-launch; evidence-grounding is what keeps it from being fan-fiction.
3. **What makes results credible?** (a) provenance chain (claim→persona→evidence→URL+date), (b) seed-variance reporting, (c) one historical backtest (P1), (d) honest uncertainty section in the memo. Commercial peers publish validation numbers ([CLAIMED] benchmarks, Section B2) — we publish *method* and *links*.
4. **More than a chatbot with charts?** The click-through demo (G) + visible multi-stage agent handoffs (F.3).
5. **Customer decision supported?** License-or-pass on an IP for India; dub language priority; release window; platform (theatrical vs OTT-first) — each with quantified deltas and confidence.
6. **Single most differentiating feature?** **Evidence-linked scenario comparison with variance** (D1 below).
7. **What NOT to build:** 3D globes/city maps (Tunnel/Agentropolis own the spectacle), voice personas (Tunnel), general horizontal persona surveys (17 vendors), giant agent counts (OASIS/MiroFish), custom crawlers (Agent-Reach/crawl4ai exist), live Reddit/Twitter pipelines (blocked/fragile even for the tool's own maintainer).
8. **Three minutes, hard to slide:** the provenance click-through + A/B delta reveal + dissent moment (Section G).

**Three differentiator candidates (evidence → feasibility → judging relevance):**

| # | Differentiator | Evidence it's open | 24h feasibility | Judging relevance | Verdict |
|---|---|---|---|---|---|
| **D1** | **Traceable evidence linked to simulated outcomes + uncertainty/sensitivity** (every agent opinion carries citation IDs; re-run across seeds → variance bars; memo flags low-confidence claims) | No comparable (B1/B2) advertises per-claim provenance into simulation outputs; Boardroom's RAG-grounded Legal agent is the nearest echo | **High** — instructor schemas w/ `citation_id`, DuckDB evidence table, 3 seeds | **High** — hits "agentic design" + "innovation" + answers the #1 judge question | ✅ **RECOMMENDED CORE** |
| **D2** | **Regional-language dubbing strategy simulation** (Hindi vs Tamil vs Telugu persona segments react to dub/window interventions) | No vendor found verticalized to India languages; Ormax data supports the business frame | Medium — needs India-segment persona logic + cached India evidence; data access is the risk | Medium-high — vivid, locally resonant | ✅ Use as the **demo vehicle for D1** (the A/B scenarios in G) |
| **D3** | **Historical backtest** (run pipeline "as of" a past India anime launch; compare vs observed Ormax/box-office/YouTube outcomes) | Vendors publish validation benchmarks — we'd have our own | Medium — one case only; needs careful as-of cutoff to avoid leakage (judges will probe) | High if done honestly; **dangerous if hand-wavy** | ⏳ P1 if time remains; else tease in closing line |

**Recommendation: D1, demoed through D2's scenarios, with D3 as stretch.** Rationale: D1 is the only one that is (a) not yet claimed by any comparable found, (b) buildable with near-zero new infra (schema fields + a join), and (c) directly converts the category's biggest weakness — "how do you know it's right?" — into our strongest moment.

---

## I. Priority actions (full list in `data/priority_actions.csv`)

**P0 — must fix before demo (est. total 7–10h):**
1. **Evidence provenance chain** (Collector writes `evidence_id/url/retrieved_at` to DuckDB; persona & simulator schemas require `citation_ids[]` via instructor) — 2–3h — test: every claim in memo resolves to ≥1 clickable source; zero uncited claims.
2. **Static evidence cache + replay mode** (commit JSON fixtures; `--live` flag off by default) — 1–2h — test: full demo runs with airplane mode on.
3. **Scenario A/B delta view with 3-seed variance** — 2–3h — test: two scenarios render side-by-side; variance bars update across seeds; deterministic seed=42 replay.
4. **Recorded fallback video** of the whole flow — 1h — test: plays in <3min, projector-legible (Boardroom's contrast lesson).

**P1 — high impact if time allows:** 5. One historical backtest case w/ as-of cutoff (3h); 6. Language-segment personas Hindi/Tamil/Telugu (2h); 7. Dissent moment engineered (show lowest-confidence agent's reasoning + citations) (1h).

**P2 — after hackathon:** real Reddit/PRAW pipeline w/ credentials; Evidence/Superset-grade report site; cost telemetry (LiteLLM); backtest suite expansion.

**P3 — don't:** fork MiroFish (AGPL + scale complexity), 3D globe, voice personas, custom crawler, fine-tuning.

---

## J. Risks & uncertainties (full list in `data/risks_uncertainties.csv`)

- **Event unknown** → judging criteria assumed from a comparable ended event; re-tune on receipt of the real rubric. [UNKNOWN]
- **Real competitors unknown** → no team names guessed; comparable-pattern analysis only. [UNKNOWN]
- SakuraScore's actual implementation state unverified (empty workspace). [VERIFIED absent]
- Vendor benchmark numbers are self-published [CLAIMED]; the roundup compiling several is vendor-authored (Minds). [VERIFIED caveat]
- Agent-Reach: Reddit blocked in maintainer env; Twitter/FB/IG experimental — plan cache-first. [VERIFIED from repo release notes]
- MiroFish AGPL-3.0 contamination risk if code copied. [VERIFIED license]
- Simulation token cost (MiroFish README's own warning). [VERIFIED]
- Judge challenge "synthetic personas are unreliable" — mitigated by arXiv:2411.10109 lineage (83–86% human-retest parity) + our variance/backtest honesty. [VERIFIED paper reference]
- Demo videos for Tunnel/Agentropolis not watched (pages verified only). [VERIFIED limitation]

---

*All sources and check dates: `data/sources_log.csv`. Report generated 2026-10-24.*
