/** Result assembly + output-contract validation — port of simulation/results.py. */

import { ENGINE_NAME, ENGINE_VERSION, engineMetadata, round6 } from "./engine.ts";
import { shortSha256 } from "../runtime.ts";
import {
  segmentVars,
  scenarioVars,
  simulationVars,
  type EvidenceItem,
  type SimulationInput,
} from "./types.ts";

export const DATA_LABELS = ["observed", "inferred", "simulated", "unknown"];
const SIMULATED_LABEL = "simulated";

export const BASE_LIMITATIONS = [
  {
    id: "not-a-forecast",
    statement:
      "Outputs are simulations of a hypothesised audience under explicit assumptions. They are NOT predictions of real awareness, revenue, viewership or streaming performance, and must never be presented as such.",
    severity: "critical",
  },
  {
    id: "synthetic-personas",
    statement:
      "Agents are stochastic-threshold actors parameterised by segment hypotheses. They do not represent real Indian consumers, and no survey responses were collected or fabricated.",
    severity: "critical",
  },
  {
    id: "segment-hypotheses",
    statement:
      "Audience segment sizes and behavioural parameters are modelling hypotheses informed (where noted) by cited public evidence, not measured demographics.",
    severity: "high",
  },
  {
    id: "engine-simplification",
    statement:
      "sakura-abm is a compact scenario model. Unlike OASIS/MiroFish LLM agents it cannot generate novel discourse; interaction structure (word-of-mouth over a preferential-attachment graph) is a simplifying assumption.",
    severity: "high",
  },
  {
    id: "no-independent-validation",
    statement:
      "Model outputs have not been validated against independent real-world observations; only internal sanity checks and ablation tests are performed.",
    severity: "high",
  },
];

const ASSUMPTION_TEMPLATES = [
  {
    id: "dub-lift",
    statement:
      "Agents whose primary language is a regional language newly offered by a scenario receive a multiplicative lift on interest, share and discuss probabilities (simulation.dub_lift).",
    role: "drives the regional-dubbing scenario effect",
    type: "assumption",
  },
  {
    id: "language-fit-modulation",
    statement:
      "Discovery probability scales with language fit via 0.7 + 0.3*fit; interest scales via 0.25 + 0.75*fit; agents without any offered-language fit fall back to a 0.25 subtitle-tolerance floor.",
    role: "translates language availability into behaviour",
    type: "assumption",
  },
  {
    id: "announcement-boost",
    statement:
      "Round 0 models a release announcement: discovery probability is multiplied by simulation.announcement_boost in the first round only.",
    role: "release-attention spike",
    type: "assumption",
  },
  {
    id: "word-of-mouth",
    statement:
      "Discovery probability is multiplied by (1 + simulation.word_of_mouth_boost * engaged-neighbour share) over a Barabasi-Albert preferential-attachment graph.",
    role: "information diffusion structure",
    type: "assumption",
  },
  {
    id: "population-heterogeneity",
    statement:
      "Personal susceptibility ~ U(0.7, 1.3) and vocalness ~ U(0.75, 1.25) are unexplained heterogeneity drawn per agent from the seeded stream.",
    role: "within-segment variance",
    type: "assumption",
  },
  {
    id: "segment-parameters",
    statement:
      "Segment sizes, base_interest, discovery_base, view/share/discuss probabilities, language and channel affinities are supplied by the config and treated as hypotheses; each segment lists its evidence_ids.",
    role: "audience model",
    type: "assumption",
  },
];

/** Python json.dumps(..., sort_keys=True, ensure_ascii=True) equivalent — byte-compatible. */
export function canonicalPythonJson(value: unknown): string {
  const pyFloatRepr = (x: number): string => {
    if (Number.isInteger(x) && Math.abs(x) < 1e16) return `${x}.0`;
    let s = String(x);
    // python pads exponents to two digits: 1e-05
    s = s.replace(/e([+-])(\d)$/, "e$10$2");
    return s;
  };
  const enc = (v: unknown): string => {
    if (v === null || v === undefined) return "null";
    if (typeof v === "boolean") return v ? "true" : "false";
    if (typeof v === "number") {
      if (!Number.isFinite(v)) return "null";
      return JSON.stringify(v);
    }
    if (typeof v === "object" && "__pyfloat__" in (v as Record<string, unknown>)) {
      const f = (v as { __pyfloat__: number }).__pyfloat__;
      return Number.isFinite(f) ? pyFloatRepr(f) : "null";
    }
    if (typeof v === "string") return JSON.stringify(v).replace(/[\u007f-\uffff]/g, (c) => {
      const hex = c.charCodeAt(0).toString(16).padStart(4, "0");
      return "\\u" + hex;
    });
    if (Array.isArray(v)) return `[${v.map(enc).join(", ")}]`;
    if (typeof v === "object") {
      const entries = Object.entries(v as Record<string, unknown>)
        .filter(([k]) => typeof k === "string")
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
        .map(([k, val]) => `${enc(k)}: ${enc(val)}`);
      return `{${entries.join(", ")}}`;
    }
    return enc(String(v));
  };
  return enc(value);
}

