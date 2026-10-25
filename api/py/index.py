"""Vercel serverless — the ONE python entrypoint.

The Vercel python runtime builds a single project-wide entrypoint, so the
pipeline + greenlight routes live here behind an internal router:

  /api/v1/pipeline/catalog | /search?q= | /analyze?title= | /compare?titles= | /refresh
  /api/v1/greenlight (POST) | /api/v1/greenlight/presets

vercel.json rewrites those paths here with the original path in ?__path=.
Same engines as the local bun worker (api/_backend), same seeded Monte Carlo.
"""

from __future__ import annotations
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_HERE = Path(__file__).resolve()

_ANILIST_API = "https://graphql.anilist.co"
REFRESH_TTL_S = 300          # live pull cache — the bundle itself never changes
_REFRESH_CACHE: dict = {"at": 0.0, "data": None}


def _find_backend() -> Path:
    """api/_backend in the serverless bundle (cwd may be /var/task)."""
    for cand in (_HERE.parents[1] / "_backend", _HERE.parents[2] / "_backend",
                 Path.cwd() / "api" / "_backend", Path.cwd() / "_backend"):
        if (cand / "worker.py").is_file():
            return cand
    return _HERE.parents[1] / "_backend"


_BACKEND = _find_backend()
sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("SAKURASCORE_BACKEND_ROOT", str(_BACKEND))

_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

_gl_engine = None


def gl_engine():
    global _gl_engine
    if _gl_engine is None:
        import greenlight as gl_mod
        _gl_engine = gl_mod.build_engine()
    return _gl_engine


# ---- live recency pull (the serverless half of scripts/backend/refresh.py) ----
# Locally, refresh.py deletes the recency cache pages, re-runs the AniList
# collectors and rebuilds the processed CSVs. A serverless bundle is read-only
# and stateless, so the honest equivalent is: pull the same live AniList pages,
# drop EVERY per-instance cache so the next analyze/compare/greenlight rebuilds
# against the fresh landing, and report exactly what moved. Deep history keeps
# coming from the shipped snapshot (same contract as the greenlight cross-match).

_LIVE_MEDIA_FIELDS = "title { romaji english } trending popularity averageScore format episodes status"


def _anilist_page(sort: str, per_page: int, timeout_s: float) -> list[dict]:
    """One bounded, keyless AniList page. Raises on timeout/4xx/5xx."""
    import urllib.request
    q = (f"query {{ Page(page: 1, perPage: {per_page}) "
         f"{{ media(type: ANIME, sort: {sort}, isAdult: false) {{ {_LIVE_MEDIA_FIELDS} }} }} }}")
    req = urllib.request.Request(
        _ANILIST_API,
        data=json.dumps({"query": q}).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": "sakurascore-pipeline/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode())["data"]["Page"]["media"]


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def live_pipeline_pull(timeout_s: float = 6.0, force: bool = False) -> dict:
    """Trending + top-popularity pages from the live AniList API (cached 5 min)."""
    now = time.time()
    if (not force and _REFRESH_CACHE["data"] is not None
            and now - _REFRESH_CACHE["at"] < REFRESH_TTL_S):
        return _REFRESH_CACHE["data"]
    out: dict = {"trending": [], "popularity": [], "offline": False, "error": None}
    try:
        out["trending"] = _anilist_page("TRENDING_DESC", 50, timeout_s)
        out["popularity"] = _anilist_page("POPULARITY_DESC", 50, timeout_s)
    except Exception as exc:  # noqa: BLE001 — offline is a normal outcome
        out["offline"] = True
        out["error"] = f"{type(exc).__name__}: {exc}"
    _REFRESH_CACHE.update({"at": now, "data": out})
    return out


def _reset_backend_caches() -> dict:
    """Drop every in-process cache so the next request rebuilds from scratch."""
    global _gl_engine
    cleared = 0
    _gl_engine = None
    try:
        import worker as wk
        cleared = len(wk._cache)
        wk._cache.clear()
        wk.APP = None
        wk._gl_engine = None
    except Exception:  # noqa: BLE001 — worker may not import; presets still work
        pass
    try:
        import greenlight as gl_mod
        gl_mod._TRENDING_CACHE.update({"at": 0.0, "data": None})
    except Exception:  # noqa: BLE001
        pass
    return {"cache_entries_cleared": cleared}


