"""Unit tests — src/data_sources/matrix.py (8-source evidence matrix)."""
from __future__ import annotations

import pytest

from src.data_sources.matrix import SOURCES, DataSource, get_matrix

VALID_STATUS = {"live", "blocked", "pending_key"}


def test_eight_sources():
    assert len(SOURCES) == 8
    assert len(get_matrix()) == 8


def test_keys_unique_and_stable():
    keys = [s.key for s in SOURCES]
    assert len(keys) == len(set(keys))
    assert keys == ["anilist", "jikan", "wiki_en", "wiki_hi", "trends",
                    "youtube", "reddit", "seed"]


def test_status_domain():
    for s in SOURCES:
        assert s.status in VALID_STATUS, s.key


def test_relevance_reliability_bounds():
    for s in SOURCES:
        assert isinstance(s.relevance, int) and 0 <= s.relevance <= 100, s.key
        assert isinstance(s.reliability, int) and 0 <= s.reliability <= 100, s.key


def test_all_string_fields_non_empty():
    for s in SOURCES:
        for f in ("key", "name", "measures", "bias", "noise", "mitigation",
                  "coverage"):
            assert isinstance(getattr(s, f), str) and getattr(s, f).strip(), (s.key, f)


def test_status_mix_present():
    statuses = {s.status for s in SOURCES}
    assert statuses == VALID_STATUS


def test_get_matrix_returns_list_of_dicts_matching_sources():
    m = get_matrix()
    assert isinstance(m, list) and all(isinstance(d, dict) for d in m)
    assert [d["key"] for d in m] == [s.key for s in SOURCES]
    for d, s in zip(m, SOURCES):
        assert d == vars(s)
        assert set(d) == {"key", "name", "measures", "status", "relevance",
                          "reliability", "bias", "noise", "mitigation", "coverage"}


def test_get_matrix_returns_new_list_each_call():
    a, b = get_matrix(), get_matrix()
    assert a is not b                       # fresh list per call
    # CURRENT BEHAVIOUR (new finding): vars(s) hands out the LIVE __dict__ of
    # each DataSource, so all "copies" share state with module-level SOURCES.
    assert a[0] is b[0] is vars(SOURCES[0])
    try:
        a[0]["status"] = "hacked"
        assert b[0]["status"] == "hacked"       # aliasing is real
        assert SOURCES[0].status == "hacked"    # module state is corrupted
    finally:
        SOURCES[0].status = "live"              # restore for other tests


def test_dataclass_is_plain_and_constructible():
    ds = DataSource(key="x", name="X", measures="m", status="pending_key",
                    relevance=1, reliability=2, bias="b", noise="n",
                    mitigation="mm", coverage="c")
    assert get_matrix()[0] != vars(ds)
    assert ds.status in VALID_STATUS


@pytest.mark.parametrize("s", SOURCES, ids=lambda s: s.key)
def test_per_source_relevance_at_least_50(s):
    # every assessed source clears a minimal usefulness bar in the matrix
    assert s.relevance >= 50
    assert s.reliability >= 40
