"""Pull anime catalog data from the AniList GraphQL API (no key required).

Collects:
  1. Top 1000 anime by all-time popularity (the "catalog" for feature building)
  2. Currently trending anime (recency signal)
  3. NOT_YET_RELEASED anime for upcoming seasons (the prediction target set)

Raw responses are cached under data/raw/anilist/; re-runs skip cached pages.
Output CSVs are written by scripts/data_collection/process.py.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, post_json, save_json, session  # noqa: E402

API = "https://graphql.anilist.co"
OUT = DATA / "raw" / "anilist"

MEDIA_FIELDS = """
  id
  idMal
  title { romaji english native }
  format
  episodes
  duration
  status
  season
  seasonYear
  startDate { year month day }
  endDate { year month day }
  genres
  tags { name rank isGeneralSpoiler }
  averageScore
  meanScore
  popularity
  favourites
  trending
  studios(isMain: true) { nodes { name } }
  source
  countryOfOrigin
  isAdult
  siteUrl
"""

QUERY = """
query ($page: Int, $perPage: Int, $sort: [MediaSort], $status: MediaStatus,
       $season: MediaSeason, $seasonYear: Int) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { total currentPage lastPage hasNextPage perPage }
    media(type: ANIME, isAdult: false, sort: $sort, status: $status,
          season: $season, seasonYear: $seasonYear) {
      """ + MEDIA_FIELDS + """
    }
  }
}
"""


def fetch_pages(name: str, variables: dict, max_pages: int, per_page: int = 50,
                sleep_s: float = 1.1):
    """Fetch multiple pages of a query, caching each page as a file."""
    s = session()
    collected = 0
    for page in range(1, max_pages + 1):
        cache = OUT / f"{name}_page{page:03d}.json"
        if cache.exists():
            data = None  # cached; only count below
        v = dict(variables, page=page, perPage=per_page)
        if cache.exists():
            import json
            with open(cache, "r", encoding="utf-8") as f:
                body = json.load(f)
        else:
            body = post_json(s, API, {"query": QUERY, "variables": v})
            save_json(cache, body)
            time.sleep(sleep_s)
        media = body["data"]["Page"]["media"]
        has_next = body["data"]["Page"]["pageInfo"]["hasNextPage"]
        collected += len(media)
        print(f"  {name} page {page}: {len(media)} media (total {collected})")
        if not has_next or not media:
            break
    print(f"{name}: collected {collected} media")


def main():
    print("AniList: top 1000 by popularity...")
    fetch_pages("top_popularity", {"sort": ["POPULARITY_DESC"]}, max_pages=20)

    print("AniList: trending (2 pages)...")
    fetch_pages("trending", {"sort": ["TRENDING_DESC"]}, max_pages=2)

    # Upcoming seasons = unreleased titles the model must score before launch.
    # Today is late 2026: target WINTER 2027 and SPRING 2027, plus any
    # NOT_YET_RELEASED titles that already have buzz regardless of season.
    for season, year in [("WINTER", 2027), ("SPRING", 2027), ("FALL", 2026)]:
        print(f"AniList: NOT_YET_RELEASED {season} {year}...")
        fetch_pages(
            f"upcoming_{season.lower()}_{year}",
            {"sort": ["POPULARITY_DESC"], "status": "NOT_YET_RELEASED",
             "season": season, "seasonYear": year},
            max_pages=4,
        )

    print("AniList: NOT_YET_RELEASED overall (any season)...")
    fetch_pages("upcoming_any", {"sort": ["POPULARITY_DESC"],
                                 "status": "NOT_YET_RELEASED"}, max_pages=6)

    print("AniList done.")


if __name__ == "__main__":
    main()
