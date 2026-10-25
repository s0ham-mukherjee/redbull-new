"""Cultural compatibility engine — Indian archetypes, CBFC risk, co-viewing.

Rule-based but fully transparent: every score carries the triggers that
produced it, so the dashboard can explain *why* a title fits or doesn't.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --- CBFC mapping -----------------------------------------------------------
# Central Board of Film Certification categories used as estimates:
#   U (all ages), U/A 7+, U/A 13+, U/A 16+, A (adults only)

ADULT_GENRES = {"Hentai", "Erotica", "Ecchi"}
ADULT_TAGS = {"Nudity", "Sexual Violence", "Explicit Sex"}

HIGH_RISK_TAGS = {
    "Gore": "graphic gore",
    "Body Horror": "body horror",
    "Graphic Violence": "graphic violence",
    "Cannibalism": "cannibalism",
    "Cultured Violence": "cultured violence",
}
MODERATE_RISK_TAGS = {
    "Violence": "violence",
    "War": "war themes",
    "Suicide": "suicide themes",
    "Self-Harm": "self-harm",
    "Drugs": "drug use",
    "Alcohol": "alcohol use",
    "Tobacco Use": "tobacco use",
    "Child Abuse": "child abuse",
    "Death": "death themes",
    "Tragedy": "tragedy",
}
MILD_RISK_GENRES = {"Horror", "Thriller", "Psychological"}

# Tags/genres that create family co-viewing friction (parents + kids watching).
COVIEW_FRICTION_TAGS = {
    "Gore": 30, "Body Horror": 28, "Graphic Violence": 25, "Nudity": 40,
    "Sexual Violence": 60, "Explicit Sex": 60, "Ecchi": 35, "Cannibalism": 30,
    "Suicide": 35, "Self-Harm": 25, "Drugs": 25, "Alcohol": 12,
    "Tobacco Use": 10, "Profanity": 15, "Child Abuse": 30, "Violence": 12,
    "Horror": 18,
}
COVIEW_FRICTION_GENRES = {"Horror": 15, "Ecchi": 35, "Erotica": 60,
                          "Hentai": 80, "Psychological": 8, "Thriller": 8}

# --- Cultural archetypes ----------------------------------------------------
# Archetype: (description, matching genres, matching tags)
ARCHETYPES = {
    "dharma_duty": {
        "label": "Dharma & Duty (धर्म/कर्तव्य)",
        "desc": "duty-before-self, honour, sacrifice, righteous struggle",
        "genres": {"Action", "Drama", "War"},
        "tags": {"Duty", "Honour", "Sacrifice", "Justice", "War", "Loyalty",
                 "Tragedy", "Vengeance"},
    },
    "guru_shishya": {
        "label": "Guru–Shishya Parampara (गुरु-शिष्य)",
        "desc": "mentor-disciple bonds, training arcs, mastering a craft",
        "genres": {"Sports", "Action", "Adventure"},
        "tags": {"Mentor", "Training", "Coming of Age", "Martial Arts",
                 "School", "Discipline"},
    },
    "parivaar": {
        "label": "Parivaar & Family (परिवार)",
        "desc": "family bonds, found-family, nakama camaraderie",
        "genres": {"Slice of Life", "Comedy", "Kids", "Drama"},
        "tags": {"Family", "Parenthood", "Friendship", "Teamwork",
                 "Found Family", "Iyashikei"},
    },
    "sahavas": {
        "label": "Sahavas / Community (सहवास)",
        "desc": "community celebration, festivals, collective joy",
        "genres": {"Comedy", "Music", "Slice of Life"},
        "tags": {"Festival", "Music", "School", "Friendship", "Culinary"},
    },
}

# Regional affinity deltas by genre (documented heuristics from Indian
# anime-fandom distribution: theatrical South, mass dub Hindi belt,
# premium metros West, high per-capita affinity Northeast).
REGION_GENRE_DELTAS = {
    "Sports": {"Southern Fortress": 8, "Western Metros": 4},
    "Mecha": {"Southern Fortress": 6, "Western Metros": 8},
    "Psychological": {"Western Metros": 6, "Southern Fortress": 3},
    "Slice of Life": {"Hindi Belt": -6},
    "Iyashikei": {"Hindi Belt": -5},
    "Kids": {"Hindi Belt": 14, "Eastern Hub": 5},
    "Ecchi": {"Hindi Belt": -12, "Southern Fortress": -8},
    "Isekai": {"Southern Fortress": 3},
    "Music": {"Western Metros": 5},
    "Horror": {"Hindi Belt": 5, "Eastern Hub": 6},
}


@dataclass
class CulturalProfile:
    archetype_alignment: dict            # archetype_id -> {score, label, why}
    cultural_distance_flags: list
    cbfc_rating_estimate: str
    cbfc_notes: list
    sensitivity_triggers: list
    family_co_viewing_friction: int      # 0-100 (higher = more friction)
    regional_variation: dict             # hub -> delta points with reason
    overall_cultural_fit: int            # 0-100


class CulturalCompatibilityEngine:
    """Scores how a Japanese title's themes land across Indian cultural
    archetypes, estimates CBFC classification risk, and quantifies family
    co-viewing friction (the #1 gatekeeper for Hindi-belt mass reach)."""

    def evaluate(self, *, genres: list[str], tags: list[tuple[str, int]],
                 is_adult: bool, format: str = "", episodes=None) -> CulturalProfile:
        genres = genres or []
        tag_names = [t for t, _ in (tags or [])]
        tag_ranks = {t: r for t, r in (tags or [])}
        text_tokens = {g.lower() for g in genres} | {t.lower() for t in tag_names}

        # --- archetypes -----------------------------------------------------
        alignment = {}
        for aid, spec in ARCHETYPES.items():
            g_hits = [g for g in spec["genres"] if g in genres]
            t_hits = [t for t in tag_names if t in spec["tags"]]
            # base 35; +18 per genre hit (max 2), +12 per tag hit (max 3)
            score = 35 + 18 * min(len(g_hits), 2) + 12 * min(len(t_hits), 3)
            why = []
            if g_hits:
                why.append(f"genres: {', '.join(g_hits)}")
            if t_hits:
                why.append(f"themes: {', '.join(t_hits)}")
            alignment[aid] = {
                "score": min(score, 100), "label": spec["label"],
                "desc": spec["desc"], "why": why or ["no direct thematic match"],
            }

        # --- sensitivity triggers + CBFC ------------------------------------
        triggers: list[str] = []
        notes: list[str] = []
        rating = "U/A 13+"

        # Tag-based triggers are rank-aware: AniList tags carry a 0-100 rank
        # of how strongly they apply; a low-rank "Nudity" tag must not mean
        # an adults-only certification.
        adult_hits = ([g for g in genres if g in ADULT_GENRES]
                      + [t for t in tag_names
                         if t in ADULT_TAGS and tag_ranks.get(t, 50) >= 55])
        if is_adult or adult_hits:
            rating = "A (Adults Only)"
            triggers.append("adult/sexual content — direct CBFC 'A' territory")
            notes.append("Adult certification blocks TV broadcast and family "
                         "co-viewing entirely; streaming-only adult lane.")
        else:
            high = [HIGH_RISK_TAGS[t] for t in tag_names
                    if t in HIGH_RISK_TAGS and tag_ranks.get(t, 50) >= 45]
            if high:
                triggers.extend(high)
                rating = "A risk / U/A 16+"
                notes.append("High-intensity content likely needs edits/cuts for "
                             "an 'U/A' certificate; theatrical 'A' caps screen count.")
            else:
                mod = [MODERATE_RISK_TAGS[t] for t in tag_names
                       if t in MODERATE_RISK_TAGS and tag_ranks.get(t, 50) >= 35]
                if mod:
                    triggers.extend(mod)
                    rating = "U/A 13+"
                    notes.append("Moderate themes typically pass with an U/A 13+; "
                                 "occasional edits for TV broadcast versions.")
                else:
                    rating = "U" if {"Kids", "Slice of Life", "Comedy"} & set(genres) \
                        else "U/A 7+"
                    notes.append("No strong censor triggers detected; "
                                 "family-friendly certification likely.")
            mild = [g for g in genres if g in MILD_RISK_GENRES]
            if mild and rating not in ("A (Adults Only)", "A risk / U/A 16+"):
                triggers.extend(f"{g} themes" for g in mild)
                if rating == "U":
                    rating = "U/A 7+"
                    notes.append("Horror/thriller undertones push past clean 'U'.")

        if "Religion" in tag_names or "Mythology" in tag_names:
            triggers.append("religious/mythological imagery — review for "
                            "community-sensitivity edits")
            notes.append("Religious imagery is generally well received when "
                         "respectful (fits devotional traditions), but review "
                         "before broadcast in the Hindi belt.")

        # --- family co-viewing friction -------------------------------------
        friction = 0
        for t in tag_names:
            friction = min(100, friction + COVIEW_FRICTION_TAGS.get(t, 0)
                           * (1 if tag_ranks.get(t, 50) >= 50 else 0.5))
        for g in genres:
            friction = min(100, friction + COVIEW_FRICTION_GENRES.get(g, 0))
        if format == "MOVIE" and friction < 20:
            friction = max(0, friction - 5)  # films are single-sitting, less drift
        friction = int(friction)

        # --- regional variation ----------------------------------------------
        regional = {}
        for g in genres:
            for hub, delta in REGION_GENRE_DELTAS.get(g, {}).items():
                regional[hub] = regional.get(hub, 0) + delta
        regional = {k: v for k, v in regional.items() if v != 0}

        # --- flags + overall fit ----------------------------------------------
        flags = []
        if rating.startswith("A"):
            flags.append("certification restricts broadcast & co-viewing")
        if friction >= 40:
            flags.append("high family co-viewing friction for the Hindi belt")
        if "Ecchi" in genres:
            flags.append("ecchi content complicates localization pitch")

        top_arch = max(alignment.items(), key=lambda kv: kv[1]["score"])
        overall = int(
            0.45 * top_arch[1]["score"]
            + 0.25 * (100 - friction)
            + 0.15 * (0 if rating.startswith("A") else 70 if rating == "U/A 13+" else 85)
            + 0.15 * (50 + max([abs(v) for v in regional.values()], default=0)
                      * (1 if any(v > 0 for v in regional.values()) else -1))
        )
        overall = max(0, min(100, overall))

        return CulturalProfile(
            archetype_alignment=alignment,
            cultural_distance_flags=flags,
            cbfc_rating_estimate=rating,
            cbfc_notes=notes,
            sensitivity_triggers=sorted(set(triggers)),
            family_co_viewing_friction=friction,
            regional_variation=regional,
            overall_cultural_fit=overall,
        )
