"""SakuraScore — transparent weighted-factor market-potential scoring.

Every factor returns 0-100 plus the rationale strings that justify it, so
the dashboard can answer *why* a title over- or under-performs. Weights are
documented and deliberately simple (weighted linear sum): defensibility over
black-box sophistication, per the challenge's emphasis on transparency.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

WEIGHTS = {
    "india_demand": 0.25,
    "global_fandom": 0.20,
    "momentum": 0.14,
    "cultural_fit": 0.14,
    "localization_reach": 0.14,
    "genre_fit": 0.13,
}

GRADES = [(80, "S"), (70, "A"), (60, "B"), (45, "C"), (0, "D")]

# Genre affinity for the Indian market (0-100). Anchored on the evidence
# seed list: action/shonen dominates; sports over-indexes (Blue Lock/Haikyu
# dub push); ecchi crashes family reach.
GENRE_AFFINITY = {
    "Action": 85, "Sports": 80, "Sci-Fi": 78, "Adventure": 72, "Fantasy": 72,
    "Thriller": 70, "Comedy": 66, "Drama": 68, "Supernatural": 66,
    "Mystery": 62, "Romance": 60, "Mecha": 58, "Music": 56,
    "Psychological": 56, "Suspense": 66, "Slice of Life": 46,
    "Iyashikei": 42, "Award Winning": 70, "Ecchi": 15, "Erotica": 5,
    "Hentai": 0, "Kids": 72, "Gourmet": 58,
}


@dataclass
class Factor:
    name: str
    value: int                    # 0-100
    weight: float
    contribution: float           # value * weight
    rationale: list = field(default_factory=list)


@dataclass
class ScoreResult:
    sakura_score: int
    grade: str
    confidence: int               # 0-100, data-coverage based
    factors: list                 # list[Factor]
    tier_notes: list = field(default_factory=list)


def grade_for(score: float) -> str:
    for floor, g in GRADES:
        if score >= floor:
            return g
    return "D"


class ScoringEngine:
    """Computes the SakuraScore from pre-normalized inputs provided by
    SakuraScoreApp (which owns the data indexes)."""

    @staticmethod
    def percentile(values: list, x: float) -> float:
        """Percentile rank of x within values (0-100)."""
        if not values:
            return 50.0
        below = sum(1 for v in values if v < x)
        eq = sum(1 for v in values if v == x)
        return 100.0 * (below + 0.5 * eq) / len(values)

    def score_candidate(self, *, meta: dict, wiki: dict | None, trends: dict,
                        cultural_fit: int, reach_multiplier: float,
                        pre_launch: bool, confidence_parts: dict,
                        note: str = "") -> ScoreResult:
        genres = meta.get("genres") or []
        factors: list[Factor] = []

        # 1. India demand -----------------------------------------------------
        ind_components = []
        rat = []
        if wiki and wiki.get("avg_daily_last30"):
            pct = self.percentile(confidence_parts["wiki_vol_values"],
                                  wiki["avg_daily_last30"])
            ind_components.append(0.40 * pct)
            rat.append(f"Wikipedia recent volume top-{100 - int(pct)}% of tracked titles "
                       f"({int(wiki['avg_daily_last30']):,} views/day, last 30d)")
            mom = wiki.get("momentum_90d_vs_prior90")
            if mom not in (None, ""):
                m = max(-1.0, min(1.0, float(mom)))
                ind_components.append(0.25 * (50 + 50 * m))
                direction = "accelerating" if m > 0.05 else "cooling" if m < -0.05 else "flat"
                rat.append(f"90-day momentum {float(mom):+.0%} ({direction})")
            if wiki.get("has_hindi_wiki"):
                ind_components.append(0.15 * 100)
                rat.append("Hindi Wikipedia article exists — direct Indian-language interest")
            else:
                ind_components.append(0.15 * 30)
        else:
            ind_components.append(0.55 * 35)
            rat.append("no Wikipedia coverage — demand inferred from metadata + trends only")
        g = trends.get("growth_2y_pct")
        if g is not None:
            ind_components.append(0.20 * max(0, min(100, 50 + g)))
            rat.append(f"category Google-Trends(IN) 2-yr growth {g:+.0f}%")
        else:
            ind_components.append(0.20 * 50)
        india_demand = int(sum(ind_components))

        # 2. Global fandom ------------------------------------------------------
        pop = meta.get("popularity") or 0
        pop_pct = self.percentile(confidence_parts["popularity_values"], pop)
        fav = meta.get("favourites") or 0
        fav_pct = self.percentile(confidence_parts["favourite_values"], fav)
        avg = meta.get("average_score")
        fandom = 0.55 * pop_pct + 0.45 * fav_pct
        fandom_rationale = [
            f"AniList popularity {int(pop):,} = top-{100 - int(pop_pct)}% of catalog",
            f"favourites {int(fav):,} = top-{100 - int(fav_pct)}%",
        ]
        if avg:
            bump = 15 if avg >= 80 else 8 if avg >= 75 else 0 if avg >= 68 else -8
            fandom = min(100, max(0, fandom + bump))
            fandom_rationale.append(f"AniList average score {avg:.0f}/100 "
                                    f"({bump:+d} quality adjustment)")
        fandom = int(fandom)

        # 3. Momentum -----------------------------------------------------------
        if pre_launch:
            # Pre-launch buzz = AniList watchlist demand percentile *among
            # unreleased titles* (survivorship-safe comparison group).
            base = self.percentile(confidence_parts["unreleased_pop_values"], pop)
            momentum = int(min(100, base))
            momentum_rationale = [
                f"pre-launch watchlist demand: top-{100 - int(base)}% among "
                f"{len(confidence_parts['unreleased_pop_values'])} unreleased titles",
            ]
            if wiki and wiki.get("momentum_90d_vs_prior90") not in (None, ""):
                momentum_rationale.append(
                    f"Wikipedia momentum {float(wiki['momentum_90d_vs_prior90']):+.0%}")
        else:
            mom = wiki.get("momentum_90d_vs_prior90") if wiki else None
            base = self.percentile(confidence_parts["wiki_vol_values"],
                                   (wiki or {}).get("avg_daily_last30") or 0)
            momentum = int(max(0, min(100, 0.6 * base + 0.4 * (
                50 + 50 * max(-1, min(1, float(mom))) if mom not in (None, "") else 50))))
            momentum_rationale = [
                "sustained post-release attention on Wikipedia"
                if momentum >= 50 else "attention below catalog median",
            ]

        # 4. Genre fit ------------------------------------------------------------
        if genres:
            affs = [GENRE_AFFINITY.get(g, 55) for g in genres]
            genre_fit = int(0.6 * max(affs) + 0.4 * (sum(affs) / len(affs)))
            genre_rationale = [f"{g}: {GENRE_AFFINITY.get(g, 55)}" for g in genres
                               if GENRE_AFFINITY.get(g, 55) in (0, 15)
                               or GENRE_AFFINITY.get(g, 55) >= 70]
        else:
            genre_fit, genre_rationale = 55, ["no genre data — neutral prior"]

        # 5. Cultural fit + 6. Localization reach ---------------------------------
        reach = int(max(0, min(100, 100 * (reach_multiplier - 1.0) / (2.2 - 1.0))))
        reach_rationale = [f"best-case localization reach {reach_multiplier:.2f}x "
                           f"subtitles-only (dub-depth driven)"]

        factors = [
            Factor("india_demand", india_demand, WEIGHTS["india_demand"],
                   india_demand * WEIGHTS["india_demand"], rat),
            Factor("global_fandom", fandom, WEIGHTS["global_fandom"],
                   fandom * WEIGHTS["global_fandom"], fandom_rationale),
            Factor("momentum", momentum, WEIGHTS["momentum"],
                   momentum * WEIGHTS["momentum"], momentum_rationale),
            Factor("cultural_fit", cultural_fit, WEIGHTS["cultural_fit"],
                   cultural_fit * WEIGHTS["cultural_fit"],
                   ["archetype alignment minus co-viewing friction & CBFC risk"]),
            Factor("localization_reach", reach, WEIGHTS["localization_reach"],
                   reach * WEIGHTS["localization_reach"], reach_rationale),
            Factor("genre_fit", genre_fit, WEIGHTS["genre_fit"],
                   genre_fit * WEIGHTS["genre_fit"], genre_rationale),
        ]

        raw = sum(f.contribution for f in factors)
        score = int(round(raw))

        notes = []
        if pre_launch:
            notes.append("Unreleased title: scored on pre-launch demand + "
                         "structural features, not Indian consumption history.")
        return ScoreResult(sakura_score=score, grade=grade_for(score),
                           confidence=confidence_parts["confidence"],
                           factors=factors, tier_notes=notes)
