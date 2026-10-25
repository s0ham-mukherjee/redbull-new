/** Input validation with stable error codes — light port of models.py's strict checks. */

import { configError, type EvidenceItem, type SimulationInput } from "./types.ts";

export const ERROR_CODES = {
  MISSING_FIELD: "MISSING_FIELD",
  INVALID_FIELD: "INVALID_FIELD",
  INVALID_ENGINE: "INVALID_ENGINE",
  NO_SCENARIOS: "NO_SCENARIOS",
  NO_SEGMENTS: "NO_SEGMENTS",
  BAD_EVIDENCE_LABEL: "BAD_EVIDENCE_LABEL",
} as const;

function requireField(data: any, key: string, ctx: string): any {
  if (data == null || typeof data !== "object" || !(key in data) || data[key] === null) {
    throw configError(ERROR_CODES.MISSING_FIELD, `missing required field '${key}'`, ctx);
  }
  return data[key];
}

function requireNumber(data: any, key: string, ctx: string, min = -Infinity, max = Infinity): number {
  const v = requireField(data, key, ctx);
  if (typeof v !== "number" || !Number.isFinite(v) || v < min || v > max) {
    throw configError(ERROR_CODES.INVALID_FIELD, `field '${key}' must be a number in [${min}, ${max}]`, ctx);
  }
  return v;
}

function requireString(data: any, key: string, ctx: string): string {
  const v = requireField(data, key, ctx);
  if (typeof v !== "string" || !v.trim()) {
    throw configError(ERROR_CODES.INVALID_FIELD, `field '${key}' must be a non-empty string`, ctx);
  }
  return v;
}

function requireStringList(data: any, key: string, ctx: string): string[] {
  const v = requireField(data, key, ctx);
  if (!Array.isArray(v) || !v.every((x) => typeof x === "string")) {
    throw configError(ERROR_CODES.INVALID_FIELD, `field '${key}' must be a list of strings`, ctx);
  }
  return v;
}

