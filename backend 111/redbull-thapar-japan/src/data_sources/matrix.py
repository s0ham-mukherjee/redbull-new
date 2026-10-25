"""Eight-source public big data assessment matrix.

Quantifies Relevance / Reliability (0-100) and documents inherent bias, noise,
and the concrete mitigation applied for each source. Backs the Evidence Audit
tab and the exported reports. Statuses reflect the actual collection run
(2026-10-24); they update when fetchers are re-run.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DataSource:
    key: str
    name: str
    measures: str
    status: str                      # live | blocked | pending_key
    relevance: int                   # 0-100 for THIS question
    reliability: int                 # 0-100
    bias: str
    noise: str
    mitigation: str
    coverage: str


SOURCES = [
    DataSource(
        key="anilist", name="AniList GraphQL",
        measures="structured metadata, global fandom metrics, unreleased watchlist demand",
        status="live", relevance=92, reliability=90,
        bias="English-first global userbase; Western/SEA skew — popularity is NOT Indian demand",
        noise="community-moderated tags; self-selected raters",
        mitigation="used as a prior only; calibrated against geo=IN signals; "
                   "unreleased titles compared within their own cohort (survivorship-safe)",
        coverage="1,352 unique titles incl. 317 unreleased (full pull)",
    ),
    DataSource(
        key="jikan", name="Jikan / MyAnimeList",
        measures="MAL scores, members — longest-running community metrics",
        status="blocked", relevance=60, reliability=62,
        bias="older demographic, score inflation / review-bombing on controversial titles",
        noise="unofficial API wrapping MAL scraping",
        mitigation="corroboration only, never a sole popularity input; mal_id kept "
                   "in catalog for later join; blocked from collector network — "
                   "script ready to re-run elsewhere",
        coverage="0 rows this run (network block); pending",
    ),
    DataSource(
        key="wiki_en", name="Wikipedia Pageviews (en)",
        measures="per-title daily interest curves over 24 months",
        status="live", relevance=85, reliability=93,
        bias="global readership (India among largest reader bases, but not India-only)",
        noise="opensearch title resolution can hit film/manga article; release spikes dominate",
        mitigation="used for curve SHAPE (momentum) not absolute cross-title levels; "
                   "resolution manifest published for audit",
        coverage="186/200 titles resolved, 731 days each",
    ),
    DataSource(
        key="wiki_hi", name="Wikipedia Pageviews (hi)",
        measures="Indian-language interest proxy",
        status="live", relevance=88, reliability=68,
        bias="Hindi-wiki editor base is small; anime coverage sparse (14/50 titles)",
        noise="opensearch mis-resolution (e.g. 'Bleach' → town 'Balachaur')",
        mitigation="existence treated as a positive binary signal; <100-day coverage "
                   "rows dropped; manifest published",
        coverage="14/50 titles on hi.wikipedia",
    ),
    DataSource(
        key="trends", name="Google Trends (geo=IN)",
        measures="Indian search demand, weekly, 5 years",
        status="live", relevance=95, reliability=74,
        bias="Google users: urban/young/English skew; misses offline and non-Google India",
        noise="sampled & self-normalized 0-100 per keyword — NOT comparable across keywords; "
              "ambiguous queries ('one piece')",
        mitigation="used for trend direction & inflection only; never cross-keyword "
                   "absolute comparison",
        coverage="10 keywords x 265 weeks (geo=IN)",
    ),
    DataSource(
        key="youtube", name="YouTube Data v3 (regionCode=IN)",
        measures="dub-clip/edit/reactor engagement; linguistic-hub probes (Ta/Te/Bn/Mr)",
        status="pending_key", relevance=90, reliability=82,
        bias="cumulative lifetime counters need upload-date normalization; fan edits pollute title search",
        noise="views inflate on shorts/re-uploads; official vs unofficial channels mixed",
        mitigation="planned: engagement-per-day-since-upload; official channel & dub-upload "
                   "weighting; awaiting API key",
        coverage="pending key (script ready)",
    ),
    DataSource(
        key="reddit", name="Reddit r/AnimeIndia",
        measures="Indian community discussion ground truth",
        status="blocked", relevance=55, reliability=40,
        bias="tiny power-user base vs market; meme skew",
        noise="self-promotion,vote dynamics",
        mitigation="qualitative validation of seed list only — not a scored feature; "
                   "403 without OAuth (token pending)",
        coverage="blocked this run",
    ),
    DataSource(
        key="seed", name="Curated India seed + state data",
        measures="evidence-graded India success cases; state demographics",
        status="live", relevance=85, reliability=70,
        bias="curator selection; evidence strength varies by row (graded strong/moderate/weak)",
        noise="press-derived claims not all independently verifiable",
        mitigation="weak rows flagged as hypotheses; 2024 state figures marked as estimates; "
                   "census 2011 columns exact",
        coverage="24 titles graded; 34 states/UTs",
    ),
]


def get_matrix() -> list[dict]:
    """Return the matrix as dicts (dashboard/export friendly)."""
    return [vars(s) for s in SOURCES]
