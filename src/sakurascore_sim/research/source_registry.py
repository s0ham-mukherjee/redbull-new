"""Static registry of research sources used (or considered) by SakuraScore India.

This is the machine-readable companion of docs/RESEARCH_SOURCE_MAP.md. Each entry
records access method, terms posture and quality so that every evidence item can
be traced back to a defined collection method. Nothing here performs network I/O.

Policies encoded in this registry:
  * Only official APIs / permitted access methods are listed as "used".
  * Sources that would require auth bypass, paywall circumvention or private-data
    harvesting are listed with status "rejected" and an explicit reason.
  * Agent-Reach is listed as "adapt_planned": credential-free channels only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

STATUS_USED = "used"
STATUS_ADAPT_PLANNED = "adapt_planned"
STATUS_REJECTED = "rejected"

REGISTRY: List[Dict[str, Any]] = [
    {
        "source_id": "crunchyroll-news",
        "name": "Crunchyroll News (official announcements)",
        "url": "https://www.crunchyroll.com/news",
        "data_type": "news / official release announcements",
        "geography": "global (incl. India-specific dub announcements)",
        "access_method": "public web pages via web search; official site ToS",
        "auth": "none",
        "terms_note": "Public pages accessed via normal search; no scraping of gated content.",
        "rate_limits": "manual search volume only",
        "quality": "high (first-party distributor statements)",
        "status": STATUS_USED,
    },
    {
        "source_id": "box-office-reporters",
        "name": "Box office trackers (IGN India, Box Office Mojo, IMDb News, Wikipedia)",
        "url": "https://www.boxofficemojo.com/ ; https://in.ign.com/",
        "data_type": "theatrical box office observations",
        "geography": "India + worldwide",
        "access_method": "public pages via web search",
        "auth": "none",
        "terms_note": "Aggregate/press figures cited, not bulk collection.",
        "rate_limits": "manual",
        "quality": "high for headline numbers; medium for fan-tracked daily figures",
        "status": STATUS_USED,
    },
    {
        "source_id": "market-research-reports",
        "name": "Market research publishers (Ken Research, MarkNtel, Grand View)",
        "url": "https://www.kenresearch.com/industry-reports/india-anime-market",
        "data_type": "market sizing, growth rates, audience estimates",
        "geography": "India / global",
        "access_method": "public summary pages via web search",
        "auth": "none",
        "terms_note": "Only free summary figures cited; methodology of reports not audited (flagged in quality).",
        "rate_limits": "manual",
        "quality": "medium (commercial estimates, methodology opaque)",
        "status": STATUS_USED,
    },
    {
        "source_id": "industry-press",
        "name": "Industry press (Forbes, Variety, Japan Times, ANN, Cartoon Brew, CBR)",
        "url": "https://www.animenewsnetwork.com/",
        "data_type": "survey coverage (NRG), industry strategy, streaming announcements",
        "geography": "global + India coverage",
        "access_method": "public pages via web search",
        "auth": "none",
        "terms_note": "Article-level citation; no bulk scraping.",
        "rate_limits": "manual",
        "quality": "medium-high (secondary reporting of primary surveys/earnings)",
        "status": STATUS_USED,
    },
    {
        "source_id": "official-social-pages",
        "name": "Official social pages of distributors/IP holders (e.g. Ani-One/Muse India YouTube, official Facebook pages)",
        "url": "https://www.youtube.com/@MuseIndia",
        "data_type": "dub availability, channel scale, engagement signals",
        "geography": "India",
        "access_method": "public channel pages; future: YouTube Data API v3 (key required, free quota)",
        "auth": "none for public pages; API key for programmatic access",
        "terms_note": "Only public posts; no private data. Programmatic path should use the official YouTube Data API.",
        "rate_limits": "YouTube Data API quota if automated",
        "quality": "high for dub availability; medium for audience proxies (subscriber counts)",
        "status": STATUS_USED,
    },
    {
        "source_id": "reddit-public-web",
        "name": "Reddit public threads via web search (r/AnimeMirchi, r/animeindian, r/boxoffice)",
        "url": "https://www.reddit.com/r/AnimeMirchi/",
        "data_type": "community discussion signals",
        "geography": "India-focused subreddits",
        "access_method": "public web search results only (no unauthenticated API hammering, no login scraping)",
        "auth": "none",
        "terms_note": "Fan communities; figures unverified. Reddit ToS restricts unauthenticated bulk access; we therefore only cite individual public search results.",
        "rate_limits": "manual",
        "quality": "low-medium (community reporting)",
        "status": STATUS_USED,
    },
    {
        "source_id": "agent-reach",
        "name": "Agent-Reach (Panniantong/Agent-Reach, MIT) — credential-free channels: web (Exa/Jina), YouTube via yt-dlp, GitHub",
        "url": "https://github.com/Panniantong/Agent-Reach",
        "data_type": "repeatable multi-source research pipeline",
        "geography": "varies by channel",
        "access_method": "CLI subprocess with fixed query list; JSON envelope with url/published_at provenance",
        "auth": "none for default channels (login channels deliberately NOT used)",
        "terms_note": "Read-only tool; refuses anti-bot circumvention. We exclude login-required channels and CloakBrowser (non-MIT binary licence).",
        "rate_limits": "built-in cooldowns/backoff; we persist outputs ourselves (tool has no cache)",
        "quality": "structural (pipeline), not a source itself",
        "status": STATUS_ADAPT_PLANNED,
    },
    {
        "source_id": "youtube-data-api",
        "name": "YouTube Data API v3 (official)",
        "url": "https://developers.google.com/youtube/v3",
        "data_type": "video metadata, view/like counts, channel stats for dub/trailer videos",
        "geography": "global",
        "access_method": "official API, API key required (free quota)",
        "auth": "API key",
        "terms_note": "Official API; respects quota. Preferred programmatic path over scraping.",
        "rate_limits": "10k units/day default quota",
        "quality": "high",
        "status": STATUS_ADAPT_PLANNED,
    },
    {
        "source_id": "x-twitter",
        "name": "X / Twitter",
        "url": "https://x.com",
        "data_type": "would-be social discussion signals",
        "geography": "global",
        "access_method": "n/a",
        "auth": "paid API only",
        "terms_note": "REJECTED for this project: no budget for paid API; unauthenticated scraping and login-session reuse violate ToS and our data-access policy.",
        "rate_limits": "n/a",
        "quality": "n/a",
        "status": STATUS_REJECTED,
    },
    {
        "source_id": "private-communities",
        "name": "Private/DM community data (WhatsApp groups, Discord servers, private accounts)",
        "url": "n/a",
        "data_type": "n/a",
        "geography": "n/a",
        "access_method": "n/a",
        "auth": "n/a",
        "terms_note": "REJECTED by policy: private messages and private account data are never collected.",
        "rate_limits": "n/a",
        "quality": "n/a",
        "status": STATUS_REJECTED,
    },
]


def get_source(source_id: str) -> Optional[Dict[str, Any]]:
    for entry in REGISTRY:
        if entry["source_id"] == source_id:
            return entry
    return None


def registry_summary() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for entry in REGISTRY:
        out[entry["status"]] = out.get(entry["status"], 0) + 1
    return out
