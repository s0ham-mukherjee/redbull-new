"""SakuraScore pipeline worker — persistent process speaking line-JSON over stdio.

Bridges the bun frontend server to the real Python scoring pipeline
(backend 111/redbull-thapar-japan/src/APP.py). Spawned once by the bun server;
handles one JSON request per stdin line, answers one JSON line per request.

Surface = 100% of PipelineResult plus the fields the pipeline computes but
historically dropped at serialization: the two-pass provisional→final score,
the confidence part-by-part breakdown, the matched trends keyword, the graded
success seed-hit row, tier notes for unreleased titles, and per-genre affinity
values. Deterministic per-title cache for instant repeat analysis.

Commands:
  {"id":1,"cmd":"boot"}
  {"id":2,"cmd":"catalog"}
  {"id":3,"cmd":"search","q":"chainsaw"}
  {"id":4,"cmd":"analyze","title":"Chainsaw Man – The Movie: Reze Arc"}
  {"id":5,"cmd":"greenlight","concept":"…script / character design…"}
  {"id":6,"cmd":"greenlight_presets"}
  {"id":7,"cmd":"voice_cast","script":"…"}
  {"id":8,"cmd":"sketch_check","image_b64":"…"}
"""

from __future__ import annotations
import dataclasses
import json
import os
import sys
import time
from pathlib import Path

# local: the full repo checkout; serverless: api/_backend (set by the function)
BACKEND = Path(os.environ.get("SAKURASCORE_BACKEND_ROOT")
               or Path(__file__).resolve().parents[2] / "backend 111" / "redbull-thapar-japan")
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.app import SakuraScoreApp, _norm  # noqa: E402
import greenlight as gl_mod  # noqa: E402
import casting  # noqa: E402
import sketch as sketch_mod  # noqa: E402

APP: SakuraScoreApp | None = None
_cache: dict[str, dict] = {}
_gl_engine: gl_mod.GreenlightEngine | None = None


def gl_engine() -> gl_mod.GreenlightEngine:
    """Lazy greenlight boot — catalog tensor built on first concept, reused."""
    global _gl_engine
    if _gl_engine is None:
        t0 = time.perf_counter()
        _gl_engine = gl_mod.build_engine()
        _gl_engine._boot_ms = int((time.perf_counter() - t0) * 1000)
    return _gl_engine


