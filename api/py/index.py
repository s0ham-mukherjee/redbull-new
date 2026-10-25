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
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_HERE = Path(__file__).resolve()


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
        return {"ok": True, "here": str(_HERE), "cwd": os.getcwd(),
                "backend": str(_BACKEND), "backend_exists": (_BACKEND / "worker.py").is_file(),
                "api_ls": ls(_HERE.parents[1]), "root_ls": ls(_HERE.parents[2])}

    # ---- the real pipeline (same worker protocol as the local bun bridge) ----
    def _pipeline(self, rest: list, q: dict):
        cmd = rest[0] if rest else ""
        if cmd == "__debug":
            self._send(self._debug())
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
        elif cmd == "refresh":
            self._send({"ok": False, "error": "deep-history refresh runs locally (bun server ⟳ button); serverless serves the shipped snapshot + live AniList trending"}, 501)
        else:
            self._send({"ok": False, "error": f"unknown pipeline route {cmd!r}"}, 404)

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