export function configHash(parsed: SimulationInput): string {
  const canonical = canonicalPythonJson({
    ip_id: parsed.ip_id,
    experiment_id: parsed.experiment_id,
    scenarios: parsed.scenarios.map(scenarioVars),
    simulation: simulationVars(parsed.simulation),
    segments: parsed.audience_segments.map(segmentVars),
  });
  return shortSha256(canonical);
}

export function buildAssumptions(parsed: SimulationInput) {
  const sim = parsed.simulation;
  const values: Record<string, Record<string, unknown>> = {
    "dub-lift": { dub_lift: sim.dub_lift },
    "language-fit-modulation": { discovery: "0.7 + 0.3*fit", interest: "0.25 + 0.75*fit", floor: 0.25 },
    "announcement-boost": { announcement_boost: sim.announcement_boost },
    "word-of-mouth": { word_of_mouth_boost: sim.word_of_mouth_boost, network_degree: sim.network_degree },
    "population-heterogeneity": { susceptibility: "U(0.7,1.3)", vocalness: "U(0.75,1.25)" },
  };
  return ASSUMPTION_TEMPLATES.map((template) => {
    const isSeg = template.id === "segment-parameters";
    const evidenceIds = isSeg
      ? [...new Set(parsed.audience_segments.flatMap((s) => s.evidence_ids))].sort()
      : [];
    return {
      ...template,
      value: values[template.id] ?? {},
      data_label: isSeg ? "inferred" : SIMULATED_LABEL,
      evidence_ids: evidenceIds,
    };
  });
}

function variabilityStats(values: number[]) {
  if (!values.length) return { mean: null, std: null, min: null, max: null };
  const mu = values.reduce((a, b) => a + b, 0) / values.length;
  const ss = values.reduce((a, b) => a + (b - mu) * (b - mu), 0);
  return {
    mean: round6(values.reduce((a, b) => a + b, 0) / values.length),
    std: values.length > 1 ? round6(Math.sqrt(ss / values.length)) : 0.0,
    min: round6(Math.min(...values)),
    max: round6(Math.max(...values)),
  };
}

function scenarioBlock(scenarioDict: Record<string, any>, metrics: Record<string, any>, seed: number) {
  return {
    id: scenarioDict.id,
    label: scenarioDict.label,
    description: scenarioDict.description ?? "",
    counterfactual: scenarioDict.counterfactual ?? false,
    languages_available: scenarioDict.languages_available,
    marketing_reach: scenarioDict.marketing_reach,
    seed,
    data_label: SIMULATED_LABEL,
    totals: { ...metrics.totals, data_label: SIMULATED_LABEL },
    per_round: metrics.per_round,
    per_segment: metrics.per_segment,
    per_language: metrics.per_language,
    graph: metrics.graph,
    duration_ms: metrics.duration_ms,
    ...(metrics.agents ? { agents: metrics.agents } : {}),
  };
}

export function sourceReferences(evidence: EvidenceItem[]) {
  return evidence.map((e) => ({
    id: e.id,
    title: e.title,
    url: e.url,
    publisher: e.publisher,
    date: e.date,
    type: e.type,
    region: e.region,
    label: e.label,
    quality: e.quality,
    tags: e.tags ?? [],
    retrieved_via: e.retrieved_via ?? null,
    retrieved_at: e.retrieved_at ?? null,
  }));
}

