"""RetailSource: parse_price matrix, fetch gating, _extract with a fake
scrapy.Selector (the real scrapy clone cannot import fully offline).

The fake Selector below implements just enough CSS for the selectors the
production code issues (title/h1/[attr*='...'] ::text, span.a-price, body ::text
and the stock attribute selectors) using stdlib html.parser.
"""

from __future__ import annotations

import re
import sys
import types
from html.parser import HTMLParser

import pytest

from engine_api import Query
from engine_api.protocols import EvidenceSource
from providers._bootstrap import ProviderError
from providers.retail import RetailSource, parse_price


# ---------------------------------------------------------------------------
# parse_price (pure)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("₹1,299.00", 1299.0),
    ("₹ 99", 99.0),
    ("₹99", 99.0),
    ("Rs 499", 499.0),
    ("Rs. 499", 499.0),
    ("Rs  499", 499.0),
    ("INR 499", 499.0),
    ("rs 199", 199.0),            # lowercase (regex IGNORECASE)
    ("RS. 89", 89.0),
    ("₹1,29,999", 129999.0),      # Indian grouping: commas simply stripped
    ("₹1,29,999.50", 129999.5),
    ("Price: Rs. 1,999 only", 1999.0),
    ("MRP ₹2,499.00 (₹2,499.00/Count)", 2499.0),
    ("₹0.50", 0.5),
    ("₹0", 0.0),
    ("₹1000000", 1000000.0),
    ("₹  1,23,45,678", 12345678.0),
    ("â‚¹999", None),             # mojibake rupee sign is not matched
    ("$", None),
    ("USD 59", None),
    ("₹", None),                  # symbol without digits
    ("Rs.", None),
    ("no price here", None),
    ("", None),
])
def test_parse_price_matrix(text, expected):
    assert parse_price(text) == expected


def test_parse_price_none_text():
    assert parse_price(None) is None  # `text or ""` guard


def test_parse_price_first_match_wins():
    assert parse_price("Rs 100 then ₹200 then INR 300") == 100.0


def test_parse_price_requires_digits_after_symbol():
    assert parse_price("₹ abc") is None
    assert parse_price("Rs abc") is None


def test_parse_price_decimal_only_fraction():
    assert parse_price("₹.50") is None  # pattern needs [\d,]+ before the dot
    assert parse_price("₹4.") == 4.0


def test_parse_price_regex_is_case_insensitive_and_unanchored():
    m = __import__("providers.retail", fromlist=["_PRICE_RE"])._PRICE_RE.search("rs 5")
    assert m is not None and m.group(1) == "5"


def test_parse_price_always_none_or_nonnegative_float():
    for text in ("₹1", "Rs -5", "INR 0.00", "garbage"):
        out = parse_price(text)
        assert out is None or out >= 0


# ---------------------------------------------------------------------------
# Fake scrapy.Selector
# ---------------------------------------------------------------------------


class _Node:
    __slots__ = ("tag", "attrs", "direct_text", "all_text")

    def __init__(self, tag, attrs):
        self.tag = tag
        self.attrs = dict(attrs)
        self.direct_text = ""
        self.all_text = ""


class _MiniDom(HTMLParser):
    """Tiny streaming DOM good enough for the selectors used by _extract."""

    _TAG_RE = re.compile(r"<(/?)(\w+)([^>]*)>|([^<]+)", re.S)
    _VOID = {"br", "img", "meta", "link", "input", "hr"}

    def __init__(self, html):
        super().__init__()
        self.nodes: list[_Node] = []
        self._build(html)

    def _build(self, html):
        stack: list[_Node] = []
        textbuf: list[str] = []

        def flush() -> None:
            if stack and textbuf:
                txt = "".join(textbuf)
                stack[-1].direct_text += txt
                for node in stack:
                    node.all_text += txt
            textbuf.clear()

        for m in self._TAG_RE.finditer(html):
            closing, tag, attrstr, text = m.groups()
            if tag:
                flush()
                if closing:
                    while stack and stack[-1].tag != tag:
                        stack.pop()
                    if stack:
                        stack.pop()
                else:
                    attrs = dict(re.findall(r"""(\w+)=["']([^"']*)["']""", attrstr))
                    node = _Node(tag, attrs)
                    self.nodes.append(node)
                    if tag not in self._VOID:
                        stack.append(node)
            elif text and text.strip():
                textbuf.append(text)
        flush()