export function validateInput(raw: any): SimulationInput {
  requireString(raw, "schema_version", "root");
  if (raw.schema_version !== "1.0") {
    throw configError(ERROR_CODES.INVALID_FIELD, "schema_version must be '1.0'", "root");
  }
  const ipId = requireString(raw, "ip_id", "root");
  const title = requireString(raw, "title", "root");
  const experimentId = requireString(raw, "experiment_id", "root");
  const mediaType = typeof raw.media_type === "string" ? raw.media_type : "anime";
  const genre = typeof raw.genre === "string" ? raw.genre : "general";

  const engine = raw.engine ?? "auto";
  if (!["auto", "abm"].includes(engine)) {
    throw configError(
      ERROR_CODES.INVALID_ENGINE,
      `engine '${engine}' is not available. Use engine 'auto' or 'abm' (sakura-abm).`,
      "root",
    );
  }

  const rawSegments = requireField(raw, "audience_segments", "root") as any[];
  if (!Array.isArray(rawSegments) || !rawSegments.length) {
    throw configError(ERROR_CODES.NO_SEGMENTS, "audience_segments must be a non-empty list", "root");
  }
  const segments = rawSegments.map((s) => {
    const ctx = `audience_segments.${s?.id ?? "?"}`;
    requireString(s, "id", ctx);
    requireString(s, "label", ctx);
    requireNumber(s, "size_share", ctx, 0, 1);
    requireNumber(s, "base_interest", ctx, 0, 1);
    requireNumber(s, "discovery_base", ctx, 0, 1);
    requireNumber(s, "view_info_prob", ctx, 0, 1);
    requireNumber(s, "share_prob", ctx, 0, 1);
    requireNumber(s, "discuss_prob", ctx, 0, 1);
    const la = requireField(s, "language_affinity", ctx);
    const ca = requireField(s, "channel_affinity", ctx);
    if (typeof la !== "object" || typeof ca !== "object") {
      throw configError(ERROR_CODES.INVALID_FIELD, "affinity maps must be objects", ctx);
    }
    return {
      id: s.id,
      label: s.label,
      size_share: s.size_share,
      base_interest: s.base_interest,
      discovery_base: s.discovery_base,
      view_info_prob: s.view_info_prob,
      share_prob: s.share_prob,
      discuss_prob: s.discuss_prob,
      language_affinity: la,
      channel_affinity: ca,
      evidence_ids: Array.isArray(s.evidence_ids) ? s.evidence_ids : [],
      notes: typeof s.notes === "string" ? s.notes : "",
      hypothesis_label: typeof s.hypothesis_label === "string" ? s.hypothesis_label : "modelling hypothesis",
    };
  });
  const shareSum = segments.reduce((a, s) => a + s.size_share, 0);
  if (Math.abs(shareSum - 1.0) > 0.01) {
    throw configError(
      ERROR_CODES.INVALID_FIELD,
      `audience_segments size_share values must sum to ~1.0 (got ${shareSum.toFixed(4)})`,
      "audience_segments",
    );
  }

  const rawScenarios = requireField(raw, "scenarios", "root") as any[];
  if (!Array.isArray(rawScenarios) || !rawScenarios.length) {
    throw configError(ERROR_CODES.NO_SCENARIOS, "scenarios must be a non-empty list", "root");
  }
  const seen = new Set<string>();
  const scenarios = rawScenarios.map((s) => {
    const ctx = `scenarios.${s?.id ?? "?"}`;
    requireString(s, "id", ctx);
    requireString(s, "label", ctx);
    requireStringList(s, "languages_available", ctx);
    const mr = requireField(s, "marketing_reach", ctx);
    if (typeof mr !== "object" || !Object.keys(mr).length) {
      throw configError(ERROR_CODES.INVALID_FIELD, "marketing_reach must be a non-empty object", ctx);
    }
    if (seen.has(s.id)) {
      throw configError(ERROR_CODES.INVALID_FIELD, `duplicate scenario id '${s.id}'`, ctx);
    }
    seen.add(s.id);
    return {
      id: s.id,
      label: s.label,
      languages_available: s.languages_available,
      marketing_reach: mr,
      counterfactual: s.counterfactual ?? false,
      is_baseline: s.is_baseline ?? false,
      description: typeof s.description === "string" ? s.description : "",
    };
  });

  const rawSim = requireField(raw, "simulation", "root");
  const simCtx = "simulation";
  const sim = {
    agent_count: rawSim.agent_count != null ? requireNumber(rawSim, "agent_count", simCtx, 1, 5000) : 20,
    rounds: rawSim.rounds != null ? requireNumber(rawSim, "rounds", simCtx, 1, 200) : 5,
    seed: rawSim.seed != null ? requireNumber(rawSim, "seed", simCtx, 0, 2 ** 31) : 42,
    seeds:
      Array.isArray(rawSim.seeds) && rawSim.seeds.every((x: any) => Number.isInteger(x) && x >= 0)
        ? rawSim.seeds
        : null,
    network_degree: rawSim.network_degree != null ? requireNumber(rawSim, "network_degree", simCtx, 1, 50) : 3,
    word_of_mouth_boost: rawSim.word_of_mouth_boost != null ? requireNumber(rawSim, "word_of_mouth_boost", simCtx, 0, 5) : 0.8,
    announcement_boost: rawSim.announcement_boost != null ? requireNumber(rawSim, "announcement_boost", simCtx, 0, 10) : 2.0,
    dub_lift: rawSim.dub_lift != null ? requireNumber(rawSim, "dub_lift", simCtx, 0, 10) : 1.6,
    discovery_cap: rawSim.discovery_cap != null ? requireNumber(rawSim, "discovery_cap", simCtx, 0, 1) : 0.95,
    variability: rawSim.variability ?? false,
  };
  if (sim.network_degree >= sim.agent_count) {
    throw configError(
      ERROR_CODES.INVALID_FIELD,
      "simulation.network_degree must be < agent_count",
      simCtx,
    );
  }

  const evidence: EvidenceItem[] = (Array.isArray(raw.evidence) ? raw.evidence : []).map((e: any, i: number) => {
    const ctx = `evidence[${i}]`;
    const item: EvidenceItem = {
      id: requireString(e, "id", ctx),
      title: requireString(e, "title", ctx),
      url: requireString(e, "url", ctx),
      publisher: requireString(e, "publisher", ctx),
      date: requireString(e, "date", ctx),
      finding: requireString(e, "finding", ctx),
      type: requireString(e, "type", ctx),
      region: requireString(e, "region", ctx),
      label: requireString(e, "label", ctx),
      quality: requireString(e, "quality", ctx),
      tags: Array.isArray(e.tags) ? e.tags : [],
      source_id: e.source_id ?? null,
      retrieved_via: e.retrieved_via ?? null,
      retrieved_at: e.retrieved_at ?? null,
    };
    if (!["observed", "inferred"].includes(item.label)) {
      throw configError(ERROR_CODES.BAD_EVIDENCE_LABEL, `evidence label must be observed|inferred (got '${item.label}')`, ctx);
    }
    return item;
  });

  return {
    schema_version: raw.schema_version,
    ip_id: ipId,
    title,
    experiment_id: experimentId,
    media_type: mediaType,
    genre,
    evidence,
    audience_segments: segments,
    scenarios,
    simulation: sim,
    engine,
    notes: typeof raw.notes === "string" ? raw.notes : "",
    options: typeof raw.options === "object" && raw.options ? raw.options : {},
    warnings: Array.isArray(raw.warnings) ? raw.warnings : [],
  };
}
