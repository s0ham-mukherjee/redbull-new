# SakuraScore Backend — 100% Map

> Scope: every source file under `src/` (the pipeline) and `modules/src/` (the
> engine API + providers). Data scripts under `scripts/data_collection/` feed it.
> Written from a full read of all 45 source files (~4,600 lines). Python 3.14,
> pandas 3.x, FastAPI, pytest.

```
redbull-thapar-japan/
├── src/                      # THE SCORING PIPELINE (challenge deliverable)
│   ├── app.py                # SakuraScoreApp — orchestrator + data indexes (343 L)
│   ├── scoring/engine.py     # SakuraScore weighted-factor scoring (195 L)
│   ├── intelligence/
│   │   ├── cultural_compat/engine.py    # Indian archetypes + CBFC (236 L)
│   │   └── localization_econ/engine.py  # INR cost model + break-even (165 L)
│   ├── briefing/japanese.py  # EN/JA executive briefings (134 L)
│   ├── reporting/exporter.py # Markdown / JSON / HTML exporters (246 L)
│   └── data_sources/matrix.py# 8-source evidence matrix (115 L)
├── modules/
│   ├── src/
│   │   ├── sakurascore.py    # facade: engine_api + providers (26 L)
│   │   ├── engine_api/       # neutral contracts (registry + types + protocols)
│   │   └── providers/        # 18 provider modules over external/ clones
│   └── tests/test_engine_api.py  # 25 existing tests (all pass)
├── scripts/data_collection/  # fetchers + process.py → data/processed CSVs
├── data/                     # raw JSON pulls + processed CSVs + reference CSVs
└── tests/                    # NEW mega-suite (this effort) for src/
```

---

## 1. Pipeline layer (`src/`) — how one title becomes a report

### 1.1 `SakuraScoreApp` (`src/app.py`)

**Init (needs data on disk):** loads 4 processed CSVs + 2 reference CSVs from
`data/`. Raises `FileNotFoundError` if `data/processed/anilist_catalog.csv` is
missing. Builds engines (`CulturalCompatibilityEngine`,
`LocalizationEconomicsEngine`, `ScoringEngine`) and the evidence matrix.

**Indexes built at init:**
- `_norm(s)` — NFKD → lowercase → non-alphanumeric → space → strip (class-level helper, also used for aliases).
- `by_english` — exact `title_english` → row.
- `popularity_values` / `favourite_values` — full-catalog percentile pools (NaN→0).
- `unreleased_pop_values` — percentile pool restricted to `status == NOT_YET_RELEASED`.
- `wiki_by_source_title` — normalized title → en.wikipedia row (`avg_daily_last30`, `peak_daily`, `momentum_90d_vs_prior90`, `total_views_24m`).
- `hi_wiki_titles` — set of normalized titles with a hi.wikipedia article.
- `trends_growth` — keyword → 2-year growth % (last-52w mean vs prior-52w mean); keywords with <104 weekly points are skipped; zero prior mean → skipped.

**`SHOWCASE_ALIASES`** — 5 normalized alias → exact catalog title (chainsaw man reze arc, jujutsu kaisen culling game, solo leveling s2, sakamoto days, lazarus).

**`lookup(title)`** — 4-stage: exact English → alias → normalized exact (`_norm_en`/`_norm_ro`) → normalized substring (first hit). Empty/blank input falls through to substring match (matches everything → first row).

**`run_candidate(title, meta_override=None)`** — the pipeline:
1. Row lookup → `meta` dict (episodes/duration/year NaN→None, genres split `|`, tags split `|` into `(name, rank)` — non-numeric rank falls back to 50). No row + no override → `ValueError`. Override path applies `setdefault`s (title/format/pop=0/fav=0/genres=[]/tags=[]/is_adult=False).
2. `unreleased` = global NOT_YET_RELEASED **OR** showcase alias (India-premiere-pending).
3. Cultural evaluation (genres, tags, is_adult, format, episodes).
4. **Two-pass scoring:** confidence → provisional score with `reach_multiplier=1.55` → econ recommendation → final score with the *recommended* plan's reach multiplier.
5. Market breakdown per linguistic hub; briefings EN/JA attached; returns `PipelineResult`.

**`_confidence`** (0-100): +30 catalog row, +25 wiki (else +8), +15 known trends growth (else +5), +10 Hindi wiki, +10 seed match, +10 released / +5 unreleased. Capped at 100. Note: `meta_override` path passes `meta=None` → never gets the +30.

