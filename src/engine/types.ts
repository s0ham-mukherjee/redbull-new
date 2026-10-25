/** Input/output contracts — mirrors src/sakurascore_sim/models.py. */

export interface EvidenceItem {
  id: string;
  title: string;
  url: string;
  publisher: string;
  date: string;
  finding: string;
  type: string;
  region: string;
  label: string; // observed | inferred (evidence itself is never "simulated")
  quality: string; // high | medium | low
  tags: string[];
  source_id?: string | null;
  retrieved_via?: string | null;
  retrieved_at?: string | null;
}

export interface AudienceSegment {
  id: string;
  label: string;
  size_share: number;
  base_interest: number;
  discovery_base: number;
  view_info_prob: number;
  share_prob: number;
  discuss_prob: number;
  language_affinity: Record<string, number>;
  channel_affinity: Record<string, number>;
  evidence_ids: string[];
  notes: string;
  hypothesis_label: string;
}

export interface Scenario {
  id: string;
  label: string;
  languages_available: string[];
  marketing_reach: Record<string, number>;
  counterfactual: boolean;
  is_baseline: boolean;
  description: string;
}

export interface SimulationParams {
  agent_count: number;
  rounds: number;
  seed: number;
  seeds: number[] | null;
  network_degree: number;
  word_of_mouth_boost: number;
  announcement_boost: number;
  dub_lift: number;
  discovery_cap: number;
  variability: boolean;
}

export interface SimulationInput {
  schema_version: string;
  ip_id: string;
  title: string;
  experiment_id: string;
  media_type: string;
  genre: string;
  evidence: EvidenceItem[];
  audience_segments: AudienceSegment[];
  scenarios: Scenario[];
  simulation: SimulationParams;
  engine: string;
  notes: string;
  options: Record<string, unknown>;
  warnings: Record<string, string>[];
}

export interface ConfigError extends Error {
  code: string;
  context?: string;
  toDict(): { code: string; message: string; context?: string };
}

export function configError(code: string, message: string, context?: string): ConfigError {
  const err = new Error(message) as ConfigError;
  err.code = code;
  err.context = context;
  err.toDict = () => ({ code, message, ...(context ? { context } : {}) });
  return err;
}

/** Tag for values Python stores as float (json.dumps renders 1.0 as "1.0", not "1"). */
export type PyFloat = { __pyfloat__: number };
export const pyFloat = (x: number): PyFloat => ({ __pyfloat__: x });
const wrapMap = (m: Record<string, number>) =>
  Object.fromEntries(Object.entries(m).map(([k, v]) => [k, pyFloat(v)]));

/** Canonical Python-field shapes used for the config hash (matches `vars(dataclass)`). */
export function scenarioVars(s: Scenario) {
  return {
    id: s.id,
    label: s.label,
    languages_available: s.languages_available,
    marketing_reach: wrapMap(s.marketing_reach),
    counterfactual: s.counterfactual,
    is_baseline: s.is_baseline,
    description: s.description,
  };
}

export function simulationVars(p: SimulationParams) {
  return {
    agent_count: p.agent_count,
    rounds: p.rounds,
    seed: p.seed,
    seeds: p.seeds,
    network_degree: p.network_degree,
    word_of_mouth_boost: pyFloat(p.word_of_mouth_boost),
    announcement_boost: pyFloat(p.announcement_boost),
    dub_lift: pyFloat(p.dub_lift),
    discovery_cap: pyFloat(p.discovery_cap),
    variability: p.variability,
  };
}

export function segmentVars(s: AudienceSegment) {
  // vars(segment) minus notes — includes hypothesis_label + evidence_ids
  const { notes: _notes, ...rest } = s;
  return {
    ...rest,
    size_share: pyFloat(s.size_share),
    base_interest: pyFloat(s.base_interest),
    discovery_base: pyFloat(s.discovery_base),
    view_info_prob: pyFloat(s.view_info_prob),
    share_prob: pyFloat(s.share_prob),
    discuss_prob: pyFloat(s.discuss_prob),
    language_affinity: wrapMap(s.language_affinity),
    channel_affinity: wrapMap(s.channel_affinity),
  };
}
