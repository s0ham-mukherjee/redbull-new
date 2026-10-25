"""sakura-abm — the deterministic agent-based audience simulation engine.

DESIGN PRINCIPLES
-----------------
1. Determinism: a single ``random.Random(seed)`` stream is consumed in a FIXED
   order (graph build -> agent population -> per-round, per-agent, fixed draw
   slots). Two scenarios run with the same seed therefore consume identical
   random draws; only the acceptance thresholds differ. This "stream-aligned
   threshold" design gives paired-comparison validity: if scenario B's parameter
   set dominates scenario A's (language superset, lift >= 1), then B's action
   sets are a strict superset of A's at every round — a testable invariant.

2. Zero dependencies: pure Python 3 stdlib. No LLM calls, no network I/O,
   no databases. Runs in milliseconds.

3. Explicit assumptions: every behavioural constant is a named, documented
   parameter surfaced in the result's ``assumptions`` block. Nothing is hidden.

SIMPLIFICATION NOTICE (important for honest reporting)
------------------------------------------------------
This is a *compact scenario model*: agents are stochastic-threshold actors with
aggregate segment parameters, NOT LLM personas with open-ended behaviour like
OASIS/MiroFish agents. It cannot produce dialogue, novel ideas or emergent
discourse. Its value is reproducibility, controllability and speed for A/B
release-strategy screening. See docs/SIMULATION_METHODOLOGY.md and LIMITATIONS.
"""

from __future__ import annotations

import platform as py_platform
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from ..models import AudienceSegment, Scenario, SimulationInput

ENGINE_NAME = "sakura-abm"
ENGINE_VERSION = "0.1.0"

ACTIONS = ("discover", "view_info", "express_interest", "share", "discuss", "ignore")

# Language-fit modulation constants (documented assumptions, see methodology doc):
LANG_MOD_DISCOVERY_INTERCEPT = 0.7   # discovery factor = 0.7 + 0.3 * lang_fit
LANG_MOD_INTEREST_FLOOR = 0.25       # hard floor when no offered language fits (subs tolerance)
ORIGINAL_LANGS = ("ja", "en")


@dataclass
class _Agent:
    agent_id: int
    segment_id: str
    primary_language: str
    language_affinity: Dict[str, float]
    susceptibility: float            # personal discovery multiplier  (0.7 .. 1.3)
    vocalness: float                 # personal share/discuss multiplier (0.75 .. 1.25)
    neighbors: List[int] = field(default_factory=list)
    aware: bool = False
    engaged: bool = False
    viewed: bool = False


@dataclass
class _RoundRecord:
    round_index: int
    counts: Dict[str, int]
    cumulative_aware: int
    cumulative_engaged: int
    cumulative_viewed: int
    wom_exposure: float


def build_barabasi_albert(n: int, m: int, rng: random.Random) -> List[List[int]]:
    """Deterministic Barabasi-Albert preferential-attachment graph (pure stdlib).

    Determinism notes: insertion order 0..n-1; new node i attaches to m distinct
    earlier nodes chosen by repeated-rejection sampling from the degree-weighted
    pool using ``rng.randrange``. Ties resolve by insertion order, so the same
    seed always yields the same graph.
    """
    if m < 1 or n < 2:
        return [[] for _ in range(n)]
    m = min(m, n - 1)
    adjacency: List[List[int]] = [[] for _ in range(n)]
    repeated_targets: List[int] = [0, 1] if n > 1 else [0]
    # seed initial star among first m+1 nodes
    for new in range(1, min(m + 1, n)):
        adjacency[new].append(0)
        adjacency[0].append(new)
        repeated_targets.extend([new, 0])

    for new in range(m + 1, n):
        chosen: List[int] = set()
        guard = 0
        while len(chosen) < m and guard < 100 * m:
            guard += 1
            candidate = repeated_targets[rng.randrange(len(repeated_targets))]
            if candidate != new and candidate not in chosen:
                chosen.add(candidate)
        for target in sorted(chosen):
            adjacency[new].append(target)
            adjacency[target].append(new)
            repeated_targets.extend([new, target])
    return adjacency


