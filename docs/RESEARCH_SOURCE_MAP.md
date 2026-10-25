# Research Source Map

**SakuraScore India — Simulation & Research Subsystem**

Scope: the small, permitted, reproducible evidence base used to ground audience-segment assumptions, plus the planned repeatable research pipeline. The machine-readable companion is `src/sakurascore_sim/research/source_registry.py`; the evidence dataset is `data/evidence/india_anime_evidence.json` (retrieved 2026-10-24 via web search; every item carries URL, publisher, date, quality and observed/inferred label).

## 1. Data-access policy (binding)

- Official APIs and permitted access methods only; licences, source terms, rate limits and access restrictions respected.
- **No** bypassing authentication, CAPTCHAs, paywalls, blocks or rate limits. **No** private messages, private account data, or unnecessary personal data. **No** unauthorized cookies/session credentials. **No** indiscriminate platform scraping.
- Prefer a small, representative, reproducible evidence sample over large unreliable collections.
- If a source cannot be accessed legitimately, the limitation is documented and no fallback pretending otherwise is used.

## 2. Sources used for the curated evidence dataset

| Source | Data type | Geography | Access method | Auth | Terms posture | Quality | Used for |
|---|---|---|---|---|---|---|---|
| Crunchyroll News (official) | release/dub announcements | global + India | public pages via web search | none | article-level citation only | high | dub-availability cadence (evidence ids `imdb-crunchyroll-13-dubs-2024`, `crunchyroll-dubs-may-2024`) |
| IGN India / IMDb News / Box Office Mojo / Wikipedia | theatrical box office | India / worldwide | public pages via web search | none | headline figures cited | high (headline), medium (compiled) | Infinity Castle India release languages + records (`imdb-infinity-castle-india-release`, `ign-infinity-castle-opening`, `wiki-infinity-castle-worldwide`) |
| Official franchise social page (Demon Slayer FB) | opening-day record | India | public post via search | none | first-party statement | high | announcement-attention assumption (`koyoharu-opening-day-record`) |
| Forbes / Japan Times / Variety / ANN / CBR (industry press) | survey coverage (NRG), strategy, streaming news | global + India | public articles via search | none | article-level citation | medium-high | penetration growth 11%→40%+, NRG method, Muse Hindi channel launch |
| Ken Research / MarkNtel / Grand View / Statista | market sizing | India / global | public summary pages | none | free summary figures only; methodology opaque (flagged) | medium | ~180M fans, CAGR ~13.4%, Crunchyroll 21M subs |
| Muse India official YouTube channel | dub availability + channel scale | India | public channel page | none | public posts only | medium | free-legal anime scale (3.16M subs), Hindi dub channel 200K |
| r/AnimeMirchi, r/animeindian, r/boxoffice | community reports | India | individual public threads via web search (NOT bulk/API access — Reddit ToS restricts unauthenticated bulk access) | none | single-thread citation | low | dub lineup reposts, Suzume ₹3.79cr, day-5 tracking |
| Anime Research (academic survey site) | survey prelim results | global | public page | none | cited as-is; India n≈1.6% flagged | low | sample-size caution |

Known gaps (documented, not papered over): no X/Twitter data (paid API only — rejected), no Instagram/TikTok data, no proprietary streaming viewership data, India-specific n in global surveys is small.

## 3. Evidence → assumption linkage

Each evidence item carries an `id`; segments reference these ids in `evidence_ids`, and the result's `assumptions[]` block propagates them. Example chain:

1. `imdb-crunchyroll-13-dubs-2024` + `crunchyroll-dubs-may-2024` → Hindi/Tamil/Telugu dub slates are a sustained distributor strategy → **hypothesis:** a regional-language-first segment exists and responds to dub availability (`regional-language-first` segment).
2. `imdb-infinity-castle-india-release` + `koyoharu-opening-day-record` + `ign-infinity-castle-opening` → the actual Infinity Castle India release carried JP/HI/TA/TE and set the all-time anime opening record → **hypothesis:** occasion-driven theatrical audiences respond strongly to dubbed releases (`film-event-audiences` segment; `announcement_boost` round-0 assumption).
3. `forbes-nrg-india-penetration` + `kenresearch-india-180m-fans` → large, fast-growing, under-monetized audience → **hypothesis:** a large casual pool with language-modulated conversion (`casual-streaming-viewers` segment).
4. `manga-first-readers` grounded (weakly) by `animesurvey-2025-india-share` + worldwide IP momentum — explicitly labelled a low-evidence hypothesis.

**No survey responses were collected or fabricated. All segment parameters are modelling hypotheses.** Where evidence exists it is cited; where it does not, the segment note says so.

## 4. Repeatable research pipeline (planned — Agent-Reach adaptation)

Design (from `REPOSITORY_EVALUATION.md` §3): fixed query list → `agent-reach` CLI subprocess (credential-free channels only: `web`, `youtube` search/read, `github`) → parse unified JSON envelope (`make_item` shape: title/url/author/published_at/text/raw) → respect `retry_after_seconds`, never retry `PLATFORM_BLOCKED` → append-only JSONL with `{query, retrieved_at, tool_version, commit}` → validate through `sakurascore_sim.research.evidence_loader` → merge into the evidence dataset with fresh `retrieved_at`.

Why not integrated yet: the hackathon P0 needs a *small curated* evidence set (already delivered with full provenance); Agent-Reach adds install + runtime surface that P0 does not require. Its refusal-don't-bypass posture matches our policy, and MIT licensing is compatible.

Complementary official-API path: YouTube Data API v3 (key, free quota) for dub/trailer video metadata and view counts — the preferred programmatic upgrade over page scraping (`source_registry.py` entry `youtube-data-api`).

## 5. Rejected / excluded sources (with reasons)

| Source | Status | Reason |
|---|---|---|
| X / Twitter data | rejected | paid API only; unauthenticated scraping or login-session reuse violates ToS and our policy |
| Instagram / TikTok | rejected | no legitimate unauthenticated access; ToS |
| Private communities (WhatsApp/Discord/DMs) | rejected by policy | private data never collected |
| Paywalled market reports | excluded | only free summary figures cited; no paywall circumvention |
| Reddit bulk/API collection | excluded | ToS restrictions; single public-thread citations only |
| Agent-Reach login channels + CloakBrowser substrate | excluded | requires user login flows / non-MIT binary; unnecessary for our query set |