class FakeSelector:
    def __init__(self, text=None, type=None):  # noqa: A002
        self.dom = _MiniDom(text or "")

    def _match(self, node, base):
        base = base.strip()
        if base == "":
            return False
        m = re.match(r"^(\w+)?(.*)$", base)
        tag, rest = m.group(1), m.group(2)
        if tag and node.tag != tag.lower():
            return False
        for attr, val in re.findall(r"\[([\w-]+)\*?='([^']*)'\]", rest):
            if attr not in node.attrs or val not in node.attrs[attr]:
                return False
        for cls in re.findall(r"\.([\w-]+)", rest):
            if cls not in (node.attrs.get("class") or "").split():
                return False
        return True

    def css(self, selector):
        results = []
        for part in selector.split(","):
            part = part.strip()
            descendant_text = part.endswith(" ::text")
            if part.endswith("::text"):
                base = part[: -len("::text")]
                want_text = True
            else:
                base = part
                want_text = False
            for node in self.dom.nodes:
                if not self._match(node, base):
                    continue
                if want_text:
                    txt = node.all_text if descendant_text else node.direct_text
                    if txt:
                        results.append(txt)
                else:
                    rendered = f"<{node.tag} " + " ".join(
                        f'{k}="{v}"' for k, v in node.attrs.items()) + \
                        f">{node.all_text}</{node.tag}>"
                    results.append(rendered)
        return _Query(results)


class _Query:
    def __init__(self, items):
        self.items = items

    def get(self):
        return self.items[0] if self.items else None

    def getall(self):
        return list(self.items)


@pytest.fixture()
def fake_scrapy(monkeypatch):
    mod = types.ModuleType("scrapy")
    mod.Selector = FakeSelector
    http_mod = types.ModuleType("scrapy.http")
    core = types.ModuleType("scrapy.core")
    dl = types.ModuleType("scrapy.core.downloader")
    handlers = types.ModuleType("scrapy.core.downloader.handlers")
    h11 = types.ModuleType("scrapy.core.downloader.handlers.http11")
    h11.HTTP11DownloadHandler = object  # from-import target
    monkeypatch.setitem(sys.modules, "scrapy", mod)
    monkeypatch.setitem(sys.modules, "scrapy.http", http_mod)
    monkeypatch.setitem(sys.modules, "scrapy.core", core)
    monkeypatch.setitem(sys.modules, "scrapy.core.downloader", dl)
    monkeypatch.setitem(sys.modules, "scrapy.core.downloader.handlers", handlers)
    monkeypatch.setitem(sys.modules, "scrapy.core.downloader.handlers.http11", h11)
    return mod


# ---------------------------------------------------------------------------
# RetailSource._extract with the fake Selector
# ---------------------------------------------------------------------------


def test_extract_full_page(fake_scrapy):
    html = ("<html><head><title>Naruto Vol 1</title></head><body>"
            '<span itemprop="price">₹499</span>'
            '<div class="stock-status">In stock</div>'
            "</body></html>")
    out = RetailSource._extract(html, "https://shop/x")
    assert out == {"url": "https://shop/x", "title": "Naruto Vol 1",
                   "price_inr": 499.0, "stock": "in_stock"}


def test_extract_title_fallback_h1_when_no_title(fake_scrapy):
    html = "<html><body><h1>Fallback Heading</h1><span class='price'>Rs. 399</span></body></html>"
    out = RetailSource._extract(html, "u")
    assert out["title"] == "Fallback Heading"
    assert out["price_inr"] == 399.0


@pytest.mark.parametrize("phrase,expected", [
    ("Out of stock", "out_of_stock"),
    ("Currently unavailable", "out_of_stock"),
    ("Sold out!", "out_of_stock"),
    ("In stock: 5 left", "in_stock"),
    ("Available for delivery", "in_stock"),
])
def test_extract_stock_vocabulary(fake_scrapy, phrase, expected):
    html = f'<html><body><div class="stock">{phrase}</div></body></html>'
    out = RetailSource._extract(html, "u")
    assert out["stock"] == expected