def build_population(parsed: SimulationInput, rng: random.Random) -> List[_Agent]:
    """Draw the agent population in a FIXED order (identical across scenarios
    sharing the same seed — the basis of the paired design)."""
    segments = parsed.audience_segments
    # cumulative distribution over segments (insertion order = deterministic)
    cumulative: List[Tuple[float, AudienceSegment]] = []
    acc = 0.0
    for seg in segments:
        acc += seg.size_share
        cumulative.append((acc, seg))

    agents: List[_Agent] = []
    for agent_id in range(parsed.simulation.agent_count):
        u_seg = rng.random()
        chosen = cumulative[-1][1]
        for threshold, seg in cumulative:
            if u_seg <= threshold:
                chosen = seg
                break
        # primary language: single draw over normalized affinity weights
        codes = list(chosen.language_affinity.keys())          # dict order = input order (deterministic)
        weights = [max(0.0, float(chosen.language_affinity[c])) for c in codes]
        total_w = sum(weights)
        if total_w <= 0:
            primary = codes[0]
        else:
            u_lang = rng.random() * total_w
            acc_w = 0.0
            primary = codes[-1]
            for code, w in zip(codes, weights):
                acc_w += w
                if u_lang <= acc_w:
                    primary = code
                    break
        susceptibility = 0.7 + 0.6 * rng.random()      # U(0.7, 1.3)
        vocalness = 0.75 + 0.5 * rng.random()          # U(0.75, 1.25)
        agents.append(_Agent(
            agent_id=agent_id,
            segment_id=chosen.id,
            primary_language=primary,
            language_affinity=dict(chosen.language_affinity),
            susceptibility=susceptibility,
            vocalness=vocalness,
        ))
    return agents


def _language_fit(agent: _Agent, scenario: Scenario) -> float:
    """Agent's best affinity across the languages offered by the scenario.

    Agents whose primary language is not offered fall back to their English
    affinity (sub-tolerance), and if English is not offered either, to a hard
    floor (LANG_MOD_INTEREST_FLOOR) representing subtitle tolerance.
    """
    offered = set(scenario.languages_available)
    best = 0.0
    for code in offered:
        best = max(best, float(agent.language_affinity.get(code, 0.0)))
    if best > 0.0:
        return best
    if "en" in offered:
        return max(best, float(agent.language_affinity.get("en", 0.0)))
    return LANG_MOD_INTEREST_FLOOR