**`market_breakdown(profile, reach_multiplier, genre_fit)`** — 6 hubs (`HUBS`); states not in any hub default to "Northern Fringe". Per hub: population share × internet/60 × (1+Δ/100) × (1−friction_penalty/200) × (reach/2.2), demand index clamped 0-100 via `int(max(0,min(100,demand*4)))`. Friction penalty: 0.35 factor for Hindi Belt, 0.2 otherwise. Mutates `self.states` with a `_hub` column (idempotent).

**`PipelineResult.why_bullets`** — factors sorted by contribution desc.

### 1.2 `ScoringEngine` (`src/scoring/engine.py`)

- `WEIGHTS`: india_demand .25, global_fandom .20, momentum .14, cultural_fit .14, localization_reach .14, genre_fit .13 (sum = 1.00).
- `GRADES`: S≥80, A≥70, B≥60, C≥45, D≥0. `grade_for` floor-march.
- `GENRE_AFFINITY`: 22 genres (Action 85 … Hentai 0); unknown genre → 55.
- `percentile(values, x)` — mid-rank: `100*(below + 0.5*eq)/len`; empty pool → 50.0.
- Factor construction (`score_candidate`):
  1. **india_demand** — if wiki has `avg_daily_last30`: 0.40×volume-percentile + 0.25×(50+50×clamp(momentum,−1..1)) + 0.15×(100 hindi / 30 not) ; else 0.55×35. Plus trends: 0.20×clamp(50+growth, 0..100) or 0.20×50. NOTE: with wiki present the weights sum to 1.00, but the no-wiki branch gives 0.55×35 + 0.20×… = max ~55 (deliberate data penalty).
  2. **global_fandom** — 0.55×pop-percentile + 0.45×fav-percentile, ±quality bump from `average_score` (≥80:+15, ≥75:+8, ≥68:0, else −8), clamped 0-100.
  3. **momentum** — pre-launch: percentile of pop within unreleased pool. Released: 0.6×wiki-volume percentile + 0.4×(50+50×clamp(mom)); no momentum → 0.4×50.
  4. **genre_fit** — 0.6×max(affinity) + 0.4×mean(affinity); no genres → 55 neutral.
  5. **cultural_fit** — passed through from cultural engine.
  6. **localization_reach** — `100*(reach−1)/(2.2−1)` clamped 0-100.
- `sakura_score = int(round(Σ value×weight))`; `tier_notes` gets the pre-launch note.

### 1.3 `CulturalCompatibilityEngine` (`src/intelligence/cultural_compat/engine.py`)

Inputs: genres, tags `(name, rank 0-100)`, is_adult, format, episodes.

- **Archetypes** (4): dharma_duty, guru_shishya, parivaar, sahavas. Base 35 + 18×min(genre_hits,2) + 12×min(tag_hits,3), capped 100.
- **CBFC ladder** (rank-aware; AniList tag rank gates the trigger):
  - adult genre OR adult tag(rank≥55) OR is_adult → `"A (Adults Only)"`
  - else any HIGH_RISK tag (rank≥45: Gore, Body Horror, Graphic Violence, Cannibalism, Cultured Violence) → `"A risk / U/A 16+"`
  - else any MODERATE tag (rank≥35: Violence, War, Suicide, Self-Harm, Drugs, Alcohol, Tobacco Use, Child Abuse, Death, Tragedy) → `"U/A 13+"`
  - else `"U"` if Kids/Slice of Life/Comedy genre else `"U/A 7+"`.
  - MILD_RISK genres (Horror/Thriller/Psychological) demote `U` → `U/A 7+` (only when not already A-track).
  - Religion/Mythology tags always append a trigger (any rating).
- **Friction (0-100):** Σ tag friction ×(1 if rank≥50 else 0.5) + Σ genre friction, capped 100; `MOVIE` and friction<20 → −5; `int()`.
- **Regional deltas:** per-genre hub deltas summed; zeros dropped.
- **Flags:** rating startswith "A"; friction≥40; "Ecchi" in genres.
- **overall_cultural_fit** = `int(0.45×top_archetype + 0.25×(100−friction) + 0.15×rating_score + 0.15×(50 + max|Δ|×sign))` clamped 0-100, where rating_score = 0 (A-track) / 70 (U/A 13+) / 85 (else incl. U, U/A 7+, U/A 16+); sign = +1 if any positive Δ else −1.

