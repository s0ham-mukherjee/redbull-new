"""WikiPageviewSource.series with an injected fake mwviews client."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from engine_api import Query
from engine_api.protocols import TimeSeriesSource
from providers._bootstrap import ProviderError
from providers.pageviews import WikiPageviewSource


class FakePageviewsClient:
    def __init__(self, raw=None, error=None):
        self.raw = raw if raw is not None else {}
        self.error = error
        self.calls = []

    def article_views(self, project, articles, start=None, end=None):
        self.calls.append({"project": project, "articles": list(articles),
                           "start": start, "end": end})
        if self.error is not None:
            raise self.error
        return self.raw


@pytest.fixture()
def src():
    s = WikiPageviewSource()
    return s


def _query(**extra):
    return Query(text="Chainsaw Man", extra=extra)


def test_series_maps_raw_dict_of_dicts(src):
    raw = {
        "20240101": {"Chainsaw Man": 5, "Other Article": None},
        "20240102": {"Chainsaw Man": 12},
        "20240103": "not-a-dict",  # skipped
    }
    src._client = lambda: FakePageviewsClient(raw)
    out = src.series(_query())
    assert [s.value for s in out] == [5.0, 12.0]
    assert all(isinstance(s.value, float) for s in out)
    assert out[0].window_start == datetime(2024, 1, 1)
    assert out[0].window_end == datetime(2024, 1, 1)
    assert out[0].name == "wiki_pageviews:Chainsaw Man"
    assert out[0].source == "wiki_pageviews"
    assert out[0].metadata["project"] == "en.wikipedia"
    assert out[0].metadata["article"] == "Chainsaw Man"
    assert out[0].metadata["date"] == "20240101"


def test_series_none_views_skipped(src):
    raw = {"20240101": {"Chainsaw Man": None}}
    src._client = lambda: FakePageviewsClient(raw)
    assert src.series(_query()) == []


def test_series_sorted_by_window_start(src):
    raw = {
        "20240103": {"Chainsaw Man": 3},
        "20240101": {"Chainsaw Man": 1},
        "20240102": {"Chainsaw Man": 2},
    }
    src._client = lambda: FakePageviewsClient(raw)
    out = src.series(_query())
    assert [s.metadata["date"] for s in out] == ["20240101", "20240102", "20240103"]


def test_series_bad_day_key_signal_kept_with_none_window(src):
    raw = {
        "bogus": {"Chainsaw Man": 9},
        "20240101": {"Chainsaw Man": 1},
    }
    src._client = lambda: FakePageviewsClient(raw)
    out = src.series(_query())
    assert len(out) == 2
    # unparseable key -> datetime.min -> sorts first
    assert out[0].window_start is None
    assert out[0].value == 9.0
    assert out[1].window_start == datetime(2024, 1, 1)


def test_series_long_day_key_truncated_unparseable_kept_with_none_window(src):
    # str(day_key)[:10] of a 14-char stamp leaves 10 digits -> %Y%m%d fails
    raw = {"20240101000000": {"Chainsaw Man": 7}}
    src._client = lambda: FakePageviewsClient(raw)
    out = src.series(_query())
    assert len(out) == 1
    assert out[0].window_start is None
    assert out[0].value == 7.0
    assert out[0].metadata["date"] == "20240101000000"


def test_series_article_from_extra_beats_text(src):
    src._client = lambda: FakePageviewsClient(
        {"20240101": {"Naruto": 4, "Chainsaw Man": 8}})
    out = src.series(_query(article="Naruto"))
    assert out[0].name == "wiki_pageviews:Naruto"
    assert out[0].value == 4.0


def test_series_article_text_stripped(src):
    raw = {"20240101": {"Naruto": 2}}
    src._client = lambda: FakePageviewsClient(raw)
    out = src.series(Query(text="  Naruto  "))
    assert out[0].metadata["article"] == "Naruto"
    assert len(out) == 1


@pytest.mark.parametrize("text,extra", [("", {}), ("   ", {}), ("", {"article": " "})])
def test_series_empty_article_raises(src, text, extra):
    with pytest.raises(ProviderError, match="requires an article title"):
        src.series(Query(text=text, extra=extra))


def test_series_project_default_and_override(src):
    fake = FakePageviewsClient({"20240101": {"X": 1}})
    src._client = lambda: fake
    src.series(Query(text="X"))
    assert fake.calls[0]["project"] == "en.wikipedia"
    fake2 = FakePageviewsClient({"20240101": {"X": 1}})
    src._client = lambda: fake2
    src.series(Query(text="X", extra={"project": "hi.wikipedia"}))
    assert fake2.calls[0]["project"] == "hi.wikipedia"


def test_series_since_overrides_extra_start(src):
    fake = FakePageviewsClient({})
    src._client = lambda: fake
    since = datetime(2024, 1, 5, tzinfo=None)
    src.series(Query(text="X", since=since,
                     extra={"start": date(2023, 12, 1), "end": date(2024, 1, 31)}))
    assert fake.calls[0]["start"] == date(2024, 1, 5)  # .date() of the datetime
    assert fake.calls[0]["end"] == date(2024, 1, 31)


def test_series_extra_start_used_when_no_since(src):
    fake = FakePageviewsClient({})
    src._client = lambda: fake
    src.series(Query(text="X", extra={"start": date(2023, 12, 15),
                                      "end": date(2024, 1, 31)}))
    assert fake.calls[0]["start"] == date(2023, 12, 15)
    assert fake.calls[0]["end"] == date(2024, 1, 31)


def test_series_default_start_is_end_minus_30_days(src):
    fake = FakePageviewsClient({})
    src._client = lambda: fake
    end = date(2024, 6, 30)
    src.series(Query(text="X", extra={"end": end}))
    assert fake.calls[0]["start"] == end - timedelta(days=30)
    assert fake.calls[0]["end"] == end


def test_series_default_end_is_today(src):
    fake = FakePageviewsClient({})
    src._client = lambda: fake
    src.series(Query(text="X"))
    assert fake.calls[0]["end"] == date.today()
    assert fake.calls[0]["start"] == date.today() - timedelta(days=30)


def test_series_raw_not_dict_returns_empty(src):
    src._client = lambda: FakePageviewsClient(["not", "a", "dict"])
    assert src.series(_query()) == []


def test_series_raw_empty_dict_returns_empty(src):
    src._client = lambda: FakePageviewsClient({})
    assert src.series(_query()) == []


def test_series_client_error_raises(src):
    src._client = lambda: FakePageviewsClient(error=RuntimeError("403 forbidden"))
    with pytest.raises(ProviderError, match="pageviews fetch failed"):
        src.series(_query())


def test_series_region_passthrough(src):
    src._client = lambda: FakePageviewsClient(
        {"20240101": {"X": 1}})
    out = src.series(Query(text="X", region="IN"))
    assert out[0].region == "IN"


def test_source_satisfies_protocol_and_name(src):
    assert isinstance(src, TimeSeriesSource)
    assert src.name == "wiki_pageviews"


def test_source_via_registry(reg):
    s = reg.create("timeseries", "wiki_pageviews")
    assert isinstance(s, TimeSeriesSource)