def run_scenario(parsed: SimulationInput, scenario: Scenario, seed: int) -> Dict[str, Any]:
    """Run one scenario once with one seed. Returns scenario metrics.

    RNG consumption order (must never change without bumping engine version):
      1. graph construction (build_barabasi_albert)
      2. population draw (build_population)
      3. per round, per agent (agent_id ascending): five uniform draws in fixed
         slots [discover, view, interest, share, discuss] — drawn unconditionally
         so the stream stays aligned across scenarios.
    """
    sim = parsed.simulation
    rng = random.Random(seed)
    t0 = time.perf_counter()

    graph = build_barabasi_albert(sim.agent_count, sim.network_degree, rng)
    agents = build_population(parsed, rng)
    for agent, neighbors in zip(agents, graph):
        agent.neighbors = neighbors
    seg_by_id = {s.id: s for s in parsed.audience_segments}

    round_records: List[_RoundRecord] = []
    total_shares = 0
    total_discussions = 0
    per_segment: Dict[str, Dict[str, int]] = {
        s.id: {"reach": 0, "engaged": 0} for s in parsed.audience_segments
    }
    per_language: Dict[str, Dict[str, int]] = {}

    for round_index in range(sim.rounds):
        counts = {a: 0 for a in ACTIONS}
        newly_engaged_agents: List[int] = []

        for agent in agents:
            seg = seg_by_id[agent.segment_id]
            # --- fixed draw slots (unconditional) ---
            u_discover = rng.random()
            u_view = rng.random()
            u_interest = rng.random()
            u_share = rng.random()
            u_discuss = rng.random()

            lang_fit = _language_fit(agent, scenario)
            regional_lift = (sim.dub_lift
                             if (agent.primary_language in scenario.languages_available
                                 and agent.primary_language not in ORIGINAL_LANGS)
                             else 1.0)
            lang_mod_disc = LANG_MOD_DISCOVERY_INTERCEPT + (1.0 - LANG_MOD_DISCOVERY_INTERCEPT) * lang_fit

            wom_exposure = 0.0
            if agent.neighbors:
                engaged_neighbors = sum(1 for nb in agent.neighbors if agents[nb].engaged)
                wom_exposure = engaged_neighbors / len(agent.neighbors)
            wom_mod = 1.0 + sim.word_of_mouth_boost * wom_exposure
            announcement = sim.announcement_boost if round_index == 0 else 1.0

            acted = False
            if not agent.aware:
                # channel-weighted marketing multiplier for this agent's segment
                mults = scenario.marketing_reach
                aff = seg.channel_affinity
                weight_sum = sum(aff.get(c, 0.0) for c in mults)
                if weight_sum > 0:
                    mix = sum(aff.get(c, 0.0) * mults[c] for c in mults) / weight_sum
                else:
                    mix = sum(mults.values()) / len(mults)
                p_discover = min(sim.discovery_cap,
                                 seg.discovery_base * mix * lang_mod_disc * wom_mod
                                 * agent.susceptibility * announcement)
                if u_discover < p_discover:
                    agent.aware = True
                    counts["discover"] += 1
                    acted = True

            if agent.aware and not agent.viewed and not agent.engaged:
                p_view = min(1.0, seg.view_info_prob * lang_mod_disc * agent.susceptibility)
                if u_view < p_view:
                    agent.viewed = True
                    counts["view_info"] += 1
                    acted = True

            if agent.aware and agent.viewed and not agent.engaged:
                p_interest = min(1.0, seg.base_interest * (LANG_MOD_INTEREST_FLOOR
                                                            + (1.0 - LANG_MOD_INTEREST_FLOOR) * lang_fit)
                                 * regional_lift * agent.susceptibility)
                if u_interest < p_interest:
                    agent.engaged = True
                    counts["express_interest"] += 1
                    newly_engaged_agents.append(agent.agent_id)
                    acted = True

            if agent.engaged:
                p_share = min(1.0, seg.share_prob * agent.vocalness
                              * (0.85 + 0.15 * lang_fit) * regional_lift)
                p_discuss = min(1.0, seg.discuss_prob * agent.vocalness
                                * (0.85 + 0.15 * lang_fit) * regional_lift)
                if u_share < p_share:
                    counts["share"] += 1
                    total_shares += 1
                    acted = True
                if u_discuss < p_discuss:
                    counts["discuss"] += 1
                    total_discussions += 1
                    acted = True

            if not acted:
                counts["ignore"] += 1

        cum_aware = sum(1 for a in agents if a.aware)
        cum_engaged = sum(1 for a in agents if a.engaged)
        cum_viewed = sum(1 for a in agents if a.viewed)
        round_records.append(_RoundRecord(
            round_index=round_index, counts=counts,
            cumulative_aware=cum_aware, cumulative_engaged=cum_engaged,
            cumulative_viewed=cum_viewed,
            wom_exposure=(sum(
                (sum(1 for nb in a.neighbors if agents[nb].engaged) / len(a.neighbors))
                if a.neighbors else 0.0 for a in agents) / max(1, len(agents))
            ),
        ))
        _ = newly_engaged_agents  # kept for future per-agent tracing

    n = sim.agent_count
    for a in agents:
        per_segment[a.segment_id]["reach"] += 1 if a.aware else 0
        per_segment[a.segment_id]["engaged"] += 1 if a.engaged else 0
        bucket = per_language.setdefault(a.primary_language, {"reach": 0, "engaged": 0})
        bucket["reach"] += 1 if a.aware else 0
        bucket["engaged"] += 1 if a.engaged else 0

    duration_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "totals": {
            "reach": cum_aware,
            "reach_rate": round(cum_aware / n, 6),
            "viewed": cum_viewed,
            "view_rate": round(cum_viewed / n, 6),
            "engaged": cum_engaged,
            "engagement_rate": round(cum_engaged / n, 6),
            "shares_total": total_shares,
            "discussions_total": total_discussions,
            "shares_per_agent": round(total_shares / n, 6),
        },
        "per_round": [
            {
                "round": rec.round_index,
                "actions": dict(rec.counts),
                "cumulative_aware": rec.cumulative_aware,
                "cumulative_viewed": rec.cumulative_viewed,
                "cumulative_engaged": rec.cumulative_engaged,
                "avg_wom_exposure": round(rec.wom_exposure, 6),
            }
            for rec in round_records
        ],
        "per_segment": {
            sid: {
                "population": _seg_population(agents, sid),
                "reach": pop["reach"],
                "engaged": pop["engaged"],
                "reach_rate": round(pop["reach"] / max(1, _seg_population(agents, sid)), 6),
                "engagement_rate": round(pop["engaged"] / max(1, _seg_population(agents, sid)), 6),
            }
            for sid, pop in per_segment.items()
        },
        "per_language": {
            lang: {
                "reach": vals["reach"],
                "engaged": vals["engaged"],
                "engagement_rate": round(vals["engaged"] / max(1, vals["reach"]), 6),
            }
            for lang, vals in sorted(per_language.items())
        },
        "graph": {"nodes": sim.agent_count, "edges": sum(len(a.neighbors) for a in agents) // 2,
                  "degree_m": sim.network_degree},
        "duration_ms": duration_ms,
    }


def _seg_population(agents: List[_Agent], sid: str) -> int:
    """Actual population drawn into a segment (may deviate slightly from
    size_share * N due to sampling)."""
    return sum(1 for a in agents if a.segment_id == sid)


def engine_metadata() -> Dict[str, Any]:
    return {
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "rng": "python.random.MersenneTwister (single stream, fixed consumption order)",
        "python_version": sys.version.split()[0],
        "platform": py_platform.platform(),
        "dependencies": "stdlib-only",
        "agent_model": "stochastic-threshold actors with segment parameters (NOT LLM personas)",
        "paired_design": True,
    }
