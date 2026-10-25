"""LocalMemoryStore edge cases: ranking, k clamping, isolation, Evidence shape."""

from __future__ import annotations

import pytest

from engine_api.protocols import MemoryStore
from providers._bootstrap import ProviderError  # noqa: F401  (re-exported name)
from providers.memory import LocalMemoryStore, ZepMemoryStore


def test_remember_recall_round_trip():
    m = LocalMemoryStore()
    m.remember("s1", "anime fans prefer Hindi dubs")
    hits = m.recall("s1", "Hindi dubs")
    assert len(hits) == 1
    assert hits[0].content == "anime fans prefer Hindi dubs"


def test_recall_ranks_best_overlap_first():
    m = LocalMemoryStore()
    m.remember("s", "alpha one entry")
    m.remember("s", "target two words here matching query")
    m.remember("s", "third unrelated filler")
    hits = m.recall("s", "matching query words", k=3)
    assert hits, "overlapping entries must be returned"
    assert hits[0].content == "target two words here matching query"


def test_recall_filters_zero_overlap_entries():
    m = LocalMemoryStore()
    m.remember("s", "completely about manga pricing")
    m.remember("s", "totally unrelated shipping talk")
    # one entry overlaps, one does not -> only the overlapping one comes back
    hits = m.recall("s", "manga pricing", k=5)
    assert [h.content for h in hits] == ["completely about manga pricing"]


def test_recall_all_zero_overlap_returns_empty():
    m = LocalMemoryStore()
    m.remember("s", "alpha beta")
    m.remember("s", "gamma delta")
    assert m.recall("s", "zzz nothing matches zzz") == []


def test_recall_empty_query_string_returns_empty():
    # "" splits to no terms -> every overlap is 0 -> all filtered out
    m = LocalMemoryStore()
    m.remember("s", "alpha beta")
    assert m.recall("s", "") == []
    assert m.recall("s", "   ") == []


def test_recall_k_zero_returns_one_entry_current_behavior():
    # FINDING #8 (memory.py:47 `scored[:max(1, k)]`): k=0 returns 1 entry.
    # Current behavior asserted here; desired k=0 -> [] lives in test_bugs.py.
    m = LocalMemoryStore()
    m.remember("s", "alpha beta")
    m.remember("s", "alpha gamma")
    hits = m.recall("s", "alpha beta", k=0)
    assert len(hits) == 1
    assert hits[0].content == "alpha beta"


@pytest.mark.parametrize("k", [-1, -5, -100])
def test_recall_negative_k_returns_one_entry(k):
    m = LocalMemoryStore()
    m.remember("s", "alpha beta")
    hits = m.recall("s", "alpha", k=k)
    assert len(hits) == 1


def test_recall_k_larger_than_store_returns_all_overlapping():
    m = LocalMemoryStore()
    for i in range(5):
        m.remember("s", f"entry number {i}")
    hits = m.recall("s", "entry number", k=100)
    assert len(hits) == 5


def test_recall_k_limits_results():
    m = LocalMemoryStore()
    for i in range(5):
        m.remember("s", f"entry number {i}")
    assert len(m.recall("s", "entry number", k=2)) == 2


def test_recall_metadata_preserved():
    m = LocalMemoryStore()
    m.remember("s", "priced content", {"tier": "tier_2", "n": 3})
    hits = m.recall("s", "priced content")
    assert hits[0].metadata == {"tier": "tier_2", "n": 3}


def test_recall_metadata_defaults_to_empty_dict():
    m = LocalMemoryStore()
    m.remember("s", "no metadata")
    assert m.recall("s", "no metadata")[0].metadata == {}


def test_recall_evidence_fields():
    m = LocalMemoryStore()
    m.remember("session-42", "alpha beta", {"x": 1})
    hits = m.recall("session-42", "alpha beta")
    ev = hits[0]
    assert ev.source == "memory:local"
    assert ev.url == "memory://session-42/0"
    assert ev.title is None
    assert ev.content == "alpha beta"


def test_sessions_isolated():
    m = LocalMemoryStore()
    m.remember("s1", "alpha beta")
    m.remember("s2", "gamma delta")
    assert [h.content for h in m.recall("s1", "alpha")] == ["alpha beta"]
    assert [h.content for h in m.recall("s2", "gamma")] == ["gamma delta"]
    assert m.recall("s1", "gamma delta") == []
    assert m.recall("s2", "alpha beta") == []


def test_recall_unknown_session_returns_empty():
    assert LocalMemoryStore().recall("never-seen", "anything") == []


def test_recall_ties_keep_insertion_order():
    m = LocalMemoryStore()
    m.remember("s", "same words one")
    m.remember("s", "same words two")
    hits = m.recall("s", "same words")
    assert [h.url for h in hits] == ["memory://s/0", "memory://s/1"]


def test_recall_is_case_insensitive():
    m = LocalMemoryStore()
    m.remember("s", "Hindi DUBS rock")
    assert m.recall("s", "hindi dubs")[0].content == "Hindi DUBS rock"


def test_local_memory_satisfies_protocol():
    assert isinstance(LocalMemoryStore(), MemoryStore)


def test_local_memory_via_registry(reg):
    m = reg.create("memory", "local")
    assert isinstance(m, MemoryStore)
    m.remember("s", "alpha beta")
    assert m.recall("s", "alpha")


def test_zep_store_constructor_offline():
    # ZepMemoryStore only imports requests at construction – no network.
    store = ZepMemoryStore(base_url="http://localhost:9999")
    assert store._base == "http://localhost:9999"
    assert isinstance(store, MemoryStore)


def test_zep_store_via_registry(reg):
    store = reg.create("memory", "zep", base_url="http://localhost:9999")
    assert isinstance(store, MemoryStore)
