"""Shared helpers for SakuraScore India data collection."""
import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

HEADERS = {
    "User-Agent": "SakuraScoreIndia/0.1 (hackathon research; contact: team@sakurascore.example)"
}


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_json(s: requests.Session, url: str, *, params=None, retries: int = 4,
             backoff: float = 2.0, timeout: float = 30):
    """GET with retry/backoff on 429/5xx. Returns parsed JSON or raises."""
    for attempt in range(retries):
        try:
            r = s.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                wait = backoff ** attempt
                print(f"  HTTP {r.status_code} on {url[:90]} - retry in {wait:.0f}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            wait = backoff ** attempt
            print(f"  {type(e).__name__} on {url[:90]} - retry in {wait:.0f}s")
            time.sleep(wait)
    raise RuntimeError(f"Exhausted retries for {url}")


def post_json(s: requests.Session, url: str, payload: dict, *, retries: int = 5,
              backoff: float = 2.0, timeout: float = 30):
    for attempt in range(retries):
        try:
            r = s.post(url, json=payload, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                wait = backoff ** attempt
                # AniList sends Retry-After when rate limited
                ra = r.headers.get("Retry-After")
                if ra:
                    try:
                        wait = max(wait, float(ra) + 1)
                    except ValueError:
                        pass
                print(f"  HTTP {r.status_code} - retry in {wait:.0f}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            wait = backoff ** attempt
            print(f"  {type(e).__name__} - retry in {wait:.0f}s")
            time.sleep(wait)
    raise RuntimeError(f"Exhausted retries for POST {url}")


def env_key(*names: str) -> str | None:
    """Return the first non-empty environment variable among names."""
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return None
