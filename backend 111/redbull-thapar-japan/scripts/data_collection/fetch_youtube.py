"""Pull India-region YouTube engagement signals via YouTube Data API v3.

REQUIRES an API key. Set it first (never commit the key):

    # Git Bash          # PowerShell
    export YOUTUBE_API_KEY="AI..."    $env:YOUTUBE_API_KEY="AI..."
    python scripts/data_collection/fetch_youtube.py

What it collects (all regionCode=IN):
  1. search.list   - top videos for each anime title / keyword (relevance)
  2. videos.list   - view/like/comment counts, durations, channel ids
  3. channels.list - subscriber counts for the top anime channels found
  4. search for "anime" topics in Hindi/Marathi/Tamil/Telugu/Bengali to
     measure linguistic-hub engagement beyond English.

Quota cost: ~100 units per search call (10k/day free tier => ~90 searches).
The default keyword list below stays well within that.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, env_key, get_json, save_json, session  # noqa: E402

API = "https://www.googleapis.com/youtube/v3"
OUT = DATA / "raw" / "youtube"

# Core titles come from the AniList top list; keep a compact curated set here
# so quota is spent predictably. Edit freely.
KEYWORDS_EN = [
    "anime", "anime hindi dubbed", "one piece", "naruto", "dragon ball",
    "demon slayer", "jujutsu kaisen", "attack on titan", "bleach",
    "solo leveling", "chainsaw man", "my hero academia", "death note",
    "anime edits", "crunchyroll india", "anime india",
]
KEYWORDS_LOCAL = [
    " anime hindi dubbed",  # combined below with title words
    "anime tamil dubbed",
    "anime telugu dubbed",
    "anime bengali dubbed",
    "anime marathi dubbed",
]


def main():
    key = env_key("YOUTUBE_API_KEY", "GOOGLE_API_KEY")
    if not key:
        print("ERROR: no API key found.")
        print("Create one at https://console.cloud.google.com/ (YouTube Data API v3),")
        print("then:  export YOUTUBE_API_KEY=\"AI...\"   and re-run this script.")
        sys.exit(2)

    s = session()
    params_common = {"key": key, "regionCode": "IN", "maxResults": 25,
                     "part": "snippet", "type": "video",
                     "order": "relevance", "relevanceLanguage": "en"}

    all_video_ids: list[str] = []
    channel_ids: set[str] = set()

    for kw in KEYWORDS_EN + KEYWORDS_LOCAL:
        cache = OUT / f"search_{kw.strip().replace(' ', '_')[:60]}.json"
        if cache.exists():
            from common import load_json
            body = load_json(cache)
        else:
            p = dict(params_common, q=kw)
            body = get_json(s, API + "/search", params=p)
            save_json(cache, body)
            time.sleep(1.0)
        vids = [it["id"]["videoId"] for it in body.get("items", [])
                if it.get("id", {}).get("videoId")]
        all_video_ids.extend(vids)
        for it in body.get("items", []):
            cid = it.get("snippet", {}).get("channelId")
            if cid:
                channel_ids.add(cid)
        print(f"  search {kw!r}: {len(vids)} videos")

    # Video statistics in batches of 50.
    uniq = list(dict.fromkeys(all_video_ids))
    for i in range(0, len(uniq), 50):
        batch = uniq[i:i + 50]
        cache = OUT / f"videos_batch{i//50:02d}.json"
        if not cache.exists():
            body = get_json(s, API + "/videos", params={
                "key": key, "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch)})
            save_json(cache, body)
            time.sleep(0.5)
        print(f"  videos batch {i//50}: {len(batch)} ids")

    # Channel stats (subscriber counts) in batches of 50.
    uch = list(channel_ids)
    for i in range(0, len(uch), 50):
        batch = uch[i:i + 50]
        cache = OUT / f"channels_batch{i//50:02d}.json"
        if not cache.exists():
            body = get_json(s, API + "/channels", params={
                "key": key, "part": "snippet,statistics",
                "id": ",".join(batch)})
            save_json(cache, body)
            time.sleep(0.5)
        print(f"  channels batch {i//50}: {len(batch)} ids")

    print("YouTube done. Raw JSON in data/raw/youtube/.")


if __name__ == "__main__":
    main()
