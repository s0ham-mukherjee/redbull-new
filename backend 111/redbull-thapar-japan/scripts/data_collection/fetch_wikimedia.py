"""Pull Wikipedia pageview demand signals from the Wikimedia Pageviews REST API.

Pipeline:
  1. Load the top-N anime titles from cached AniList data (data/raw/anilist).
  2. Resolve each title to an en.wikipedia article via the MediaWiki opensearch
     API (handles "Attack on Titan" -> "Attack on Titan" and disambiguations).
  3. For each resolved article, fetch ~24 months of daily pageviews from the
     per-article REST endpoint (all-access, all-agents).
  4. For the top 50 titles, also try hi.wikipedia (Hindi) as an India-language
     interest proxy; misses are recorded in the manifest, not treated as errors.

Everything is cached; a manifest JSON tracks resolution status per title.
"""
import json
import re
import sys
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, get_json, load_json, save_json, session  # noqa: E402

OUT = DATA / "raw" / "wikimedia"
PV_DIR = OUT / "pageviews"
TOP_N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
HINDI_N = 50

REST = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
OPENSEARCH = "https://{project}.wikipedia.org/w/api.php"


def dly(d: date) -> str:
    return d.strftime("%Y%m%d")


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")
    return s[:120] or "untitled"


def resolve_article(s, title: str, project: str = "en") -> str | None:
    """Resolve an anime title to the best-matching wiki article via opensearch."""
    try:
        body = get_json(s, OPENSEARCH.format(project=project), params={
            "action": "opensearch", "search": title, "limit": 3,
            "namespace": 0, "format": "json",
        }, timeout=15)
        names = body[1] if len(body) > 1 else []
        return names[0] if names else None
    except Exception as e:
        print(f"    opensearch failed for {title!r}: {e}")
        return None


def fetch_pageviews(s, project: str, article: str, start: date, end: date) -> list:
    url = f"{REST}/{project}/all-access/all-agents/{quote(article)}/daily/{dly(start)}/{dly(end)}"
    try:
        body = get_json(s, url, timeout=30)
        return body.get("items", [])
    except Exception as e:
        msg = str(e)
        if "404" in msg or "404 Client Error" in msg:
            return []  # no data for this article - fine
        raise


def quote(title: str) -> str:
    from urllib.parse import quote as _q
    return _q(title.replace(" ", "_"), safe="")


def main():
    # 1. Collect candidate titles from AniList caches (top popularity first).
    anilist_dir = DATA / "raw" / "anilist"
    titles: list[str] = []
    seen = set()
    for f in sorted(anilist_dir.glob("top_popularity_page*.json")):
        body = load_json(f)
        for m in body["data"]["Page"]["media"]:
            t = m["title"].get("english") or m["title"].get("romaji")
            if t and t.lower() not in seen:
                seen.add(t.lower())
                titles.append(t)
    titles = titles[:TOP_N]
    print(f"Wikimedia: resolving {len(titles)} anime titles (top {TOP_N} by popularity)")

    today = date.today()
    end = today - timedelta(days=2)          # pageview API lags ~1 day
    start = end.replace(year=end.year - 2)   # ~24 months of history

    manifest_path = OUT / "manifest_en.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {}

    s = session()
    for i, title in enumerate(titles, 1):
        if title in manifest and manifest[title].get("status") == "ok":
            continue
        article = resolve_article(s, title)
        time.sleep(0.15)
        if not article:
            manifest[title] = {"status": "no_article", "article": None}
            print(f"[{i}/{len(titles)}] {title}: NO ARTICLE")
            save_json(manifest_path, manifest)
            continue
        slug = slugify(article)
        cache = PV_DIR / f"en_{slug}.json"
        if not cache.exists():
            items = fetch_pageviews(s, "en.wikipedia", article, start, end)
            save_json(cache, {"article": article, "project": "en.wikipedia",
                              "source_title": title, "items": items})
            time.sleep(0.15)
        views = load_json(cache)["items"]
        manifest[title] = {"status": "ok", "article": article,
                           "days": len(views)}
        print(f"[{i}/{len(titles)}] {title} -> {article} ({len(views)} days)")
        save_json(manifest_path, manifest)

    # 2. Hindi Wikipedia proxy for the top 50 titles.
    hmanifest_path = OUT / "manifest_hi.json"
    hmanifest = load_json(hmanifest_path) if hmanifest_path.exists() else {}
    for i, title in enumerate(titles[:HINDI_N], 1):
        if title in hmanifest:
            continue
        article = resolve_article(s, title, project="hi")
        time.sleep(0.15)
        if not article:
            hmanifest[title] = {"status": "no_article", "article": None}
            save_json(hmanifest_path, hmanifest)
            continue
        slug = slugify(article)
        cache = PV_DIR / f"hi_{slug}.json"
        if not cache.exists():
            items = fetch_pageviews(s, "hi.wikipedia", article, start, end)
            save_json(cache, {"article": article, "project": "hi.wikipedia",
                              "source_title": title, "items": items})
            time.sleep(0.15)
        views = load_json(cache)["items"]
        hmanifest[title] = {"status": "ok", "article": article,
                            "days": len(views)}
        print(f"[hi {i}/{min(HINDI_N, len(titles))}] {title} -> {article} ({len(views)} days)")
        save_json(hmanifest_path, hmanifest)

    print("Wikimedia done.")


if __name__ == "__main__":
    main()
