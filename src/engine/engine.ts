/**
 * sakura-abm (TypeScript port) — deterministic agent-based audience simulation.
 *
 * Port of src/sakurascore_sim/adapters/abm_engine.py. Line-for-line fidelity
 * matters: the RNG stream consumption order (graph → population → per-round,
 * per-agent, five fixed draw slots) must match the Python engine exactly so
 * paired-seed results are bit-comparable. Engine version stays 0.1.0 while
 * parity holds (tested against tests/fixtures/python_output.json).
 */

import { MT19937 } from "./mt19937.ts";
import { RUNTIME_LABEL } from "../runtime.ts";
import type { AudienceSegment, Scenario, SimulationInput } from "./types.ts";

export const ENGINE_NAME = "sakura-abm";
export const ENGINE_VERSION = "0.1.0";

export const ACTIONS = ["discover", "view_info", "express_interest", "share", "discuss", "ignore"] as const;

// Language-fit modulation constants (documented assumptions):
const LANG_MOD_DISCOVERY_INTERCEPT = 0.7; // discovery factor = 0.7 + 0.3 * lang_fit
const LANG_MOD_INTEREST_FLOOR = 0.25; // hard floor when no offered language fits
const ORIGINAL_LANGS = ["ja", "en"];

interface Agent {
  agent_id: number;
  segment_id: string;
  primary_language: string;
  language_affinity: Record<string, number>;
  susceptibility: number;
  vocalness: number;
  neighbors: number[];
  aware: boolean;
  engaged: boolean;
  viewed: boolean;
}

export function round6(x: number): number {
  // python round(x, 6) equivalent at the precision we care about
  return Math.round((x + Number.EPSILON * Math.sign(x)) * 1e6) / 1e6;
}

/** Deterministic Barabasi-Albert preferential-attachment graph (stdlib port). */
export function buildBarabasiAlbert(n: number, m: number, rng: MT19937): number[][] {
  if (m < 1 || n < 2) return Array.from({ length: n }, () => []);
  m = Math.min(m, n - 1);
  const adjacency: number[][] = Array.from({ length: n }, () => []);
  const repeatedTargets: number[] = [0, 1];
  // seed initial star among first m+1 nodes
  for (let newv = 1; newv < Math.min(m + 1, n); newv++) {
    adjacency[newv].push(0);
    adjacency[0].push(newv);
    repeatedTargets.push(newv, 0);
  }
  for (let newv = m + 1; newv < n; newv++) {
    const chosen = new Set<number>();
    let guard = 0;
    while (chosen.size < m && guard < 100 * m) {
      guard++;
      const candidate = repeatedTargets[rng.randrange(repeatedTargets.length)];
      if (candidate !== newv && !chosen.has(candidate)) chosen.add(candidate);
    }
    for (const target of [...chosen].sort((a, b) => a - b)) {
      adjacency[newv].push(target);
      adjacency[target].push(newv);
      repeatedTargets.push(newv, target);
    }
  }
  return adjacency;
}

/** Draw the agent population in a FIXED order (identical across scenarios sharing a seed). */
export function buildPopulation(parsed: SimulationInput, rng: MT19937): Agent[] {
  const segments = parsed.audience_segments;
  const cumulative: { threshold: number; seg: AudienceSegment }[] = [];
  let acc = 0.0;
  for (const seg of segments) {
    acc += seg.size_share;
    cumulative.push({ threshold: acc, seg });
  }

  const agents: Agent[] = [];
  for (let agentId = 0; agentId < parsed.simulation.agent_count; agentId++) {
    const uSeg = rng.random();
    let chosen = cumulative[cumulative.length - 1].seg;
    for (const { threshold, seg } of cumulative) {
      if (uSeg <= threshold) {
        chosen = seg;
        break;
      }
    }
    // primary language: single draw over normalized affinity weights
    const codes = Object.keys(chosen.language_affinity);
    const weights = codes.map((c) => Math.max(0.0, Number(chosen.language_affinity[c])));
    const totalW = weights.reduce((a, b) => a + b, 0);
    let primary: string;
    if (totalW <= 0) {
      primary = codes[0];
    } else {
      const uLang = rng.random() * totalW;
      let accW = 0.0;
      primary = codes[codes.length - 1];
      for (let i = 0; i < codes.length; i++) {
        accW += weights[i];
        if (uLang <= accW) {
          primary = codes[i];
          break;
        }
      }
    }
    const susceptibility = 0.7 + 0.6 * rng.random(); // U(0.7, 1.3)
    const vocalness = 0.75 + 0.5 * rng.random(); // U(0.75, 1.25)
    agents.push({
      agent_id: agentId,
      segment_id: chosen.id,
      primary_language: primary,
      language_affinity: { ...chosen.language_affinity },
      susceptibility,
      vocalness,
      neighbors: [],
      aware: false,
      engaged: false,
      viewed: false,
    });
  }
  return agents;
}

