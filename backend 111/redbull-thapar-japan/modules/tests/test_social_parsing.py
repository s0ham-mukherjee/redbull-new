"""Reddit + YouTube parsing edges with fakes (no praw/yt-dlp, no network)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from engine_api import Query
from engine_api.protocols import EvidenceSource
from providers._bootstrap import ProviderError
from providers.social import RedditSource, YouTubeSource


# ---------------------------------------------------------------------------
# RedditSource
# ---------------------------------------------------------------------------


@pytest.fixture()
def no_reddit_creds(monkeypatch):
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)


def test_reddit_fetch_without_creds_actionable_error(no_reddit_creds):
    src = RedditSource(client_id=None, client_secret=None)
    with pytest.raises(ProviderError, match="REDDIT_CLIENT_ID"):
        src.fetch(Query(text="naruto"))


def test_reddit_ctor_env_fallback_no_creds_kept(no_reddit_creds):
    src = RedditSource()
    assert src._client_id is None and src._client_secret is None


def test_reddit_explicit_creds_beat_env(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "env-id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "env-secret")
    src = RedditSource(client_id="explicit-id", client_secret="explicit-secret")
    assert src._client_id == "explicit-id"
    assert src._client_secret == "explicit-secret"


def test_reddit_client_is_lazy_until_accessed(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
    src = RedditSource()
    assert src._reddit is None  # nothing imported/built yet


def test_reddit_client_builds_with_fake_praw(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id-1")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "sec-1")
    built = {}

    class FakeReddit:
        def __init__(self, **kwargs):
            built.update(kwargs)

    fake_praw = SimpleNamespace(Reddit=FakeReddit)
    monkeypatch.setitem(sys.modules, "praw", fake_praw)
    src = RedditSource(user_agent="UA/9")
    client = src._client
    assert client is not None and isinstance(client, FakeReddit)
    assert built == {"client_id": "id-1", "client_secret": "sec-1",
                     "user_agent": "UA/9", "check_for_async": False}
    assert src._client is client  # cached after first build


class CommentList(list):
    def replace_more(self, limit=0):
        pass


class ExplodingComments(CommentList):
    def replace_more(self, limit=0):
        raise RuntimeError("praw exploded")


def _submission(**overrides):
    base = dict(
        title="Best dub of 2024?",
        selftext="Discussion thread body",
        score=42,
        upvote_ratio=0.95,
        num_comments=5,
        created_utc=1700000000,
        permalink="/r/AnimeIndia/abc123",
        subreddit="AnimeIndia",
        comments=CommentList(
            SimpleNamespace(body=f"comment {i}", score=i, created_utc=1700000100 + i)
            for i in range(5)
        ),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_submission_evidence_full_payload():
    src = RedditSource(comments_per_thread=10)
    ev = src._submission_evidence(_submission(), include_comments=True)
    payload = json.loads(ev.content)
    assert payload["title"] == "Best dub of 2024?"
    assert payload["selftext"] == "Discussion thread body"
    assert payload["score"] == 42
    assert payload["upvote_ratio"] == 0.95
    assert payload["num_comments"] == 5
    assert payload["created_utc"] == 1700000000
    assert payload["permalink"] == "https://reddit.com/r/AnimeIndia/abc123"
    assert [c["body"] for c in payload["comments"]] == [f"comment {i}" for i in range(5)]
    assert payload["comments"][0] == {"body": "comment 0", "score": 0,
                                      "created_utc": 1700000100}
    # Evidence-level fields
    assert ev.source == "reddit"
    assert ev.url == "https://reddit.com/r/AnimeIndia/abc123"
    assert ev.title == "Best dub of 2024?"
    assert ev.published_at == datetime.fromtimestamp(1700000000, tz=timezone.utc)
    assert ev.published_at.tzinfo is timezone.utc
    assert ev.metadata == {"subreddit": "AnimeIndia", "score": 42,
                           "num_comments": 5, "has_comments": True}


def test_submission_evidence_respects_comments_per_thread():
    src = RedditSource(comments_per_thread=3)
    ev = src._submission_evidence(_submission(), include_comments=True)
    assert len(json.loads(ev.content)["comments"]) == 3


def test_submission_evidence_include_comments_false():
    src = RedditSource()
    ev = src._submission_evidence(_submission(), include_comments=False)
    payload = json.loads(ev.content)
    assert payload["comments"] == []
    assert ev.metadata["has_comments"] is False


def test_submission_evidence_comment_fetch_failure_swallowed():
    src = RedditSource()
    ev = src._submission_evidence(_submission(comments=ExplodingComments()),
                                  include_comments=True)
    payload = json.loads(ev.content)
    assert payload["comments"] == []
    assert ev.metadata["has_comments"] is False
    assert ev.title == "Best dub of 2024?"  # evidence still built


def test_submission_evidence_created_utc_zero_gives_none():
    src = RedditSource()
    ev = src._submission_evidence(_submission(created_utc=0), include_comments=False)
    assert ev.published_at is None


def test_submission_evidence_missing_upvote_ratio_defaults_none():
    sub = _submission()
    del sub.upvote_ratio  # getattr(submission, "upvote_ratio", None) path
    src = RedditSource()
    payload = json.loads(src._submission_evidence(sub, False).content)
    assert payload["upvote_ratio"] is None


def test_submission_evidence_unicode_payload():
    src = RedditSource()
    ev = src._submission_evidence(_submission(title="ナルト 第2期", selftext="हिंदी डब"),
                                  include_comments=False)
    payload = json.loads(ev.content)
    assert payload["title"] == "ナルト 第2期"
    assert payload["selftext"] == "हिंदी डब"


def test_reddit_source_satisfies_protocol():
    assert isinstance(RedditSource(), EvidenceSource)


def test_reddit_via_registry(reg, no_reddit_creds):
    src = reg.create("source", "reddit")
    assert isinstance(src, EvidenceSource)
    assert src.name == "reddit"


# ---------------------------------------------------------------------------
# YouTubeSource._info_to_evidence
# ---------------------------------------------------------------------------


def _info(**overrides):
    base = dict(
        id="vid42", title="Official Trailer",
        channel="Studio CH", uploader="studio_ch",
        view_count=1_234_567, like_count=12_000, comment_count=340,
        duration=95, upload_date="20240115",
        description="A trailer description",
        webpage_url="https://www.youtube.com/watch?v=vid42",
    )
    base.update(overrides)
    return base


def test_info_to_evidence_full_dict():
    y = YouTubeSource(fetch_captions=True)
    ev = y._info_to_evidence(_info(subtitles={"en": [], "hi": []}))
    payload = json.loads(ev.content)
    assert payload["id"] == "vid42"
    assert payload["title"] == "Official Trailer"
    assert payload["channel"] == "Studio CH"  # channel beats uploader
    assert payload["view_count"] == 1_234_567
    assert payload["upload_date"] == "20240115"
    assert payload["webpage_url"] == "https://www.youtube.com/watch?v=vid42"
    assert ev.source == "youtube"
    assert ev.url == "https://www.youtube.com/watch?v=vid42"
    assert ev.title == "Official Trailer"
    assert ev.published_at == datetime(2024, 1, 15, tzinfo=timezone.utc)
    assert ev.metadata["view_count"] == 1_234_567
    assert ev.metadata["channel"] == "Studio CH"
    assert ev.metadata["upload_date"] == "20240115"
    assert ev.metadata["query_kind"] == "search"  # no _from_url flag


def test_info_to_evidence_channel_falls_back_to_uploader():
    y = YouTubeSource()
    ev = y._info_to_evidence(_info(channel=None))
    assert json.loads(ev.content)["channel"] == "studio_ch"
    assert ev.metadata["channel"] == "studio_ch"


def test_info_to_evidence_url_falls_back_to_watch_link():
    y = YouTubeSource()
    ev = y._info_to_evidence(_info(webpage_url=None))
    assert ev.url == "https://www.youtube.com/watch?v=vid42"


@pytest.mark.parametrize("upload_date", [
    "20231345",  # month 13 -> ValueError -> None
    "2023-1-5",  # wrong shape
    "202315",    # len 5 != 8
    "123456789",  # len 9
    "",
])
def test_info_to_evidence_invalid_upload_date_gives_none(upload_date):
    y = YouTubeSource()
    assert y._info_to_evidence(_info(upload_date=upload_date)).published_at is None


@pytest.mark.parametrize("upload_date,expected", [
    ("20240115", datetime(2024, 1, 15, tzinfo=timezone.utc)),
    ("19990701", datetime(1999, 7, 1, tzinfo=timezone.utc)),
    (20240115, datetime(2024, 1, 15, tzinfo=timezone.utc)),  # int is str()-ed
])
def test_info_to_evidence_valid_upload_date(upload_date, expected):
    y = YouTubeSource()
    assert y._info_to_evidence(_info(upload_date=upload_date)).published_at == expected


def test_info_to_evidence_upload_date_none_gives_none():
    y = YouTubeSource()
    assert y._info_to_evidence(_info(upload_date=None)).published_at is None


def test_info_to_evidence_captions_off_gives_empty_list():
    y = YouTubeSource(fetch_captions=False)
    payload = json.loads(y._info_to_evidence(_info(subtitles={"en": []})).content)
    assert payload["caption_languages"] == []


def test_info_to_evidence_captions_language_codes():
    y = YouTubeSource(fetch_captions=True)
    payload = json.loads(y._info_to_evidence(
        _info(subtitles={"en": [], "hi": [], "ta": []})).content)
    assert payload["caption_languages"] == ["en", "hi", "ta"]


def test_info_to_evidence_automatic_captions_fallback():
    y = YouTubeSource(fetch_captions=True)
    payload = json.loads(y._info_to_evidence(
        _info(subtitles=None, automatic_captions={"en": []})).content)
    assert payload["caption_languages"] == ["en"]


def test_info_to_evidence_description_truncated_to_4000():
    y = YouTubeSource()
    payload = json.loads(y._info_to_evidence(_info(description="x" * 9000)).content)
    assert len(payload["description"]) == 4000


def test_info_to_evidence_description_none_becomes_empty():
    y = YouTubeSource()
    payload = json.loads(y._info_to_evidence(_info(description=None)).content)
    assert payload["description"] == ""


def test_info_to_evidence_from_url_flag_sets_query_kind_url():
    y = YouTubeSource()
    info = _info()
    info["_from_url"] = True
    assert y._info_to_evidence(info).metadata["query_kind"] == "url"


def test_youtube_source_satisfies_protocol():
    assert isinstance(YouTubeSource(), EvidenceSource)


# ---------------------------------------------------------------------------
# YouTubeSource.fetch with a fake yt-dlp context manager
# ---------------------------------------------------------------------------


class FakeYdl:
    """Context-manager standing in for yt_dlp.YoutubeDL."""

    def __init__(self, extract_result=None, calls=None):
        self._extract_result = extract_result
        self._calls = calls if calls is not None else []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, target, download=False):
        self._calls.append(target)
        if isinstance(self._extract_result, Exception):
            raise self._extract_result
        result = self._extract_result
        if callable(result):
            return result(target)
        return result


def _patch_ydl(monkeypatch, src, extract_result, calls):
    monkeypatch.setattr(src, "_ydl", lambda opts: FakeYdl(extract_result, calls))


def test_youtube_fetch_url_path(monkeypatch):
    src = YouTubeSource()
    calls = []
    info = _info()
    _patch_ydl(monkeypatch, src, info, calls)
    out = src.fetch(Query(text="ignored", limit=1,
                          extra={"url": "https://www.youtube.com/watch?v=vid42"}))
    assert calls == ["https://www.youtube.com/watch?v=vid42"]
    assert len(out) == 1
    assert out[0].metadata["query_kind"] == "url"


def test_youtube_fetch_url_path_none_info_returns_empty(monkeypatch):
    src = YouTubeSource()
    calls = []
    _patch_ydl(monkeypatch, src, None, calls)
    out = src.fetch(Query(text="x", extra={"url": "https://u"}))
    assert out == []


def test_youtube_fetch_url_path_failure_raises(monkeypatch):
    src = YouTubeSource()
    _patch_ydl(monkeypatch, src, RuntimeError("boom"), [])
    with pytest.raises(ProviderError, match="yt-dlp failed"):
        src.fetch(Query(text="x", extra={"url": "https://u"}))


def test_youtube_fetch_search_path_filters_none_entries(monkeypatch):
    src = YouTubeSource()
    calls = []
    result = {"entries": [_info(id="a"), None, _info(id="b")]}
    _patch_ydl(monkeypatch, src, result, calls)
    out = src.fetch(Query(text="naruto trailer", limit=10))
    assert len(out) == 2
    assert [ev.metadata["channel"] for ev in out] == ["Studio CH", "Studio CH"]
    assert calls == ["ytsearch10:naruto trailer"]


def test_youtube_fetch_search_limit_cap_and_zero(monkeypatch):
    src = YouTubeSource(max_videos=7)
    calls = []
    _patch_ydl(monkeypatch, src, {"entries": []}, calls)
    src.fetch(Query(text="q", limit=40))       # min(40, 25) -> 25
    src.fetch(Query(text="q", limit=0))        # 0 or max_videos -> min(7,25) -> 7
    src.fetch(Query(text="q"))                 # default 50 -> min(50,25) -> 25
    assert calls == ["ytsearch25:q", "ytsearch7:q", "ytsearch25:q"]


def test_youtube_fetch_search_no_entries(monkeypatch):
    src = YouTubeSource()
    _patch_ydl(monkeypatch, src, {}, [])
    assert src.fetch(Query(text="q")) == []


def test_youtube_fetch_search_none_result(monkeypatch):
    src = YouTubeSource()
    _patch_ydl(monkeypatch, src, None, [])
    assert src.fetch(Query(text="q")) == []


def test_youtube_fetch_search_failure_raises(monkeypatch):
    src = YouTubeSource()
    _patch_ydl(monkeypatch, src, RuntimeError("download page broke"), [])
    with pytest.raises(ProviderError, match="yt-dlp search failed"):
        src.fetch(Query(text="q"))
