"""X/Twitter & Telegram microblog ingestion.

Upstream clones: vladkens/twscrape (MIT), d60/twikit (MIT),
tweepy/tweepy (MIT), lonamiwebs/telethon (MIT).

Exposed capabilities:
- ``source`` / ``x_scrape``   - account-pool X search (twscrape, no API key)
- ``source`` / ``x_client``   - cookie-based X client (twikit, no API key)
- ``source`` / ``x_official`` - official X API v2 (tweepy, keys required)
- ``source`` / ``telegram``   - public Telegram channel/group sampling (opt-in)
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

from engine_api import Evidence, Query, provider

from ._bootstrap import ProviderError, ensure_paths


def _tweet_evidence(item: dict[str, Any], source: str) -> Evidence:
    url = item.get("url") or (
        f"https://x.com/{item.get('screen_name') or item.get('username') or 'i'}/status/{item.get('id')}"
    )
    published = item.get("created_at")
    if isinstance(published, str):
        try:
            published = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError:
            published = None
    return Evidence(
        source=source,
        url=url,
        title=None,
        content=str(item.get("text") or ""),
        published_at=published if isinstance(published, datetime) else None,
        metadata={
            "author": item.get("screen_name") or item.get("username") or item.get("author"),
            "likes": item.get("like_count") or item.get("favorite_count"),
            "retweets": item.get("retweet_count") or item.get("retweet_count"),
            "views": item.get("view_count"),
            "query": item.get("_query"),
        },
    )


class XScrapeSource:
    """EvidenceSource over twscrape (async X search via account pool)."""

    name = "x_scrape"

    def __init__(self, db_path: str | None = None, timeout: float = 30.0) -> None:
        ensure_paths("twscrape")
        self._db = db_path or os.environ.get("TWSCRAPE_DB", "twscrape.db")
        self._timeout = timeout

    def fetch(self, query: Query) -> list[Evidence]:
        try:
            import twscrape  # lazy upstream import
            from twscrape import API, AccountsPool
        except Exception as exc:
            raise ProviderError(f"twscrape unavailable: {exc}") from exc

        limit = min(query.limit or 20, 40)
        params = {"query": query.text, "limit": limit, **(query.extra.get("params") or {})}

        async def _run() -> list[dict[str, Any]]:
            pool = AccountsPool(self._db)
            api = API(pool)
            out = []
            async for tw in api.search(params["query"], limit=params["limit"]):
                out.append({
                    "id": str(tw.id),
                    "text": tw.text,
                    "created_at": tw.date.isoformat() if tw.date else None,
                    "like_count": tw.likeCount,
                    "retweet_count": tw.retweetCount,
                    "view_count": getattr(tw, "viewCount", None),
                    "screen_name": getattr(tw.user, "screenName", None),
                    "_query": params["query"],
                })
            return out

        try:
            rows = asyncio.run(asyncio.wait_for(_run(), timeout=self._timeout))
        except asyncio.TimeoutError as exc:
            raise ProviderError(f"x_scrape timed out after {self._timeout}s") from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                f"x_scrape failed ({exc}); add accounts first: twscrape add_accounts ..."
            ) from exc
        return [_tweet_evidence(r, self.name) for r in rows]


class XClientSource:
    """EvidenceSource over twikit (cookie login, no developer keys)."""

    name = "x_client"

    def __init__(self, auth: tuple[str, str] | None = None, timeout: float = 30.0) -> None:
        ensure_paths("twikit")
        self._auth = auth  # (email, password) or None -> env below
        self._timeout = timeout

    def fetch(self, query: Query) -> list[Evidence]:
        try:
            from twikit import Client  # lazy upstream import
        except Exception as exc:
            raise ProviderError(f"twikit unavailable: {exc}") from exc

        email, password = self._auth or (
            os.environ.get("X_EMAIL"), os.environ.get("X_PASSWORD"))
        auth_token = os.environ.get("X_AUTH_TOKEN")
        ct0 = os.environ.get("X_CT0")
        limit = min(query.limit or 20, 40)

        async def _run() -> list[dict[str, Any]]:
            client = Client("en-US")
            if auth_token and ct0:
                client.set_cookies({"auth_token": auth_token, "ct0": ct0})
            elif email and password:
                await client.login(user_auth=(email, password))
            else:
                raise ProviderError(
                    "x_client needs X_AUTH_TOKEN+X_CT0 or X_EMAIL+X_PASSWORD"
                )
            results = await client.search_tweet(query.text, limit=limit)
            return [
                {
                    "id": t.id,
                    "text": t.text,
                    "created_at": t.created_at,
                    "like_count": t.favorite_count,
                    "retweet_count": t.retweet_count,
                    "screen_name": getattr(t.user, "screen_name", None),
                    "_query": query.text,
                }
                for t in results
            ]

        try:
            rows = asyncio.run(asyncio.wait_for(_run(), timeout=self._timeout))
        except ProviderError:
            raise
        except asyncio.TimeoutError as exc:
            raise ProviderError(f"x_client timed out after {self._timeout}s") from exc
        except Exception as exc:
            raise ProviderError(f"x_client failed: {exc}") from exc
        return [_tweet_evidence(r, self.name) for r in rows]


class XOfficialSource:
    """EvidenceSource over the official X API v2 (bearer token)."""

    name = "x_official"

    def __init__(self, bearer_token: str | None = None) -> None:
        ensure_paths("tweepy")
        self._token = bearer_token or os.environ.get("X_BEARER_TOKEN")

    def fetch(self, query: Query) -> list[Evidence]:
        if not self._token:
            raise ProviderError("x_official requires X_BEARER_TOKEN")
        try:
            import tweepy  # lazy upstream import
        except Exception as exc:
            raise ProviderError(f"tweepy unavailable: {exc}") from exc
        client = tweepy.Client(bearer_token=self._token, wait_on_rate_limit=True)
        try:
            resp = client.search_recent_tweets(
                query=query.text,
                max_results=min(max(query.limit or 10, 10), 100),
                tweet_fields=["created_at", "public_metrics", "author_id"],
            )
        except Exception as exc:
            raise ProviderError(f"x_official search failed: {exc}") from exc
        out: list[Evidence] = []
        for tw in resp.data or []:
            metrics = tw.public_metrics or {}
            out.append(
                _tweet_evidence(
                    {
                        "id": str(tw.id),
                        "text": tw.text,
                        "created_at": tw.created_at.isoformat() if tw.created_at else None,
                        "like_count": metrics.get("like_count"),
                        "retweet_count": metrics.get("retweet_count"),
                        "view_count": metrics.get("impression_count"),
                        "author": str(tw.author_id),
                        "_query": query.text,
                    },
                    self.name,
                )
            )
        return out


class TelegramSource:
    """EvidenceSource: public Telegram channels/groups via Telethon (opt-in).

    Requires TELEGRAM_API_ID / TELEGRAM_API_HASH and a one-time login
    (user session); only public entities are read.
    """

    name = "telegram"

    def __init__(self, entities: tuple[str, ...] = (), limit: int = 20) -> None:
        ensure_paths("telethon")
        self._entities = entities
        self._limit = limit

    def fetch(self, query: Query) -> list[Evidence]:
        api_id = os.environ.get("TELEGRAM_API_ID")
        api_hash = os.environ.get("TELEGRAM_API_HASH")
        if not (api_id and api_hash):
            raise ProviderError("telegram needs TELEGRAM_API_ID + TELEGRAM_API_HASH")
        try:
            from telethon import TelegramClient  # lazy upstream import
        except Exception as exc:
            raise ProviderError(f"telethon unavailable: {exc}") from exc

        entities = tuple(query.extra.get("entities") or self._entities)
        if not entities:
            raise ProviderError("telegram source needs extra['entities'] (public @channels)")

        async def _run() -> list[dict[str, Any]]:
            session = os.environ.get("TELEGRAM_SESSION", "sakura_telegram")
            async with TelegramClient(session, int(api_id), api_hash) as client:
                out: list[dict[str, Any]] = []
                for entity in entities:
                    async for msg in client.iter_messages(entity, search=query.text,
                                                          limit=self._limit):
                        if not msg.text:
                            continue
                        out.append({
                            "id": msg.id,
                            "text": msg.text,
                            "created_at": msg.date.isoformat() if msg.date else None,
                            "views": getattr(msg, "views", None),
                            "entity": str(entity),
                            "url": f"https://t.me/{str(entity).lstrip('@')}/{msg.id}",
                        })
                return out

        try:
            rows = asyncio.run(_run())
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"telegram fetch failed: {exc}") from exc
        return [
            Evidence(
                source=self.name,
                url=r["url"],
                content=r["text"],
                published_at=datetime.fromisoformat(r["created_at"]) if r["created_at"] else None,
                metadata={"entity": r["entity"], "views": r["views"], "query": query.text},
            )
            for r in rows
        ]


@provider("source", "x_scrape")
def _xscrape(**config: Any) -> XScrapeSource:
    return XScrapeSource(**config)


@provider("source", "x_client")
def _xclient(**config: Any) -> XClientSource:
    return XClientSource(**config)


@provider("source", "x_official")
def _xofficial(**config: Any) -> XOfficialSource:
    return XOfficialSource(**config)


@provider("source", "telegram")
def _tg(**config: Any) -> TelegramSource:
    return TelegramSource(**config)


__all__ = ["XScrapeSource", "XClientSource", "XOfficialSource", "TelegramSource"]
