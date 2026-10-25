"""Wikimedia pageview attention signals (upstream clone: mediawiki-utilities/python-mwviews, MIT).

Exposed capability: ``timeseries`` / ``wiki_pageviews`` - daily article
pageviews per Wikipedia project, used for baseline attention velocity (Feature 4).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from engine_api import Query, Signal, provider

from ._bootstrap import ProviderError, ensure_paths


class WikiPageviewSource:
    """TimeSeriesSource over the Wikimedia Pageviews REST API via mwviews."""

    name = "wiki_pageviews"

    def __init__(self, user_agent: str = "SakuraScoreIndia/1.0 (research)", parallelism: int = 5) -> None:
        ensure_paths("python-mwviews")
        self._user_agent = user_agent
        self._parallelism = parallelism

    def _client(self) -> Any:
        from mwviews.api.pageviews import PageviewsClient  # lazy upstream import

        return PageviewsClient(user_agent=self._user_agent, parallelism=self._parallelism)

    def series(self, query: Query) -> list[Signal]:
        article = str(query.extra.get("article") or query.text or "").strip()
        if not article:
            raise ProviderError("wiki_pageviews requires an article title (query.text or extra['article'])")
        project = str(query.extra.get("project", "en.wikipedia"))
        end = query.extra.get("end") or date.today()
        start = query.extra.get("start")
        if isinstance(start, datetime):
            start = start.date()
        if query.since is not None:
            start = query.since.date()
        if start is None:
            start = (end if isinstance(end, date) else date.today()) - timedelta(days=30)

        try:
            client = self._client()
            raw = client.article_views(project, [article], start=start, end=end)
        except Exception as exc:
            raise ProviderError(f"pageviews fetch failed: {exc}") from exc

        # Shape: {start_date: {article: views|None}, ..., end_date: {...}}
        signals: list[Signal] = []
        if not isinstance(raw, dict):
            return signals
        for day_key, articles in raw.items():
            if not isinstance(articles, dict):
                continue
            views = articles.get(article)
            if views is None:
                continue
            try:
                window = datetime.strptime(str(day_key)[:10], "%Y%m%d")
            except ValueError:
                window = None
            signals.append(
                Signal(
                    name=f"wiki_pageviews:{article}",
                    value=float(views),
                    region=query.region,
                    window_start=window,
                    window_end=window,
                    source=self.name,
                    metadata={"project": project, "article": article, "date": str(day_key)},
                )
            )
        signals.sort(key=lambda s: s.window_start or datetime.min)
        return signals


@provider("timeseries", "wiki_pageviews")
def _factory(**config: Any) -> WikiPageviewSource:
    return WikiPageviewSource(**config)
