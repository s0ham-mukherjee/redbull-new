"""SakuraScoreApp — pipeline core: data indexes -> run_candidate() -> PipelineResult.

The app loads the processed CSVs under data/ (produced by
scripts/data_collection/*), builds lookup indexes, and orchestrates:
  Data Aggregation -> Signal Processing -> Predictive Scoring -> Reporting
with cultural compatibility, rupee localization economics, the 8-source
evidence matrix, and bilingual briefings attached to every result.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.briefing.japanese import (GRADE_COMMENT_JA,
                                   build_executive_briefing_en,
                                   build_executive_briefing_ja)
from src.data_sources.matrix import get_matrix
from src.intelligence.cultural_compat.engine import (CulturalCompatibilityEngine,
                                                     CulturalProfile)
from src.intelligence.localization_econ.engine import (LocalizationEconomics,
                                                       LocalizationEconomicsEngine)
from src.scoring.engine import ScoringEngine

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

# Showcase aliases (normalized keys) -> exact catalog english titles
# (verified in the catalog).
SHOWCASE_ALIASES = {
    "chainsaw man reze arc": "Chainsaw Man – The Movie: Reze Arc",
    "jujutsu kaisen culling game": "JUJUTSU KAISEN Season 3: The Culling Game Part 1",
    "solo leveling s2": "Solo Leveling Season 2 -Arise from the Shadow-",
    "sakamoto days": "SAKAMOTO DAYS",
    "lazarus": "LAZARUS",
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


@dataclass
class PipelineResult:
    title: str
    metadata: dict
    unreleased: bool
    sakura_score: int
    grade: str
    confidence: int
    factors: list
    cultural_profile: CulturalProfile
    localization_economics: LocalizationEconomics
    data_source_matrix: list
    executive_briefing_en: str
    executive_briefing_ja: str
    market_breakdown: dict = field(default_factory=dict)
    wiki_evidence: dict | None = None
    grade_comment_ja: str = ""

    @property
    def why_bullets(self) -> list[str]:
        """Factor-attribution bullets for the 'Why This Score?' view."""
        out = []
        for f in sorted(self.factors, key=lambda x: -x.contribution):
            out.append(f"[{f.value:.0f}/100 x {f.weight:.2f} = {f.contribution:+.1f}] "
                       + "; ".join(f.rationale))
        return out


class SakuraScoreApp:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        p = self.data_dir / "processed"
        if not (p / "anilist_catalog.csv").exists():
            raise FileNotFoundError(
                f"{p} is missing processed CSVs — run scripts/data_collection/"
                "fetch_anilist.py and process.py first.")
        self.catalog = pd.read_csv(p / "anilist_catalog.csv", encoding="utf-8-sig")
        self.wiki = pd.read_csv(p / "wikipedia_pageviews_summary.csv", encoding="utf-8-sig")
        self.trends = pd.read_csv(p / "google_trends_india_long.csv", encoding="utf-8-sig")
        self.states = pd.read_csv(self.data_dir / "reference" / "india_states.csv")
        self.seed = pd.read_csv(self.data_dir / "reference" / "india_anime_success_seed.csv")

        self.cultural = CulturalCompatibilityEngine()
        self.econ = LocalizationEconomicsEngine()
        self.scoring = ScoringEngine()
        self._matrix = get_matrix()

        # --- indexes -------------------------------------------------------
        self.catalog["_norm_en"] = self.catalog["title_english"].fillna("").map(_norm)
        self.catalog["_norm_ro"] = self.catalog["title_romaji"].fillna("").map(_norm)
        self.by_english = {r["title_english"]: r for _, r in self.catalog.iterrows()
                           if isinstance(r["title_english"], str)}
        self.popularity_values = self.catalog["popularity"].fillna(0).astype(float).tolist()
        self.favourite_values = self.catalog["favourites"].fillna(0).astype(float).tolist()
        unreleased_mask = self.catalog["status"].eq("NOT_YET_RELEASED")
        self.unreleased_pop_values = self.catalog.loc[
            unreleased_mask, "popularity"].fillna(0).astype(float).tolist()
        en_wiki = self.wiki[self.wiki["project"] == "en.wikipedia"]
        self.wiki_vol_values = en_wiki["avg_daily_last30"].astype(float).tolist()
        self.wiki_by_source_title = {
            _norm(r["source_title"]): r for _, r in en_wiki.iterrows()
            if isinstance(r["source_title"], str)}
        self.hi_wiki_titles = {
            _norm(r["source_title"]) for _, r in self.wiki.iterrows()
            if r["project"] == "hi.wikipedia" and isinstance(r["source_title"], str)}
        self.trends_growth = self._trends_growth_index()

    # ------------------------------------------------------------------ data
    def _trends_growth_index(self) -> dict:
        """keyword -> 2-year growth % of mean interest (last 52w vs prior 52w)."""
        out = {}
        for kw, g in self.trends.groupby("keyword"):
            g = g.copy()
            g["date"] = pd.to_datetime(g["date"], errors="coerce")
            g = g.dropna(subset=["date"]).sort_values("date")
            if len(g) < 104:
                continue
            recent = g["interest"].tail(52).astype(float).mean()
            prior = g["interest"].iloc[-104:-52].astype(float).mean()
            if prior:
                out[kw] = round(100 * (recent / prior - 1), 1)
        return out

    def lookup(self, title: str) -> dict | None:
        """Find a catalog row by exact english, alias, or normalized substring."""
        key = title.strip()
        if key in self.by_english:
            return self.by_english[key]
        alias = SHOWCASE_ALIASES.get(_norm(key))
        if alias and alias in self.by_english:
            return self.by_english[alias]
        n = _norm(key)
        hits = self.catalog[(self.catalog["_norm_en"] == n)
                            | (self.catalog["_norm_ro"] == n)]
        if hits.empty:
            hits = self.catalog[self.catalog["_norm_en"].str.contains(n, regex=False)
                                | self.catalog["_norm_ro"].str.contains(n, regex=False)]
        return None if hits.empty else hits.iloc[0]

    def showcase_titles(self) -> list[str]:
        return list(SHOWCASE_ALIASES)

    def released_top(self, n: int = 40) -> list[str]:
        fin = self.catalog[self.catalog["status"].isin(
            ["FINISHED", "RELEASING"])].copy()
        fin = fin.sort_values("popularity", ascending=False)
        return [t for t in fin["title_english"].dropna().head(n)]

    # ----------------------------------------------------------------- signals
    def _wiki_for(self, meta: dict) -> dict | None:
        for key in (meta.get("title_english"), meta.get("title_romaji")):
            if not key:
                continue
            row = self.wiki_by_source_title.get(_norm(key))
            if row is not None and row["project"] == "en.wikipedia":
                return {"article": row["article"],
                        "avg_daily_last30": float(row["avg_daily_last30"]),
                        "peak_daily": float(row["peak_daily"]),
                        "momentum_90d_vs_prior90": row["momentum_90d_vs_prior90"],
                        "has_hindi_wiki": _norm(key) in self.hi_wiki_titles,
                        "total_views_24m": float(row["total_views_24m"])}
        return None

    def _trends_for(self, meta: dict, title: str) -> dict:
        """Match franchise keywords to the title; fall back to 'anime' index."""
        t = _norm(title)
        best = None
        for kw, growth in self.trends_growth.items():
            if _norm(kw) in t or t in _norm(kw):
                best = (kw, growth)
        kw, growth = best if best else ("anime", self.trends_growth.get("anime"))
        return {"keyword": kw, "growth_2y_pct": growth}

    def _confidence(self, *, meta: dict | None, wiki: dict | None,
                    trends: dict, seed_match: pd.DataFrame | None,
                    unreleased: bool) -> int:
        c = 0
        c += 30 if meta is not None else 0
        c += 25 if wiki else 8
        c += 15 if trends.get("growth_2y_pct") is not None else 5
        if wiki and wiki.get("has_hindi_wiki"):
            c += 10
        c += 10 if seed_match is not None else 0
        c += 10 if not unreleased else 5   # released titles have realized demand
        return int(min(100, c))

    # ------------------------------------------------------------- market map
    HUBS = {
        "Hindi Belt": ["Uttar Pradesh", "Bihar", "Madhya Pradesh", "Rajasthan",
                       "Haryana", "Delhi", "Uttarakhand", "Chhattisgarh",
                       "Himachal Pradesh", "Jharkhand"],
        "Southern Fortress": ["Tamil Nadu", "Karnataka", "Kerala", "Telangana",
                              "Andhra Pradesh", "Puducherry"],
        "Western Metros": ["Maharashtra", "Gujarat", "Goa"],
        "Eastern Hub": ["West Bengal", "Odisha", "Tripura"],
        "Northeast": ["Assam", "Arunachal Pradesh", "Manipur", "Meghalaya",
                      "Mizoram", "Nagaland", "Sikkim"],
        "Northern Fringe": ["Punjab", "Jammu and Kashmir", "Chandigarh"],
    }

    def market_breakdown(self, cultural_profile: CulturalProfile,
                         reach_multiplier: float, genre_fit: int) -> dict:
        """Linguistic-hub demand split (Hindi belt vs Southern Fortress etc.),
        blending population x internet penetration with cultural deltas."""
        state_hub = {}
        for hub, states in self.HUBS.items():
            for s in states:
                state_hub[s] = hub
        self.states["_hub"] = self.states["state"].map(state_hub).fillna("Northern Fringe")

        deltas = cultural_profile.regional_variation or {}
        friction = cultural_profile.family_co_viewing_friction
        out = {}
        for hub, g in self.states.groupby("_hub"):
            pop = g["population_2011_census"].sum()
            internet = (g["internet_penetration_est_2024_pct"]
                        * g["population_2011_census"]).sum() / pop
            young = (g["median_age_years_est_2024"]
                     * g["population_2011_census"]).sum() / pop
            delta = sum(v for k, v in deltas.items() if k == hub)
            # friction hits dub-first, co-viewing-driven hubs hardest
            friction_penalty = friction * (0.35 if hub == "Hindi Belt" else 0.2)
            demand = (100 * (pop / self.states["population_2011_census"].sum())
                      * (internet / 60) * (1 + delta / 100)
                      * (1 - friction_penalty / 200) * (reach_multiplier / 2.2))
            out[hub] = {
                "population": int(pop),
                "internet_penetration_pct": round(float(internet), 1),
                "median_age": round(float(young), 1),
                "cultural_delta": delta,
                "demand_index": int(max(0, min(100, demand * 4))),
            }
        return dict(sorted(out.items(), key=lambda kv: -kv[1]["demand_index"]))

    # ---------------------------------------------------------------- pipeline
    def run_candidate(self, title: str, meta_override: dict | None = None) -> PipelineResult:
        row = self.lookup(title)
        if row is not None:
            meta = {
                "title_english": row.get("title_english") or title,
                "title_romaji": row.get("title_romaji") or "",
                "format": row.get("format") or "TV",
                "episodes": None if pd.isna(row.get("episodes")) else int(row["episodes"]),
                "duration": None if pd.isna(row.get("duration_min")) else int(row["duration_min"]),
                "status": row.get("status") or "",
                "season_year": None if pd.isna(row.get("season_year")) else int(row["season_year"]),
                "genres": [g for g in str(row.get("genres") or "").split("|") if g],
                "tags": [tuple(t.rsplit(":", 1) if ":" in t else (t, 50))
                         for t in str(row.get("tags") or "").split("|") if t],
                "popularity": float(row.get("popularity") or 0),
                "favourites": float(row.get("favourites") or 0),
                "average_score": None if pd.isna(row.get("average_score")) else float(row["average_score"]),
                "studios": str(row.get("main_studios") or ""),
                "is_adult": "Hentai" in str(row.get("genres") or ""),
                "site_url": row.get("site_url") or "",
            }
        elif meta_override:
            meta = dict(meta_override)
            meta.setdefault("title_english", title)
            meta.setdefault("format", "TV")
            meta.setdefault("popularity", 0)
            meta.setdefault("favourites", 0)
            meta.setdefault("genres", [])
            meta.setdefault("tags", [])
            meta.setdefault("is_adult", False)
        else:
            raise ValueError(f"Title {title!r} not in catalog; supply meta_override.")

        unreleased_global = meta.get("status") == "NOT_YET_RELEASED"
        # Showcase titles are India-premiere-pending: released in Japan but with
        # zero/limited Indian consumption history (the plan's unreleased showcase).
        india_premiere_pending = _norm(title) in SHOWCASE_ALIASES
        unreleased = unreleased_global or india_premiere_pending
        display_title = meta.get("title_english") or title

        tags = []
        for t in meta.get("tags", []):
            name, rank = t[0], t[1] if len(t) > 1 else 50
            try:
                tags.append((name, float(rank)))
            except ValueError:
                tags.append((name, 50.0))

        wiki = self._wiki_for(meta)
        trends = self._trends_for(meta, display_title)
        seed_match = self.seed[self.seed["title"].fillna("").map(
            lambda s: _norm(s) == _norm(display_title)
            or _norm(display_title) in _norm(s))]
        seed_hit = None if seed_match.empty else seed_match.iloc[0]

        cul = self.cultural.evaluate(genres=meta.get("genres", []), tags=tags,
                                     is_adult=bool(meta.get("is_adult")),
                                     format=str(meta.get("format") or "TV"),
                                     episodes=meta.get("episodes"))

        # First pass: provisional score -> econ recommendation -> final scoring.
        conf = self._confidence(meta=meta if row is not None else None, wiki=wiki,
                                trends=trends, seed_match=seed_hit,
                                unreleased=unreleased)
        conf_parts = {"wiki_vol_values": self.wiki_vol_values,
                      "popularity_values": self.popularity_values,
                      "favourite_values": self.favourite_values,
                      "unreleased_pop_values": self.unreleased_pop_values,
                      "confidence": conf}
        provisional = self.scoring.score_candidate(
            meta=meta, wiki=wiki, trends=trends,
            cultural_fit=cul.overall_cultural_fit, reach_multiplier=1.55,
            pre_launch=unreleased, confidence_parts=conf_parts)
        econ = self.econ.evaluate(sakura_score=provisional.sakura_score,
                                  format=str(meta.get("format") or "TV"),
                                  episodes=meta.get("episodes"),
                                  duration_min=meta.get("duration"))
        final = self.scoring.score_candidate(
            meta=meta, wiki=wiki, trends=trends,
            cultural_fit=cul.overall_cultural_fit,
            reach_multiplier=econ.recommended_plan.reach_multiplier,
            pre_launch=unreleased, confidence_parts=conf_parts)

        breakdown = self.market_breakdown(cul,
                                          econ.recommended_plan.reach_multiplier,
                                          final.factors and dict(
                                              (f.name, f.value)
                                              for f in final.factors)["genre_fit"])

        result = PipelineResult(
            title=display_title, metadata=meta, unreleased=unreleased,
            sakura_score=final.sakura_score, grade=final.grade,
            confidence=final.confidence, factors=final.factors,
            cultural_profile=cul, localization_economics=econ,
            data_source_matrix=self._matrix,
            executive_briefing_en="", executive_briefing_ja="",
            market_breakdown=breakdown, wiki_evidence=wiki,
            grade_comment_ja=GRADE_COMMENT_JA[final.grade],
        )
        result.executive_briefing_en = build_executive_briefing_en(result)
        result.executive_briefing_ja = build_executive_briefing_ja(result)
        return result
