"""Live data refresh — bounded, observable re-pull of the recency signals.

Deletes only the recency-sensitive cache pages (trending x2, top-popularity
page 1), re-fetches them from the live AniList GraphQL API (keyless), rebuilds
the processed CSVs, and reports exactly what changed. Deep history stays
cached, so the operation is bounded to a handful of live requests.

Output: one JSON summary line on stdout.
"""

from __future__ import annotations
import json
import subprocess
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend 111" / "redbull-thapar-japan"
COLLECT = BACKEND / "scripts" / "data_collection"
RAW = BACKEND / "data" / "raw" / "anilist"

REFRESH_PAGES = ["trending_page001.json", "trending_page002.json", "top_popularity_page001.json"]


def run(script: str) -> tuple[int, str]:
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, str(COLLECT / script)],
                       capture_output=True, text=True, cwd=str(COLLECT))
    ms = int((time.perf_counter() - t0) * 1000)
    return ms, (p.stdout + p.stderr)[-1200:]


def main() -> None:
    t0 = time.perf_counter()
    out = {"steps": []}

    # 1. invalidate recency caches
    invalidated = []
    for name in REFRESH_PAGES:
        f = RAW / name
        if f.exists():
            f.unlink()
            invalidated.append(name)
    out["steps"].append({"step": "invalidate recency caches", "invalidated": invalidated})

    # 2. live fetch (cached pages skip; only invalidated ones hit the API)
    ms, log = run("fetch_anilist.py")
    out["steps"].append({"step": "fetch_anilist.py (live)", "ms": ms, "log_tail": log.strip().splitlines()[-6:]})

    # 3. rebuild processed CSVs
    ms, log = run("process.py")
    catalog = BACKEND / "data" / "processed" / "anilist_catalog.csv"
    rows = sum(1 for _ in open(catalog, encoding="utf-8-sig")) - 1
    out["steps"].append({"step": "process.py", "ms": ms,
                         "catalog_rows": rows,
                         "log_tail": log.strip().splitlines()[-6:]})

    out["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    out["freshness"] = time.strftime("%Y-%m-%d %H:%M:%S")
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
