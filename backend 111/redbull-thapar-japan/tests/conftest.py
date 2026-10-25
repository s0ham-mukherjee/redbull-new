"""Shared fixtures & hypothesis profiles for the SakuraScore src/ test suite.

Run from the project root:  python3 -m pytest tests -q
Profiles:                   --hypothesis-profile={default,thorough,exhaustive}
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hypothesis import settings

settings.register_profile("default", max_examples=100, deadline=None)
settings.register_profile("thorough", max_examples=300, deadline=None)
settings.register_profile("exhaustive", max_examples=1500, deadline=None)
# Only force the default profile when the user did not pick one on the CLI
# (conftest imports after the hypothesis plugin applied --hypothesis-profile,
# so an unconditional load here would stomp the requested profile).
if not any(arg == "--hypothesis-profile" or arg.startswith("--hypothesis-profile=")
           for arg in sys.argv):
    settings.load_profile("default")

import pytest

from src.app import SHOWCASE_ALIASES, SakuraScoreApp, _norm

# 9 real catalog titles (8 released incl. one MOVIE + 1 NOT_YET_RELEASED)
# plus 1 showcase alias -> 10 sample titles resolved/verified at session start.
_CATALOG_TITLES = [
    "Chainsaw Man",                                   # released, wiki+seed hit
    "JUJUTSU KAISEN",                                 # top-5 released
    "Attack on Titan",                                # first catalog row
    "Demon Slayer: Kimetsu no Yaiba",
    "Death Note",
    "ONE PIECE",
    "Naruto",
    "A Silent Voice",                                 # MOVIE format
    "Delicious in Dungeon Season 2",                  # status NOT_YET_RELEASED
]
_SHOWCASE_ALIAS = "lazarus"                           # SHOWCASE_ALIASES key


@pytest.fixture(scope="session")
def app() -> SakuraScoreApp:
    """One cached SakuraScoreApp for the whole session (init ~1-2s)."""
    return SakuraScoreApp()


@pytest.fixture(scope="session")
def sample_titles(app: SakuraScoreApp) -> list[str]:
    """~10 verified catalog titles + one showcase alias (lookup-checked)."""
    titles = _CATALOG_TITLES + [_SHOWCASE_ALIAS]
    missing = [t for t in titles if app.lookup(t) is None]
    assert not missing, f"sample titles not resolvable in catalog: {missing}"
    # the NOT_YET_RELEASED pick really is unreleased
    unreleased = set(
        app.catalog.loc[app.catalog["status"] == "NOT_YET_RELEASED",
                        "title_english"].dropna())
    assert "Delicious in Dungeon Season 2" in unreleased
    # the showcase alias is a normalized SHOWCASE_ALIASES key that resolves
    assert _norm(_SHOWCASE_ALIAS) in SHOWCASE_ALIASES
    assert app.lookup(_SHOWCASE_ALIAS)["title_english"] == \
        SHOWCASE_ALIASES[_norm(_SHOWCASE_ALIAS)]
    assert len(titles) == 10
    return titles