function languageFit(agent: Agent, scenario: Scenario): number {
  const offered = new Set(scenario.languages_available);
  let best = 0.0;
  for (const code of offered) {
    best = Math.max(best, agent.language_affinity[code] ?? 0.0);
  }
  if (best > 0.0) return best;
  if (offered.has("en")) return Math.max(best, agent.language_affinity["en"] ?? 0.0);
  return LANG_MOD_INTEREST_FLOOR;
}

function segPopulation(agents: Agent[], sid: string): number {
  return agents.reduce((n, a) => n + (a.segment_id === sid ? 1 : 0), 0);
}

/** Run one scenario once with one seed. RNG order: graph → population → fixed draw slots.
 *  includeAgents: attach the per-agent roster (head-line seed only; additive field, never changes the stream). */
export function runScenario(parsed: SimulationInput, scenario: Scenario, seed: number, includeAgents = false) {
  const sim = parsed.simulation;
  const rng = new MT19937(seed);
  const t0 = performance.now();

  const graph = buildBarabasiAlbert(sim.agent_count, sim.network_degree, rng);
  const agents = buildPopulation(parsed, rng);
  agents.forEach((a, i) => (a.neighbors = graph[i]));
  const segById = new Map(parsed.audience_segments.map((s) => [s.id, s]));

  type RoundRecord = {
    round_index: number;
    counts: Record<string, number>;
    cumulative_aware: number;
    cumulative_engaged: number;
    cumulative_viewed: number;
    wom_exposure: number;
  };
  const roundRecords: RoundRecord[] = [];
  let totalShares = 0;
  let totalDiscussions = 0;
  const perSegment: Record<string, { reach: number; engaged: number }> = {};
  for (const s of parsed.audience_segments) perSegment[s.id] = { reach: 0, engaged: 0 };
  const perLanguage: Record<string, { reach: number; engaged: number }> = {};

  for (let roundIndex = 0; roundIndex < sim.rounds; roundIndex++) {
    const counts: Record<string, number> = {};
    for (const a of ACTIONS) counts[a] = 0;

    for (const agent of agents) {
      const seg = segById.get(agent.segment_id)!;
      // --- fixed draw slots (unconditional, stream-aligned) ---
      const uDiscover = rng.random();
      const uView = rng.random();
      const uInterest = rng.random();
      const uShare = rng.random();
      const uDiscuss = rng.random();

      const langFit = languageFit(agent, scenario);
      const regionalLift =
        scenario.languages_available.includes(agent.primary_language) &&
        !ORIGINAL_LANGS.includes(agent.primary_language)
          ? sim.dub_lift
          : 1.0;
      const langModDisc = LANG_MOD_DISCOVERY_INTERCEPT + (1.0 - LANG_MOD_DISCOVERY_INTERCEPT) * langFit;

      let womExposure = 0.0;
      if (agent.neighbors.length) {
        let engagedNeighbors = 0;
        for (const nb of agent.neighbors) if (agents[nb].engaged) engagedNeighbors++;
        womExposure = engagedNeighbors / agent.neighbors.length;
      }
      const womMod = 1.0 + sim.word_of_mouth_boost * womExposure;
      const announcement = roundIndex === 0 ? sim.announcement_boost : 1.0;

      let acted = false;
      if (!agent.aware) {
        const mults = scenario.marketing_reach;
        const aff = seg.channel_affinity;
        let weightSum = 0;
        let mixNum = 0;
        for (const c of Object.keys(mults)) {
          weightSum += aff[c] ?? 0.0;
          mixNum += (aff[c] ?? 0.0) * mults[c];
        }
        const mix = weightSum > 0 ? mixNum / weightSum : Object.values(mults).reduce((a, b) => a + b, 0) / Object.keys(mults).length;
        const pDiscover = Math.min(
          sim.discovery_cap,
          seg.discovery_base * mix * langModDisc * womMod * agent.susceptibility * announcement,
        );
        if (uDiscover < pDiscover) {
          agent.aware = true;
          counts["discover"]++;
          acted = true;
        }
      }

      if (agent.aware && !agent.viewed && !agent.engaged) {
        const pView = Math.min(1.0, seg.view_info_prob * langModDisc * agent.susceptibility);
        if (uView < pView) {
          agent.viewed = true;
          counts["view_info"]++;
          acted = true;
        }
      }

      if (agent.aware && agent.viewed && !agent.engaged) {
        const pInterest = Math.min(
          1.0,
          seg.base_interest *
            (LANG_MOD_INTEREST_FLOOR + (1.0 - LANG_MOD_INTEREST_FLOOR) * langFit) *
            regionalLift *
            agent.susceptibility,
        );
        if (uInterest < pInterest) {
          agent.engaged = true;
          counts["express_interest"]++;
          acted = true;
        }
      }

      if (agent.engaged) {
        const pShare = Math.min(1.0, seg.share_prob * agent.vocalness * (0.85 + 0.15 * langFit) * regionalLift);
        const pDiscuss = Math.min(1.0, seg.discuss_prob * agent.vocalness * (0.85 + 0.15 * langFit) * regionalLift);
        if (uShare < pShare) {
          counts["share"]++;
          totalShares++;
          acted = true;
        }
        if (uDiscuss < pDiscuss) {
          counts["discuss"]++;
          totalDiscussions++;
          acted = true;
        }
      }

      if (!acted) counts["ignore"]++;
    }

    const cumAware = agents.reduce((n, a) => n + (a.aware ? 1 : 0), 0);
    const cumEngaged = agents.reduce((n, a) => n + (a.engaged ? 1 : 0), 0);
    const cumViewed = agents.reduce((n, a) => n + (a.viewed ? 1 : 0), 0);
    let womSum = 0.0;
    for (const a of agents) {
      if (a.neighbors.length) {
        let engagedNeighbors = 0;
        for (const nb of a.neighbors) if (agents[nb].engaged) engagedNeighbors++;
        womSum += engagedNeighbors / a.neighbors.length;
      }
    }
    roundRecords.push({
      round_index: roundIndex,
      counts,
      cumulative_aware: cumAware,
      cumulative_engaged: cumEngaged,
      cumulative_viewed: cumViewed,
      wom_exposure: womSum / Math.max(1, agents.length),
    });
  }

  const n = sim.agent_count;
  for (const a of agents) {
    perSegment[a.segment_id].reach += a.aware ? 1 : 0;
    perSegment[a.segment_id].engaged += a.engaged ? 1 : 0;
    const bucket = (perLanguage[a.primary_language] ??= { reach: 0, engaged: 0 });
    bucket.reach += a.aware ? 1 : 0;
    bucket.engaged += a.engaged ? 1 : 0;
  }

  const durationMs = Math.round(performance.now() - t0);
  const perSegmentOut: Record<string, unknown> = {};
  for (const [sid, pop] of Object.entries(perSegment)) {
    const p = segPopulation(agents, sid);
    perSegmentOut[sid] = {
      population: p,
      reach: pop.reach,
      engaged: pop.engaged,
      reach_rate: round6(pop.reach / Math.max(1, p)),
      engagement_rate: round6(pop.engaged / Math.max(1, p)),
    };
  }
  const perLanguageOut: Record<string, unknown> = {};
  for (const lang of Object.keys(perLanguage).sort()) {
    const vals = perLanguage[lang];
    perLanguageOut[lang] = {
      reach: vals.reach,
      engaged: vals.engaged,
      engagement_rate: round6(vals.engaged / Math.max(1, vals.reach)),
    };
  }

  const out: Record<string, any> = {
    totals: {
      reach: roundRecords[roundRecords.length - 1].cumulative_aware,
      reach_rate: round6(roundRecords[roundRecords.length - 1].cumulative_aware / n),
      viewed: roundRecords[roundRecords.length - 1].cumulative_viewed,
      view_rate: round6(roundRecords[roundRecords.length - 1].cumulative_viewed / n),
      engaged: roundRecords[roundRecords.length - 1].cumulative_engaged,
      engagement_rate: round6(roundRecords[roundRecords.length - 1].cumulative_engaged / n),
      shares_total: totalShares,
      discussions_total: totalDiscussions,
      shares_per_agent: round6(totalShares / n),
    },
    per_round: roundRecords.map((rec) => ({
      round: rec.round_index,
      actions: { ...rec.counts },
      cumulative_aware: rec.cumulative_aware,
      cumulative_viewed: rec.cumulative_viewed,
      cumulative_engaged: rec.cumulative_engaged,
      avg_wom_exposure: round6(rec.wom_exposure),
    })),
    per_segment: perSegmentOut,
    per_language: perLanguageOut,
    graph: {
      nodes: sim.agent_count,
      edges: agents.reduce((s, a) => s + a.neighbors.length, 0) / 2,
      degree_m: sim.network_degree,
    },
    duration_ms: durationMs,
  };
  if (includeAgents) {
    out.agents = agents.map((a) => ({
      agent_id: a.agent_id,
      segment_id: a.segment_id,
      primary_language: a.primary_language,
      susceptibility: Math.round(a.susceptibility * 1000) / 1000,
      vocalness: Math.round(a.vocalness * 1000) / 1000,
      aware: a.aware,
      viewed: a.viewed,
      engaged: a.engaged,
      neighbors: a.neighbors.length,
    }));
  }
  return out;
}

export function engineMetadata() {
  return {
    engine: ENGINE_NAME,
    engine_version: ENGINE_VERSION,
    rng: "MT19937 (CPython-compatible, single stream, fixed consumption order)",
    python_version: RUNTIME_LABEL,
    platform: `${process.platform}-${process.arch}`,
    dependencies: "bun-runtime, zero npm dependencies",
    agent_model: "stochastic-threshold actors with segment parameters (NOT LLM personas)",
    paired_design: true,
  };
}
