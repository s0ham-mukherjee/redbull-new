"""Anime/manga metadata ingestion (upstream clone: abhinavk99/jikanpy, MIT).

Exposed capability: ``source`` / ``anime_metadata`` - searches the Jikan
(MyAnimeList) API and returns provenance-bearing evidence, plus helpers to
project results into canonical :class:`IPNode` graph nodes.
"""

from __future__ import annotations

import json
import time
from typing import Any

from engine_api import Evidence, IPNode, Query, provider

from ._bootstrap import ProviderError, ensure_paths


class AnimeMetadataSource:
    """EvidenceSource over the Jikan REST API (free, 3 req/s)."""

    name = "anime_metadata"

    def __init__(self, min_interval: float = 0.34, session: Any = None) -> None:
        ensure_paths("jikanpy")
        from jikanpy import Jikan  # lazy upstream import

        # Jikan accepts (selected_base, session); per-request timeouts go
        # through the injected requests.Session instead.
        if session is None:
            import requests

            session = requests.Session()
            session.timeout = 15.0  # type: ignore[attr-defined]
        self._client = Jikan(session=session)
        self._min_interval = min_interval
        self._last_call = 0.0

    # -- rate limiting -----------------------------------------------------
    def _throttle(self) -> None:
        delta = time.monotonic() - self._last_call
        if delta < self._min_interval:
            time.sleep(self._min_interval - delta)
        self._last_call = time.monotonic()

    # -- EvidenceSource ----------------------------------------------------
    def fetch(self, query: Query) -> list[Evidence]:
        search_type = str(query.extra.get("search_type", "anime"))
        page = query.extra.get("page")
        self._throttle()
        try:
            payload = self._client.search(search_type, query.text, page=page)
        except Exception as exc:  # upstream raises JikanException subclasses
            raise ProviderError(f"jikan search failed: {exc}") from exc

        results = payload.get("data") or []
        limit = max(1, query.limit)
        evidence: list[Evidence] = []
        for item in results[:limit]:
            content = json.dumps(item, ensure_ascii=False, sort_keys=True)
            evidence.append(
                Evidence(
                    source=self.name,
                    url=str(item.get("url") or ""),
                    title=item.get("title"),
                    content=content,
                    metadata={
                        "mal_id": item.get("mal_id"),
                        "type": item.get("type"),
                        "episodes": item.get("episodes"),
                        "score": item.get("score"),
                        "members": item.get("members"),
                        "genres": [g.get("name") for g in item.get("genres") or []],
                        "studios": [s.get("name") for s in item.get("studios") or []],
                        "query": query.text,
                    },
                )
            )
        return evidence

    # -- graph projection helpers -----------------------------------------
    @staticmethod
    def to_ip_node(item: dict[str, Any]) -> IPNode:
        """Map one Jikan result dict to a canonical IPNode."""
        relation = item.get("relation") or {}
        adaptation_of = None
        for prev in item.get("related") or []:
            if "adaptation" in str(prev.get("relation", "")).lower():
                adaptation_of = str(prev.get("entry", [{}])[0].get("name") or "") or None
                break
        del relation  # relation text is advisory only
        return IPNode(
            id=f"mal:{item.get('mal_id')}",
            title=str(item.get("title") or ""),
            kind="anime" if item.get("type") in (None, "TV", "Movie", "OVA", "ONA", "Special") else "manga",
            genres=tuple(g.get("name", "") for g in item.get("genres") or []),
            studio=(item.get("studios") or [{}])[0].get("name"),
            adaptation_of=adaptation_of,
            aliases=tuple(
                a for a in (item.get("title_japanese"), item.get("title_english")) if a
            ),
            attributes={
                "source": "jikan",
                "score": item.get("score"),
                "members": item.get("members"),
                " aired_from": item.get("aired", {}).get("from"),
            },
        )


@provider("source", "anime_metadata")
def _factory(**config: Any) -> AnimeMetadataSource:
    return AnimeMetadataSource(**config)
