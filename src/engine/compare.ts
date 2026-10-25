/** Paired scenario comparison — port of src/sakurascore_sim/simulation/scenarios.py. */

import { round6 } from "./engine.ts";
import type { Scenario, SimulationInput } from "./types.ts";

export const METRIC_KEYS = ["reach_rate", "engagement_rate", "view_rate", "shares_total", "discussions_total"] as const;

type Metrics = {
  totals: Record<string, number>;
  per_segment: Record<string, Record<string, number>>;
};

function mean(values: number[]): number | null {
  if (!values.length) return null;
  return round6(values.reduce((a, b) => a + b, 0) / values.length);
}

function pstdev(values: number[]): number | null {
  if (values.length <= 1) return null;
  const mu = values.reduce((a, b) => a + b, 0) / values.length;
  const ss = values.reduce((a, b) => a + (b - mu) * (b - mu), 0);
  return round6(Math.sqrt(ss / values.length));
}

function relLift(base: number, value: number): number | null {
  if (base === 0) return null;
  return round6((value - base) / base);
}

export function differingParameters(baseline: Scenario, scenario: Scenario): Record<string, unknown>[] {
  const drivers: Record<string, unknown>[] = [];
  const added = scenario.languages_available.filter((l) => !baseline.languages_available.includes(l));
  const removed = baseline.languages_available.filter((l) => !scenario.languages_available.includes(l));
  if (added.length || removed.length) {
    drivers.push({
      parameter: "languages_available",
      baseline: baseline.languages_available,
      comparison: scenario.languages_available,
      added,
      removed,
      engine_assumption: added.length
        ? "dub_lift applied to agents whose primary language is regional and newly " +
          "offered (simulation.dub_lift); language-fit modulation of discovery/interest " +
          "(constants in adapters/abm_engine.py)."
        : "reduced language coverage (language-fit modulation).",
    });
  }
  const baseMkt = baseline.marketing_reach;
  const compMkt = scenario.marketing_reach;
  if (JSON.stringify(baseMkt) !== JSON.stringify(compMkt)) {
    const channels = [...new Set([...Object.keys(baseMkt), ...Object.keys(compMkt)])].sort();
    const changed: Record<string, { baseline: number | undefined; comparison: number | undefined }> = {};
    for (const k of channels) {
      if (baseMkt[k] !== compMkt[k]) changed[k] = { baseline: baseMkt[k], comparison: compMkt[k] };
    }
    drivers.push({
      parameter: "marketing_reach",
      baseline: baseMkt,
      comparison: compMkt,
      changed_channels: changed,
      engine_assumption: "channel-affinity-weighted marketing multiplier in discovery probability.",
    });
  }
  return drivers;
}

function compareSingleRun(baselineMetrics: Metrics, comparisonMetrics: Metrics) {
  const deltas: Record<string, unknown> = {};
  for (const key of METRIC_KEYS) {
    const b = baselineMetrics.totals[key];
    const c = comparisonMetrics.totals[key];
    deltas[key] = {
      baseline: b,
      comparison: c,
      delta: round6(c - b),
      relative_lift: relLift(b, c),
    };
  }
  return deltas;
}

export function compareScenarios(
  parsed: SimulationInput,
  runs: Record<string, Record<string, any>[]>,
  baselineId: string,
): Record<string, any>[] {
  const scenarios = new Map(parsed.scenarios.map((s) => [s.id, s]));
  if (!scenarios.has(baselineId)) return [];
  const baseline = scenarios.get(baselineId)!;
  const baselineRuns = runs[baselineId] ?? [];

  const comparisons: Record<string, any>[] = [];
  for (const scenario of parsed.scenarios) {
    if (scenario.id === baselineId) continue;
    const scenRuns = runs[scenario.id] ?? [];
    if (!baselineRuns.length || !scenRuns.length) continue;

    const paired = baselineRuns.map((b, i) => [b, scenRuns[i]] as const);
    const perRep = paired.map(([b, c]) => compareSingleRun(b as Metrics, c as Metrics));

    const aggregate: Record<string, unknown> = {};
    for (const key of METRIC_KEYS) {
      const deltas = perRep.map((rep) => (rep[key] as any).delta);
      const lifts = perRep.map((rep) => (rep[key] as any).relative_lift).filter((v) => v !== null);
      const baseVals = perRep.map((rep) => (rep[key] as any).baseline);
      const compVals = perRep.map((rep) => (rep[key] as any).comparison);
      aggregate[key] = {
        baseline_mean: mean(baseVals),
        comparison_mean: mean(compVals),
        delta_mean: mean(deltas),
        delta_std: pstdev(deltas),
        delta_min: deltas.length ? round6(Math.min(...deltas)) : null,
        delta_max: deltas.length ? round6(Math.max(...deltas)) : null,
        relative_lift_mean: mean(lifts),
        repetitions: paired.length,
      };
    }

    // per-segment engagement lift (mean across repetitions)
    const segLift: Record<string, unknown> = {};
    const segIds = [...new Set(scenRuns.flatMap((r) => Object.keys(r.per_segment)))].sort();
    for (const sid of segIds) {
      const lifts: number[] = [];
      for (const [b, c] of paired) {
        const bSeg = (b as Metrics).per_segment[sid];
        const cSeg = (c as Metrics).per_segment[sid];
        if (!bSeg || !cSeg) continue;
        lifts.push(cSeg.engagement_rate - bSeg.engagement_rate);
      }
      if (lifts.length) {
        segLift[sid] = {
          engagement_rate_delta_mean: mean(lifts),
          delta_std: pstdev(lifts),
        };
      }
    }

    comparisons.push({
      baseline_id: baselineId,
      scenario_id: scenario.id,
      scenario_label: scenario.label,
      is_counterfactual_baseline: baseline.counterfactual,
      paired_seeds: true,
      repetitions: paired.length,
      metrics: aggregate,
      per_segment_engagement_delta: segLift,
      drivers: differingParameters(baseline, scenario),
    });
  }
  return comparisons;
}
