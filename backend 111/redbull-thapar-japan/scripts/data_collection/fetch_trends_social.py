"""Pull supplementary trend/social signals.

  A) Google Trends via pytrends (unofficial; often rate-limited by Google).
     - 5-year interest-over-time for a set of anime keywords, geo=IN
     - falls back gracefully and records failures in the manifest.
  B) Reddit public JSON endpoints (no OAuth): r/AnimeIndia top posts of
     all-time/year/month -> which titles the Indian community actually
     discusses (great qualitative ground-truth for the India seed list).

Both are best-effort: network blocks are recorded, never fatal.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, get_json, save_json, session  # noqa: E402

OUT = DATA / "raw" / "trends"
MANIFEST = OUT / "manifest.json"

TREND_KEYWORDS = [
    ["anime"], ["crunchyroll"], ["one piece"], ["demon slayer"],
    ["jujutsu kaisen"], ["solo leveling"], ["naruto"], ["anime hindi dub"],
    ["manga"], ["otaku"],
]


def google_trends():
    results = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("pytrends not installed - skipping (pip install pytrends)")
        results["pytrends"] = "not_installed"
        save_json(MANIFEST, results)
        return

    try:
        py = TrendReq(hl="en-IN", tz=330, timeout=(10, 25))
    except Exception as e:
        print(f"TrendReq init failed: {e}")
        results["pytrends"] = f"init_failed: {e}"
        save_json(MANIFEST, results)
        return

    ok = 0
    for kw in TREND_KEYWORDS:
        name = kw[0].replace(" ", "_")
        cache = OUT / f"trends_in_{name}.json"
        if cache.exists():
            ok += 1
            continue
        try:
            py.build_payload(kw, timeframe="2021-10-01 2026-10-20", geo="IN")
            df = py.interest_over_time()
            if df is None or df.empty:
                raise RuntimeError("empty frame")
            records = df.reset_index().rename(
                columns={"date": "date", kw[0]: "interest"}).astype(str).to_dict("records")
            save_json(cache, {"keyword": kw[0], "geo": "IN", "data": records})
            ok += 1
            print(f"  trends IN {kw[0]!r}: {len(records)} weeks")
        except Exception as e:
            print(f"  trends IN {kw[0]!r} FAILED: {type(e).__name__}: {e}")
            results[f"trends_{name}"] = f"{type(e).__name__}: {e}"
            save_json(MANIFEST, results)
        time.sleep(3.0)
    results["trends_ok"] = ok
    save_json(MANIFEST, results)
    print(f"Google Trends: {ok}/{len(TREND_KEYWORDS)} keywords succeeded")


def reddit():
    s = session()
    s.headers["User-Agent"] = ("SakuraScoreIndia/0.1 research bot "
                               "(hackathon project; learning about anime interest in India)")
    sub = "AnimeIndia"
    for period in ["month", "year", "all"]:
        cache = OUT / f"reddit_{sub}_top_{period}.json"
        if cache.exists():
            continue
        try:
            body = get_json(
                s, f"https://www.reddit.com/r/{sub}/top.json",
                params={"t": period, "limit": 100}, timeout=20)
            posts = [{
                "title": c["data"].get("title"),
                "score": c["data"].get("score"),
                "num_comments": c["data"].get("num_comments"),
                "upvote_ratio": c["data"].get("upvote_ratio"),
                "created_utc": c["data"].get("created_utc"),
                "flair": c["data"].get("link_flair_text"),
                "url": c["data"].get("url"),
            } for c in body.get("data", {}).get("children", [])]
            save_json(cache, {"subreddit": sub, "period": period, "posts": posts})
            print(f"  reddit r/{sub} top/{period}: {len(posts)} posts")
        except Exception as e:
            print(f"  reddit r/{sub} top/{period} FAILED: {type(e).__name__}: {e}")
        time.sleep(2.0)
    print("Reddit done (failures above are non-fatal - Reddit blocks some clients)")


if __name__ == "__main__":
    print("A) Google Trends (best-effort)...")
    google_trends()
    print("B) Reddit r/AnimeIndia (best-effort)...")
    reddit()
