"""X/Twitter + Telegram: _tweet_evidence parsing and offline constructor paths."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine_api import Query
from engine_api.protocols import EvidenceSource
from providers._bootstrap import ProviderError
from providers.microblog import (
    TelegramSource,
    XClientSource,
    XOfficialSource,
    XScrapeSource,
    _tweet_evidence,
)


# ---------------------------------------------------------------------------
# _tweet_evidence
# ---------------------------------------------------------------------------


def _item(**overrides):
    base = dict(
        id="123",
        text="naruto hindi dub when?",
        created_at="2024-01-15T10:00:00Z",
        like_count=10,
        retweet_count=7,
        view_count=500,
        screen_name="weeb_1",
        url="https://x.com/weeb_1/status/123",
        _query="naruto",
    )
    base.update(overrides)
    return base


def test_tweet_evidence_full_item():
    ev = _tweet_evidence(_item(), "x_official")
    assert ev.source == "x_official"
    assert ev.url == "https://x.com/weeb_1/status/123"
    assert ev.title is None
    assert ev.content == "naruto hindi dub when?"
    assert ev.published_at == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
    assert ev.metadata == {
        "author": "weeb_1",
        "likes": 10,
        "retweets": 7,
        "views": 500,
        "query": "naruto",
    }


def test_tweet_evidence_url_missing_uses_screen_name():
    ev = _tweet_evidence(_item(url=None), "s")
    assert ev.url == "https://x.com/weeb_1/status/123"


def test_tweet_evidence_url_missing_uses_username():
    ev = _tweet_evidence(_item(url=None, screen_name=None, username="alt_name"), "s")
    assert ev.url == "https://x.com/alt_name/status/123"


def test_tweet_evidence_url_missing_no_names_uses_i():
    ev = _tweet_evidence(_item(url=None, screen_name=None, username=None), "s")
    assert ev.url == "https://x.com/i/status/123"


def test_tweet_evidence_author_precedence():
    # screen_name > username > author > None
    assert _tweet_evidence(_item(), "s").metadata["author"] == "weeb_1"
    ev = _tweet_evidence(_item(screen_name=None, username="u1"), "s")
    assert ev.metadata["author"] == "u1"
    ev2 = _tweet_evidence(_item(screen_name=None, username=None, author="a1"), "s")
    assert ev2.metadata["author"] == "a1"
    ev3 = _tweet_evidence({"id": "1", "text": "t"}, "s")
    assert ev3.metadata["author"] is None


def test_tweet_evidence_likes_fallback_favorite_count():
    assert _tweet_evidence(_item(like_count=None, favorite_count=99), "s") \
        .metadata["likes"] == 99
    assert _tweet_evidence({"id": "1"}, "s").metadata["likes"] is None


def test_tweet_evidence_retweets_duplicate_key_current_behavior():
    # FINDING #2 (microblog.py:44): "retweet_count" appears twice in the dict
    # literal, so retweets is just retweet_count (or the or-fallback value).
    assert _tweet_evidence(_item(), "s").metadata["retweets"] == 7
    # 0 or 0 -> 0 (falsy first operand falls through to the identical second)
    assert _tweet_evidence(_item(retweet_count=0), "s").metadata["retweets"] == 0
    assert _tweet_evidence({"id": "1"}, "s").metadata["retweets"] is None
    # desired fallback to a secondary metric -> test_bugs.py


def test_tweet_evidence_created_at_invalid_iso_gives_none():
    ev = _tweet_evidence(_item(created_at="not-a-date"), "s")
    assert ev.published_at is None


def test_tweet_evidence_created_at_offset_form():
    ev = _tweet_evidence(_item(created_at="2024-06-01T12:30:45+05:30"), "s")
    assert ev.published_at == datetime.fromisoformat("2024-06-01T12:30:45+05:30")


def test_tweet_evidence_created_at_datetime_object_passes_through():
    dt = datetime(2023, 5, 5, tzinfo=timezone.utc)
    ev = _tweet_evidence(_item(created_at=dt), "s")
    assert ev.published_at is dt  # isinstance(str) is False -> used verbatim


def test_tweet_evidence_created_at_non_datetime_non_str_is_none():
    ev = _tweet_evidence(_item(created_at=1700000000), "s")
    assert ev.published_at is None


def test_tweet_evidence_created_at_none_is_none():
    assert _tweet_evidence(_item(created_at=None), "s").published_at is None


def test_tweet_evidence_text_missing_becomes_empty_string():
    ev = _tweet_evidence({"id": "1"}, "s")
    assert ev.content == ""
    assert _tweet_evidence({"id": "1", "text": 123}, "s").content == "123"


def test_tweet_evidence_minimal_item():
    ev = _tweet_evidence({"id": "9"}, "x_scrape")
    assert ev.url == "https://x.com/i/status/9"
    assert ev.metadata["views"] is None and ev.metadata["query"] is None


# ---------------------------------------------------------------------------
# Constructors all work offline (lazy imports inside fetch only)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("make", [
    lambda: XScrapeSource(),
    lambda: XScrapeSource(db_path="/tmp/x.db", timeout=1.5),
    lambda: XClientSource(),
    lambda: XClientSource(auth=("a@b.c", "pw")),
    lambda: XOfficialSource(bearer_token="tok"),
    lambda: TelegramSource(),
    lambda: TelegramSource(entities=("@channel",), limit=5),
])
def test_constructors_offline(make):
    src = make()
    assert isinstance(src, EvidenceSource)


def test_x_sources_satisfy_protocol_and_names():
    assert XScrapeSource().name == "x_scrape"
    assert XClientSource().name == "x_client"
    assert XOfficialSource().name == "x_official"
    assert TelegramSource().name == "telegram"


# ---------------------------------------------------------------------------
# Offline error paths
# ---------------------------------------------------------------------------


def test_x_official_fetch_without_token(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    with pytest.raises(ProviderError, match="X_BEARER_TOKEN"):
        XOfficialSource(bearer_token=None).fetch(Query(text="q"))


def test_x_official_token_env_fallback(monkeypatch):
    monkeypatch.setenv("X_BEARER_TOKEN", "env-token")
    assert XOfficialSource()._token == "env-token"


def test_telegram_fetch_without_api_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    with pytest.raises(ProviderError, match="TELEGRAM_API_ID"):
        TelegramSource().fetch(Query(text="q"))


def test_telegram_fetch_with_env_but_no_entities(monkeypatch):
    # env present, no entities -> actionable ProviderError. Depending on the
    # clone state, the telethon import itself may fail first; both paths carry
    # an actionable message (current behavior).
    monkeypatch.setenv("TELEGRAM_API_ID", "123456")
    monkeypatch.setenv("TELEGRAM_API_HASH", "abcdef")
    with pytest.raises(ProviderError) as exc:
        TelegramSource(entities=()).fetch(Query(text="q", extra={}))
    msg = str(exc.value)
    assert ("extra['entities']" in msg) or ("telethon unavailable" in msg), msg


def test_x_scrape_db_path_env_fallback(monkeypatch):
    monkeypatch.setenv("TWSCRAPE_DB", "/tmp/env.db")
    assert XScrapeSource()._db == "/tmp/env.db"


def test_x_sources_via_registry(reg):
    for name, cls in [("x_scrape", XScrapeSource), ("x_client", XClientSource),
                      ("x_official", XOfficialSource), ("telegram", TelegramSource)]:
        src = reg.create("source", name)
        assert isinstance(src, cls)
        assert isinstance(src, EvidenceSource)
