"""WebPageExtractor with a stubbed crawl4ai module (no Playwright, no net)."""

from __future__ import annotations

import sys
import types

import pytest

from engine_api import Document
from engine_api.protocols import ContentExtractor
from providers._bootstrap import ProviderError
from providers.web_extract import WebPageExtractor


class FakeCrawlResult:
    def __init__(self, success=True, error_message=None, markdown=None,
                 cleaned_html=None, fit_html=None, status_code=200, media=None,
                 links=None, metadata=None):
        self.success = success
        self.error_message = error_message
        self.markdown = markdown
        self.cleaned_html = cleaned_html
        self.fit_html = fit_html
        self.status_code = status_code
        self.media = media
        self.links = links
        self.metadata = metadata


class MarkdownObj:
    def __init__(self, raw):
        self.raw_markdown = raw


class FakeAsyncWebCrawler:
    result = None  # set per-test via class attr

    def __init__(self, config=None, **cfg):
        self.config = config
        self.cfg = cfg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def arun(self, url=None):
        if isinstance(FakeAsyncWebCrawler.result, Exception):
            raise FakeAsyncWebCrawler.result
        return FakeAsyncWebCrawler.result


@pytest.fixture()
def fake_crawl4ai(monkeypatch):
    mod = types.ModuleType("crawl4ai")
    mod.AsyncWebCrawler = FakeAsyncWebCrawler

    class BrowserConfig:
        def __init__(self, browser_type=None, headless=None):
            self.browser_type = browser_type
            self.headless = headless

    mod.BrowserConfig = BrowserConfig
    monkeypatch.setitem(sys.modules, "crawl4ai", mod)
    return mod


def test_extract_none_result_raises_no_result(fake_crawl4ai):
    FakeAsyncWebCrawler.result = None
    ext = WebPageExtractor()
    with pytest.raises(ProviderError, match="no result"):
        ext.extract("https://example.com")


def test_extract_failure_message_surfaces(fake_crawl4ai):
    FakeAsyncWebCrawler.result = FakeCrawlResult(success=False,
                                                 error_message="net::ERR_CONNECTION_REFUSED")
    ext = WebPageExtractor()
    with pytest.raises(ProviderError) as exc:
        ext.extract("https://example.com")
    assert "crawl failed" in str(exc.value)
    assert "net::ERR_CONNECTION_REFUSED" in str(exc.value)


def test_extract_markdown_object_raw_markdown(fake_crawl4ai):
    FakeAsyncWebCrawler.result = FakeCrawlResult(markdown=MarkdownObj("# Title\n\ntext"))
    doc = WebPageExtractor().extract("https://example.com")
    assert isinstance(doc, Document)
    assert doc.text == "# Title\n\ntext"
    assert doc.url == "https://example.com"
    assert doc.status == 200


def test_extract_markdown_plain_string(fake_crawl4ai):
    FakeAsyncWebCrawler.result = FakeCrawlResult(markdown="plain markdown string")
    assert WebPageExtractor().extract("https://x").text == "plain markdown string"


def test_extract_markdown_none_falls_back_to_cleaned_html(fake_crawl4ai):
    FakeAsyncWebCrawler.result = FakeCrawlResult(
        markdown=None, cleaned_html="<p>cleaned</p>")
    assert WebPageExtractor().extract("https://x").text == "<p>cleaned</p>"


def test_extract_fit_html_fallback_when_no_markdown_or_cleaned(fake_crawl4ai):
    FakeAsyncWebCrawler.result = FakeCrawlResult(markdown=None, cleaned_html=None,
                                                 fit_html="<b>fit</b>")
    assert WebPageExtractor().extract("https://x").text == "<b>fit</b>"


def test_extract_empty_markdown_string_falls_back(fake_crawl4ai):
    # "" is falsy -> falls through to html fallbacks -> finally ""
    FakeAsyncWebCrawler.result = FakeCrawlResult(markdown="", cleaned_html=None)
    assert WebPageExtractor().extract("https://x").text == ""


@pytest.mark.parametrize("status,expected", [(200, 200), (404, 404), (500, 500),
                                             (None, 200), ("301", 301)])
def test_extract_status_code_mapping(fake_crawl4ai, status, expected):
    FakeAsyncWebCrawler.result = FakeCrawlResult(markdown="m", status_code=status)
    assert WebPageExtractor().extract("https://x").status == expected


def test_extract_metadata_media_links_title(fake_crawl4ai):
    FakeAsyncWebCrawler.result = FakeCrawlResult(
        markdown="m", media={"images": [1]}, links={"external": []},
        metadata={"title": "Page Title"})
    doc = WebPageExtractor().extract("https://x")
    assert doc.metadata["media"] == {"images": [1]}
    assert doc.metadata["links"] == {"external": []}
    assert doc.metadata["title"] == "Page Title"


def test_extract_metadata_defaults_when_absent(fake_crawl4ai):
    FakeAsyncWebCrawler.result = FakeCrawlResult(markdown="m")
    doc = WebPageExtractor().extract("https://x")
    assert doc.metadata == {"media": {}, "links": {}, "title": None}
    assert doc.crawled_at is not None


def test_extract_arun_raising_runtimeerror_maps_to_loop_message(fake_crawl4ai):
    # CURRENT: *any* RuntimeError (even from inside the crawl) is mapped to
    # the "active event loop" message – the except clauses cannot tell them
    # apart.
    FakeAsyncWebCrawler.result = RuntimeError("playwright crashed")
    with pytest.raises(ProviderError) as exc:
        WebPageExtractor().extract("https://x")
    assert "active event loop" in str(exc.value)
    assert "playwright crashed" in str(exc.value)


def test_extract_runtime_error_from_sync_maps_to_event_loop_message(monkeypatch):
    def raise_runtime(url):
        raise RuntimeError("asyncio.run() cannot be called from a running event loop")

    ext = WebPageExtractor()
    monkeypatch.setattr(ext, "_extract_sync", raise_runtime)
    with pytest.raises(ProviderError) as exc:
        ext.extract("https://x")
    assert "active event loop" in str(exc.value)


def test_extract_provider_error_passthrough(monkeypatch):
    def raise_provider(url):
        raise ProviderError("no result")

    ext = WebPageExtractor()
    monkeypatch.setattr(ext, "_extract_sync", raise_provider)
    with pytest.raises(ProviderError, match="no result"):
        ext.extract("https://x")


def test_extractor_config_stored():
    ext = WebPageExtractor(browser_type="firefox", headless=False, custom_flag=1)
    assert ext._browser_type == "firefox"
    assert ext._headless is False
    assert ext._crawler_cfg == {"custom_flag": 1}


def test_extractor_satisfies_protocol():
    assert isinstance(WebPageExtractor(), ContentExtractor)


def test_extractor_via_registry(reg):
    ext = reg.create("extractor", "web_page")
    assert isinstance(ext, ContentExtractor)
