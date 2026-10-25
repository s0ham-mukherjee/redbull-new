"""SearchTrendSource (fake pytrends client) + TrendGrowthNormalizer."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd
import pytest

from engine_api import Query, Signal
from engine_api.protocols import Normalizer, TimeSeriesSource
from providers._bootstrap import ProviderError
from providers.trends import SearchTrendSource, TrendGrowthNormalizer


# ---------------------------------------------------------------------------
# TrendGrowthNormalizer (pure)
# ---------------------------------------------------------------------------


def _sig(value=80.0, year=2025, name="search_interest:naruto", region="IN",
         source="search_trends", metadata=None):
    return Signal(name=name, value=value, region=region,
                  window_start=datetime(year, 6, 1, tzinfo=timezone.utc),
                  window_end=datetime(year, 6, 2, tzinfo=timezone.utc),
                  source=source, metadata=metadata or {"keyword": "naruto"})


def test_normalize_empty_signals():
    assert TrendGrowthNormalizer().normalize([]) == []


def test_normalize_base_index_empty_factor_one_unchanged_value():
    out = TrendGrowthNormalizer().normalize([_sig(value=42.0)])
    assert out[0].value == 42.0
    assert out[0].name == "search_interest:naruto:normalized"


def test_normalize_year_matched_from_window_start():
    norm = TrendGrowthNormalizer(base_index={"2025": 2.0})
    out = norm.normalize([_sig(value=80.0, year=2025), _sig(value=90.0, year=2024)])
    assert out[0].value == 40.0
    assert out[1].value == 90.0  # 2024 not in base -> factor 1.0
    assert out[0].metadata["growth_factor"] == 2.0
    assert out[1].metadata["growth_factor"] == 1.0


def test_normalize_window_start_none_year_none_factor_default():
    norm = TrendGrowthNormalizer(base_index={"2025": 5.0})
    out = norm.normalize([Signal(name="n", value=10.0)])  # window_start None
    assert out[0].value == 10.0
    assert out[0].metadata["growth_factor"] == 1.0


def test_normalize_zero_factor_guarded_to_one():
    # CURRENT (trends.py:104 `... or 1.0`): a 0 factor never divides by zero
    norm = TrendGrowthNormalizer(base_index={"2025": 0.0})
    out = norm.normalize([_sig(value=10.0, year=2025)])
    assert out[0].value == 10.0
    assert out[0].metadata["growth_factor"] == 1.0


def test_normalize_metadata_growth_factor_and_original_preserved():
    norm = TrendGrowthNormalizer(base_index={"2025": 4.0})
    out = norm.normalize([_sig(value=100.0, year=2025, metadata={"keyword": "k", "x": 1})])
    assert out[0].metadata["growth_factor"] == 4.0
    assert out[0].metadata["keyword"] == "k"
    assert out[0].metadata["x"] == 1


def test_normalize_passthrough_fields():
    norm = TrendGrowthNormalizer()
    out = norm.normalize([_sig(year=2024, region="MH")])
    assert out[0].region == "MH"
    assert out[0].window_start == datetime(2024, 6, 1, tzinfo=timezone.utc)
    assert out[0].window_end == datetime(2024, 6, 2, tzinfo=timezone.utc)


def test_normalize_empty_source_uses_class_name():
    out = TrendGrowthNormalizer().normalize([Signal(name="n", value=1.0,
                                                    window_start=datetime(2024, 1, 1))])
    assert out[0].source == "TrendGrowthNormalizer"


def test_normalize_nonempty_source_preserved():
    out = TrendGrowthNormalizer().normalize([_sig(source="search_trends")])
    assert out[0].source == "search_trends"


def test_normalize_preserves_length_and_order():
    sigs = [_sig(value=float(v), year=2020 + v) for v in range(5)]
    out = TrendGrowthNormalizer(base_index={"2022": 2.0}).normalize(sigs)
    assert [s.value for s in out] == [0.0, 1.0, 1.0, 3.0, 4.0]


def test_normalizer_satisfies_protocol():
    assert isinstance(TrendGrowthNormalizer(), Normalizer)


def test_normalizer_via_registry(reg):
    norm = reg.create("normalizer", "trend_growth", base_index={"2025": 2.0})
    assert isinstance(norm, Normalizer)
    assert norm.normalize([_sig(value=8.0, year=2025)])[0].value == 4.0


# ---------------------------------------------------------------------------
# SearchTrendSource.series with a fake pytrends client
# ---------------------------------------------------------------------------


class FakeTrendClient:
    def __init__(self, frame=None, error=None):
        self.frame = frame
        self.error = error
        self.payload_calls = []

    def build_payload(self, keywords, timeframe=None, geo=None):
        self.payload_calls.append({"keywords": list(keywords),
                                   "timeframe": timeframe, "geo": geo})

    def interest_over_time(self):
        if self.error is not None:
            raise self.error
        return self.frame

    def interest_by_region(self, resolution=None, inc_low_vol=None):
        if self.error is not None:
            raise self.error
        return self.frame


def _frame():
    idx = pd.DatetimeIndex([datetime(2024, 1, 1), datetime(2024, 1, 2),
                            datetime(2024, 1, 3)])
    # object dtype keeps the true None (float dtype would turn it into NaN)
    return pd.DataFrame({"naruto": pd.Series([10.0, None, 30.0], index=idx,
                                             dtype=object),
                         "isPartial": pd.Series([False, False, False], index=idx,
                                                dtype=object)}, index=idx)


def test_series_none_value_skipped_with_object_dtype():
    src = SearchTrendSource()
    src._client = lambda: FakeTrendClient(_frame())
    out = src.series(Query(text="naruto"))
    assert [s.value for s in out] == [10.0, 30.0]


def test_series_none_becomes_nan_in_float_frame_current():
    # CURRENT: a float-dtype frame holds NaN (not None), which passes the
    # `is not None` guard and surfaces as a NaN signal value.
    idx = pd.DatetimeIndex([datetime(2024, 1, 1), datetime(2024, 1, 2)])
    frame = pd.DataFrame({"naruto": [10.0, None]}, index=idx)
    src = SearchTrendSource()
    src._client = lambda: FakeTrendClient(frame)
    out = src.series(Query(text="naruto"))
    assert len(out) == 2
    assert math.isnan(out[1].value)


def test_series_with_fake_client():
    src = SearchTrendSource()
    fake = FakeTrendClient(_frame())
    src._client = lambda: fake
    out = src.series(Query(text="naruto"))
    # None row skipped; isPartial column ignored
    assert [s.value for s in out] == [10.0, 30.0]
    assert [s.name for s in out] == ["search_interest:naruto"] * 2
    assert out[0].window_start == datetime(2024, 1, 1)
    assert out[0].source == "search_trends"
    assert out[0].metadata["keyword"] == "naruto"
    assert out[0].metadata["timeframe"] == "today 12-m"
    assert fake.payload_calls == [{"keywords": ["naruto"],
                                   "timeframe": "today 12-m", "geo": "IN"}]


def test_series_keywords_from_text_and_extra_capped_at_five():
    src = SearchTrendSource()
    fake = FakeTrendClient(pd.DataFrame())
    src._client = lambda: fake
    src.series(Query(text="one", extra={"keywords": ("two", "three", "four",
                                                      "five", "six", "seven")}))
    assert fake.payload_calls[0]["keywords"] == ["one", "two", "three", "four", "five"]


def test_series_empty_text_and_keywords_raises():
    src = SearchTrendSource()
    with pytest.raises(ProviderError, match="at least one keyword"):
        src.series(Query(text=""))


def test_series_empty_string_keywords_filtered():
    src = SearchTrendSource()
    with pytest.raises(ProviderError):
        src.series(Query(text="", extra={"keywords": ("", None)}))


@pytest.mark.parametrize("extra,region,expected_geo", [
    ({"geo": "US"}, None, "US"),            # extra geo wins
    ({}, "JP", "JP"),                        # query.region next
    ({}, None, "IN"),                        # constructor default
    ({"geo": "GB"}, "US", "GB"),             # extra beats region
])
def test_series_geo_precedence(extra, region, expected_geo):
    src = SearchTrendSource()
    fake = FakeTrendClient(pd.DataFrame())
    src._client = lambda: fake
    src.series(Query(text="k", region=region, extra=extra))
    assert fake.payload_calls[0]["geo"] == expected_geo


def test_series_timeframe_default_and_override():
    src = SearchTrendSource()
    fake = FakeTrendClient(pd.DataFrame())
    src._client = lambda: fake
    src.series(Query(text="k"))
    assert fake.payload_calls[0]["timeframe"] == "today 12-m"
    src.series(Query(text="k", extra={"timeframe": "now 7-d"}))
    assert fake.payload_calls[1]["timeframe"] == "now 7-d"


def test_series_frame_none_or_empty_returns_empty():
    src = SearchTrendSource()
    src._client = lambda: FakeTrendClient(None)
    assert src.series(Query(text="k")) == []
    src._client = lambda: FakeTrendClient(pd.DataFrame())
    assert src.series(Query(text="k")) == []


def test_series_client_error_raises():
    src = SearchTrendSource()
    src._client = lambda: FakeTrendClient(error=RuntimeError("429 rate limited"))
    with pytest.raises(ProviderError, match="trends fetch failed"):
        src.series(Query(text="k"))


def test_series_region_on_signals_follows_geo():
    src = SearchTrendSource()
    src._client = lambda: FakeTrendClient(_frame())
    out = src.series(Query(text="naruto", extra={"geo": "US"}))
    assert all(s.region == "US" for s in out)


def test_series_keyword_missing_from_frame_skipped():
    src = SearchTrendSource()
    fake = FakeTrendClient(pd.DataFrame(
        {"other": [1.0]}, index=pd.DatetimeIndex([datetime(2024, 1, 1)])))
    src._client = lambda: fake
    assert src.series(Query(text="naruto", extra={"keywords": ("other",)})) != []
    assert src.series(Query(text="naruto")) == []  # 'naruto' column absent


# ---------------------------------------------------------------------------
# SearchTrendSource.regional
# ---------------------------------------------------------------------------


def _region_frame():
    return pd.DataFrame({"naruto": {"Maharashtra": 50.0, "Bihar": 20.0}})


def test_regional_with_fake_client():
    src = SearchTrendSource()
    fake = FakeTrendClient(_region_frame())
    src._client = lambda: fake
    out = src.regional(Query(text="naruto"))
    assert len(out) == 2
    by_region = {s.region: s.value for s in out}
    assert by_region == {"Maharashtra": 50.0, "Bihar": 20.0}
    assert out[0].name == "regional_interest:naruto"
    assert out[0].source == "search_trends"
    assert out[0].metadata["geo"] == "IN"
    assert out[0].metadata["resolution"] == "REGION"
    assert fake.payload_calls[0]["keywords"] == ["naruto"]


def test_regional_frame_none_returns_empty():
    src = SearchTrendSource()
    src._client = lambda: FakeTrendClient(None)
    assert src.regional(Query(text="naruto")) == []


def test_regional_empty_text_with_nonempty_frame_indexerror_current():
    # CURRENT (trends.py:79 `keywords[0]`): empty text and a non-empty frame
    # crash with IndexError. Desired ProviderError -> test_bugs.py.
    src = SearchTrendSource()
    src._client = lambda: FakeTrendClient(_region_frame())
    with pytest.raises(IndexError):
        src.regional(Query(text=""))


def test_regional_none_values_become_nan_signals_current():
    # pandas turns None into NaN and the `is not None` guard passes it through
    src = SearchTrendSource()
    frame = pd.DataFrame({"naruto": {"MH": 50.0, "BR": None}})
    src._client = lambda: FakeTrendClient(frame)
    out = src.regional(Query(text="naruto"))
    values = {s.region: s.value for s in out}
    assert values["MH"] == 50.0
    assert math.isnan(values["BR"])


def test_regional_client_error_raises():
    src = SearchTrendSource()
    src._client = lambda: FakeTrendClient(error=RuntimeError("boom"))
    with pytest.raises(ProviderError, match="trends regional fetch failed"):
        src.regional(Query(text="naruto"))


def test_trend_source_satisfies_protocol():
    assert isinstance(SearchTrendSource(), TimeSeriesSource)
    assert SearchTrendSource().name == "search_trends"


def test_trend_source_via_registry(reg):
    src = reg.create("timeseries", "search_trends")
    assert isinstance(src, TimeSeriesSource)
