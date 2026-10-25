"""Flatten raw API JSON caches into analysis-ready CSVs under data/processed/.

Outputs:
  1. anilist_catalog.csv          - one row per anime (top/trending/upcoming)
  2. wikipedia_pageviews_long.csv - one row per article per day (en + hi)
  3. wikipedia_pageviews_summary.csv - momentum features per article
  4. google_trends_india_long.csv - one row per keyword per week (geo=IN)
  5. jikan_top_anime.csv          - only if Jikan data exists

Run any time; it reads whatever raw data is present.
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, load_json  # noqa: E402

RAW = DATA / "raw"
PROC = DATA / "processed"


def w(path: Path, header: list, rows: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(header)
        wr.writerows(rows)
    print(f"  {path.name}: {len(rows)} rows")


def anilist():
    rows = []
    seen = set()
    for f in sorted((RAW / "anilist").glob("*.json")):
        listname = f.stem.split("_page")[0]
        body = load_json(f)
        try:
            media = body["data"]["Page"]["media"]
        except (KeyError, TypeError):
            continue
        for m in media:
            key = m["id"]
            if key in seen:
                continue  # same anime may appear in multiple lists
            seen.add(key)
            title = m["title"]
            rows.append([
                m["id"], m.get("idMal") or "",
                title.get("romaji") or "", title.get("english") or "",
                title.get("native") or "",
                m.get("format") or "", m.get("episodes") or "",
                m.get("duration") or "", m.get("status") or "",
                m.get("season") or "", m.get("seasonYear") or "",
                (m.get("startDate") or {}).get("year") or "",
                (m.get("startDate") or {}).get("month") or "",
                (m.get("startDate") or {}).get("day") or "",
                (m.get("endDate") or {}).get("year") or "",
                "|".join(m.get("genres") or []),
                "|".join(f"{t['name']}:{t['rank']}" for t in (m.get("tags") or [])
                         if not t.get("isGeneralSpoiler")),
                m.get("averageScore") or "", m.get("meanScore") or "",
                m.get("popularity") or "", m.get("favourites") or "",
                m.get("trending") or "",
                "|".join(n["name"] for n in
                         ((m.get("studios") or {}).get("nodes") or [])),
                m.get("source") or "", m.get("countryOfOrigin") or "",
                m.get("siteUrl") or "", listname,
            ])
    if rows:
        w(PROC / "anilist_catalog.csv", [
            "anilist_id", "mal_id", "title_romaji", "title_english",
            "title_native", "format", "episodes", "duration_min", "status",
            "season", "season_year", "start_year", "start_month", "start_day",
            "end_year", "genres", "tags", "average_score", "mean_score",
            "popularity", "favourites", "trending", "main_studios", "source",
            "country", "site_url", "source_list",
        ], rows)


def wikimedia():
    long_rows, sum_rows = [], []
    files = sorted((RAW / "wikimedia" / "pageviews").glob("*.json"))
    for f in files:
        body = load_json(f)
        article = body["article"]
        project = body["project"]
        src = body.get("source_title", "")
        views = [(it["timestamp"][:8], it["views"]) for it in body.get("items", [])]
        # Hindi resolution is noisy (opensearch can land on unrelated articles,
        # e.g. "Bleach" -> Punjabi town "Balachaur"); drop hi.wiki matches with
        # too little coverage to be the real long-running anime article.
        if project.startswith("hi.") and len(views) < 100:
            continue
        for day, v in views:
            long_rows.append([project, article, src,
                              f"{day[:4]}-{day[4:6]}-{day[6:]}", v])
        if not views:
            continue
        vals = [v for _, v in views]
        days = sorted(views)
        n = len(vals)
        last30 = vals[-30:] if n >= 30 else vals
        prev90 = vals[-180:-90] if n >= 180 else []
        recent90 = vals[-90:] if n >= 90 else []
        momentum = ""
        if prev90 and sum(prev90) > 0:
            momentum = round((sum(recent90) / 90) / (sum(prev90) / 90) - 1, 3)
        peak_v = max(vals)
        peak_day = next(d for d, v in days if v == peak_v)
        sum_rows.append([
            project, article, src, n, sum(vals), round(sum(vals) / n, 1),
            peak_v, f"{peak_day[:4]}-{peak_day[4:6]}-{peak_day[6:]}",
            round(sum(last30) / len(last30), 1), momentum,
        ])
    if long_rows:
        w(PROC / "wikipedia_pageviews_long.csv",
          ["project", "article", "source_title", "date", "views"], long_rows)
    if sum_rows:
        w(PROC / "wikipedia_pageviews_summary.csv", [
            "project", "article", "source_title", "days_coverage",
            "total_views_24m", "avg_daily", "peak_daily", "peak_date",
            "avg_daily_last30", "momentum_90d_vs_prior90",
        ], sum_rows)


def trends():
    rows = []
    for f in sorted((RAW / "trends").glob("trends_in_*.json")):
        body = load_json(f)
        for rec in body.get("data", []):
            rows.append([body["keyword"], body.get("geo", "IN"),
                         rec.get("date"), rec.get("interest")])
    if rows:
        w(PROC / "google_trends_india_long.csv",
          ["keyword", "geo", "date", "interest"], rows)


def jikan():
    rows, seen = [], set()
    for f in sorted((RAW / "jikan").glob("top_anime_page*.json")):
        body = load_json(f)
        for a in body.get("data", []):
            if a["mal_id"] in seen:
                continue
            seen.add(a["mal_id"])
            rows.append([
                a["mal_id"], a.get("title") or "", a.get("title_english") or "",
                (a.get("titles") and next((t["title"] for t in a["titles"]
                  if t["type"] == "Japanese"), "")) or "",
                a.get("type") or "", a.get("episodes") or "",
                a.get("status") or "", a.get("score") or "",
                a.get("scored_by") or "", a.get("rank") or "",
                a.get("popularity") or "", a.get("members") or "",
                a.get("favorites") or "",
                a.get("season") or "", a.get("year") or "",
                a.get("source") or "", a.get("rating") or "",
                "|".join(g["name"] for g in a.get("genres") or []),
                "|".join(s["name"] for s in a.get("studios") or []),
            ])
    if rows:
        w(PROC / "jikan_top_anime.csv", [
            "mal_id", "title", "title_english", "title_japanese", "type",
            "episodes", "status", "score", "scored_by", "rank", "popularity",
            "members", "favorites", "season", "year", "source", "rating",
            "genres", "studios",
        ], rows)


def main():
    print(f"Processing raw -> processed @ {datetime.now():%Y-%m-%d %H:%M}")
    print("AniList catalog...")
    anilist()
    print("Wikimedia pageviews...")
    wikimedia()
    print("Google Trends...")
    trends()
    print("Jikan...")
    jikan()
    print("Done.")


if __name__ == "__main__":
    main()
