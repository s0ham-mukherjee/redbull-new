"""Pull anime metadata from Jikan v4 (MyAnimeList unofficial API, no key).

Collects:
  1. /top/anime        - top ~500 anime by MAL score (catalog + quality signal)
  2. /top/anime        filter=upcoming - most anticipated unreleased anime
  3. /seasons/2027/winter + /seasons/2027/spring - upcoming season lineups
  4. /top/anime type=movie - top anime movies (box-office relevance)

Jikan rate limit: ~3 req/s, 60/min -> sleep 1.2s between calls.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, get_json, save_json, session  # noqa: E402

API = "https://api.jikan.moe/v4"
OUT = DATA / "raw" / "jikan"
SLEEP = 1.2  # stay under Jikan's 60 req/min


def fetch(name: str, path: str, params: dict | None = None, pages: int = 1):
    s = session()
    for page in range(1, pages + 1):
        cache = OUT / f"{name}_page{page:02d}.json"
        if cache.exists():
            continue
        p = dict(params or {}, page=page)
        body = get_json(s, API + path, params=p)
        save_json(cache, body)
        n = len(body.get("data", []))
        print(f"  {name} page {page}: {n} items")
        has_next = body.get("pagination", {}).get("has_next_page", False)
        time.sleep(SLEEP)
        if not has_next or n == 0:
            break
    print(f"{name}: done")


def main():
    print("Jikan: top anime by score (20 pages x 25)...")
    fetch("top_anime", "/top/anime", {"limit": 25}, pages=20)

    print("Jikan: most anticipated upcoming...")
    fetch("top_upcoming", "/top/anime", {"limit": 25, "filter": "upcoming"}, pages=8)

    print("Jikan: top anime movies...")
    fetch("top_movies", "/top/anime", {"limit": 25, "type": "movie"}, pages=4)

    print("Jikan: 2027 winter / spring season lineups...")
    fetch("season_2027_winter", "/seasons/2027/winter", pages=2)
    fetch("season_2027_spring", "/seasons/2027/spring", pages=2)

    print("Jikan done.")


if __name__ == "__main__":
    main()
