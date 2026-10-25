"""IP knowledge graph storage (upstream clone: dgraph-io/dgraph, Apache-2.0).

Exposed capabilities:
- ``store`` / ``dgraph`` - Dgraph-backed IP graph + provenance ledger (Features 10/11/14).
- ``store`` / ``local_graph`` - dependency-free in-process graph (tests / offline).

The Dgraph provider speaks Dgraph's HTTP API (JSON mutations + DQL), so the
Go database runs as an external service; nothing from its repo is vendored.
"""

from __future__ import annotations

import json
import os
from typing import Any

from engine_api import Evidence, IPNode, Relation, provider

from ._bootstrap import ProviderError


_NODE_FIELDS = "uid, id, title, kind, genres, studio, adaptation_of, aliases, attributes_json"


class LocalGraphStore:
    """KnowledgeStore kept in process memory (dict-backed)."""

    def __init__(self) -> None:
        self._nodes: dict[str, IPNode] = {}
        self._relations: list[Relation] = []
        self._evidence: dict[str, list[Evidence]] = {}

    def upsert_node(self, node: IPNode) -> str:
        self._nodes[node.id] = node
        return node.id

    def add_relation(self, relation: Relation) -> None:
        self._relations.append(relation)
        if relation.provenance is not None and relation.src:
            self._evidence.setdefault(relation.src, []).append(relation.provenance)

    def get_node(self, node_id: str) -> IPNode | None:
        return self._nodes.get(node_id)

    def relations_for(self, node_id: str) -> list[Relation]:
        return [r for r in self._relations if r.src == node_id or r.dst == node_id]

    def evidence_for(self, node_id: str) -> list[Evidence]:
        return list(self._evidence.get(node_id, []))

    def all_ids(self) -> list[str]:
        return sorted(self._nodes)


class DgraphStore:
    """KnowledgeStore over a running Dgraph alpha (HTTP: :8080)."""

    def __init__(self, base_url: str | None = None, namespace: str = "main") -> None:
        self._base = (base_url or os.environ.get("DGRAPH_URL") or "http://localhost:8080").rstrip("/")
        self._namespace = namespace
        self._import()

    def _import(self) -> None:
        try:
            import requests  # stdlib-adjacent, always available in this env
        except ImportError as exc:  # pragma: no cover
            raise ProviderError("requests is required for DgraphStore") from exc
        self._http = requests

    # -- low-level ---------------------------------------------------------
    def _post(self, path: str, payload: Any, content_type: str = "application/json") -> Any:
        try:
            resp = self._http.post(f"{self._base}{path}", data=payload if isinstance(payload, str) else json.dumps(payload),
                                   headers={"Content-Type": content_type}, timeout=15)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except self._http.exceptions.ConnectionError as exc:
            raise ProviderError(
                f"cannot reach Dgraph at {self._base} (start it or set DGRAPH_URL): {exc}"
            ) from exc
        except Exception as exc:
            raise ProviderError(f"Dgraph request {path} failed: {exc}") from exc

    def apply_schema(self, schema: str) -> None:
        self._post("/alter", schema, content_type="application/dql")

    # -- KnowledgeStore ----------------------------------------------------
    def upsert_node(self, node: IPNode) -> str:
        mutation = {
            "set": [
                {
                    "id": node.id,
                    "title": node.title,
                    "kind": node.kind,
                    "genres": list(node.genres),
                    "studio": node.studio or "",
                    "adaptation_of": node.adaptation_of or "",
                    "aliases": list(node.aliases),
                    "attributes_json": json.dumps(dict(node.attributes), ensure_ascii=False),
                    "dgraph.type": "IPNode",
                }
            ]
        }
        # Upsert by deterministic id: query existing uid, then mutate.
        query = "query N($id: string) { n as var(func: eq(id, $id)) }"
        body = {
            "query": query,
            "variables": {"$id": node.id},
            "set": [{"uid": "uid(n)", **mutation["set"][0]}],
        }
        # uid(n) unset -> Dgraph creates a new node; set -> updates in place.
        self._post("/mutate?commitNow=true", body)
        return node.id

    def add_relation(self, relation: Relation) -> None:
        edge = {"dgraph.type": "Relation", "src_id": relation.src, "dst_id": relation.dst,
                "kind": relation.kind}
        if relation.provenance is not None:
            edge["evidence_json"] = json.dumps(
                {
                    "source": relation.provenance.source,
                    "url": relation.provenance.url,
                    "content_hash": relation.provenance.content_hash,
                    "retrieved_at": relation.provenance.retrieved_at.isoformat(),
                },
                ensure_ascii=False,
            )
        query = "query R($s: string, $d: string) { s as var(func: eq(id, $s)); d as var(func: eq(id, $d)) }"
        body = {
            "query": query,
            "variables": {"$s": relation.src, "$d": relation.dst},
            "set": [{"uid": "uid(s)", relation.kind: {"uid": "uid(d)"}, **{k: v for k, v in edge.items() if k not in ("src_id", "dst_id")}}],
        }
        self._post("/mutate?commitNow=true", body)

    def get_node(self, node_id: str) -> IPNode | None:
        data = self._query(
            "query N($id: string) { q(func: eq(id, $id)) { %s } }" % _NODE_FIELDS,
            {"$id": node_id},
        )
        rows = (data.get("data") or {}).get("q") if isinstance(data, dict) else None
        if not rows:
            return None
        row = rows[0]
        return IPNode(
            id=row.get("id") or node_id,
            title=row.get("title") or "",
            kind=row.get("kind") or "anime",
            genres=tuple(row.get("genres") or []),
            studio=row.get("studio") or None,
            adaptation_of=row.get("adaptation_of") or None,
            aliases=tuple(row.get("aliases") or []),
            attributes=json.loads(row.get("attributes_json") or "{}"),
        )

    def evidence_for(self, node_id: str) -> list[Evidence]:
        data = self._query(
            "query E($id: string) { q(func: eq(id, $id)) { ~dst_id { evidence_json } } }",
            {"$id": node_id},
        )
        out: list[Evidence] = []
        rows = (data.get("data") or {}).get("q") or []
        for row in rows:
            for rel in row.get("~dst_id") or []:
                raw = rel.get("evidence_json")
                if not raw:
                    continue
                payload = json.loads(raw)
                out.append(
                    Evidence(
                        source=payload.get("source", "dgraph"),
                        url=payload.get("url", ""),
                        content=payload.get("content_hash", ""),
                        metadata={"node_id": node_id},
                    )
                )
        return out

    def _query(self, dql: str, variables: dict[str, str]) -> Any:
        return self._post("/query", {"query": dql, "variables": variables})


@provider("store", "local_graph")
def _local_factory(**config: Any) -> LocalGraphStore:
    return LocalGraphStore(**config)


@provider("store", "dgraph")
def _dgraph_factory(**config: Any) -> DgraphStore:
    return DgraphStore(**config)


__all__ = ["LocalGraphStore", "DgraphStore"]
