# Data Source Assessment — SakuraScore India

Assessment of each public source used in this dataset: what it measures, how
reliable it is, what noise it contains, and where it can bias a market-potential
model for Japanese content in India. Ordered by role in the pipeline.

---

## 1. AniList GraphQL API — *content metadata & global demand proxy*

| Aspect | Assessment |
|---|---|
| Relevance | High — the only structured source of genres, tags, studios, season, scores, popularity for thousands of titles, including **unreleased** ones (the model's prediction targets). |
| Reliability | High — official API, stable schema, rate-limited but consistent. |
| Noise | `popularity` (users with the title on their lists) is a *global* engaged-fan metric, not viewership. `averageScore` is self-selected raters. Tags are community-moderated. |
| India bias | **Significant**: userbase skews English-speaking, Western + Southeast Asian. AniList popularity ≠ Indian popularity; treat as a *prior*, never as the target. |
| Mitigation | Use AniList popularity as one feature; calibrate against India-specific signals (Trends geo=IN, Hindi Wikipedia, Hindi-dub YouTube engagement). |

## 2. Jikan / MyAnimeList — *secondary metadata & MAL-side signals*

| Aspect | Assessment |
|---|---|
| Relevance | Medium — overlaps AniList; `members`/`score` are the longest-running community metrics. Good cross-validation of scores. |
| Reliability | Medium — unofficial API wrapping MAL; **blocked from our network during collection** (connection reset; scripts ready at `scripts/data_collection/fetch_jikan.py`). AniList rows carry `mal_id` for later joins. |
| Noise | MAL has a notorious score-inflation / review-bombing history on controversial titles. |
| India bias | Same as AniList, slightly older demographic. |
| Mitigation | Treat as corroboration only; never as the sole popularity input. |

## 3. Wikimedia Pageviews API — *demand time-series (interest signal)*

| Aspect | Assessment |
|---|---|
| Relevance | High — daily interest curves per title for ~24 months; spikes align with releases/announcements; usable for momentum & seasonality features. |
| Reliability | High — server-side logs, no sampling, official REST API, full history. |
| Noise | Bot traffic is filtered by the `all-agents` choice partially (we use all-agents per-article; spiky bot campaigns are rare on anime articles). Title resolution via opensearch can hit disambiguation/manga/film articles instead of the TV article — recorded transparently in `manifest_en.json`. |
| India bias | **en.wikipedia is global**, not India-only — though India is one of its largest reader bases. hi.wikipedia is a *direct* Indian-language signal but covers only a minority of titles (manifest shows the coverage). |
| Mitigation | Use en.wiki curves for shape (momentum), hi.wiki existence+volume for India-language resonance; normalize per-title by its own history rather than cross-title absolute levels. |

## 4. Google Trends (pytrends, geo=IN) — *India-specific search demand*

| Aspect | Assessment |
|---|---|
| Relevance | **Highest for the India question** — the only source that directly measures Indian search interest over time (10 keywords × 5 years × weekly, geo=IN, hl=en-IN). |
| Reliability | Medium-High — real data, but **sampled and normalized**: each keyword's series is scaled 0–100 against its own window, so values are *not comparable across keywords*, only across time within a keyword. |
| Noise | Unofficial endpoint (pytrends); occasional 429s (we got none this run). Ambiguous queries ("one piece" can mean clothing). |
| India bias | By design geo=IN — but reflects *Google users*, i.e., English + urban + younger skew; misses non-Google and offline India. |
| Mitigation | Use for trend direction & inflection detection; never compare absolute levels between keywords. |

## 5. YouTube Data API v3 (regionCode=IN) — *engagement & linguistic reach*

| Aspect | Assessment |
|---|---|
| Relevance | High — where Indian anime fandom visibly aggregates (dub clips, edits, reactors). Local-language search terms (Tamil/Telugu/Bengali/Marathi dubbed) probe linguistic hubs. |
| Reliability | High API reliability; **blocked pending API key** (script ready; no key found in env at collection time). |
| Noise | Views/likes are cumulative since upload — need upload-date normalization (script captures `publishedAt`). Fan edits pollute title search. |
| India bias | regionCode=IN helps; but Indian viewers also watch global uploads, and YouTube premium/shorts behavior differs. |
| Mitigation | When key arrives: compare engagement per day-since-upload; weight official channels & dub uploads higher than edits. |

## 6. Reddit r/AnimeIndia — *community ground truth*

| Aspect | Assessment |
|---|---|
| Relevance | Medium — small but genuinely Indian community; top posts reveal which titles actually get discussed. |
| Reliability | Low-Medium for reach (tiny vs the market) — **403-blocked during collection** without OAuth; needs a Reddit app token to retry. |
| Noise | Power users, self-promotion, meme skew. |
| Mitigation | Use only as qualitative validation of the seed list, not as a scored feature. |

## 7. Curated seed list (`india_anime_success_seed.csv`) — *weak ground truth*

Evidence-graded (strong/moderate/weak) list of titles with documented Indian
success (TV broadcast history, Crunchyroll India Hindi-dub rollouts, Sony/
Crunchyroll-reported records, theatrical releases). This is the closest thing
to labels available publicly; treat `weak` rows as hypotheses, not facts.

## 8. `india_states.csv` — *regional priors*

Census 2011 population/literacy/urbanization + 2024 estimates of median age and
internet penetration (latter are team estimates from public reporting, flagged
in column names as `est_2024`). Use for regional weighting, not as outcomes.

---

## Cross-cutting bias summary

1. **English-platform bias** — every API over-represents English-literate,
   urban, younger Indians. Regional-language signals (hi.wiki, local YouTube
   search, dub announcements) partially correct this.
2. **Fandom ≠ market** — global popularity metrics measure fans, not the
   casual mass audience that Hindi TV dubs reach (the Doraemon/Shin-chan lane).
   The seed list deliberately includes mass-market TV titles to anchor this.
3. **Survivorship** — AniList "top" lists only contain already-noticed titles;
   unreleased-title scoring must rely on *structural* features (studio, genre,
   source material, franchise lineage) rather than existing popularity.
4. **No revenue data** — public sources expose interest, not box office /
   subscribers. Scores built on this data predict *attention potential*;
   conversion to revenue needs distributor assumptions.
