"""Long-term agent memory (upstream clone: getzep/zep, Apache-2.0).

Exposed capability: ``memory`` / ``zep`` - session-based memory over the Zep
community server's REST API (Features 11-17), plus ``memory`` / ``local`` -
a dependency-free dict-backed fallback for tests and offline runs.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from engine_api import Evidence, provider

from ._bootstrap import ProviderError


class LocalMemoryStore:
    """MemoryStore: in-process, per-session text store with recency recall."""

    def __init__(self) -> None:
        self._sessions: dict[str, list[dict[str, Any]]] = {}

    def remember(self, session_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        self._sessions.setdefault(session_id, []).append(
            {"text": text, "metadata": dict(metadata or {}), "ts": time.time()}
        )

    def recall(self, session_id: str, query: str, k: int = 5) -> list[Evidence]:
        entries = self._sessions.get(session_id, [])
        terms = {t for t in query.lower().split() if t}
        scored = []
        for entry in entries:
            words = set(entry["text"].lower().split())
            scored.append((len(terms & words), entry))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            Evidence(
                source="memory:local",
                url=f"memory://{session_id}/{idx}",
                title=None,
                content=entry["text"],
                metadata=entry["metadata"],
            )
            for idx, (_, entry) in enumerate(scored[: max(1, k)])
            if _
        ]


class ZepMemoryStore:
    """MemoryStore over the Zep community-edition REST API."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self._base = (base_url or os.environ.get("ZEP_URL") or "http://localhost:8080").rstrip("/")
        self._api_key = api_key or os.environ.get("ZEP_API_KEY")
        try:
            import requests
        except ImportError as exc:  # pragma: no cover
            raise ProviderError("requests is required for ZepMemoryStore") from exc
        self._http = requests

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Api-Key {self._api_key}"
        return headers

    def _post(self, path: str, payload: Any) -> Any:
        try:
            resp = self._http.post(f"{self._base}{path}", data=json.dumps(payload),
                                   headers=self._headers(), timeout=15)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except self._http.exceptions.ConnectionError as exc:
            raise ProviderError(
                f"cannot reach Zep at {self._base} (start it or set ZEP_URL): {exc}"
            ) from exc
        except Exception as exc:
            raise ProviderError(f"Zep request {path} failed: {exc}") from exc

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            resp = self._http.get(f"{self._base}{path}", params=params or {},
                                  headers=self._headers(), timeout=15)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except Exception as exc:
            raise ProviderError(f"Zep GET {path} failed: {exc}") from exc

    # -- MemoryStore -------------------------------------------------------
    def remember(self, session_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        # Ensure session exists (idempotent - 409/200 tolerated via _post).
        self._post("/sessions", {"session_id": session_id, "metadata": dict(metadata or {})})
        self._post(
            f"/sessions/{session_id}/memory",
            {"messages": [{"role": "user", "content": text, "metadata": dict(metadata or {})}]},
        )

    def recall(self, session_id: str, query: str, k: int = 5) -> list[Evidence]:
        data = self._post(
            "/sessions/search",
            {"text": query, "session_id": session_id, "top_k": k},
        )
        if not data:
            data = self._get(f"/sessions/{session_id}/memory", params={"search_query": query}) or {}
        rows = data.get("results") or data.get("matches") or []
        out: list[Evidence] = []
        for idx, row in enumerate(rows[: max(1, k)]):
            if isinstance(row, dict):
                msg = row.get("message") or row
                content = msg.get("content") or row.get("summary") or json.dumps(row, default=str)
                metadata = msg.get("metadata") or {}
            else:
                content, metadata = str(row), {}
            out.append(
                Evidence(
                    source="memory:zep",
                    url=f"zep://sessions/{session_id}#{idx}",
                    content=content,
                    metadata=metadata,
                )
            )
        return out


@provider("memory", "local")
def _local_factory(**config: Any) -> LocalMemoryStore:
    return LocalMemoryStore(**config)


@provider("memory", "zep")
def _zep_factory(**config: Any) -> ZepMemoryStore:
    return ZepMemoryStore(**config)


__all__ = ["LocalMemoryStore", "ZepMemoryStore"]