### 1.4 `LocalizationEconomicsEngine` (`src/intelligence/localization_econ/engine.py`)

Constants: subs ₹400/min; series dub ₹16,000/ep; extra dub langs ×0.85 each; movie dub ₹8,000/min; reach 1.0/1.55/1.85/2.2; ₹0.90/view; ₹170/ticket.

- **Format handling:** `MOVIE` (case-insensitive) → 1 ep × (duration or 105) min. Series → eps or 12, min/ep or 24, capped at 60 eps.
- **Plans** (4): movie costs = per-min × Σ(0.85^k); series = dub×Σ + subs. `cost_per_reach_unit = cost/reach`.
- **Recommendation:** score ≥72 → five_language; ≥55 → three_language; ≥40 → hindi_dub; else subtitles_only.
- **Break-even:** movie → tickets = cost/170; series → views = cost/0.9 and payback = max(1, cost/(monthly_views×0.9)) with monthly views 2.6M/1.4M/700k/280k by mode.
- `format_inr` — lakh/crore formatting (≥1Cr → "₹X.XX Cr", ≥1L → "₹X.X L", else comma).

### 1.5 Briefings (`src/briefing/japanese.py`)

- `build_executive_briefing_en/ja(r)` — markdown; top-3 factors by contribution; recommended plan; CBFC; archetype max; triggers[:4]; live-source count from matrix. `GRADE_COMMENT_JA` maps all 5 grades (module-level dict + duplicate private function `_grade_comment_ja`).

### 1.6 Exporters (`src/reporting/exporter.py`)

- `to_markdown` — full report: factor table, cultural tables, 4-plan cost table, market map, 8-source matrix, both briefings.
- `to_json` — schema `sakurascore-india/0.2`; tags → `[{name, rank}]`; `default=str`.
- `to_html` — styled shell; `html.escape` on user-visible strings (labels, triggers, briefings, bias/mitigation) — but **not** on title/grade/status/mode names/format values (they flow into HTML via f-strings; `_HTML_SHELL.format` escapes only title).
- Note: markdown table cells interpolate rationales/notes unescaped (markdown context).

### 1.7 Evidence matrix (`src/data_sources/matrix.py`)

8 `DataSource` rows (anilist, jikan, wiki_en, wiki_hi, trends, youtube, reddit, seed) with status live/blocked/pending_key; `get_matrix()` returns `[vars(s)]`.

---

## 2. Engine layer (`modules/src/`)

### 2.1 `engine_api` (the neutral contract)

- **`types.py`** — frozen dataclasses: `Query`, `Evidence` (auto sha256 `content_hash` in `__post_init__` via `object.__setattr__`), `Document`, `Signal`, `IPNode`, `Relation`, `Interval`, `Forecast`, `Directive`, `Persona` (defaults: tier_2, hi, dub, shonen, ₹8000), `Scenario`, `AgentTurn`, `SimulationReport`, `EvaluationResult`; `Action` enum (pilot/investigate/wait/abstain); `utcnow`, `content_hash`.
- **`registry.py`** — 30 capability `KINDS` (18 wave-1 + 12 wave-2: embedder…preprocessor). `Registry.register/create/names/__contains__`; unknown kind → KeyError; unknown name → KeyError listing alternatives. `provider(kind, name)` decorator registers lazy factories. `available()` → all kinds. Global singleton `registry` (module-level, shared process-wide).
- **`protocols.py`** — 17 `@runtime_checkable` Protocols (EvidenceSource, ContentExtractor, ResearchRouter, KnowledgeStore, MemoryStore, TimeSeriesSource, Normalizer, SentimentAnalyzer, TextProcessor, UncertaintyEstimator, ProbabilityCalibrator, ForecastGate, Simulator, Evaluator, Scheduler, Cache, RateLimiter).
- **`sakurascore.py`** — facade: `import providers` then re-exports engine_api.

### 2.2 `_bootstrap.py` — `ensure_paths(repo)` prepends `external/<repo>/<roots>` to `sys.path` (idempotent); unknown repo → KeyError; missing clone dir → FileNotFoundError. `ProviderError(RuntimeError)`.