export function buildOutput(
  parsed: SimulationInput,
  runs: Record<string, Record<string, any>[]>,
  comparisons: Record<string, any>[],
  baselineId: string,
  totalDurationMs: number,
): Record<string, any> {
  const scenarioInputs = new Map(parsed.scenarios.map((s) => [s.id, scenarioVars(s)]));

  const scenarioBlocks: Record<string, any>[] = [];
  for (const scenario of parsed.scenarios) {
    const reps = runs[scenario.id] ?? [];
    if (!reps.length) continue;
    const primary = reps[0];
    const block = scenarioBlock(scenarioInputs.get(scenario.id)!, primary, primary.seed);
    if (reps.length > 1) {
      ;(block as any).variability = {
        repetitions: reps.length,
        seeds: reps.map((r) => r.seed),
        engagement_rate: variabilityStats(reps.map((r) => r.totals.engagement_rate)),
        reach_rate: variabilityStats(reps.map((r) => r.totals.reach_rate)),
        shares_total: variabilityStats(reps.map((r) => r.totals.shares_total)),
        data_label: SIMULATED_LABEL,
      };
    }
    scenarioBlocks.push(block);
  }

  const warnings = [...parsed.warnings];
  if (!parsed.evidence.length) {
    warnings.push({
      code: "LIMITATION_STRENGTHENED",
      message:
        "No evidence supplied: all assumptions are unsupported hypotheses; results are for demonstration only.",
    });
  }

  const limitations = BASE_LIMITATIONS.map((l) => ({ ...l }));
  limitations.push({
    id: "baseline-counterfactual",
    statement: `Scenario '${baselineId}' is a counterfactual construct (${
      parsed.scenarios.some((s) => s.counterfactual) ? "labelled" : "CHECK LABELLING"
    }); it did not necessarily occur in the real world and is not derived from observed history.`,
    severity: "high",
  });

  const seeds = [...new Set(Object.values(runs).flatMap((reps) => reps.map((r) => r.seed)))].sort((a, b) => a - b);

  return {
    schema_version: "1.0",
    ip_id: parsed.ip_id,
    title: parsed.title,
    experiment_id: parsed.experiment_id,
    simulation_status: "completed",
    engine: ENGINE_NAME,
    engine_version: ENGINE_VERSION,
    data_label_legend: {
      observed: "figure/report taken from a cited public source",
      inferred: "derived from cited sources by interpretation",
      simulated: "produced by this simulation under stated assumptions",
      unknown: "not known",
    },
    scenarios: scenarioBlocks,
    comparisons,
    assumptions: buildAssumptions(parsed),
    source_references: sourceReferences(parsed.evidence),
    limitations,
    warnings,
    run_metadata: {
      ...engineMetadata(),
      agent_count: parsed.simulation.agent_count,
      rounds: parsed.simulation.rounds,
      seeds,
      paired_design: parsed.scenarios.length > 1,
      config_hash: configHash(parsed),
      total_duration_ms: totalDurationMs,
      generated_at: new Date().toISOString().replace(/\.\d+Z$/, "+00:00"),
    },
  };
}

export function buildFailureOutput(configOrNone: Record<string, any> | null, error: any): Record<string, any> {
  return {
    schema_version: "1.0",
    ip_id: (configOrNone ?? {}).ip_id ?? "unknown",
    experiment_id: (configOrNone ?? {}).experiment_id ?? "unknown",
    simulation_status: "failed",
    engine: ENGINE_NAME,
    engine_version: ENGINE_VERSION,
    errors: [error?.toDict ? error.toDict() : { code: "INTERNAL", message: String(error) }],
    scenarios: [],
    comparisons: [],
    assumptions: [],
    source_references: [],
    limitations: BASE_LIMITATIONS,
    run_metadata: { failed_at: new Date().toISOString().replace(/\.\d+Z$/, "+00:00") },
  };
}

export function validateOutput(output: Record<string, any>): string[] {
  const problems: string[] = [];
  for (const key of ["schema_version", "ip_id", "experiment_id", "simulation_status", "engine", "scenarios", "comparisons", "assumptions", "source_references", "limitations", "run_metadata"]) {
    if (!(key in output)) problems.push(`missing required key: ${key}`);
  }
  if (problems.length) return problems;
  if (output.schema_version !== "1.0") problems.push("schema_version must be '1.0'");
  if (!["completed", "failed", "completed_with_warnings"].includes(output.simulation_status))
    problems.push(`invalid simulation_status: ${output.simulation_status}`);
  if (!Array.isArray(output.scenarios)) problems.push("'scenarios' must be a list");
  if (problems.length) return problems;

  if (output.simulation_status === "failed") {
    if (!output.errors?.length) problems.push("failed results must carry an 'errors' list");
    return problems;
  }
  if (!output.scenarios.length && output.simulation_status === "completed")
    problems.push("completed simulation has no scenario results");

  output.scenarios.forEach((scenario: Record<string, any>, i: number) => {
    if (scenario.data_label !== SIMULATED_LABEL) problems.push(`scenarios[${i}] must be labelled '${SIMULATED_LABEL}'`);
    for (const key of ["id", "label", "languages_available", "totals", "per_round", "per_segment", "per_language"]) {
      if (!(key in scenario)) problems.push(`scenarios[${i}] missing key: ${key}`);
    }
    if (!("engagement_rate" in (scenario.totals ?? {})))
      problems.push(`scenarios[${i}].totals missing engagement_rate`);
    if (!("data_label" in (scenario.totals ?? {}))) problems.push(`scenarios[${i}].totals missing data_label`);
  });

  (output.assumptions ?? []).forEach((a: Record<string, any>, i: number) => {
    if (!DATA_LABELS.includes(a.data_label)) problems.push(`assumptions[${i}] has invalid data_label`);
  });
  (output.source_references ?? []).forEach((ref: Record<string, any>, i: number) => {
    if (!["observed", "inferred"].includes(ref.label))
      problems.push(`source_references[${i}] label must be observed|inferred`);
    if (!/^https?:\/\//.test(ref.url ?? "")) problems.push(`source_references[${i}] must carry an http(s) url`);
  });
  if (output.simulation_status === "completed_with_warnings" && !output.warnings?.length)
    problems.push("status completed_with_warnings requires a 'warnings' list");

  return problems;
}
