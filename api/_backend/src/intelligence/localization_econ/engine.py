"""Rupee localization economics — INR cost models, reach multipliers, break-even.

All rupee figures are *calibrated estimates* for anime localization in India
(2024-26 market), exposed as explicit, configurable assumptions so a licensing
executive can flex them. Nothing here pretends to be an audited quote.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --- Cost assumptions (INR) --------------------------------------------------
SUBS_PER_MIN_INR = 400          # subtitle translation + QC per minute
DUB_PER_EP_SERIES_INR = 16_000  # per-episode Hindi dub (cast, direction, mix)
DUB_PER_LANG_MULTIPLIER = 0.85  # 2nd/3rd dub languages run ~85% of first
DUB_MOVIE_PER_MIN_INR = 8_000   # movie dub per minute (single language)

# Reach multipliers vs subtitles-only (documented heuristic anchored on
# platform statements that dubs drive the majority of India viewing;
# 5-language campaigns ~2.2x subtitles-only per the challenge brief).
REACH_MULTIPLIERS = {
    "subtitles_only": 1.0,
    "hindi_dub": 1.55,
    "three_language": 1.85,
    "five_language": 2.2,
}
MODE_LANGUAGES = {
    "subtitles_only": ["all languages (subtitles)"],
    "hindi_dub": ["Hindi"],
    "three_language": ["Hindi", "Tamil", "Telugu"],
    "five_language": ["Hindi", "Tamil", "Telugu", "Bengali", "Marathi"],
}

# Revenue assumptions (INR, net to licensor)
NET_REVENUE_PER_STREAM_VIEW_INR = 0.90   # blended sub+ad yield per long-form view
NET_TICKET_INR = 170                     # avg net ticket share per theatrical seat


@dataclass
class LocalizationPlan:
    mode: str
    languages: list
    cost_inr: int
    reach_multiplier: float
    cost_per_reach_unit: float        # INR per 1k reachable views


@dataclass
class LocalizationEconomics:
    content_type: str                 # 'series' | 'movie'
    episodes: int
    minutes_per_ep: int
    total_minutes: int
    plans: list                       # list[LocalizationPlan]
    recommended_mode: str
    recommended_plan: LocalizationPlan
    break_even_views: int | None      # streaming break-even (views)
    break_even_tickets: int | None    # theatrical break-even (tickets)
    payback_months: int | None
    assumptions: list = field(default_factory=list)


def _inr(n: float) -> int:
    return int(round(n))


def _fmt_lakh(inr: int) -> str:
    """Format INR in lakh/crore (Indian numbering)."""
    if inr >= 1_00_00_000:
        return f"₹{inr / 1_00_00_000:.2f} Cr"
    if inr >= 1_00_000:
        return f"₹{inr / 1_00_000:.1f} L"
    return f"₹{inr:,.0f}"


class LocalizationEconomicsEngine:
    """Estimates rupee localization costs, reach expansion, and break-even
    units for a title under four localization strategies."""

    def evaluate(self, *, sakura_score: int, format: str = "TV",
                 episodes=None, duration_min=None) -> LocalizationEconomics:
        is_movie = (format or "").upper() == "MOVIE"
        if is_movie:
            minutes_per_ep = duration_min or 105
            episodes = 1
        else:
            episodes = episodes or 12
            minutes_per_ep = duration_min or 24
            episodes = min(episodes, 60)  # long-runners costed per 60-ep block
        total_minutes = episodes * minutes_per_ep

        plans: list[LocalizationPlan] = []
        if is_movie:
            costs = {
                "subtitles_only": SUBS_PER_MIN_INR * total_minutes * 1.15,  # QC + versioning
                "hindi_dub": DUB_MOVIE_PER_MIN_INR * total_minutes,
                "three_language": DUB_MOVIE_PER_MIN_INR * total_minutes * (1 + 0.85 + 0.85**2),
                "five_language": DUB_MOVIE_PER_MIN_INR * total_minutes
                                 * (1 + 0.85 + 0.85**2 + 0.85**3 + 0.85**4),
            }
        else:
            subs = SUBS_PER_MIN_INR * total_minutes
            dub1 = DUB_PER_EP_SERIES_INR * episodes
            costs = {
                "subtitles_only": subs * 1.15,
                "hindi_dub": dub1 + subs,
                "three_language": dub1 * (1 + 0.85 + 0.85**2) + subs,
                "five_language": dub1 * (1 + 0.85 + 0.85**2 + 0.85**3 + 0.85**4) + subs,
            }
        for mode in ("subtitles_only", "hindi_dub", "three_language", "five_language"):
            cost = _inr(costs[mode])
            reach = REACH_MULTIPLIERS[mode]
            plans.append(LocalizationPlan(
                mode=mode, languages=MODE_LANGUAGES[mode], cost_inr=cost,
                reach_multiplier=reach,
                cost_per_reach_unit=round(cost / reach, 2),
            ))

        # Recommendation tiers: score-driven dub depth.
        if sakura_score >= 72:
            rec = "five_language"
        elif sakura_score >= 55:
            rec = "three_language"
        elif sakura_score >= 40:
            rec = "hindi_dub"
        else:
            rec = "subtitles_only"
        rec_plan = next(p for p in plans if p.mode == rec)

        # Break-even: streaming views vs theatrical tickets.
        be_views = be_tickets = None
        payback = None
        if is_movie:
            be_tickets = _inr(rec_plan.cost_inr / NET_TICKET_INR)
        else:
            be_views = _inr(rec_plan.cost_inr / NET_REVENUE_PER_STREAM_VIEW_INR)
            # Monthly view estimate by score tier (documented heuristic).
            monthly_views = {  # per-season views/month post-launch
                "five_language": 2_600_000, "three_language": 1_400_000,
                "hindi_dub": 700_000, "subtitles_only": 280_000,
            }[rec]
            payback = max(1, _inr(rec_plan.cost_inr /
                                  max(monthly_views * NET_REVENUE_PER_STREAM_VIEW_INR, 1)))

        assumptions = [
            f"subtitle cost ₹{SUBS_PER_MIN_INR}/min; series dub ₹{DUB_PER_EP_SERIES_INR:,}/ep, "
            f"movie dub ₹{DUB_MOVIE_PER_MIN_INR:,}/min; extra languages at 85% each",
            "reach multipliers vs subtitles-only: Hindi 1.55x, 3-language 1.85x, "
            "5-language 2.2x (heuristic anchored on platform dub-viewership statements)",
            f"net revenue per stream view ₹{NET_REVENUE_PER_STREAM_VIEW_INR}; "
            f"net ticket ₹{NET_TICKET_INR}",
            "costs exclude marketing/P&A and IP licensing fee",
        ]

        return LocalizationEconomics(
            content_type="movie" if is_movie else "series",
            episodes=episodes, minutes_per_ep=minutes_per_ep,
            total_minutes=total_minutes, plans=plans,
            recommended_mode=rec, recommended_plan=rec_plan,
            break_even_views=be_views, break_even_tickets=be_tickets,
            payback_months=payback, assumptions=assumptions,
        )


def format_inr(inr_amount) -> str:
    return _fmt_lakh(int(inr_amount))
