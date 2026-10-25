"""Shared fixtures for the modules test-suite.

Importing this conftest puts ``modules/src`` on ``sys.path`` so the suite runs
with a plain ``python -m pytest tests -q`` from ``modules/`` (no PYTHONPATH
needed), imports ``providers`` once so every lazy factory is registered, and
registers the hypothesis profiles used by the property tests:

- ``default``    max_examples=100  (CI / everyday runs)
- ``thorough``   max_examples=300  (``--hypothesis-profile=thorough``)
- ``exhaustive`` max_examples=1500 (``--hypothesis-profile=exhaustive``)

All tests are offline: no real network, no real Redis, no model downloads.
"""

from __future__ import annotations

import sys
from pathlib import Path

MODULES_ROOT = Path(__file__).resolve().parents[1]
SRC = MODULES_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import providers  # noqa: E402,F401  (registers every provider factory once)

import pytest  # noqa: E402
from hypothesis import settings  # noqa: E402


# ---------------------------------------------------------------------------
# Opt-in live-data tests (tests/test_live.py): skipped unless --run-live is
# passed, and additionally skipped per-endpoint when the network blocks it.
# ---------------------------------------------------------------------------


def pytest_addoption(parser):
    group = parser.getgroup("sakurascore")
    group.addoption(
        "--run-live", action="store_true", default=False,
        help="Run the live-network smoke tests (marked @pytest.mark.live).",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: hits real external APIs; opt in with --run-live")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-live"):
        return
    skip = pytest.mark.skip(reason="live test: pass --run-live to enable")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


settings.register_profile("default", max_examples=100, deadline=None)
settings.register_profile("thorough", max_examples=300, deadline=None)
settings.register_profile("exhaustive", max_examples=1500, deadline=None)

# Only force the default profile when the user did not pick one on the CLI
# (the hypothesis pytest plugin re-loads the requested profile at configure
# time, which happens after conftest import).
if not any(arg == "--hypothesis-profile" or arg.startswith("--hypothesis-profile=")
           for arg in sys.argv):
    settings.load_profile("default")

from engine_api import Evidence, IPNode, Query, registry  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def reg():
    """The process-global provider registry (same object everywhere)."""
    return registry


@pytest.fixture()
def no_redis_env(monkeypatch):
    """Remove REDIS_URL (and friends) so cache/limiter code uses defaults."""
    for var in ("REDIS_URL", "REDIS_HOST", "REDIS_PORT"):
        monkeypatch.delenv(var, raising=False)
    return None


# -- quick factories --------------------------------------------------------


@pytest.fixture()
def evidence_factory():
    """Build an Evidence with sane defaults in one call."""

    def make(source: str = "test", url: str = "https://example.com",
             content: str = "sample content", **kwargs) -> Evidence:
        return Evidence(source=source, url=url, content=content, **kwargs)

    return make


@pytest.fixture()
def query_factory():
    """Build a Query with sane defaults in one call."""

    def make(text: str = "naruto", **kwargs) -> Query:
        return Query(text=text, **kwargs)

    return make


@pytest.fixture()
def ipnode_factory():
    """Build an IPNode with sane defaults in one call."""

    def make(id: str = "mal:1", title: str = "Naruto", **kwargs) -> IPNode:  # noqa: A002
        return IPNode(id=id, title=title, **kwargs)

    return make
