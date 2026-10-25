"""Greenlight engine — turn a raw concept (script / character design / any
Japanese-media pitch) into an India-viability verdict, through the real
SakuraScore pipeline.

Pipeline of the pipeline:

  concept text ──ConceptParser──▶ genres + tags + format + media type
                                   │
  catalog (live CSV, 1.3k titles) ─▶ CatalogTensor (float32, India-affinity
                                   │  weighted, norms precomputed)
                                   ▼
                       cosine similarity = ONE BLAS matvec ──▶ top-K comparables
                                   │
                    ┌──────────────┴───────────────┐
                    ▼                              ▼
     real pipeline on concept          real pipeline on each comparable
     (meta_override: cultural fit,     (cached; cohort score distribution)
      CBFC, economics, two-pass)
                    └──────────────┬───────────────┘
                                   ▼
              cohort LOO calibration (empirical-Bayes shrinkage,
              blend weight fitted per concept on the cohort itself)
                                   ▼
              QUANT LAYER — vectorized antithetic Monte Carlo
              (20k sims, fat-tail mixture) → E/σ, P(grade), VaR5, CVaR5,
              Sharpe, Kelly fraction, P(profit), plan frontier
                                   ▼
              STATE MODEL — the pipeline's hub demand math evaluated at
              every one of the 32 states (sourced: india_states.csv)
                                   ▼
              verdict JSON (parse receipts + timings + module inventory)

Everything is deterministic (seeded), cached (per-concept + per-comparable),
and every number carries a receipt. Live network use is one bounded AniList
trending pull (keyless, 6s timeout, 10-min cache, graceful offline fallback)
unless SAKURASCORE_GREENLIGHT_OFFLINE=1.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# local: the full repo checkout; serverless: api/_backend (set by the function)
BACKEND = Path(os.environ.get("SAKURASCORE_BACKEND_ROOT")
               or Path(__file__).resolve().parents[2] / "backend 111" / "redbull-thapar-japan")
MODULES_SRC = BACKEND / "modules" / "src"

K_COMPARABLES = 10
MC_SIMS = 20_000
MC_SEED = 42
TRENDING_TTL_S = 600  # live trending cross-match cache
ANILIST_API = "https://graphql.anilist.co"

# ============================================================================
# 1. Concept parser — free text → structured AniList-space profile
# ============================================================================

# AniList's fixed genre vocabulary (the pipeline's scoring engine knows these).
GENRE_VOCAB = [
    "Action", "Adventure", "Comedy", "Drama", "Ecchi", "Fantasy", "Horror",
    "Mahou Shoujo", "Mecha", "Music", "Mystery", "Psychological", "Romance",
    "Sci-Fi", "Slice of Life", "Sports", "Supernatural", "Thriller",
]

# keyword → (kind, value, base_rank). kind: g=genre, t=tag, d=demographic tag.
# Ranks follow AniList semantics (0-100, higher = more central to the work).
# Japanese terms (kanji/kana/romaji) are first-class: anything and everything
# Japanese parses.
LEXICON: list[tuple[str, str, str, int]] = [
    # -- genres (direct + aliases) --
    ("action", "g", "Action", 0), ("battle", "g", "Action", 0), ("fight", "g", "Action", 0),
    ("fighting", "g", "Action", 0), ("martial arts", "g", "Sports", 0), ("adventure", "g", "Adventure", 0),
    ("quest", "g", "Adventure", 0), ("journey", "g", "Adventure", 0), ("comedy", "g", "Comedy", 0),
    ("funny", "g", "Comedy", 0), ("slapstick", "t", "Slapstick", 75), ("parody", "g", "Comedy", 0),
    ("satire", "t", "Satire", 70), ("drama", "g", "Drama", 0), ("emotional", "g", "Drama", 0),
    ("fantasy", "g", "Fantasy", 0), ("magic", "g", "Fantasy", 0), ("magical", "g", "Fantasy", 0),
    ("horror", "g", "Horror", 0), ("scary", "g", "Horror", 0), ("creepy", "g", "Horror", 0),
    ("mahou shoujo", "g", "Mahou Shoujo", 0), ("magical girl", "g", "Mahou Shoujo", 0),
    ("mecha", "g", "Mecha", 0), ("giant robot", "g", "Mecha", 0), ("robot", "t", "Robots", 70),
    ("super robot", "t", "Super Robot", 80), ("real robot", "t", "Real Robot", 80),
    ("music", "g", "Music", 0), ("band", "t", "Band", 75), ("idol", "t", "Idol", 80),
    ("concert", "g", "Music", 0), ("mystery", "g", "Mystery", 0), ("detective", "g", "Mystery", 0),
    ("whodunnit", "g", "Mystery", 0), ("psychological", "g", "Psychological", 0),
    ("romance", "g", "Romance", 0), ("love story", "g", "Romance", 0), ("sci-fi", "g", "Sci-Fi", 0),
    ("science fiction", "g", "Sci-Fi", 0), ("cyberpunk", "g", "Sci-Fi", 0), ("space opera", "g", "Sci-Fi", 0),
    ("slice of life", "g", "Slice of Life", 0), ("iyashikei", "g", "Slice of Life", 0),
    ("healing", "t", "Iyashikei", 70), ("sports", "g", "Sports", 0), ("supernatural", "g", "Supernatural", 0),
    ("thriller", "g", "Thriller", 0), ("suspense", "g", "Thriller", 0), ("ecchi", "g", "Ecchi", 0),
    ("fanservice", "g", "Ecchi", 0), ("harem", "t", "Female Harem", 75), ("reverse harem", "t", "Male Harem", 75),
    # -- tags: setting / premise --
    ("isekai", "t", "Isekai", 85), ("異世界", "t", "Isekai", 85), ("another world", "t", "Isekai", 85),
    ("transported", "t", "Isekai", 75), ("reincarnat", "t", "Isekai", 70), ("time loop", "t", "Time Loop", 80),
    ("time travel", "t", "Time Loop", 65), ("dungeon", "t", "Dungeon", 75), ("video game", "t", "Video Games", 70),
    ("virtual world", "t", "Virtual World", 75), ("battle royale", "t", "Battle Royale", 80),
    ("death game", "t", "Death Game", 85), ("post-apocalyptic", "t", "Post-Apocalyptic", 80),
    ("apocalypse", "t", "Post-Apocalyptic", 70), ("dystopian", "t", "Dystopian", 80),
    ("dystopia", "t", "Dystopian", 80), ("school", "t", "School", 75), ("high school", "t", "School", 80),
    ("academy", "t", "School", 70), ("college", "t", "College", 70), ("school club", "t", "School Club", 75),
    ("urban", "t", "Urban", 60), ("urban fantasy", "t", "Urban Fantasy", 80), ("medieval", "t", "Medieval", 75),
    ("historical", "t", "Historical", 75), ("steampunk", "t", "Steampunk", 80), ("cyberpunk", "t", "Cyberpunk", 80),
    ("space", "t", "Space", 70), ("military", "t", "Military", 75), ("war", "t", "War", 75),
    ("politics", "t", "Politics", 70), ("conspiracy", "t", "Conspiracy", 70), ("espionage", "t", "Espionage", 70),
    ("spy", "t", "Espionage", 65), ("crime", "t", "Crime", 70), ("mafia", "t", "Mafia", 80),
    ("yakuza", "t", "Yakuza", 85), ("gang", "t", "Gangs", 70), ("assassin", "t", "Assassins", 80),
    ("pirate", "t", "Pirates", 80), ("ninja", "t", "Ninja", 85), ("忍者", "t", "Ninja", 85),
    ("shinobi", "t", "Ninja", 80), ("samurai", "t", "Samurai", 85), ("侍", "t", "Samurai", 85),
    ("katana", "t", "Swordplay", 80), ("sword", "t", "Swordplay", 80), ("swordplay", "t", "Swordplay", 85),
    ("swordsman", "t", "Swordplay", 80), ("swordswoman", "t", "Swordplay", 80), ("刀", "t", "Swordplay", 75),
    ("kenjutsu", "t", "Swordplay", 80), ("archery", "t", "Archery", 75), ("spear", "t", "Spearplay", 75),
    ("guns", "t", "Guns", 75), ("gunplay", "t", "Guns", 75), ("dragons", "t", "Dragons", 80),
    ("kaiju", "t", "Kaiju", 85), ("怪獣", "t", "Kaiju", 85), ("monster", "t", "Kaiju", 60),
    ("giant monster", "t", "Kaiju", 85), ("demons", "t", "Demons", 85), ("demon", "t", "Demons", 75),
    ("oni", "t", "Demons", 70), ("鬼", "t", "Demons", 70), ("youkai", "t", "Youkai", 85),
    ("yokai", "t", "Youkai", 85), ("妖怪", "t", "Youkai", 85), ("spirit", "t", "Ghost", 60),
    ("ghost", "t", "Ghost", 75), ("ghosts", "t", "Ghost", 75), ("zombie", "t", "Zombie", 80),
    ("zombies", "t", "Zombie", 80), ("vampire", "t", "Vampire", 80), ("vampires", "t", "Vampire", 80),
    ("werewolf", "t", "Werewolf", 75), ("witch", "t", "Witch", 75), ("witches", "t", "Witch", 75),
    ("alchemy", "t", "Alchemy", 80), ("necromancy", "t", "Necromancy", 80), ("curses", "t", "Curses", 75),
    ("curse", "t", "Curses", 75), ("呪い", "t", "Curses", 75), ("exorcism", "t", "Exorcism", 80),
    ("exorcist", "t", "Exorcism", 80), ("shinto", "t", "Religion", 75), ("shrine", "t", "Shrine Maiden", 75),
    ("shrine maiden", "t", "Shrine Maiden", 85), ("miko", "t", "Shrine Maiden", 80), ("kami", "t", "Gods", 75),
    ("gods", "t", "Gods", 75), ("deity", "t", "Gods", 70), ("mythology", "t", "Mythology", 80),
    ("myth", "t", "Mythology", 70), ("神話", "t", "Mythology", 80), ("fairy", "t", "Fairy", 75),
    ("fairies", "t", "Fairy", 75), ("elves", "t", "Elf", 75), ("elf", "t", "Elf", 75),
    ("kemonomimi", "t", "Kemonomimi", 80), ("animal ears", "t", "Kemonomimi", 80), ("nekomimi", "t", "Nekomimi", 75),
    ("catgirl", "t", "Kemonomimi", 75), ("tanuki", "t", "Youkai", 70), ("kitsune", "t", "Youkai", 75),
    ("fox spirit", "t", "Youkai", 75), ("tsukumogami", "t", "Youkai", 70), ("tokusatsu", "t", "Tokusatsu", 85),
    ("henshin", "t", "Henshin", 85), ("変身", "t", "Henshin", 80), ("superhero", "t", "Superhero", 80),
    ("super power", "t", "Super Power", 80), ("superpowers", "t", "Super Power", 80),
    ("kamen", "t", "Tokusatsu", 80), ("sentai", "t", "Tokusatsu", 80),
    # -- tags: character design --
    ("protagonist", "t", "Ensemble Cast", 50), ("male protagonist", "t", "Male Protagonist", 90),
    ("female protagonist", "t", "Female Protagonist", 90), ("male lead", "t", "Male Protagonist", 85),
    ("female lead", "t", "Female Protagonist", 85), ("heroine", "t", "Female Protagonist", 85),
    ("ensemble", "t", "Ensemble Cast", 80), ("orphan", "t", "Orphan", 75), ("amnesia", "t", "Amnesia", 75),
    ("revenge", "t", "Revenge", 85), ("vengeance", "t", "Revenge", 85), ("anti-hero", "t", "Anti-Hero", 80),
    ("antihero", "t", "Anti-Hero", 80), ("villainess", "t", "Villainess", 85), ("mentor", "t", "Coming of Age", 55),
    ("master and apprentice", "t", "Coming of Age", 65), ("training", "t", "Coming of Age", 60),
    ("coming of age", "t", "Coming of Age", 80), ("found family", "t", "Found Family", 80),
    ("family", "t", "Family Life", 70), ("friendship", "t", "Found Family", 65), ("bullying", "t", "Bullying", 75),
    ("delinquent", "t", "Delinquents", 80), ("delinquents", "t", "Delinquents", 80),
    ("chuunibyou", "t", "Chuunibyou", 80), ("hikikomori", "t", "Hikikomori", 80), ("otaku", "t", "Otaku Culture", 80),
    ("cosplay", "t", "Cosplay", 75), ("crossdressing", "t", "Crossdressing", 75),
    ("tsundere", "t", "Tsundere", 85), ("kuudere", "t", "Kuudere", 85), ("yandere", "t", "Yandere", 85),
    ("dandere", "t", "Kuudere", 65), ("ojou-sama", "t", "Ojou-sama", 80), ("ojousama", "t", "Ojou-sama", 80),
    ("gyaru", "t", "Gyaru", 80), ("maid", "t", "Maids", 80), ("butler", "t", "Butler", 80),
    ("twins", "t", "Twins", 75), ("tomboy", "t", "Tomboy", 75), ("kawaii", "t", "Cute Girls Doing Cute Things", 65),
    ("cute girls", "t", "Cute Girls Doing Cute Things", 75), ("cute boys", "t", "Cute Boys Doing Cute Things", 75),
    ("chibi", "t", "Chibi", 75), ("shrine priestess", "t", "Shrine Maiden", 80),
    ("teenage girl", "t", "Primarily Teen Cast", 80), ("teenage boy", "t", "Primarily Teen Cast", 80),
    ("teenager", "t", "Primarily Teen Cast", 75), ("teen", "t", "Primarily Teen Cast", 70),
    ("adult protagonist", "t", "Primarily Adult Cast", 80), ("office lady", "t", "Office Lady", 80),
    ("salaryman", "t", "Office", 75), ("child protagonist", "t", "Primarily Child Cast", 80),
    ("kids", "t", "Primarily Child Cast", 70), ("teacher", "t", "Teacher", 75),
    # -- demographics --
    ("shounen", "d", "Shounen", 90), ("shonen", "d", "Shounen", 90), ("少年", "d", "Shounen", 90),
    ("shoujo", "d", "Shoujo", 90), ("少女", "d", "Shoujo", 90), ("seinen", "d", "Seinen", 90),
    ("青年", "d", "Seinen", 90), ("josei", "d", "Josei", 90), ("女性", "d", "Josei", 85),
    # -- risk / CBFC-relevant --
    ("gore", "t", "Gore", 85), ("gory", "t", "Gore", 80), ("blood", "t", "Gore", 65),
    ("bloody", "t", "Gore", 70), ("graphic violence", "t", "Graphic Violence", 85),
    ("body horror", "t", "Body Horror", 85), ("cannibalism", "t", "Cannibalism", 85),
    ("violence", "t", "Violence", 65), ("brutal", "t", "Gore", 70), ("torture", "t", "Torture", 85),
    ("suicide", "t", "Suicide", 85), ("self-harm", "t", "Self-Harm", 85), ("drugs", "t", "Drugs", 80),
    ("alcohol", "t", "Alcohol", 70), ("smoking", "t", "Tobacco Use", 70), ("nudity", "t", "Nudity", 85),
    ("sexual", "t", "Nudity", 60), ("sex scene", "t", "Nudity", 75), ("death", "t", "Death", 55),
    ("tragedy", "t", "Tragedy", 75), ("tragic", "t", "Tragedy", 70), ("war crimes", "t", "War", 80),
    ("slavery", "t", "Slavery", 80), ("terrorism", "t", "Terrorism", 80),
    # -- settings / extras --
    ("food", "t", "Food", 80), ("cooking", "t", "Food", 80), ("restaurant", "t", "Restaurant", 80),
    ("ramen", "t", "Food", 75), ("baseball", "t", "Baseball", 85), ("basketball", "t", "Basketball", 85),
    ("football", "t", "Football", 85), ("volleyball", "t", "Volleyball", 85), ("swimming", "t", "Swimming", 85),
    ("soccer", "t", "Football", 85), ("motorcycle", "t", "Motorcycles", 80), ("racing", "t", "Motorcycles", 60),
    ("train", "t", "Trains", 75), ("trains", "t", "Trains", 75), ("planes", "t", "Aviation", 75),
    ("gambling", "t", "Gambling", 80), ("detective agency", "t", "Detective", 80),
    ("police", "t", "Police", 75), ("prison", "t", "Prison", 80), ("zombie apocalypse", "t", "Zombie", 85),
    ("pandemic", "t", "Pandemic", 80), ("ai", "t", "Artificial Intelligence", 75),
    ("artificial intelligence", "t", "Artificial Intelligence", 85), ("cyborg", "t", "Cyborg", 80),
    ("clone", "t", "Clone", 80), ("aliens", "t", "Aliens", 80), ("alien", "t", "Aliens", 75),
    ("cosmic horror", "t", "Cosmic Horror", 85), ("lovecraft", "t", "Cosmic Horror", 85),
    ("cult", "t", "Cult", 80), ("cultists", "t", "Cult", 75), ("royal", "t", "Royal Affairs", 75),
    ("kingdom", "t", "Kingdom Management", 70), ("arranged marriage", "t", "Arranged Marriage", 85),
    ("marriage", "t", "Marriage", 75), ("love triangle", "t", "Love Triangle", 85),
    ("unrequited love", "t", "Unrequited Love", 80), ("fake relationship", "t", "Fake Relationship", 80),
    ("cohabitation", "t", "Cohabitation", 80), ("romcom", "g", "Romance", 0), ("rom-com", "g", "Romance", 0),
    ("mecha pilot", "g", "Mecha", 0), ("gundam", "g", "Mecha", 0),
    ("warrior", "t", "War", 70), ("battleground", "t", "War", 70),
    ("rural", "t", "Rural", 75), ("village", "t", "Rural", 65), ("fishing", "t", "Fishing", 80),
    ("agriculture", "t", "Agriculture", 80), ("farming", "t", "Agriculture", 80),
    ("photography", "t", "Photography", 80), ("writing", "t", "Writing", 80), ("acting", "t", "Acting", 80),
    ("astronomy", "t", "Astronomy", 80), ("board game", "t", "Board Game", 80), ("video games", "t", "Video Games", 75),
    ("full cgi", "t", "Full CGI", 85), ("cgi", "t", "CGI", 65), ("rotoscoping", "t", "Rotoscoping", 85),
]

# Emphasis modifiers adjust the rank of the nearest keyword hit.
EMPHASIS = [
    (r"\b(very|extremely|super|heavily|heavy|brutal|brutally|intense|intensely)\b", 18),
    (r"\b(mild|mildly|slight|slightly|light|lightly|a bit of|hints? of)\b", -15),
]

# Age mentions imply cast tags ("a 17-year-old pilot" → Primarily Teen Cast).
AGE_PATTERN = re.compile(r"\b(\d{1,2})[- ]year[- ]olds?\b")
AGE_TAG = lambda age: ("Primarily Child Cast", 75) if age <= 12 else (
    ("Primarily Teen Cast", 80) if age <= 19 else ("Primarily Adult Cast", 75))

# Ambiguous as a bare English word (the name "Ai", romaji 愛) — the long form
# "artificial intelligence" carries the real signal.
SKIP_KEYWORDS = {"ai"}

# When no genre keyword fired, strong tags still imply genres (max 4 inferred).
TAG_TO_GENRE = {
    "Isekai": "Fantasy", "Dragons": "Fantasy", "Magic": "Fantasy", "Gods": "Supernatural",
    "Demons": "Supernatural", "Youkai": "Supernatural", "Ghost": "Supernatural",
    "Vampire": "Supernatural", "Swordplay": "Action", "Guns": "Action",
    "Martial Arts": "Action", "Assassins": "Action", "Military": "Action",
    "Ninja": "Action", "Samurai": "Action", "Kaiju": "Action", "Super Power": "Action",
    "Mecha": "Mecha", "Super Robot": "Mecha", "Real Robot": "Mecha",
    "Detective": "Mystery", "Zombie": "Horror", "Cosmic Horror": "Horror",
    "Idol": "Music", "Band": "Music", "Food": "Slice of Life", "Iyashikei": "Slice of Life",
    "Baseball": "Sports", "Basketball": "Sports", "Football": "Sports",
    "Volleyball": "Sports", "Athletics": "Sports", "Robots": "Sci-Fi",
    "Cyberpunk": "Sci-Fi", "Space": "Sci-Fi", "Time Loop": "Sci-Fi",
    "Love Triangle": "Romance", "Unrequited Love": "Romance", "Arranged Marriage": "Romance",
    "Bullying": "Drama", "Tragedy": "Drama", "Revenge": "Drama", "War": "Drama",
}

MEDIA_PATTERNS = [
    (r"\b(movie|film|theatrical|feature film|劇場版)\b", "movie"),
    (r"\b(manga|漫画|comic)\b", "manga"),
    (r"\b(light novel|ln series|ranobe|ライトノベル)\b", "light novel"),
    (r"\b(visual novel|vn|ビジュアルノベル)\b", "visual novel"),
    (r"\b(video game|game|rpg|jrpg|ゲーム)\b", "game"),
    (r"\b(tokusatsu|live-?action|j-?drama|drama series)\b", "live-action"),
    (r"\b(ova|original video animation)\b", "ova"),
    (r"\b(ona|original net animation|web series|webseries)\b", "ona"),
    (r"\b(tv series|tv show|television|season \d|episodic series|anime series)\b", "tv"),
]

_Q_OPEN = "\u300c\u300e\"'"      # 「 『 " '
_Q_CLOSE = "\u300d\u300f\"'"     # 」 』 " '

TITLE_PATTERNS = [
    # Title: "Quoted Name"  /  called 'X'
    r'\b(?:title|called|named)\s*[:\-]?\s*(?P<q>[' + re.escape(_Q_OPEN) + r'])(?P<t1>[^' + re.escape(_Q_CLOSE) + r']{2,60})(?P=q)',
    # any quoted string early in the pitch (symmetric quotes)
    r'(?P<q2>[' + re.escape(_Q_OPEN) + r'])(?P<t2>[^' + re.escape(_Q_CLOSE) + r']{2,60})(?P=q2)',
    # CJK directional quotes: 「名前」 / 『名前』 (open ≠ close, pairs explicit)
    r'[「『](?P<t4>[^」』]{2,60})[」』]',
    # Title: Unquoted Name. (to sentence end / line end)
    r'^\s*(?:title|name)\s*[:\-]\s*(?P<t3>.{2,60}?)(?:\.\s|$)',
]


@dataclass
class ParsedConcept:
    title: str
    media_type: str            # anime | movie | manga | light novel | visual novel | game | live-action
    pipeline_format: str       # TV | MOVIE | ONA | OVA (what the pipeline scores)
    genres: list[str] = field(default_factory=list)
    tags: list[tuple[str, float]] = field(default_factory=list)
    demographics: list[str] = field(default_factory=list)
    episodes: int | None = None
    duration_min: int | None = None
    is_adult: bool = False
    japanese_terms: list[str] = field(default_factory=list)
    receipts: list[dict] = field(default_factory=list)  # keyword → what it fired


def _lexicon_compiled():
    """Keyword matchers, longest-first.

    ASCII keywords match on word boundaries (plural-tolerant via s?), so
    "protagonist" never fires 鬼/oni→Demons, "culture" never fires Cult,
    "reward" never fires War, "himself" never fires Elf. Keywords already
    ending in "s" match their exact form only (so "demon" keeps its lower
    base rank vs the stronger "demons"). CJK keywords keep substring
    semantics — Japanese has no word spaces to bound on.
    """
    out = []
    for kw, kind, val, base in sorted(LEXICON, key=lambda k: -len(k[0])):
        if re.fullmatch(r"[a-z0-9 \-']+", kw):
            if kw.endswith("s"):
                pat: re.Pattern | None = re.compile(r"\b" + re.escape(kw) + r"\b")
            else:
                pat = re.compile(r"\b" + re.escape(kw) + r"s?\b")
        else:
            pat = None  # CJK / mixed script: substring semantics
        out.append((kw, kind, val, base, pat))
    return out


def parse_concept(text: str, *, title: str = "", format: str = "",
                  episodes: int | None = None) -> ParsedConcept:
    """Lexicon parse of a free-text concept. Every hit becomes a receipt."""
    raw = (text or "").strip()
    low = " " + re.sub(r"\s+", " ", raw.lower()) + " "

    receipts: list[dict] = []
    genre_hits: dict[str, int] = {}
    tag_hits: dict[str, float] = {}
    demo_hits: dict[str, float] = {}
    jp_terms: list[str] = []

    # title extraction
    ctitle = (title or "").strip()
    if not ctitle:
        for pat in TITLE_PATTERNS:
            m = re.search(pat, raw, flags=re.IGNORECASE | re.MULTILINE)
            if m:
                ctitle = (m.groupdict().get("t1") or m.groupdict().get("t2")
                          or m.groupdict().get("t4") or m.groupdict().get("t3")
                          or "").strip()
                break

    # media type
    media = "anime"
    for pat, val in MEDIA_PATTERNS:
        if re.search(pat, low):
            media = val
            break
    pipeline_format = {"movie": "MOVIE", "ova": "OVA", "ona": "ONA"}.get(media, "TV")
    if format:
        pipeline_format = str(format).upper()
        if pipeline_format == "FILM":
            pipeline_format = "MOVIE"
        media = {"MOVIE": "movie", "OVA": "ova", "ONA": "ona", "TV": "anime",
                 "TV_SHORT": "anime", "SPECIAL": "anime"}.get(pipeline_format, media)

    # episodes / duration
    eps = episodes
    if eps is None:
        m = re.search(r"(\d{1,3})\s*(?:-|\s)?\s*(?:episodes|eps|ep\b|episodes long)", low)
        if m:
            eps = max(1, min(500, int(m.group(1))))
    m = re.search(r"(\d{2,3})\s*(?:-|\s)?\s*min(?:ute)?s?\s*(?:per ep|each|\/ep)?", low)
    duration = max(1, min(180, int(m.group(1)))) if m else None

    # keyword scan — longest keyword wins on overlap (e.g. "magical girl" > "magical");
    # ASCII keywords are word-boundary anchored, CJK keywords substring-match
    for kw, kind, val, base, pat in _lexicon_compiled():
        if kw in SKIP_KEYWORDS:
            continue
        if pat is not None:
            hits = pat.findall(low)
            if not hits:
                continue
            idx = low.find(hits[0])
            n = len(hits)
        else:
            idx = low.find(kw)
            if idx == -1:
                continue
            n = low.count(kw)
        # emphasis modifiers in a ±40-char window
        rank = float(base)
        window = low[max(0, idx - 40): idx + len(kw) + 40]
        for epat, delta in EMPHASIS:
            if re.search(epat, window):
                rank = min(100.0, max(5.0, rank + delta))
                break
        # repeats strengthen (max +10)
        if n > 1:
            rank = min(100.0, rank + min(10.0, (n - 1) * 5.0))
        if kind == "g":
            genre_hits[val] = genre_hits.get(val, 0) + 1
        elif kind == "d":
            demo_hits[val] = max(demo_hits.get(val, 0.0), rank)
        else:
            tag_hits[val] = max(tag_hits.get(val, 0.0), rank)
        receipts.append({"keyword": kw, "fires": f"{'genre' if kind == 'g' else 'demographic' if kind == 'd' else 'tag'} {val}", "rank": round(rank) if kind != "g" else None})
        if re.match(r"^[\u3040-\u30ff\u4e00-\u9fff]+$", kw) and kw not in jp_terms:
            jp_terms.append(kw)
        if kw in ("isekai", "ninja", "samurai", "katana", "youkai", "yokai", "kaiju",
                  "shounen", "shonen", "shoujo", "seinen", "josei", "tokusatsu",
                  "henshin", "kemonomimi", "kuudere", "tsundere", "yandere",
                  "ojou-sama", "gyaru", "chuunibyou", "hikikomori", "otaku",
                  "iyashikei", "mecha", "onsen", "kawaii", "romcom") and kw not in jp_terms:
            jp_terms.append(kw)

    # age mentions → cast tags ("a 17-year-old pilot" → Primarily Teen Cast)
    age_m = AGE_PATTERN.search(low)
    if age_m:
        age = int(age_m.group(1))
        if 1 <= age <= 99:
            cast_tag, cast_rank = AGE_TAG(age)
            tag_hits[cast_tag] = max(tag_hits.get(cast_tag, 0.0), float(cast_rank))
            receipts.append({"keyword": f"{age}-year-old", "fires": f"tag {cast_tag}", "rank": cast_rank})

    # risk gate: explicit adult terms
    if re.search(r"\b(hentai|explicit sex|eroge|adults only|porn)\b", low):
        is_adult = True
        tag_hits["Nudity"] = max(tag_hits.get("Nudity", 0.0), 90.0)
        receipts.append({"keyword": "adult-content term", "fires": "is_adult=True (Hentai-track)", "rank": 90})
    else:
        is_adult = False

    # demographics also imply genre-adjacent casts
    for d, rank in demo_hits.items():
        tag_hits[d] = max(tag_hits.get(d, 0.0), rank)

    # cap: pipeline cultural engine uses top tags by rank; keep all (rank-aware)
    tags = sorted(tag_hits.items(), key=lambda kv: -kv[1])
    genres = list(genre_hits.keys())
    if not genres:  # infer genres from strong tags (no explicit genre words)
        for name, _ in tags:
            g = TAG_TO_GENRE.get(name)
            if g and g not in genres:
                genres.append(g)
                receipts.append({"keyword": f"tag {name}", "fires": f"inferred genre {g}", "rank": None})
            if len(genres) >= 4:
                break

    # honest fallback: with zero signal, use the catalog's central profile
    if not genres and not tags:
        genres = ["Action", "Fantasy"]
        receipts.append({"keyword": "(no keywords matched)", "fires":
                         "neutral fallback genres Action+Fantasy — confidence will reflect the empty parse", "rank": None})

    return ParsedConcept(
        title=ctitle or "Untitled Concept",
        media_type=media,
        pipeline_format=pipeline_format,
        genres=genres,
        tags=tags,
        demographics=list(demo_hits.keys()),
        episodes=eps,
        duration_min=duration,
        is_adult=is_adult,
        japanese_terms=jp_terms,
        receipts=receipts,
    )


# ============================================================================
# 2. Catalog tensor — the 1.3k-title catalog as one float32 matrix
# ============================================================================

class CatalogTensor:
    """Feature tensor over the live catalog.

    Dims: 18 AniList genres (India-affinity weighted via the scoring engine's
    GENRE_AFFINITY — similarity is measured in *India-relevance space*, not raw
    content space) + top-T tags (rank/100) + format dims + adult flag.

    Built once at boot; cosine similarity against a concept vector is then a
    single BLAS matvec (numpy dispatches to Accelerate/vDSP on macOS arm64).
    """

    TAG_DIMS = 180

    def __init__(self, catalog_df, genre_affinity: dict[str, int]):
        self.titles: list[str] = []
        self.rows = catalog_df
        genre_cols = [g for g in GENRE_VOCAB]
        # tag vocabulary by catalog frequency (top-N only, keeps tensor tight)
        tag_counts: dict[str, int] = {}
        for cell in catalog_df["tags"].dropna():
            for pair in str(cell).split("|"):
                if ":" in pair:
                    name = pair.rsplit(":", 1)[0].strip()
                    if name:
                        tag_counts[name] = tag_counts.get(name, 0) + 1
        self.tag_cols = [t for t, _ in sorted(tag_counts.items(), key=lambda kv: -kv[1])[: self.TAG_DIMS]]
        tag_index = {t: i for i, t in enumerate(self.tag_cols)}
        genre_index = {g: i for i, g in enumerate(genre_cols)}
        fmt_cols = ["TV", "MOVIE", "OVA", "ONA", "TV_SHORT", "SPECIAL"]
        fmt_index = {f: i for i, f in enumerate(fmt_cols)}
        self.fmt_cols = fmt_cols
        self.genre_cols = genre_cols

        D = len(genre_cols) + len(self.tag_cols) + len(fmt_cols) + 1
        X = np.zeros((len(catalog_df), D), dtype=np.float32)

        # India-affinity genre weights, centered at 1.0 (55 = neutral in the engine)
        self.genre_w = np.array(
            [max(0.35, genre_affinity.get(g, 55) / 55.0) for g in genre_cols], dtype=np.float32)

        for r, (_, row) in enumerate(catalog_df.iterrows()):
            for g in str(row.get("genres") or "").split("|"):
                g = g.strip()
                if g in genre_index:
                    X[r, genre_index[g]] = self.genre_w[genre_index[g]]
            for pair in str(row.get("tags") or "").split("|"):
                if ":" not in pair:
                    continue
                name, _, rank = pair.rpartition(":")
                name = name.strip()
                if name in tag_index:
                    try:
                        X[r, len(genre_cols) + tag_index[name]] = max(0.0, min(100.0, float(rank))) / 100.0
                    except ValueError:
                        pass
            fmt = str(row.get("format") or "TV").upper()
            if fmt in fmt_index:
                X[r, len(genre_cols) + len(self.tag_cols) + fmt_index[fmt]] = 0.6
            if bool(row.get("is_adult")) or "Hentai" in str(row.get("genres") or ""):
                X[r, D - 1] = 1.0
            self.titles.append(str(row.get("title_english") or row.get("title_romaji") or ""))

        self.X = np.ascontiguousarray(X)
        self.norms = np.sqrt((self.X ** 2).sum(axis=1))
        self.norms[self.norms == 0] = 1.0
        self.D = D
        self.title_index = {t: i for i, t in enumerate(self.titles)}

    def concept_vector(self, p: ParsedConcept) -> np.ndarray:
        v = np.zeros(self.D, dtype=np.float32)
        gi = {g: i for i, g in enumerate(self.genre_cols)}
        for g in p.genres:
            if g in gi:
                v[gi[g]] = self.genre_w[gi[g]]
            else:  # genre outside vocab (e.g. Kids) still gets neutral weight
                pass
        base = len(self.genre_cols)
        ti = {t: i for i, t in enumerate(self.tag_cols)}
        for name, rank in p.tags:
            if name in ti:
                v[base + ti[name]] = max(0.0, min(100.0, rank)) / 100.0
        fi = {f: i for i, f in enumerate(self.fmt_cols)}
        fmt = p.pipeline_format.upper()
        if fmt in fi:
            v[base + len(self.tag_cols) + fi[fmt]] = 0.6
        if p.is_adult:
            v[-1] = 1.0
        return v

    def similar(self, v: np.ndarray, k: int = K_COMPARABLES) -> list[tuple[int, float]]:
        """Cosine similarity of one concept vector vs the whole catalog —
        one matrix-vector product (BLAS), then argpartition for top-k."""
        nv = float(np.linalg.norm(v)) or 1.0
        sims = (self.X @ v) / (self.norms * nv)
        k = min(k, len(sims))
        part = np.argpartition(-sims, k - 1)[:k]
        order = part[np.argsort(-sims[part])]
        return [(int(i), float(sims[i])) for i in order]


# ============================================================================
# 3. Live trending cross-match (bounded, keyless, cached, offline-safe)
# ============================================================================

_TRENDING_CACHE: dict = {"at": 0.0, "data": None}


def fetch_live_trending(timeout_s: float = 6.0) -> dict[str, dict] | None:
    """One keyless AniList pull: current top-50 trending. Cached 10 minutes.
    Returns normalized-title → {trending, popularity, average_score} or None."""
    if os_environ_flag("SAKURASCORE_GREENLIGHT_OFFLINE"):
        return None
    now = time.time()
    if _TRENDING_CACHE["data"] is not None and now - _TRENDING_CACHE["at"] < TRENDING_TTL_S:
        return _TRENDING_CACHE["data"]
    q = """
    query { Page(page: 1, perPage: 50) {
      media(type: ANIME, sort: TRENDING_DESC, isAdult: false) {
        title { romaji english } trending popularity averageScore
      }
    } }
    """
    try:
        req = urllib.request.Request(
            ANILIST_API,
            data=json.dumps({"query": q}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "sakurascore-greenlight/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            media = json.loads(resp.read().decode())["data"]["Page"]["media"]
        out = {}
        for m in media:
            t = m["title"].get("english") or m["title"].get("romaji") or ""
            out[_norm_key(t)] = {"trending": m.get("trending") or 0,
                                 "popularity": m.get("popularity") or 0,
                                 "average_score": m.get("averageScore")}
        _TRENDING_CACHE.update({"at": now, "data": out})
        return out
    except Exception:
        return _TRENDING_CACHE["data"]  # stale beats nothing; None if never fetched


def os_environ_flag(name: str) -> bool:
    import os
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


# ============================================================================
# 4. Greenlight engine — orchestrates everything, adds the quant layer
# ============================================================================

@dataclass
class GreenlightEngine:
    app: object                      # SakuraScoreApp (the real pipeline)
    tensor: CatalogTensor
    genre_affinity: dict[str, int]
    _score_cache: dict = field(default_factory=dict)
    _run_cache: dict = field(default_factory=dict)

    # ---- real pipeline on a catalog title, cached ----
    def comparable_score(self, title: str) -> dict:
        key = _norm_key(title)
        if key not in self._score_cache:
            r = self.app.run_candidate(title)
            self._score_cache[key] = {
                "title": r.title, "sakura_score": r.sakura_score, "grade": r.grade,
                "confidence": r.confidence, "factors": [
                    {"name": f.name, "value": f.value, "weight": f.weight,
                     "contribution": f.contribution} for f in r.factors],
                "genres": r.metadata.get("genres") or [],
                "format": r.metadata.get("format"),
                "recommended": r.localization_economics.recommended_mode,
                "hub_demand": {h: v["demand_index"] for h, v in r.market_breakdown.items()},
            }
        return self._score_cache[key]

    # ---- the full greenlight run ----
    def run(self, payload: dict) -> dict:
        t0 = time.perf_counter()
        text = str(payload.get("concept") or payload.get("text") or "")
        if len(text.strip()) < 12:
            return {"status": "error", "error": "concept text too short — paste a logline, "
                    "script excerpt, character design or any Japanese-media pitch (≥ 12 chars)"}

        cache_key = (_norm_key(text)[:180] + "|" + _norm_key(str(payload.get("title") or ""))
                     + "|" + str(payload.get("format") or "") + "|" + str(payload.get("episodes") or ""))
        if cache_key in self._run_cache:
            out = dict(self._run_cache[cache_key])
            out["cache_hit"] = True
            return out

        t_parse = time.perf_counter()
        parsed = parse_concept(text, title=str(payload.get("title") or ""),
                               format=str(payload.get("format") or ""),
                               episodes=payload.get("episodes"))
        parse_ms = (time.perf_counter() - t_parse) * 1000

        # ---- comparables from the live catalog tensor ----
        t_t = time.perf_counter()
        v = self.tensor.concept_vector(parsed)
        sims = self.tensor.similar(v, K_COMPARABLES)
        tensor_ms = (time.perf_counter() - t_t) * 1000

        t_c = time.perf_counter()
        comparables = []
        for idx, sim in sims:
            title = self.tensor.titles[idx]
            scored = self.comparable_score(title)
            comparables.append({**scored, "similarity": round(sim, 4)})
        cohort_ms = (time.perf_counter() - t_c) * 1000

        # ---- live trending cross-match (bounded, offline-safe) ----
        t_l = time.perf_counter()
        live = fetch_live_trending()
        live_hits = 0
        for c in comparables:
            key = _norm_key(c["title"])
            if live and key in live:
                c["live_trending"] = live[key]["trending"]
                c["live_popularity"] = live[key]["popularity"]
                live_hits += 1
            else:
                c["live_trending"] = None
        live_ms = (time.perf_counter() - t_l) * 1000

        # ---- the concept through the REAL pipeline (meta_override) ----
        # spy on the two-pass scoring so the UI can show provisional → plan → final
        t_p = time.perf_counter()
        override = {
            "title_english": parsed.title,
            "format": parsed.pipeline_format,
            "episodes": parsed.episodes,
            "duration": parsed.duration_min,
            "genres": parsed.genres,
            "tags": parsed.tags,
            "popularity": 0, "favourites": 0,
            "is_adult": parsed.is_adult,
            "studios": "", "site_url": "",
        }
        captured: list = []
        orig_score = self.app.scoring.score_candidate

        def _spy(**kw):
            r2 = orig_score(**kw)
            captured.append(r2)
            return r2

        self.app.scoring.score_candidate = _spy
        try:
            result = self.app.run_candidate(parsed.title, meta_override=override)
        finally:
            self.app.scoring.score_candidate = orig_score
        structural_score = result.sakura_score
        pipeline_ms = round((time.perf_counter() - t_p) * 1000, 1)

        # ---- cohort stats + LOO calibration (empirical-Bayes shrinkage) ----
        t_q = time.perf_counter()
        sims_arr = np.array([c["similarity"] for c in comparables], dtype=np.float64)
        # softmax-ish similarity weights (temperature keeps near-ties informative)
        w = sims_arr ** 4
        w = w / w.sum()
        scores_arr = np.array([c["sakura_score"] for c in comparables], dtype=np.float64)
        knn_mu = float((w * scores_arr).sum())
        ess = float(1.0 / np.maximum((w ** 2).sum(), 1e-9))  # effective sample size
        cohort_sigma = float(np.sqrt(max((w * (scores_arr - knn_mu) ** 2).sum(), 1.0)))
        sigma_est = cohort_sigma / math.sqrt(max(ess, 1.0))

        # leave-one-out on the cohort: how well does kNN-within-cohort predict?
        loo_err = []
        for i in range(len(comparables)):
            mask = np.ones(len(comparables), dtype=bool)
            mask[i] = False
            wi = sims_arr[mask] ** 4
            if wi.sum() <= 0:
                continue
            wi = wi / wi.sum()
            loo_err.append(float((wi * scores_arr[mask]).sum()) - float(scores_arr[i]))
        loo_mae = float(np.mean(np.abs(loo_err))) if loo_err else 10.0

        # blend weight fitted on the cohort LOO (0 = pure structural, 1 = pure kNN)
        grid = np.linspace(0.0, 1.0, 41)
        loo_losses = []
        for b in grid:
            errs = [(b * e) + ((1 - b) * (structural_score - s)) for e, s in zip(loo_err, scores_arr)]
            loo_losses.append(float(np.mean(np.abs(errs))))
        blend_knn = float(grid[int(np.argmin(loo_losses))])
        # shrink blend toward the LOO-optimal but keep informative prior 0.55
        blend = 0.5 * blend_knn + 0.5 * 0.55

        # shrinkage λ: strong cohort signal → trust kNN; weak → regress to structural
        lam = 1.0 / (1.0 + (loo_mae / max(cohort_sigma, 1e-9)) ** 2)
        knn_shrunk = lam * knn_mu + (1 - lam) * np.median(scores_arr)
        mu = blend * knn_shrunk + (1 - blend) * structural_score

        # ---- Monte Carlo: antithetic + fat tails, fully vectorized ----
        rng = np.random.default_rng(MC_SEED)
        n = MC_SIMS // 2
        z = rng.standard_normal((n, 1))
        z = np.vstack([z, -z])  # antithetic variates — variance reduction
        tail = rng.standard_t(df=4, size=(MC_SIMS, 1)) * 0.35  # 35% fat-tail mixture weight
        mix = rng.random((MC_SIMS, 1)) < 0.35
        noise_unit = np.where(mix, tail, z)
        sigma_conf = (100 - result.confidence) / 100.0 * 12.0  # structural-score uncertainty
        sigma_total = math.sqrt((blend * lam * cohort_sigma) ** 2
                                + (blend * sigma_est) ** 2
                                + ((1 - blend) * sigma_conf) ** 2)
        draws = np.clip(mu + noise_unit[:, 0] * sigma_total, 0, 100)

        mean = float(draws.mean())
        std = float(draws.std())
        var5 = float(np.percentile(draws, 5))
        cvar5 = float(draws[draws <= var5].mean())
        p_b = float((draws >= 60).mean())
        p_a = float((draws >= 70).mean())
        p_s = float((draws >= 80).mean())
        # grade of the median draw
        med = float(np.median(draws))
        grade = "S" if med >= 80 else "A" if med >= 70 else "B" if med >= 60 else "C" if med >= 45 else "D"

        quant_ms = (time.perf_counter() - t_q) * 1000

        # ---- investment view: plans, ROI distribution, Sharpe, Kelly ----
        # Two-regime model: a draw either "launches" (reaches tier-level
        # viewership, prob rising in the score) or lands niche (12% of tier
        # views). This left-tail mixture is what makes VaR/Sharpe/Kelly
        # discriminate between plans instead of screaming BUY on everything.
        t_i = time.perf_counter()
        econ = result.localization_economics
        p_launch = np.clip((draws - 35.0) / 50.0, 0.05, 0.95)
        launch = rng.random(MC_SIMS) < p_launch
        regime = np.where(launch, 1.0, 0.12)
        plans = []
        for p in econ.plans:
            # tier views are gated by the *score draw*, not the plan label;
            # the plan contributes its reach multiplier relative to the
            # 1.55× Hindi baseline
            tier_base = np.select(
                [draws >= 72, draws >= 55, draws >= 40],
                [2_600_000, 1_400_000, 700_000], default=280_000)
            monthly = tier_base * (p.reach_multiplier / 1.55) ** 0.8
            revenue = monthly * 12 * 0.90 * regime
            roi = revenue / max(p.cost_inr, 1.0) - 1.0
            mu_r, sd_r = float(roi.mean()), float(roi.std())
            sharpe = (mu_r - 0.065) / sd_r if sd_r > 1e-9 else 0.0  # rf = India 10y G-sec ≈ 6.5%
            kelly = mu_r / (sd_r ** 2) if sd_r > 1e-9 else 0.0      # continuous-time Kelly f*
            plans.append({
                "mode": p.mode, "languages": list(p.languages),
                "cost_inr": float(p.cost_inr), "reach_multiplier": p.reach_multiplier,
                "cost_per_reach_unit": float(p.cost_per_reach_unit),
                "roi_mean": mu_r, "roi_std": sd_r,
                "roi_var5": float(np.percentile(roi, 5)),
                "roi_cvar5": float(roi[roi <= np.percentile(roi, 5)].mean()),
                "sharpe": sharpe, "kelly_fraction": max(0.0, min(1.0, kelly)),
                "p_profit": float((roi > 0).mean()),
                "expected_12m_views": float((monthly * regime).mean() * 12),
            })
        recommended = next((p for p in plans if p["mode"] == econ.recommended_mode), plans[-1])
        inv_ms = (time.perf_counter() - t_i) * 1000

        # ---- state-level India prediction (32 states, sourced CSV) ----
        t_s = time.perf_counter()
        states = state_demand(self.app, result.cultural_profile,
                              econ.recommended_plan.reach_multiplier)
        state_ms = (time.perf_counter() - t_s) * 1000

        # ---- module inventory (the registry is the module contract) ----
        inventory = module_inventory()

        out = {
            "status": "ok",
            "schema": "sakurascore-greenlight/1.0",
            "concept": {
                "title": parsed.title,
                "media_type": parsed.media_type,
                "pipeline_format": parsed.pipeline_format,
                "genres": parsed.genres,
                "tags": [{"name": n, "rank": int(r)} for n, r in parsed.tags],
                "demographics": parsed.demographics,
                "episodes": parsed.episodes,
                "duration_min": parsed.duration_min,
                "is_adult": parsed.is_adult,
                "japanese_terms": parsed.japanese_terms,
                "receipts": parsed.receipts,
            },
            "greenlight_score": int(round(mean)),
            "grade": grade,
            "blend": {
                "knn_weight": round(blend, 3),
                "knn_score": round(knn_shrunk, 1),
                "structural_score": structural_score,
                "cohort_median": float(np.median(scores_arr)),
                "shrinkage_lambda": round(lam, 3),
                "loo_mae": round(loo_mae, 1),
                "loo_optimal_knn_weight": round(blend_knn, 2),
                "ess": round(ess, 1),
            },
            "risk": {
                "mean": round(mean, 1), "std": round(std, 1),
                "var5": round(var5, 1), "cvar5": round(cvar5, 1),
                "p_grade_b": round(p_b, 3), "p_grade_a": round(p_a, 3),
                "p_grade_s": round(p_s, 3),
                "sigma_total": round(sigma_total, 1),
                "sims": int(len(draws)), "method": "antithetic normal + 35% Student-t(4) mixture, seeded 42",
            },
            "comparables": comparables,
            "cohort": {
                "mean": round(float(scores_arr.mean()), 1),
                "std": round(float(scores_arr.std()), 1),
                "min": int(scores_arr.min()), "max": int(scores_arr.max()),
                "concept_percentile": int(round(100 * (scores_arr < mean).mean())),
            },
            "pipeline_result": _serialize_pipeline(result, app=self.app, genres=parsed.genres,
                                                   pipeline_ms=pipeline_ms, captured=captured),
            "plans": plans,
            "recommended_plan": recommended["mode"],
            "states": states,
            "live": {
                "trending_crossmatch": live_hits,
                "trending_pulled": live is not None,
                "anilist_trending_source": "https://graphql.anilist.co (keyless, top-50, 10-min cache)" if live else "offline — cached catalog signals only",
            },
            "modules": inventory,
            "timings_ms": {
                "parse": round(parse_ms, 1), "tensor": round(tensor_ms, 1),
                "cohort_scoring": round(cohort_ms, 1), "live_pull": round(live_ms, 1),
                "pipeline": round(pipeline_ms, 1), "quant": round(quant_ms, 1),
                "investment": round(inv_ms, 1), "states": round(state_ms, 1),
                "total": round((time.perf_counter() - t0) * 1000, 1),
                "catalog_titles": len(self.tensor.titles),
                "tensor_dims": self.tensor.D,
            },
            "cache_hit": False,
        }
        self._run_cache[cache_key] = out
        out["cache_hit"] = False
        return out


def _serialize_pipeline(r, app=None, genres=None, pipeline_ms=None, captured=None) -> dict:
    """The full PipelineResult surface the dashboard already knows how to draw,
    plus the display-only extras the worker's analyze path attaches."""
    def s(o):
        if hasattr(o, "__dataclass_fields__"):
            return {k: s(v) for k, v in o.__dict__.items()}
        if isinstance(o, dict):
            return {k: s(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [s(v) for v in o]
        return o
    d = s(r)
    d["why_bullets"] = r.why_bullets
    if pipeline_ms is not None:
        d["pipeline_ms"] = pipeline_ms
    if captured:
        d["two_pass"] = {
            "provisional": captured[0].sakura_score if captured else None,
            "final": captured[1].sakura_score if len(captured) > 1 else r.sakura_score,
            "plan_reach": r.localization_economics.recommended_plan.reach_multiplier,
            "note": "pass 1 scores at the 1.55x prior → econ picks the plan → pass 2 rescores at the plan's reach",
        }
    if app is not None:
        # confidence parts, concept edition: no catalog row / no wiki / no trends /
        # no seed / unreleased (a concept is by definition pre-launch)
        d["confidence_parts"] = [
            {"part": "catalog metadata", "got": False, "points": 0, "max": 30},
            {"part": "wikipedia volume", "got": False, "points": 8, "max": 25},
            {"part": "trends growth", "got": False, "points": 5, "max": 15},
            {"part": "hindi wikipedia", "got": False, "points": 0, "max": 10},
            {"part": "graded success seed", "got": False, "points": 0, "max": 10},
            {"part": "released demand", "got": False, "points": 5, "max": 10},
        ]
        from src.scoring.engine import GENRE_AFFINITY
        d["genre_affinity"] = [
            {"genre": g, "affinity": GENRE_AFFINITY.get(g, 55)} for g in (genres or [])
        ]
        d["tier_notes"] = [
            "concept scored as a pre-launch title: popularity/fandom signals are floor "
            "values by design — the greenlight blend supplies the demand-side estimate "
            "from live-scored comparables",
        ]
    return d


# ============================================================================
# 5. State-level demand — the hub math evaluated at every state
# ============================================================================

def state_demand(app, cultural_profile, reach_multiplier: float) -> dict:
    """The pipeline's market_breakdown formula, evaluated per state.

    Same math (population share × internet/60 × cultural delta × friction ×
    reach/2.2, clamped via ×4 to 0-100), but at the 32-state granularity of
    data/reference/india_states.csv, plus the state's own dub-language fit.
    """
    from src.app import SakuraScoreApp  # noqa: F401 — HUBS lives on the class
    hub_of = {}
    for hub, sts in SakuraScoreApp.HUBS.items():
        for st in sts:
            hub_of[st] = hub
    deltas = cultural_profile.regional_variation or {}
    friction = cultural_profile.family_co_viewing_friction
    total_pop = float(app.states["population_2011_census"].sum())

    rows = []
    for _, st in app.states.iterrows():
        name = st["state"]
        hub = hub_of.get(name, "Northern Fringe")
        pop = float(st["population_2011_census"])
        internet = float(st["internet_penetration_est_2024_pct"])
        delta = float(deltas.get(hub, 0.0))
        friction_penalty = friction * (0.35 if hub == "Hindi Belt" else 0.2)
        demand = (100 * (pop / total_pop) * (internet / 60) * (1 + delta / 100)
                  * (1 - friction_penalty / 200) * (reach_multiplier / 2.2))
        idx = int(max(0, min(100, demand * 4)))
        langs = [l.strip() for l in str(st.get("primary_languages") or "").split(",") if l.strip()]
        dub_fit = "hi" if "Hindi" in langs else ("ta" if "Tamil" in langs else
                     ("te" if "Telugu" in langs else
                      ("en" if "English" in langs else "hi")))
        rows.append({
            "state": name, "region": str(st.get("region") or ""), "hub": hub,
            "population": int(pop), "internet_pct": round(internet, 1),
            "median_age": round(float(st.get("median_age_years_est_2024") or 0), 1),
            "demand_index": idx, "cultural_delta": delta,
            "best_dub_language": dub_fit, "languages": langs,
        })
    rows.sort(key=lambda r: -r["demand_index"])
    hubs = {}
    for r in rows:
        h = hubs.setdefault(r["hub"], {"hub": r["hub"], "states": 0, "demand_index": 0, "population": 0})
        h["states"] += 1
        h["demand_index"] += r["demand_index"]
        h["population"] += r["population"]
    return {"states": rows, "hubs": sorted(hubs.values(), key=lambda h: -h["demand_index"])}


# ============================================================================
# 6. Module inventory — the engine_api registry, enumerated live
# ============================================================================

def module_inventory() -> dict:
    """Enumerate the engine_api registry (capability kinds + providers) and
    the external module repos — the toolbox this engine is wired into."""
    inv: dict = {"registry_kinds": [], "providers": {}, "external_repos": 0, "total_modules": 0}
    try:
        import sys
        if str(MODULES_SRC) not in sys.path:
            sys.path.insert(0, str(MODULES_SRC))
        # import the providers package so the lazy factories actually register
        # (the registry is empty until then — registration happens at import)
        import providers  # type: ignore  # noqa: F401
        from engine_api.registry import registry, KINDS  # type: ignore
        inv["registry_kinds"] = list(KINDS)
        for kind in KINDS:
            names = registry.names(kind)
            if names:
                inv["providers"][kind] = list(names)
        n_prov = sum(len(v) for v in inv["providers"].values())
        ext = MODULES_SRC.parent / "external"
        inv["external_repos"] = len([d for d in ext.iterdir() if d.is_dir()]) if ext.exists() else 0
        inv["total_modules"] = n_prov + inv["external_repos"]
    except Exception as e:
        inv["error"] = f"{type(e).__name__}: {e}"
    return inv


# ============================================================================
# 7. Roadmap (P0 shipped → P4) — maps phases to the actual repos on disk
# ============================================================================

ROADMAP = [
    {"phase": "P0", "status": "SHIPPED", "title": "Concept terminal (this page)",
     "what": "lexicon parser → catalog tensor kNN comparables → real-pipeline structural score → "
             "cohort LOO calibration → antithetic Monte Carlo → VaR/CVaR/Sharpe/Kelly → "
             "32-state demand model → live AniList trending cross-match",
     "modules": ["catalog tensor (numpy BLAS)", "engine_api registry inventory",
                 "SakuraScore pipeline (scoring + cultural + econ)"]},
    {"phase": "P1", "status": "NEXT", "title": "Semantic comparables",
     "what": "replace/augment the lexicon+tag tensor with sentence-transformers embeddings of "
             "real synopses; indic_nlp_library for Hinglish/Devanagari concept input",
     "modules": ["sentence-transformers (external clone)", "indic_nlp_library", "IndicTrans2"]},
    {"phase": "P2", "status": "PLANNED", "title": "Causal uplift + fairness audit",
     "what": "EconML/dowhy causal estimate of dub-lift on comparable cohorts instead of the "
             "1.55/1.85/2.2 heuristic reach multipliers; AIF360 audit of the state demand "
             "model for regional bias",
     "modules": ["EconML", "dowhy", "AIF360"]},
    {"phase": "P3", "status": "PLANNED", "title": "Forecasting + conformal gates",
     "what": "darts/prophet time-series forecasts of state-level demand; MAPIE conformal "
             "prediction intervals published with every score; drift detection (alibi-detect) "
             "on the catalog tensor",
     "modules": ["darts", "prophet", "MAPIE", "alibi-detect", "sktime"]},
    {"phase": "P4", "status": "VISION", "title": "Swarm validation + live evidence",
     "what": "OASIS-style agent swarm reacts to the concept's pilot script; Agent-Reach "
             "retrieves live Reddit/YouTube evidence on the comparables; dgraph knowledge "
             "graph of IP similarity at scale",
     "modules": ["oasis", "Agent-Reach", "dgraph", "zep"]},
]


# ============================================================================
# 8. Boot + CLI selftest
# ============================================================================

def build_engine() -> GreenlightEngine:
    import sys
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from src.app import SakuraScoreApp
    from src.scoring.engine import GENRE_AFFINITY
    app = SakuraScoreApp()
    tensor = CatalogTensor(app.catalog, GENRE_AFFINITY)
    return GreenlightEngine(app=app, tensor=tensor, genre_affinity=GENRE_AFFINITY)


SAMPLE_CONCEPTS = [
    {
        "name": "Isekai revenge drama",
        "concept": 'Title: "Kurogane no Kokoro". A dark shounen series: a 17-year-old blacksmith\'s '
                   'apprentice is transported to another world (isekai) ruled by an immortal shogun. '
                   'He joins a guild of demon hunters, learns katana swordplay from a gruff mentor, '
                   'and pursues brutal revenge against the oni that burned his village. 24 episodes, '
                   'very graphic violence, themes of found family and coming of age.',
    },
    {
        "name": "Iyashikei cooking slice",
        "concept": '"Shokudo no Sora" — a healing slice-of-life about a retired Tokyo office lady who '
                   'opens a tiny ramen restaurant in a rural coastal village. Cooking, food, festivals, '
                   'gentle comedy, found family with the local fishermen. Iyashikei vibes, 12 episodes.',
    },
    {
        "name": "Mecha OVA pilot",
        "concept": 'A prestige mecha movie: teenage girl mecha pilot defends a space colony from kaiju '
                   'spawned by a dying god. Real robot military politics, very emotional drama, '
                   'body horror transformation sequences. Theatrical film, 118 minutes.',
    },
]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--concept", type=str, default=None)
    args = ap.parse_args()
    t0 = time.perf_counter()
    eng = build_engine()
    print(f"boot: catalog {len(eng.tensor.titles)} titles · tensor {eng.tensor.X.shape} "
          f"float32 · {round((time.perf_counter()-t0)*1000)} ms")
    if args.selftest:
        for s in SAMPLE_CONCEPTS:
            out = eng.run({"concept": s["concept"]})
            ok = out.get("status") == "ok"
            print(f"  {s['name']:26s} → {'OK' if ok else 'FAIL'} "
                  f"score {out.get('greenlight_score')} grade {out.get('grade')} "
                  f"comparables {[c['title'][:18] for c in out.get('comparables', [])[:3]]}")
            if not ok:
                print("   ", out.get("error"))
        print("PASS" if all(eng.run({"concept": s["concept"]}).get("status") == "ok"
                           for s in SAMPLE_CONCEPTS) else "FAIL")
    elif args.concept:
        print(json.dumps(eng.run({"concept": args.concept}), ensure_ascii=False, default=str)[:4000])
