"""Search-interest time series (upstream clone: GeneralMills/pytrends, Apache-2.0).

Exposed capabilities:
- ``timeseries`` / ``search_trends`` - regional Google Trends signals for an IP.
- ``normalizer`` / ``trend_growth`` - de-trends raw interest against a base
  index (population / internet-user growth), per Feature 2 of the dossier.
"""

from __future__ import annotations

from typing import Any, Sequence

from engine_api import Query, Signal, provider

from ._bootstrap import ProviderError, ensure_paths


class SearchTrendSource:
    """TimeSeriesSource over Google Trends (unofficial API, rate-limited)."""

    name = "search_trends"

    def __init__(self, hl: str = "en-IN", tz: int = 330, geo: str = "IN") -> None:
        ensure_paths("pytrends")
        self._hl, self._tz, self._geo = hl, tz, geo

    def _client(self) -> Any:
        from pytrends.request import TrendReq  # lazy upstream import

        return TrendReq(hl=self._hl, tz=self._tz)

    def series(self, query: Query) -> list[Signal]:
        keywords = [k for k in (query.text, *query.extra.get("keywords", ())) if k][:5]
        if not keywords:
            raise ProviderError("search_trends requires at least one keyword")
        timeframe = str(query.extra.get("timeframe", "today 12-m"))
        geo = str(query.extra.get("geo", query.region or self._geo))
        try:
            client = self._client()
            client.build_payload(keywords, timeframe=timeframe, geo=geo)
            frame = client.interest_over_time()
        except Exception as exc:
            raise ProviderError(f"trends fetch failed: {exc}") from exc

        if frame is None or getattr(frame, "empty", True):
            return []
        signals: list[Signal] = []
        for keyword in keywords:
            if keyword not in frame:
                continue
            for ts, value in frame[keyword].items():
                if value is None:
                    continue
                signals.append(
                    Signal(
                        name=f"search_interest:{keyword}",
                        value=float(value),
                        region=geo or None,
                        window_start=ts.to_pydatetime(),
                        source=self.name,
                        metadata={"keyword": keyword, "timeframe": timeframe},
                    )
                )
        return signals

    def regional(self, query: Query, resolution: str = "REGION") -> list[Signal]:
        """Interest by sub-region (Indian states with geo='IN')."""
        keywords = [query.text] if query.text else []
        geo = str(query.extra.get("geo", query.region or self._geo))
        try:
            client = self._client()
            client.build_payload(keywords, geo=geo, timeframe=str(query.extra.get("timeframe", "today 12-m")))
            frame = client.interest_by_region(resolution=resolution, inc_low_vol=True)
        except Exception as exc:
            raise ProviderError(f"trends regional fetch failed: {exc}") from exc

        if frame is None or getattr(frame, "empty", True):
            return []
        keyword = keywords[0]
        return [
            Signal(
                name=f"regional_interest:{keyword}",
                value=float(value),
                region=str(region),
                source=self.name,
                metadata={"geo": geo, "resolution": resolution},
            )
            for region, value in frame[keyword].items()
            if value is not None
        ]


class TrendGrowthNormalizer:
    """Normalizer: divide raw interest by a growth base index (Feature 2)."""

    def __init__(self, base_index: dict[str, float] | None = None) -> None:
        # base_index maps ISO year -> multiplier (e.g. internet-user growth).
        self._base_index = base_index or {}

    def normalize(self, signals: Sequence[Signal]) -> list[Signal]:
        out: list[Signal] = []
        for sig in signals:
            year = str(sig.window_start.year) if sig.window_start else None
            factor = self._base_index.get(year or "", 1.0) or 1.0
            out.append(
                Signal(
                    name=f"{sig.name}:normalized",
                    value=sig.value / factor,
                    region=sig.region,
                    window_start=sig.window_start,
                    window_end=sig.window_end,
                    source=sig.source or self.__class__.__name__,
                    metadata={**dict(sig.metadata), "growth_factor": factor},
                )
            )
        return out


@provider("timeseries", "search_trends")
def _trends_factory(**config: Any) -> SearchTrendSource:
    return SearchTrendSource(**config)


@provider("normalizer", "trend_growth")
def _normalizer_factory(**config: Any) -> TrendGrowthNormalizer:
    return TrendGrowthNormalizer(**config)