def test_extract_stock_unknown_when_no_markup(fake_scrapy):
    html = "<html><body><p>nothing about stock</p></body></html>"
    assert RetailSource._extract(html, "u")["stock"] == "unknown"


def test_extract_out_of_stock_beats_in_stock(fake_scrapy):
    html = ('<html><body><div class="availability">Out of stock, was available'
            "</div></body></html>")
    assert RetailSource._extract(html, "u")["stock"] == "out_of_stock"


@pytest.mark.parametrize("selector_html,expected", [
    ('<span itemprop="price">₹699</span>', 699.0),
    ('<span class="a-price">Rs. 399</span>', 399.0),
    ('<div id="priceblock">INR 250</div>', 250.0),
    ('<span class="ourprice">₹ 1,299.00</span>', 1299.0),
])
def test_extract_price_selector_variants(fake_scrapy, selector_html, expected):
    html = f"<html><body>{selector_html}</body></html>"
    assert RetailSource._extract(html, "u")["price_inr"] == expected


def test_extract_price_falls_back_to_body(fake_scrapy):
    html = "<html><body><p>Costs ₹159 shipped</p></body></html>"
    assert RetailSource._extract(html, "u")["price_inr"] == 159.0


def test_extract_price_none_when_absent(fake_scrapy):
    html = "<html><body><p>no numbers at all</p></body></html>"
    assert RetailSource._extract(html, "u")["price_inr"] is None


def test_extract_result_keys_exact(fake_scrapy):
    out = RetailSource._extract("<html><body><p>x</p></body></html>", "u")
    assert set(out) == {"url", "title", "price_inr", "stock"}


# ---------------------------------------------------------------------------
# RetailSource.fetch
# ---------------------------------------------------------------------------


def test_fetch_without_urls_raises_actionable():
    src = RetailSource()
    with pytest.raises(ProviderError, match=r"extra\['urls'\]"):
        src.fetch(Query(text="tell me about naruto"))
    with pytest.raises(ProviderError):
        src.fetch(Query(text=""))


def test_fetch_text_url_with_patched_html(fake_scrapy, monkeypatch):
    src = RetailSource()
    monkeypatch.setattr(src, "_fetch_html",
                        lambda url: "<html><title>T</title></html>")
    out = src.fetch(Query(text="https://shop.example/product"))
    assert len(out) == 1
    ev = out[0]
    assert ev.source == "retail"
    assert ev.url == "https://shop.example/product"
    assert ev.title == "T"
    assert ev.metadata["price_inr"] is None
    assert ev.metadata["stock"] == "unknown"


def test_fetch_multiple_urls_in_extra(fake_scrapy, monkeypatch):
    src = RetailSource()
    fetched = []

    def fake_html(url):
        fetched.append(url)
        return f"<html><title>Page {url}</title></html>"

    monkeypatch.setattr(src, "_fetch_html", fake_html)
    out = src.fetch(Query(text="ignored", extra={"urls": ["https://a", "https://b"]}))
    assert fetched == ["https://a", "https://b"]
    assert [ev.url for ev in out] == ["https://a", "https://b"]
    assert [ev.title for ev in out] == ["Page https://a", "Page https://b"]


def test_fetch_html_requests_error_wrapped(fake_scrapy, monkeypatch):
    import requests as real_requests
    monkeypatch.setattr(real_requests, "get",
                        lambda *a, **k: (_ for _ in ()).throw(
                            real_requests.exceptions.ConnectionError("down")))
    src = RetailSource()
    with pytest.raises(ProviderError, match="retail fetch failed"):
        src._fetch_html("https://shop.example/x")


def test_fetch_html_non_200_raises(fake_scrapy, monkeypatch):
    class Resp:
        text = "server says no"

        def raise_for_status(self):
            raise RuntimeError("500")

    import requests as real_requests
    monkeypatch.setattr(real_requests, "get", lambda *a, **k: Resp())
    with pytest.raises(ProviderError, match="retail fetch failed"):
        RetailSource()._fetch_html("https://x")


def test_retail_source_satisfies_protocol():
    assert isinstance(RetailSource(), EvidenceSource)
    assert RetailSource().name == "retail"


def test_retail_via_registry(reg):
    src = reg.create("source", "retail")
    assert isinstance(src, EvidenceSource)
