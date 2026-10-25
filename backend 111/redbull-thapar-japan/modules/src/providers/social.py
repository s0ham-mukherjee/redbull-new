"""Reddit & YouTube discussion/video ingestion.

Upstream clones: praw-dev/praw (BSD-2-Clause), yt-dlp/yt-dlp (Unlicense).

Exposed capabilities:
- ``source`` / ``reddit`` - structured threads + comment trees (Feature 5).
- ``source`` / ``youtube`` - trailer metadata, view velocity, captions (Features 25/26/30/40).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from engine_api import Evidence, Query, provider

from ._bootstrap import ProviderError, ensure_paths


class RedditSource:
    """EvidenceSource over Reddit via PRAW (OAuth app credentials required)."""

    name = "reddit"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str = "SakuraScoreIndia/1.0",
        subreddits: tuple[str, ...] = ("AnimeIndia", "manga", "IndianAnimeClub"),
        comments_per_thread: int = 10,
    ) -> None:
        ensure_paths("praw")
        self._client_id = client_id or os.environ.get("REDDIT_CLIENT_ID")
        self._client_secret = client_secret or os.environ.get("REDDIT_CLIENT_SECRET")
        self._user_agent = user_agent
        self._subreddits = subreddits
        self._comments_per_thread = comments_per_thread
        self._reddit: Any = None

    @property
    def _client(self) -> Any:
        if self._reddit is None:
            if not (self._client_id and self._client_secret):
                raise ProviderError(
                    "reddit credentials missing: set REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET"
                )
            import praw  # lazy upstream import

            self._reddit = praw.Reddit(
                client_id=self._client_id,
                client_secret=self._client_secret,
                user_agent=self._user_agent,
                check_for_async=False,
            )
        return self._reddit

    def _submission_evidence(self, submission: Any, include_comments: bool) -> Evidence:
        comments: list[dict[str, Any]] = []
        if include_comments:
            try:
                submission.comments.replace_more(limit=0)
                for comment in submission.comments[: self._comments_per_thread]:
                    comments.append(
                        {
                            "body": comment.body,
                            "score": comment.score,
                            "created_utc": comment.created_utc,
                        }
                    )
            except Exception:
                pass
        payload = {
            "title": submission.title,
            "selftext": submission.selftext,
            "score": submission.score,
            "upvote_ratio": getattr(submission, "upvote_ratio", None),
            "num_comments": submission.num_comments,
            "created_utc": submission.created_utc,
            "permalink": f"https://reddit.com{submission.permalink}",
            "comments": comments,
        }
        return Evidence(
            source=self.name,
            url=payload["permalink"],
            title=submission.title,
            content=json.dumps(payload, ensure_ascii=False, default=str),
            published_at=datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
            if submission.created_utc
            else None,
            metadata={
                "subreddit": str(submission.subreddit),
                "score": submission.score,
                "num_comments": submission.num_comments,
                "has_comments": bool(comments),
            },
        )

    def fetch(self, query: Query) -> list[Evidence]:
        subreddit_names = tuple(query.extra.get("subreddits") or self._subreddits)
        sort = str(query.extra.get("sort", "relevance"))
        include_comments = bool(query.extra.get("comments", True))
        out: list[Evidence] = []
        for name in subreddit_names:
            try:
                for submission in self._client.subreddit(name).search(
                    query.text, sort=sort, limit=query.limit
                ):
                    out.append(self._submission_evidence(submission, include_comments))
            except Exception as exc:
                raise ProviderError(f"reddit search failed for r/{name}: {exc}") from exc
        return out


class YouTubeSource:
    """EvidenceSource over YouTube via yt-dlp (metadata + captions, no API key)."""

    name = "youtube"

    def __init__(self, max_videos: int = 10, fetch_captions: bool = False) -> None:
        ensure_paths("yt-dlp")
        self._max_videos = max_videos
        self._fetch_captions = fetch_captions

    def _ydl(self, opts: dict[str, Any]) -> Any:
        import yt_dlp  # lazy upstream import

        return yt_dlp.YoutubeDL(opts)

    def _info_to_evidence(self, info: dict[str, Any]) -> Evidence:
        captions: list[str] = []
        if self._fetch_captions:
            subs = info.get("subtitles") or info.get("automatic_captions") or {}
            captions = [str(code) for code in subs]
        payload = {
            "id": info.get("id"),
            "title": info.get("title"),
            "channel": info.get("channel") or info.get("uploader"),
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
            "comment_count": info.get("comment_count"),
            "duration": info.get("duration"),
            "upload_date": info.get("upload_date"),
            "description": (info.get("description") or "")[:4000],
            "caption_languages": captions,
            "webpage_url": info.get("webpage_url"),
        }
        upload_raw = info.get("upload_date")  # YYYYMMDD
        published = None
        if upload_raw and len(str(upload_raw)) == 8:
            try:
                published = datetime.strptime(str(upload_raw), "%Y%m%d").replace(tzinfo=timezone.utc)
            except ValueError:
                published = None
        return Evidence(
            source=self.name,
            url=str(info.get("webpage_url") or f"https://www.youtube.com/watch?v={info.get('id')}"),
            title=info.get("title"),
            content=json.dumps(payload, ensure_ascii=False, default=str),
            published_at=published,
            metadata={
                "view_count": info.get("view_count"),
                "channel": payload["channel"],
                "upload_date": upload_raw,
                "query_kind": "url" if info.get("_from_url") else "search",
            },
        )

    def fetch(self, query: Query) -> list[Evidence]:
        target = str(query.extra.get("url") or "").strip()
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
            "ignoreerrors": True,
        }
        if target:
            try:
                with self._ydl(opts) as ydl:
                    info = ydl.extract_info(target, download=False)
                if not info:
                    return []
                info["_from_url"] = True
                return [self._info_to_evidence(info)]
            except Exception as exc:
                raise ProviderError(f"yt-dlp failed for {target}: {exc}") from exc

        search = f"ytsearch{min(query.limit or self._max_videos, 25)}:{query.text}"
        try:
            with self._ydl(opts) as ydl:
                result = ydl.extract_info(search, download=False)
        except Exception as exc:
            raise ProviderError(f"yt-dlp search failed: {exc}") from exc
        entries = (result or {}).get("entries") or []
        return [self._info_to_evidence(e) for e in entries if e]


@provider("source", "reddit")
def _reddit_factory(**config: Any) -> RedditSource:
    return RedditSource(**config)


@provider("source", "youtube")
def _youtube_factory(**config: Any) -> YouTubeSource:
    return YouTubeSource(**config)


__all__ = ["RedditSource", "YouTubeSource"]
