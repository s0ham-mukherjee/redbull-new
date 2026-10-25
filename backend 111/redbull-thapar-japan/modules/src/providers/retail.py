"""Retail catalogue & price scraping (upstream clone: Scrapy/scrapy, BSD-3).

Exposed capability: ``source`` / ``retail`` - a generic price/stock spider
factory for Indian storefronts (Amazon.in, BookSwagon, ...) with an in-process
fetch helper for small URL batches (Features 6/7/37/51).
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from engine_api import Evidence, Query, provider

from ._bootstrap import ProviderError, ensure_paths

_PRICE_RE = re.compile(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)


def parse_price(text: str) -> float | None:
    match = _PRICE_RE.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


class RetailSource:
    """EvidenceSource: fetches product pages and extracts price/stock signals.

    Uses scrapy's HTTP stack + selectors for parsing (no spider scheduling),
    which keeps it safe to call in-process from an engine request loop.
    """

    name = "retail"

    def __init__(self, user_agent: str = "SakuraScoreIndia/1.0 (research)", timeout: float = 20.0) -> None:
        ensure_paths("scrapy")
        self._user_agent = user_agent
        self._timeout = timeout

    def _fetch_html(self, url: str) -> str:
        try:
            import scrapy.http  # lazy upstream import
            from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler  # noqa: F401
            import requests
        except Exception as exc:
            raise ProviderError(f"retail fetch stack unavailable: {exc}") from exc
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": self._user_agent},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            raise ProviderError(f"retail fetch failed for {url}: {exc}") from exc

    @staticmethod
    def _extract(html: str, url: str) -> dict[str, Any]:
        from scrapy import Selector  # lazy upstream import

        sel = Selector(text=html, type="html")
        title = sel.css("title::text").get() or sel.css(
            "h1::text, [id*='title'] ::text, span[id*='product']::text"
        ).get()
        price_text = " ".join(
            sel.css(
                "[itemprop='price']::text, [class*='price'] ::text, "
                "[id*='price'] ::text, span.a-price::text"
            ).getall()[:10]
        )
        body_text = " ".join(sel.css("body ::text").getall()[:400])
        price = parse_price(price_text) or parse_price(body_text)
        stock_l = " ".join(sel.css("[class*='stock'], [id*='stock'], [class*='availability']").getall()[:5]).lower()
        if any(w in stock_l for w in ("out of stock", "unavailable", "sold out")):
            stock: str | bool = "out_of_stock"
        elif any(w in stock_l for w in ("in stock", "available")):
            stock = "in_stock"
        else:
            stock = "unknown"
        return {"url": url, "title": (title or "").strip(), "price_inr": price, "stock": stock}

    def fetch(self, query: Query) -> list[Evidence]:
        urls: Iterable[str] = query.extra.get("urls") or ([query.text] if query.text.startswith("http") else [])
        urls = list(urls)
        if not urls:
            raise ProviderError("retail source needs extra['urls'] (list of product URLs)")
        out: list[Evidence] = []
        for url in urls:
            html = self._fetch_html(url)
            parsed = self._extract(html, url)
            out.append(
                Evidence(
                    source=self.name,
                    url=url,
                    title=parsed["title"] or None,
                    content=json.dumps(parsed, ensure_ascii=False),
                    metadata={"price_inr": parsed["price_inr"], "stock": parsed["stock"]},
                )
            )
        return out


@provider("source", "retail")
def _factory(**config: Any) -> RetailSource:
    return RetailSource(**config)


__all__ = ["RetailSource", "parse_price"]
