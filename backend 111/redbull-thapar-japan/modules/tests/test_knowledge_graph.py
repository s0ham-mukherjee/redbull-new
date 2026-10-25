"""LocalGraphStore edge cases: upsert/get, relations, evidence ledger rules."""

from __future__ import annotations

from engine_api import Evidence, IPNode, Relation
from engine_api.protocols import KnowledgeStore
from providers.knowledge_graph import LocalGraphStore


def _ev(content: str = "grounded claim") -> Evidence:
    return Evidence(source="test", url="https://example.com", content=content)


def _node(nid: str, title: str = "T") -> IPNode:
    return IPNode(id=nid, title=title)


def test_upsert_returns_id():
    g = LocalGraphStore()
    assert g.upsert_node(_node("mal:1")) == "mal:1"


def test_get_missing_node_returns_none():
    assert LocalGraphStore().get_node("mal:nope") is None


def test_upsert_overwrite_same_id_returns_latest():
    g = LocalGraphStore()
    g.upsert_node(IPNode(id="mal:1", title="First", kind="anime"))
    g.upsert_node(IPNode(id="mal:1", title="Second", kind="manga"))
    got = g.get_node("mal:1")
    assert got.title == "Second" and got.kind == "manga"
    assert g.all_ids() == ["mal:1"]  # no duplicate nodes


def test_get_returns_identical_object():
    g = LocalGraphStore()
    node = _node("mal:7", "Keep")
    g.upsert_node(node)
    assert g.get_node("mal:7") is node


def test_relations_for_matches_src_or_dst():
    g = LocalGraphStore()
    r1 = Relation(src="a", dst="b", kind="sequel")
    r2 = Relation(src="c", dst="b", kind="adapted_from")
    r3 = Relation(src="x", dst="y", kind="produced_by")
    for r in (r1, r2, r3):
        g.add_relation(r)
    assert g.relations_for("a") == [r1]
    assert g.relations_for("b") == [r1, r2]
    assert g.relations_for("c") == [r2]
    assert g.relations_for("y") == [r3]
    assert g.relations_for("zzz") == []


def test_add_relation_records_evidence_on_src():
    g = LocalGraphStore()
    ev = _ev()
    g.add_relation(Relation(src="a", dst="b", kind="adapted_from", provenance=ev))
    out = g.evidence_for("a")
    assert len(out) == 1
    assert out[0].content_hash == ev.content_hash
    # dst gets nothing
    assert g.evidence_for("b") == []


def test_add_relation_without_provenance_records_no_evidence():
    g = LocalGraphStore()
    g.add_relation(Relation(src="a", dst="b", kind="sequel"))
    assert g.evidence_for("a") == []


def test_add_relation_with_empty_src_records_no_evidence():
    # CURRENT behavior (knowledge_graph.py:39 `and relation.src`): provenance
    # is dropped entirely when src is the empty string.
    g = LocalGraphStore()
    g.add_relation(Relation(src="", dst="b", kind="sequel", provenance=_ev()))
    assert g.evidence_for("") == []
    assert g.evidence_for("b") == []


def test_evidence_accumulates_in_insertion_order():
    g = LocalGraphStore()
    e1, e2, e3 = _ev("one"), _ev("two"), _ev("three")
    g.add_relation(Relation(src="a", dst="b", kind="k1", provenance=e1))
    g.add_relation(Relation(src="a", dst="c", kind="k2", provenance=e2))
    g.add_relation(Relation(src="a", dst="d", kind="k3", provenance=e3))
    hashes = [e.content_hash for e in g.evidence_for("a")]
    assert hashes == [e1.content_hash, e2.content_hash, e3.content_hash]


def test_evidence_for_missing_node_returns_empty_list():
    assert LocalGraphStore().evidence_for("nope") == []


def test_evidence_for_returns_copy_not_internal_list():
    g = LocalGraphStore()
    g.add_relation(Relation(src="a", dst="b", kind="k", provenance=_ev()))
    first = g.evidence_for("a")
    first.clear()
    assert len(g.evidence_for("a")) == 1


def test_all_ids_sorted():
    g = LocalGraphStore()
    for nid in ("mal:9", "mal:1", "zzz", "aaa"):
        g.upsert_node(_node(nid))
    assert g.all_ids() == ["aaa", "mal:1", "mal:9", "zzz"]


def test_all_ids_empty():
    assert LocalGraphStore().all_ids() == []


def test_mixed_cycle_round_trip():
    g = LocalGraphStore()
    g.upsert_node(_node("mal:1", "Naruto"))
    g.upsert_node(_node("mal:2", "Boruto"))
    ev = _ev("boruto is a sequel")
    g.add_relation(Relation(src="mal:2", dst="mal:1", kind="sequel", provenance=ev))
    assert g.get_node("mal:2").title == "Boruto"
    assert len(g.relations_for("mal:1")) == 1
    assert g.evidence_for("mal:2")[0].content == "boruto is a sequel"


def test_local_graph_satisfies_knowledge_store_protocol():
    assert isinstance(LocalGraphStore(), KnowledgeStore)


def test_local_graph_via_registry(reg):
    g = reg.create("store", "local_graph")
    assert isinstance(g, KnowledgeStore)
    g.upsert_node(_node("mal:1"))


def test_dgraph_store_registered_but_needs_service(reg):
    # DgraphStore constructor only wires HTTP (no network) – constructing is
    # offline-safe; using it would need the service.
    from providers.knowledge_graph import DgraphStore
    store = reg.create("store", "dgraph", base_url="http://localhost:9080")
    assert isinstance(store, DgraphStore)
    assert store._base == "http://localhost:9080"


def test_dgraph_base_url_env_and_slash_strip(monkeypatch):
    from providers.knowledge_graph import DgraphStore
    monkeypatch.setenv("DGRAPH_URL", "http://dgraph.example:8080///")
    assert DgraphStore()._base == "http://dgraph.example:8080"
    assert DgraphStore(base_url="http://x:8080/")._base == "http://x:8080"
