"""Web page extraction (upstream clone: unclecode/crawl4ai, Apache-2.0).

Exposed capability: ``extractor`` / ``web_page`` - URL -> clean Document
markdown with JS rendering, used by the ingestion layer (Features 1/3/8).
"""

from __future__ import annotations

import asyncio
from typing import Any

from engine_api import Document, provider

from ._bootstrap import ProviderError, ensure_paths


class WebPageExtractor:
    """ContentExtractor over crawl4ai's AsyncWebCrawler (Playwright-backed)."""

    def __init__(self, browser_type: str = "chromium", headless: bool = True, **crawler_cfg: Any) -> None:
        ensure_paths("crawl4ai")
        self._browser_type = browser_type
        self._headless = headless
        self._crawler_cfg = crawler_cfg

    def _extract_sync(self, url: str) -> Document:
        from crawl4ai import AsyncWebCrawler, BrowserConfig  # lazy upstream import

        browser_cfg = BrowserConfig(browser_type=self._browser_type, headless=self._headless)

        async def _run() -> Document:
            async with AsyncWebCrawler(config=browser_cfg, **self._crawler_cfg) as crawler:
                result = await crawler.arun(url=url)
            if result is None:
                raise ProviderError(f"crawl returned no result for {url}")
            if not getattr(result, "success", True):
                raise ProviderError(f"crawl failed for {url}: {getattr(result, 'error_message', '')}")
            markdown = getattr(result, "markdown", None)
            text = getattr(markdown, "raw_markdown", None) or (str(markdown) if markdown else "")
            if not text:
                text = getattr(result, "cleaned_html", None) or getattr(result, "fit_html", None) or ""
            return Document(
                url=url,
                text=text or "",
                status=int(getattr(result, "status_code", 200) or 200),
                metadata={
                    "media": getattr(result, "media", None) or {},
                    "links": getattr(result, "links", None) or {},
                    "title": getattr(result, "metadata", None) and (result.metadata or {}).get("title"),
                },
            )

        return asyncio.run(_run())

    def extract(self, url: str) -> Document:
        try:
            return self._extract_sync(url)
        except ProviderError:
            raise
        except RuntimeError as exc:
            # asyncio.run refused (running loop) - surface an actionable error.
            raise ProviderError(
                f"WebPageExtractor.extract cannot run inside an active event loop: {exc}"
            ) from exc
        except Exception as exc:
            raise ProviderError(f"extraction failed for {url}: {exc}") from exc


@provider("extractor", "web_page")
def _factory(**config: Any) -> WebPageExtractor:
    return WebPageExtractor(**config)


__all__ = ["WebPageExtractor"]
