# SakuraScore India — Data Folder

All data for predicting Indian market potential of Japanese media content.
Collected 2026-10-24 via `scripts/data_collection/` (idempotent, cached).

## Layout

```
data/
├── raw/                      # immutable API responses (JSON caches)
│   ├── anilist/              #   1000 top anime + trending + upcoming seasons
│   ├── jikan/                #   EMPTY — Jikan blocked from this network; script ready
│   ├── wikimedia/            #   per-article daily pageviews (en + hi) + manifests
│   ├── youtube/              #   EMPTY — awaiting YOUTUBE_API_KEY; script ready
│   └── trends/               #   Google Trends geo=IN 5yr weekly + (Reddit blocked)
├── processed/                # analysis-ready CSVs (regenerate: python .../process.py)
│   ├── anilist_catalog.csv
│   ├── wikipedia_pageviews_long.csv
│   ├── wikipedia_pageviews_summary.csv
│   └── google_trends_india_long.csv
└── reference/                # curated static data
    ├── india_states.csv              # state demographics for regional scoring
    ├── india_anime_success_seed.csv  # evidence-graded India ground truth
    └── data_source_assessment.md     # reliability / noise / bias per source
```

## Processed files

**`anilist_catalog.csv`** — one row per unique anime across all AniList pulls
(top-1000 popularity, trending, NOT_YET_RELEASED for FALL 2026 / WINTER 2027 /
SPRING 2027 and any-season upcoming). Key columns: `mal_id` (join key to MAL
data later), `genres`, `tags` (`name:rank` pipe-separated), `popularity`,
`average_score`, `main_studios`, `source_list` (which pull it came from —
`upcoming_*` rows are your **prediction targets**, the rest are training
candidates).

**`wikipedia_pageviews_long.csv`** — daily views per resolved article,
2024-10 → 2026-10 (~731 days), `project` = en.wikipedia / hi.wikipedia.

**`wikipedia_pageviews_summary.csv`** — per-article features:
`avg_daily`, `peak_daily`, `peak_date`, `avg_daily_last30`,
`momentum_90d_vs_prior90` (ratio of recent 90-day mean to prior 90-day mean,
minus 1). Momentum > 0 means interest is accelerating.

**`google_trends_india_long.csv`** — weekly interest (0–100, self-normalized
per keyword — compare across time, NOT across keywords), geo=IN, 2021-10 →
2026-10. Keywords: anime, crunchyroll, one piece, demon slayer, jujutsu kaisen,
solo leveling, naruto, anime hindi dub, manga, otaku.

## Status of the four planned APIs

| Source | Status | Notes |
|---|---|---|
| Wikimedia Pageviews | ✅ pulled | 186/200 titles resolved on en.wiki (24 months daily, 127.7k day-rows); 14/50 on hi.wiki (most anime lack Hindi articles — itself a useful signal) |
| AniList GraphQL | ✅ pulled | 1,352 unique anime: top-1000 catalog + trending + **317 unreleased prediction targets** (FALL 2026 / WINTER 2027 / SPRING 2027 / any-season upcoming) |
| YouTube Data v3 | ⏳ needs key | `export YOUTUBE_API_KEY="AI..."` then run `fetch_youtube.py` |
| Jikan v4 | ❌ network-blocked | connection reset from this network; works elsewhere — rerun `fetch_jikan.py` from any other machine/cloud VM |
| Google Trends (bonus) | ✅ pulled | geo=IN, 5 years weekly, 10/10 keywords (2,650 rows) |
| Reddit r/AnimeIndia (bonus) | ❌ 403 | needs OAuth app token; optional |

Cross-validation note: Solo Leveling is the #1 most-viewed anime article on
English Wikipedia over the last 24 months in our pull (5.7M views) — matching
press reports (TOI, Jun 2025) that it became Crunchyroll's most-viewed/most-
rated series ever. Independent signal agreement is a good sanity check.

## Re-run / extend

```bash
python scripts/data_collection/fetch_anilist.py       # cached pages skipped
python scripts/data_collection/fetch_wikimedia.py 300 # top-N titles arg
YOUTUBE_API_KEY="AI..." python scripts/data_collection/fetch_youtube.py
python scripts/data_collection/fetch_trends_social.py
python scripts/data_collection/process.py              # rebuild processed CSVs
```

## Caveats (read before modeling)

- AniList popularity is **global**, not Indian — calibrate with India signals.
- Wikipedia article resolution (opensearch) sometimes lands on the manga or
  film article rather than the TV series; see `raw/wikimedia/manifest_en.json`.
  Hindi resolution is noisier (36/50 misses; e.g. "Bleach" resolved to the
  Punjabi town "Balachaur") — check `manifest_hi.json` before using hi.wiki rows;
  consider dropping suspiciously-low-coverage matches (< 100 days).
- Trends values are per-keyword normalized (0–100); no cross-keyword compares.
- `india_states.csv` 2024 columns are team estimates; census 2011 columns are exact.
- Full source reliability/bias analysis: `reference/data_source_assessment.md`.

**Never commit API keys.** Keys live in environment variables only.