def ser(o):
    if dataclasses.is_dataclass(o):
        return {k: ser(v) for k, v in dataclasses.asdict(o).items()}
    if isinstance(o, dict):
        return {k: ser(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [ser(v) for v in o]
    if isinstance(o, (int, float, str, bool)) or o is None:
        return o
    return str(o)


def confidence_breakdown(*, meta_found: bool, wiki: dict | None, trends: dict,
                         seed_hit, unreleased: bool) -> list[dict]:
    """Mirror of SakuraScoreApp._confidence, part by part (display only)."""
    return [
        {"part": "catalog metadata", "got": meta_found, "points": 30 if meta_found else 0, "max": 30},
        {"part": "wikipedia volume", "got": wiki is not None, "points": 25 if wiki else 8, "max": 25},
        {"part": "trends growth", "got": trends.get("growth_2y_pct") is not None,
         "points": 15 if trends.get("growth_2y_pct") is not None else 5, "max": 15},
        {"part": "hindi wikipedia", "got": bool(wiki and wiki.get("has_hindi_wiki")),
         "points": 10 if (wiki and wiki.get("has_hindi_wiki")) else 0, "max": 10},
        {"part": "graded success seed", "got": seed_hit is not None,
         "points": 10 if seed_hit is not None else 0, "max": 10},
        {"part": "released demand", "got": not unreleased, "points": 10 if not unreleased else 5, "max": 10},
    ]


def ensure_boot():
    """serverless helper — boot the pipeline once per lambda instance."""
    if APP is None:
        handle({"cmd": "boot"})


def handle(req: dict) -> dict:
    global APP
    cmd = req.get("cmd")
    if cmd == "boot":
        t0 = time.perf_counter()
        APP = SakuraScoreApp()
        return {
            "catalog_rows": int(len(APP.catalog)),
            "trend_keywords": len(APP.trends_growth),
            "wiki_rows": int(len(APP.wiki)),
            "states": int(len(APP.states)),
            "boot_ms": int((time.perf_counter() - t0) * 1000),
        }
    if APP is None:
        raise RuntimeError("worker not booted")
    if cmd == "catalog":
        return {"titles": APP.released_top(80), "showcase": APP.showcase_titles()}
    if cmd == "search":
        q = str(req.get("q") or "")
        n = _norm(q)
        if not n:
            return {"titles": APP.showcase_titles()}
        hits = APP.catalog[APP.catalog["_norm_en"].str.contains(n, regex=False)
                           | APP.catalog["_norm_ro"].str.contains(n, regex=False)]
        hits = hits.sort_values("popularity", ascending=False)
        titles = [t for t in hits["title_english"].dropna().head(12)]
        return {"titles": titles or APP.showcase_titles()}
    if cmd == "compare":
        titles = [str(t) for t in (req.get("titles") or [])][:4]
        if len(titles) < 2:
            raise ValueError("compare needs >= 2 titles")
        results = []
        for t in titles:
            r = handle({"cmd": "analyze", "title": t})
            results.append({
                "title": r["title"], "sakura_score": r["sakura_score"], "grade": r["grade"],
                "confidence": r["confidence"], "unreleased": r["unreleased"],
                "factors": r["factors"], "genres": r["metadata"].get("genres") or [],
                "format": r["metadata"].get("format"), "recommended": r["localization_economics"]["recommended_mode"],
            })
        factor_names = sorted({f["name"] for r_ in results for f in r_["factors"]})
        matrix = []
        for fn in factor_names:
            vals = []
            for r_ in results:
                f = next((x for x in r_["factors"] if x["name"] == fn), None)
                vals.append(f["value"] if f else None)
            best = max(v for v in vals if v is not None) if any(v is not None for v in vals) else None
            matrix.append({"factor": fn, "values": vals, "best": best})
        winner = max(results, key=lambda r_: r_["sakura_score"])
        return {"results": results, "matrix": matrix, "winner": winner["title"],
                "score_gap": winner["sakura_score"] - min(r_["sakura_score"] for r_ in results)}
    if cmd == "clear_cache":
        global _gl_engine
        n = len(_cache)
        _cache.clear()
        # re-load the CSVs so a live data refresh is visible without a
        # worker restart; the greenlight catalog tensor rebuilds lazily
        APP = SakuraScoreApp()
        _gl_engine = None
        return {"cleared": n, "app_reloaded": True,
                "catalog_rows": int(len(APP.catalog))}
    if cmd == "greenlight":
        concept = str(req.get("concept") or req.get("text") or "")
        out = gl_engine().run({
            "concept": concept,
            "title": req.get("title") or "",
            "format": req.get("format") or "",
            "episodes": req.get("episodes"),
        })
        if out.get("status") != "ok":
            raise ValueError(str(out.get("error") or "greenlight failed"))
        # voice casting from the concept text itself (a script reads as a script)
        try:
            out["casting"] = casting.cast_for_script(concept, top_n=5)
        except Exception as exc:
            out["casting"] = {"status": "error", "error": str(exc)}
        # optional sketch check (character design attached as base64)
        if req.get("image_b64"):
            try:
                out["sketch"] = sketch_mod.classify_base64(str(req["image_b64"]))
            except Exception as exc:
                out["sketch"] = {"status": "error", "error": str(exc)}
        return out
    if cmd == "greenlight_presets":
        return {"presets": gl_mod.SAMPLE_CONCEPTS, "roadmap": gl_mod.ROADMAP}
    if cmd == "voice_cast":
        script = str(req.get("script") or "")
        out = casting.cast_for_script(script, top_n=int(req.get("top_n") or 5))
        if out.get("status") != "ok":
            raise ValueError(str(out.get("error")))
        return out
    if cmd == "sketch_check":
        b64 = req.get("image_b64") or req.get("image") or ""
        out = sketch_mod.classify_base64(str(b64))
        if out.get("status") != "ok":
            raise ValueError(str(out.get("error")))
        return out
    if cmd == "analyze":
        title = str(req.get("title") or "")
        key = _norm(title)
        if key in _cache:
            return {**_cache[key], "cache_hit": True}
        t0 = time.perf_counter()

        # spy on the two-pass scoring: call 1 = provisional @1.55x, call 2 = final
        captured: list = []
        orig_score = APP.scoring.score_candidate
        def spy(**kw):
            r = orig_score(**kw)
            captured.append(r)
            return r
        APP.scoring.score_candidate = spy
        try:
            r = APP.run_candidate(title)
        finally:
            APP.scoring.score_candidate = orig_score

        out = ser(r)
        out["why_bullets"] = r.why_bullets
        out["pipeline_ms"] = int((time.perf_counter() - t0) * 1000)

        # hidden-but-valuable fields, recomputed exactly as the pipeline does
        meta_found = APP.lookup(title) is not None
        wiki = r.wiki_evidence
        display = r.title
        trends = APP._trends_for({"title_english": display}, display)
        seed_match = APP.seed[APP.seed["title"].fillna("").map(
            lambda s: _norm(s) == _norm(display) or _norm(display) in _norm(s))]
        seed_hit = None if seed_match.empty else ser(seed_match.iloc[0].to_dict())
        unreleased = bool(r.unreleased)
        out["confidence_parts"] = confidence_breakdown(
            meta_found=meta_found, wiki=wiki, trends=trends,
            seed_hit=seed_hit, unreleased=unreleased)
        out["trends"] = trends
        out["seed_hit"] = seed_hit
        out["two_pass"] = {
            "provisional": captured[0].sakura_score if captured else None,
            "final": captured[1].sakura_score if len(captured) > 1 else r.sakura_score,
            "plan_reach": r.localization_economics.recommended_plan.reach_multiplier,
            "note": "pass 1 scores at the 1.55x prior → economics pick the plan → pass 2 rescores at the plan's reach",
        }
        if captured and getattr(captured[-1], "tier_notes", None):
            out["tier_notes"] = captured[-1].tier_notes
        genre_aff = getattr(APP.scoring, "GENRE_AFFINITY", {})
        out["genre_affinity"] = [
            {"genre": g, "affinity": genre_aff.get(g, 55)} for g in (r.metadata.get("genres") or [])
        ]
        out["cache_hit"] = False

        _cache[key] = out
        return out
    raise ValueError(f"unknown cmd {cmd!r}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            out = {"id": req.get("id"), "ok": True, "result": handle(req)}
        except Exception as exc:  # structured failure, worker stays alive
            out = {"id": req.get("id") if isinstance(req, dict) else None,
                   "ok": False, "error": f"{type(exc).__name__}: {exc}"}
        try:
            sys.stdout.write(json.dumps(out, default=str, ensure_ascii=False) + "\n")
        except UnicodeEncodeError:
            sys.stdout.write(json.dumps(out, default=str, ensure_ascii=True) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