def _live_catalog_matches(live: dict, catalog_titles: list[str]) -> dict:
    """How much of the live pull is already in the shipped snapshot (receipts)."""
    idx = {_norm_key(t) for t in catalog_titles}
    trending_titles = [m["title"].get("english") or m["title"].get("romaji") or ""
                       for m in (live.get("trending") or [])]
    hits = [t for t in trending_titles if t and _norm_key(t) in idx]
    return {"trending_rows": len(live.get("trending") or []),
            "popularity_rows": len(live.get("popularity") or []),
            "in_shipped_catalog": len(hits),
            "examples": hits[:6]}


class handler(BaseHTTPRequestHandler):
    def _send(self, payload: dict, code: int = 200):
        body = json.dumps(payload, default=str, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        for k, v in _CORS.items():
            self.send_header(k, v)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        for k, v in _CORS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):  # noqa: N802
        self._route("GET")

    def do_POST(self):  # noqa: N802
        self._route("POST")

    def _route(self, method: str):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        # vercel rewrites carry the original path in ?__path= ; direct calls
        # (local `vercel dev`) reach this file with the real path already
        orig = (q.get("__path") or [u.path])[0].split("?")[0]
        parts = [p for p in orig.split("/") if p]
        # parts like [api, v1, pipeline, catalog] or [api, v1, greenlight, presets]
        try:
            if "voice-cast" in parts and method == "POST":
                n = int(self.headers.get("content-length") or 0)
                self._voice_cast(self.rfile.read(n))
            elif "sketch-check" in parts and method == "POST":
                n = int(self.headers.get("content-length") or 0)
                self._sketch_check(self.rfile.read(n))
            elif "pipeline" in parts:
                self._pipeline(parts[parts.index("pipeline") + 1:], q)
            elif "greenlight" in parts:
                self._greenlight(method, parts, q)
            else:
                self._send({"ok": False, "error": f"unknown route {orig!r}"}, 404)
        except Exception as exc:
            self._send({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    def _debug(self):
        import os
        def ls(d):
            try: return sorted(os.listdir(d))[:25]
            except Exception as e: return f"err {e}"
        deps: dict = {}
        for mod in ("numpy", "pandas", "PIL", "torch"):
            try:
                m = __import__(mod)
                deps[mod] = getattr(m, "__version__", "present")
            except Exception as e:  # noqa: BLE001
                deps[mod] = f"MISSING ({type(e).__name__})"
        imports: dict = {}
        for mod in ("worker", "greenlight", "casting", "sketch"):
            try:
                __import__(mod)
                imports[mod] = "ok"
            except Exception as e:  # noqa: BLE001
                imports[mod] = f"{type(e).__name__}: {e}"
        catalog_rows = None
        try:
            import worker as wk
            wk.ensure_boot()
            catalog_rows = int(len(wk.APP.catalog))
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "here": str(_HERE), "cwd": os.getcwd(),
                "python": sys.version.split()[0],
                "backend": str(_BACKEND), "backend_exists": (_BACKEND / "worker.py").is_file(),
                "backend_ls": ls(_BACKEND) if (_BACKEND / "worker.py").is_file() else None,
                "deps": deps, "imports": imports, "catalog_rows": catalog_rows,
                "api_ls": ls(_HERE.parents[1]), "root_ls": ls(_HERE.parents[2])}

    # ---- the real pipeline (same worker protocol as the local bun bridge) ----
    def _pipeline(self, rest: list, q: dict):
        cmd = rest[0] if rest else ""
        if cmd == "__debug":
            self._send(self._debug())
            return
        if cmd == "refresh":
            self._refresh()
            return
        import worker as wk
        wk.ensure_boot()
        if cmd == "catalog":
            self._send(wk.handle({"cmd": "catalog"}))
        elif cmd == "search":
            self._send(wk.handle({"cmd": "search", "q": (q.get("q") or [""])[0]}))
        elif cmd == "analyze":
            title = (q.get("title") or [""])[0]
            if not title.strip():
                self._send({"ok": False, "error": "missing ?title="}, 400)
                return
            self._send({"ok": True, "result": wk.handle({"cmd": "analyze", "title": title})})
        elif cmd == "compare":
            titles = [t for t in (q.get("titles") or [""])[0].split("|") if t][:4]
            if len(titles) < 2:
                self._send({"ok": False, "error": "need >=2 titles, | separated"}, 400)
                return
            self._send({"ok": True, "result": wk.handle({"cmd": "compare", "titles": titles})})
        else:
            self._send({"ok": False, "error": f"unknown pipeline route {cmd!r}"}, 404)

    # ---- ⟳ Pull live data: bounded live AniList pull + cache invalidation ----
    def _refresh(self):
        t0 = time.perf_counter()
        steps: list[dict] = []

        # 1. live pull (trending + top-popularity, the pages refresh.py refreshes)
        live = live_pipeline_pull(force=True)
        pull_ms = int((time.perf_counter() - t0) * 1000)
        steps.append({
            "step": "live AniList pull — TRENDING_DESC + POPULARITY_DESC (top-50 each)",
            "trending_rows": len(live.get("trending") or []),
            "popularity_rows": len(live.get("popularity") or []),
            "offline": bool(live.get("offline")),
            "error": live.get("error"),
            "source": _ANILIST_API,
            "ms": pull_ms,
        })

        # 2. drop every cache, then re-boot so the row count is a fresh receipt
        t1 = time.perf_counter()
        reset = _reset_backend_caches()
        rows, reload_err = 0, None
        try:
            import worker as wk
            wk.ensure_boot()
            rows = int(len(wk.APP.catalog))
        except Exception as exc:  # noqa: BLE001
            reload_err = f"{type(exc).__name__}: {exc}"
        reset_ms = int((time.perf_counter() - t1) * 1000)
        steps.append({
            "step": "reload pipeline + clear worker/greenlight caches",
            "catalog_rows": rows,
            "cache_entries_cleared": reset.get("cache_entries_cleared", 0),
            "reload_error": reload_err,
            "ms": reset_ms,
        })

        # 3. receipts: how much of the live pull already sits in the snapshot
        titles: list[str] = []
        if rows:
            try:
                import worker as wk
                titles = [str(t) for t in wk.APP.catalog["title_english"].dropna().tolist()]
            except Exception:  # noqa: BLE001
                titles = []
        live_summary = _live_catalog_matches(live, titles)

        self._send({
            "ok": True,
            "serverless": True,
            "note": ("serverless refresh = live AniList pull + full cache invalidation; the deep-history "
                     "CSVs stay the shipped snapshot (read-only bundle). Run `bun run dev` locally for "
                     "the full re-pull that rebuilds the CSVs."),
            "result": {
                "freshness": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "steps": steps,
                "live": live_summary,
                "offline": bool(live.get("offline")),
            },
        })

    # ---- voice casting (pure python + JSON — runs on serverless) ----
    def _voice_cast(self, body: bytes):
        import json as _json
        import casting as cast_mod
        try:
            payload = _json.loads(body or b"{}")
        except Exception:
            payload = {}
        out = cast_mod.cast_for_script(str(payload.get("script") or ""),
                                       top_n=int(payload.get("top_n") or 5))
        if out.get("status") != "ok":
            self._send({"ok": False, "error": out.get("error")}, 400)
            return
        self._send({"ok": True, "result": out})

    # ---- sketch check: heuristics on serverless (CNN is local-only) ----
    def _sketch_check(self, body: bytes):
        import json as _json
        import sketch as sketch_mod
        try:
            payload = _json.loads(body or b"{}")
        except Exception:
            payload = {}
        out = sketch_mod.classify_base64(str(payload.get("image_b64") or ""))
        if out.get("status") != "ok":
            self._send({"ok": False, "error": out.get("error")}, 400)
            return
        self._send({"ok": True, "result": out})

    # ---- the greenlight concept terminal ----
    def _greenlight(self, method: str, parts: list, q: dict):
        import greenlight as gl_mod
        if parts[-1] == "presets":
            self._send({"ok": True, "result": {"presets": gl_mod.SAMPLE_CONCEPTS,
                                               "roadmap": gl_mod.ROADMAP}})
            return
        if method != "POST":
            self._send({"ok": False, "error": "POST a {concept} JSON body"}, 405)
            return
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        concept = str(body.get("concept") or body.get("text") or "")
        if len(concept.strip()) < 12:
            self._send({"ok": False, "error": "concept text too short — paste a logline, script excerpt, character design or any Japanese-media pitch (≥ 12 chars)"}, 400)
            return
        out = gl_engine().run({
            "concept": concept,
            "title": body.get("title") or "",
            "format": body.get("format") or "",
            "episodes": body.get("episodes"),
        })
        if out.get("status") != "ok":
            self._send({"ok": False, "error": out.get("error")}, 400)
            return
        self._send({"ok": True, "result": out})

    def log_message(self, *args):
        pass
