"""Multi-backend web research routing (upstream clone: Panniantong/Agent-Reach, MIT).

Exposed capabilities:
- ``router`` / ``multi_channel`` - routes a query to a named channel
  (reddit, youtube, github, web, ...) with upstream fallback handling.
- ``source`` / ``reach_reddit`` - convenience EvidenceSource over the
  reddit channel for Indian anime communities.
"""

from __future__ import annotations

import json
from typing import Any

from engine_api import Evidence, Query, provider

from ._bootstrap import ProviderError, ensure_paths


def _to_evidence(envelope: dict[str, Any], channel: str, fallback_query: str) -> list[Evidence]:
    items = envelope.get("items") or []
    out: list[Evidence] = []
    for item in items:
        if not isinstance(item, dict):
            item = {"value": item}
        url = str(item.get("url") or item.get("link") or item.get("target") or "")
        title = item.get("title") or item.get("name")
        # Prefer explicit text fields; fall back to full JSON payload.
        text = item.get("text") or item.get("content") or item.get("body") or item.get("description")
        content = str(text) if text else json.dumps(item, ensure_ascii=False, default=str)
        out.append(
            Evidence(
                source=f"reach:{channel}",
                url=url,
                title=str(title) if title else None,
                content=content,
                metadata={"channel": channel, "query": fallback_query, "raw": item},
            )
        )
    return out


class MultiChannelResearchRouter:
    """ResearchRouter over Agent-Reach's unified action dispatch."""

    name = "multi_channel"

    def __init__(self, timeout: float = 30.0) -> None:
        ensure_paths("Agent-Reach")
        self._timeout = timeout

    def _run(self, channel: str, action: str, params: dict[str, Any]) -> dict[str, Any]:
        from agent_reach.channels import get_channel  # lazy upstream import
        from agent_reach.runtime.dispatch import run_action

        ch = get_channel(channel)
        if ch is None:
            raise ProviderError(f"unknown research channel: {channel!r}")
        try:
            return run_action(ch, action, params, timeout=self._timeout)
        except Exception as exc:
            raise ProviderError(f"reach {channel}.{action} failed: {exc}") from exc

    def research(self, query: Query) -> list[Evidence]:
        channel = str(query.extra.get("channel", "web"))
        action = str(query.extra.get("action", "search"))
        params: dict[str, Any] = {"query": query.text, "limit": min(query.limit, 25)}
        params.update(query.extra.get("params") or {})
        envelope = self._run(channel, action, params)
        if not envelope.get("ok"):
            err = envelope.get("error") or {}
            raise ProviderError(f"reach error [{err.get('code')}]: {err.get('message')}")
        return _to_evidence(envelope, channel, query.text)

    def read(self, channel: str, target: str) -> list[Evidence]:
        """Fetch a specific item (post/page) as clean evidence."""
        envelope = self._run(channel, "read", {"target": target})
        if not envelope.get("ok"):
            err = envelope.get("error") or {}
            raise ProviderError(f"reach error [{err.get('code')}]: {err.get('message')}")
        return _to_evidence(envelope, channel, target)

    def health(self) -> dict[str, Any]:
        from agent_reach.channels import ALL_CHANNELS  # lazy upstream import

        return {
            "channels": [
                {
                    "name": ch.name,
                    "actions": [a.name for a in ch.actions],
                    "available": bool(getattr(ch, "availability", None) or True),
                }
                for ch in ALL_CHANNELS
            ]
        }


class RedditDiscussionSource:
    """EvidenceSource over Indian anime subreddits via Agent-Reach."""

    name = "reach_reddit"

    def __init__(self, subreddits: tuple[str, ...] = ("AnimeIndia", "manga", "IndianAnimeClub"),
                 limit: int = 15, timeout: float = 30.0) -> None:
        ensure_paths("Agent-Reach")
        self._subreddits = subreddits
        self._limit = limit
        self._timeout = timeout

    def fetch(self, query: Query) -> list[Evidence]:
        from agent_reach.channels import get_channel
        from agent_reach.runtime.dispatch import run_action

        ch = get_channel("reddit")
        if ch is None:
            raise ProviderError("reddit channel unavailable")
        params = {"query": query.text, "limit": min(query.limit or self._limit, 25)}
        try:
            envelope = run_action(ch, "search", params, timeout=self._timeout)
        except Exception as exc:
            raise ProviderError(f"reddit search failed: {exc}") from exc
        if not envelope.get("ok"):
            err = envelope.get("error") or {}
            raise ProviderError(f"reddit error [{err.get('code')}]: {err.get('message')}")
        return _to_evidence(envelope, "reddit", query.text)


@provider("router", "multi_channel")
def _router_factory(**config: Any) -> MultiChannelResearchRouter:
    return MultiChannelResearchRouter(**config)


@provider("source", "reach_reddit")
def _reddit_factory(**config: Any) -> RedditDiscussionSource:
    return RedditDiscussionSource(**config)