### 2.3 Providers (18 modules, all factories lazy — importing registers, nothing heavy loads)

| module | kind/name | class | network? | testable offline |
|---|---|---|---|---|
| social.py | source/reddit | RedditSource | OAuth PRAW | cred-missing path, `_submission_evidence` w/ fake submission |
| social.py | source/youtube | YouTubeSource | yt-dlp | `_info_to_evidence` pure |
| microblog.py | source/x_scrape, x_client, x_official, telegram | twscrape/twikit/tweepy/telethon | yes | `_tweet_evidence` pure; timeout/cred paths |
| anime_metadata.py | source/anime_metadata | Jikan | yes | `to_ip_node` pure; fetch w/ fake Jikan |
| research_router.py | router/multi_channel + source/reach_reddit | Agent-Reach | yes | `_to_evidence` pure; health w/ real clone |
| knowledge_graph.py | store/local_graph, store/dgraph | Local/Dgraph | dgraph yes | LocalGraphStore fully; Dgraph via fake requests |
| memory.py | memory/local, memory/zep | Local/Zep REST | zep yes | LocalMemoryStore fully |
| cache.py | cache/local, cache/redis; limiter/token_bucket | LocalCache/RedisCache/TokenBucketLimiter | redis optional | fully (use_redis=False) |
| pageviews.py | timeseries/wiki_pageviews | mwviews | yes | `series()` w/ injected fake client (monkeypatch `_client`) |
| trends.py | timeseries/search_trends; normalizer/trend_growth | pytrends | yes | TrendGrowthNormalizer fully |
| nlp.py | sentiment/transformer; text/indic | HF/indicnlp | model download | TransformerSentiment label mapping w/ fake pipeline; IndicTextProcessor detect/normalize (clone present) |
| uncertainty.py | uncertainty/conformal_regressor; gate/data_readiness | MAPIE | no | fully (real numpy) |
| evaluation.py | evaluator/factual_consistency | deepeval (LLM optional) | no | deterministic mode fully |
| scheduling.py | scheduler/prefect | Prefect | no | fully (clone present) |
| simulation.py | simulator/oasis_swarm; simulator/mirofish_service | OASIS LLM / MiroFish HTTP | yes | `_grounding_block` pure; MiroFish errors w/ fake http |
| presentation.py | app/decision_api; ui/decision_dashboard | FastAPI / Streamlit | no | TestClient; directive_rows pure |
| retail.py | source/retail | scrapy+requests | yes | `parse_price` pure; `_extract` w/ injected HTML |
| web_extract.py | extractor/web_page | crawl4ai/Playwright | yes | error paths w/ fake crawler |

### 2.4 Cross-cutting behaviors

- All network failures funnel to `ProviderError` with actionable messages (missing env var / start-service hint).
- Registry is process-global: tests share it (order effects possible if a test registers junk names).
- `presentation.create_decision_api` binds a pydantic model post-hoc to dodge `from __future__ import annotations` ForwardRef issues; `/research` → 503 without engine_fetch, 404 on KeyError, 502 on other exceptions.

---

## 3. Data flow (end to end)

```
scripts/data_collection/fetch_*  → data/raw/*.json
scripts/data_collection/process.py → data/processed/{anilist_catalog,
  wikipedia_pageviews_summary, wikipedia_pageviews_long, google_trends_india_long}.csv
SakuraScoreApp.__init__ → indexes
run_candidate(title) → lookup → cultural.evaluate → scoring.score_candidate (provisional, reach 1.55)
  → econ.evaluate(rec → plan) → scoring.score_candidate(final, rec reach)
  → market_breakdown → briefings → PipelineResult
exporter.to_markdown / to_json / to_html → report
```

## 4. Findings (18 total; every one is test-covered)

Bugs #1–#10 were found during the full source read; #11–#13 were discovered by
the test suite (each has a current-behavior test plus an `xfail(strict=True)`
desired-behavior test in `tests/test_bugs.py`, so a fix flips the xfail to a
failure and forces the test to be updated).

