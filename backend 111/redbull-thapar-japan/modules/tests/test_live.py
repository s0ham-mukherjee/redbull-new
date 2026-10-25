"""Opt-in LIVE smoke tests — prove the real network pull path end to end.

These are the only tests that leave the machine. Everything else in this
suite is offline and deterministic.

Run them explicitly::

    python -m pytest tests -q --run-live -m live

Each test pre-flights the endpoint with a 6s HTTP probe; if the network is
blocked (e.g. Jikan is blocked from this collector network per the evidence
matrix) the test SKIPs with a clear reason instead of failing — a restricted
network is not an engine defect.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date

import pytest

from engine_api import Query

pytestmark = pytest.mark.live

JIKAN_PROBE = "https://api.jikan.moe/v4/anime?q=naruto&limit=1"
WIKIMEDIA_PROBE = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia/all-access/user/Naruto/daily/20260901/20260905"
)


def _reachable(url: str) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SakuraScoreIndia/1.0 (test)"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            return resp.status == 200, f"HTTP {resp.status}"
    except Exception as exc:  # noqa: BLE001 - any probe failure means skip
        return False, str(exc)[:120]


@pytest.fixture(scope="module")
def jikan_up() -> None:
    ok, why = _reachable(JIKAN_PROBE)
    if not ok:
        pytest.skip(f"Jikan unreachable from this network ({why}) — matches "
                    "the evidence-matrix 'blocked' status")


@pytest.fixture(scope="module")
def wikimedia_up() -> None:
    ok, why = _reachable(WIKIMEDIA_PROBE)
    if not ok:
        pytest.skip(f"Wikimedia pageviews unreachable ({why})")


def test_live_jikan_evidence_pull(jikan_up):
    """AnimeMetadataSource.fetch against the real Jikan/MAL API."""
    from providers.anime_metadata import AnimeMetadataSource

    src = AnimeMetadataSource(min_interval=0.0)
    evidence = src.fetch(Query(text="naruto", limit=2))
    assert evidence, "expected at least one result for 'naruto'"
    for ev in evidence[:2]:
        assert ev.source == "anime_metadata"
        assert ev.url.startswith("https://myanimelist.net/") or ev.url == ""
        payload = json.loads(ev.content)
        assert payload.get("title")
        assert ev.content_hash and len(ev.content_hash) == 64


def test_live_jikan_ip_node_projection(jikan_up):
    """Live pull -> canonical IPNode projection (the ingestion path)."""
    from providers.anime_metadata import AnimeMetadataSource

    src = AnimeMetadataSource(min_interval=0.0)
    evidence = src.fetch(Query(text="naruto", limit=1))
    node = AnimeMetadataSource.to_ip_node(json.loads(evidence[0].content))
    assert node.id.startswith("mal:") and node.id != "mal:None"
    assert node.title
    assert node.kind in ("anime", "manga")


def test_live_wikimedia_pageview_signals(wikimedia_up):
    """WikiPageviewSource.series against the real Wikimedia REST API."""
    src = __import__("providers.pageviews", fromlist=["WikiPageviewSource"]).WikiPageviewSource()
    signals = src.series(Query(text="Naruto", limit=5,
                               extra={"start": date(2026, 9, 1),
                                      "end": date(2026, 9, 5)}))
    assert signals, "expected pageview signals for Naruto"
    assert all(s.name == "wiki_pageviews:Naruto" for s in signals)
    assert all(s.value >= 0 for s in signals)
    assert all(s.source == "wiki_pageviews" for s in signals)
    assert all(s.metadata["date"] for s in signals)
    # CURRENT BEHAVIOR (live-verified 2026-10-24): window_start is None on
    # every signal from the REAL mwviews client — pageviews.py:63 parses day
    # keys as '%Y%m%d' strings but mwviews returns datetime.date keys, so
    # str(date)[:10] ('2026-09-01') fails the parse. The raw date survives
    # only in metadata['date']. If this assertion fails, the provider was
    # FIXED — update BACKEND_MAP finding #18 and remove this pin.
    assert all(s.window_start is None for s in signals)


def test_live_wikimedia_hindi_project(wikimedia_up):
    """Same provider against hi.wikipedia (the Indian-language proxy).

    Uses भारत (India) — an article guaranteed to exist on hi.wikipedia.
    A nonexistent article makes mwviews raise (wrapped as ProviderError),
    which is current behavior, not a bug.
    """
    WikiPageviewSource = __import__(
        "providers.pageviews", fromlist=["WikiPageviewSource"]).WikiPageviewSource
    src = WikiPageviewSource()
    signals = src.series(Query(text="भारत", limit=5,
                               extra={"project": "hi.wikipedia",
                                      "start": date(2026, 8, 1),
                                      "end": date(2026, 8, 5)}))
    assert signals, "hi.wikipedia भारत must have pageviews"
    assert all(s.metadata["project"] == "hi.wikipedia" for s in signals)
    assert all(s.value >= 0 for s in signals)
