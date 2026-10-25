"""Path bootstrap: make the cloned repositories in ``external/`` importable.

Upstream code is used *in place* from the shallow clones; nothing is copied
into this package (see NOTICE). Heavy imports stay lazy inside factories.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL = PROJECT_ROOT / "external"

# repo directory name -> import roots inside that clone (relative to the clone)
REPO_PATHS: dict[str, tuple[str, ...]] = {
    "jikanpy": (".",),
    "pytrends": (".",),
    "python-mwviews": ("src",),
    "MAPIE": (".",),
    "crawl4ai": (".",),
    "praw": (".",),
    "yt-dlp": (".",),
    "transformers": ("src",),
    "oasis": (".",),
    "Agent-Reach": (".",),
    "prefect": ("src",),
    "deepeval": (".",),
    "scrapy": (".",),
    "indic_nlp_library": (".",),
    "MiroFish": ("backend",),
    # wave 2
    "twscrape": (".",),
    "twikit": (".",),
    "tweepy": (".",),
    "youtube-transcript-api": (".",),
    "anime-offline-database": (".",),
    "MyAnimeList-Database": (".",),
    "dowhy": (".",),
    "EconML": (".",),
    "CausalPy": (".",),
    "shap": (".",),
    "interpret": (".",),
    "statsforecast": (".",),
    "sktime": (".",),
    "darts": (".",),
    "prophet": (".",),
    "alibi-detect": (".",),
    "AIF360": (".",),
    "mlflow": (".",),
    "mlxtend": (".",),
    "pymc-marketing": (".",),
    "datameet-maps": (".",),
    "indian_admin_boundaries": (".",),
    "india-geodata": (".",),
    "presidio": ("presidio",),
    "EasyOCR": (".",),
    "whisper": (".",),
    "librosa": (".",),
    "spotipy": (".",),
    "networkx": (".",),
    "datasketch": (".",),
    "IndicTrans2": (".",),
    "open_clip": (".",),
    "CLIP": (".",),
    "fasttext": (".",),
    "hf-datasets": ("src",),
    "sentence-transformers": (".",),
    "plotly": (".",),
    "telethon": (".",),
    "pycaret": (".",),
    "datameet-catalog": (".",),
    "india-census-2011": (".",),
    "vaderSentiment": (".",),
}


def ensure_paths(*repos: str) -> None:
    """Prepend the import roots of each cloned repo to ``sys.path`` (idempotent)."""
    for repo in repos:
        if repo not in REPO_PATHS:
            raise KeyError(f"unknown cloned repo: {repo!r} (known: {sorted(REPO_PATHS)})")
        base = EXTERNAL / repo
        if not base.is_dir():
            raise FileNotFoundError(f"clone missing: {base} (run the download step)")
        for rel in REPO_PATHS[repo]:
            path = str(base / rel) if rel != "." else str(base)
            if path not in sys.path:
                sys.path.insert(0, path)


class ProviderError(RuntimeError):
    """Raised when an upstream dependency is missing or misconfigured."""