1. **NaN momentum inflates score** — `scoring/engine.py:93,149` `float(mom)` with NaN: `min(1, nan)→1`, so momentum clamps to +1 (max acceleration) instead of neutral.
2. **Duplicate dict key** — `microblog.py:44` `"retweets": item.get("retweet_count") or item.get("retweet_count")` (same key twice; probably meant a fallback metric).
3. **`_confidence` override penalty** — `app.py:303` passes `meta=None` on the override path, so a fully-specified `meta_override` never earns the +30 catalog points (33 vs 63 observed).
4. **`_trends_for` "best" is last-match** — `app.py:174-176` iterates dict order and keeps the *last* substring hit, not the longest/best; a title containing several keywords silently picks the final one.
5. **Empty-title lookup matches everything** — `app.py:139-143` `str.contains("")` is always True, so `lookup("")` returns the first catalog row rather than None.
6. **`duration_min=0` / `episodes=0` fall back to defaults** — `localization_econ` uses `or`, so explicit 0 is treated as missing.
7. **HTML escaping gaps** — `exporter.to_html` escapes briefings/labels but interpolates `r.title`, status, mode names, market-hub names unescaped (XSS surface only if titles become attacker-controlled).
8. **`LocalMemoryStore.recall` k=0 returns 1 entry** — `memory.py:47` `scored[:max(1, k)]`.
9. **`_grade_comment_ja` dead code** — duplicated by module-level `GRADE_COMMENT_JA`.
10. **States not in any HUB silently join "Northern Fringe"** — `app.market_breakdown` `fillna("Northern Fringe")` (latent: the current CSV happens to cover every state).
11. **Genre-fit rationale empty for mid-affinity genres** — `engine.py:159-161` the rationale filter only keeps affinities in (0, 15) or ≥70, so e.g. `["Romance"]` (60) yields a factor with an empty rationale list — transparency gap in the "why this score" story.
12. **`get_matrix()` leaks live `__dict__`** — `matrix.py:113-115` returns `vars(s)` of the module-level `SOURCES` dataclasses; any caller mutation corrupts global state for the whole process (verified by identity test).
13. **Empty `meta_override={}` raises** — `app.py:263` `elif meta_override:` is falsy for `{}`, so a caller passing an explicit empty dict gets `ValueError` instead of the documented setdefault-defaults path.
14. **`regional()` crashes on empty query text** — `trends.py:79` `keywords[0]` IndexError (desired: `ProviderError` like `series()`).
15. **`to_ip_node` IndexError on empty adaptation entry** — `anime_metadata.py:89` `prev.get("entry", [{}])[0]` with `entry: []`.
16. **Confidence-mismatch destroys fitted model** — `uncertainty.py:68` the handler re-runs `__init__` before raising, wiping the fitted estimator state.
17. **Negative limiter cost always granted** — `cache.py:127` `tokens >= cost` is trivially true for `cost < 0`.
18. **Live pageview timestamps always None** — `pageviews.py:63` parses mwviews day keys as `%Y%m%d` strings, but the real client returns `datetime.date` keys, so `window_start` is None on every signal from a live pull (found by the `--run-live` suite on 2026-10-24; the raw date survives only in `metadata['date']`). Offline tests with string-key fakes can't see this.

Style-level notes asserted as current behavior: `PipelineResult` drops
`ScoreResult.tier_notes`; `market_breakdown`'s `genre_fit` parameter is unused;
the `format=="MOVIE"` co-viewing discount is case-sensitive while the econ
engine's movie check is case-insensitive (inconsistent); the CBFC high-risk
branch suppresses moderate-risk triggers (`elif` chain).

## 5. Test infrastructure

```bash
./run_mega_tests.sh              # both suites, default profile (~10s)
./run_mega_tests.sh thorough     # 300 examples/property (~20s)
./run_mega_tests.sh exhaustive   # 1,500 examples/property (~40s) → 139,919 total cases
cd modules && python3 -m pytest tests -q --run-live -m live   # opt-in real network
```

- `tests/` — src pipeline suite: 725 tests (unit/property/mass/integration + bug pins).
- `modules/tests/` — engine+providers suite: 702 tests incl. 26 property tests,
  mass enumeration, 4 opt-in live tests, bug pins.
- Counting: pytest cases + executed hypothesis examples (parsed from
  `--hypothesis-show-statistics`) + `ENUMERATED_CASES` mass checks, summed by
  `tools/count_test_cases.py`.
- All 18 findings have a current-behavior test; the clear-cut ones also have an
  `xfail(strict=True)` desired-behavior pin (`tests/test_bugs.py`,
  `modules/tests/test_bugs.py`) that flips to failure when someone fixes them.
