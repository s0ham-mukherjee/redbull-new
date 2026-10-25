/**
 * Simulation laboratory — parametric live runs + sensitivity sweeps.
 *
 * The engine is deterministic and ~1ms per run, so the browser can drive real
 * experiments: override simulation parameters, run paired seeds, and sweep a
 * parameter across a range to probe sensitivity (the answer to limitation R7:
 * "is the effect robust to your assumptions?"). All numbers come from the same
 * sakura-abm stream — nothing here is interpolated or faked.
 */

import { runSimulation } from "./run_simulation.ts";
import { validateInput } from "./engine/validate.ts";
import { runScenario } from "./engine/engine.ts";

import { ROOT, readJsonFile } from "./runtime.ts";

async function shippedConfig() {
  return readJsonFile(`${ROOT}/configs/example_experiment.json`);
}

export type PlaygroundResult = Awaited<ReturnType<typeof runParams>>;

/** One live run: shipped config + user overrides → full envelope + per-seed paired deltas. */
export async function runParams(overrides: {
  dub_lift?: number;
  word_of_mouth_boost?: number;
  announcement_boost?: number;
  seeds?: number[];
  title?: string;
}) {
  const config = await shippedConfig();
  const sim = (config.simulation = { ...config.simulation });
  if (overrides.dub_lift != null) sim.dub_lift = clamp(+overrides.dub_lift, 0, 5);
  if (overrides.word_of_mouth_boost != null) sim.word_of_mouth_boost = clamp(+overrides.word_of_mouth_boost, 0, 3);
  if (overrides.announcement_boost != null) sim.announcement_boost = clamp(+overrides.announcement_boost, 0, 6);
  if (overrides.seeds?.length) sim.seeds = overrides.seeds.slice(0, 12).map((s: any) => Math.trunc(+s) || 42);
  if (overrides.title) {
    config.title = String(overrides.title).slice(0, 120);
    config.ip_id = String(overrides.title).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || config.ip_id;
  }
  const t0 = performance.now();
  const result = await runSimulation(config, { configDir: `${ROOT}/configs` });
  const ms = Math.round(performance.now() - t0);

  // per-seed paired deltas, computed from the same seeded stream
  const parsed = validateInput(config);
  const seeds = parsed.simulation.seeds?.length ? parsed.simulation.seeds : [parsed.simulation.seed];
  const perSeed = seeds.map((seed) => {
    const b = runScenario(parsed, parsed.scenarios[0], seed);
    const d = runScenario(parsed, parsed.scenarios[1], seed);
    return {
      seed,
      baseline: b.totals.engagement_rate,
      dub: d.totals.engagement_rate,
      delta: Math.round((d.totals.engagement_rate - b.totals.engagement_rate) * 1e6) / 1e6,
      baseline_reach: b.totals.reach,
      dub_reach: d.totals.reach,
    };
  });

  const cmp = result.comparisons?.[0];
  return {
    simulation_status: result.simulation_status,
    overrides: { ...overrides },
    config_hash: result.run_metadata?.config_hash,
    duration_ms: ms,
    runs_executed: seeds.length * parsed.scenarios.length,
    headline: {
      baseline: cmp?.metrics?.engagement_rate?.baseline_mean,
      dub: cmp?.metrics?.engagement_rate?.comparison_mean,
      delta_pp: cmp?.metrics?.engagement_rate?.delta_mean,
      delta_std_pp: cmp?.metrics?.engagement_rate?.delta_std,
      relative_lift: cmp?.metrics?.engagement_rate?.relative_lift_mean,
      seeds_positive: perSeed.filter((p) => p.delta > 0).length,
      seeds_total: perSeed.length,
    },
    scenarios: (result.scenarios ?? []).map((s: any) => ({
      id: s.id,
      totals: s.totals,
      per_round: s.per_round,
      per_language: s.per_language,
      per_segment: s.per_segment,
      variability: s.variability,
    })),
    per_segment_engagement_delta: cmp?.per_segment_engagement_delta ?? {},
    per_seed: perSeed,
    parameters: { dub_lift: sim.dub_lift, word_of_mouth_boost: sim.word_of_mouth_boost, announcement_boost: sim.announcement_boost, seeds: sim.seeds },
    limitations: (result.limitations ?? []).map((l: any) => ({ id: l.id, severity: l.severity })),
  };
}

export type SweepResult = Awaited<ReturnType<typeof sweep>>;

/** Sensitivity sweep: run paired seeds across a parameter range → robustness curve. */
export async function sweep(opts: {
  param?: "dub_lift" | "word_of_mouth_boost" | "announcement_boost";
  from?: number;
  to?: number;
  steps?: number;
  seeds?: number[];
}) {
  const param = opts.param ?? "dub_lift";
  if (!["dub_lift", "word_of_mouth_boost", "announcement_boost"].includes(param)) {
    throw new Error(`unknown sweep param '${param}'`);
  }
  const from = clamp(opts.from ?? 1, 0, 5);
  const to = clamp(opts.to ?? (param === "dub_lift" ? 2.2 : param === "word_of_mouth_boost" ? 1.5 : 4), 0, 6);
  const steps = clamp(Math.trunc(opts.steps ?? 7), 2, 13);
  const seeds = (opts.seeds?.length ? opts.seeds : [42, 43, 44, 45, 46]).slice(0, 12).map((s: any) => Math.trunc(+s) || 42);

  const base = await shippedConfig();
  const t0 = performance.now();
  const points = [];
  for (let i = 0; i < steps; i++) {
    const value = +(from + ((to - from) * i) / (steps - 1)).toFixed(3);
    const config = JSON.parse(JSON.stringify(base));
    config.simulation = { ...config.simulation, seeds, [param]: value };
    const parsed = validateInput(config);
    const perSeed = seeds.map((seed) => {
      const b = runScenario(parsed, parsed.scenarios[0], seed);
      const d = runScenario(parsed, parsed.scenarios[1], seed);
      return {
        seed,
        baseline: b.totals.engagement_rate,
        dub: d.totals.engagement_rate,
        delta: Math.round((d.totals.engagement_rate - b.totals.engagement_rate) * 1e6) / 1e6,
      };
    });
    const deltas = perSeed.map((p) => p.delta);
    const mu = deltas.reduce((a, b) => a + b, 0) / deltas.length;
    const ss = deltas.reduce((a, b) => a + (b - mu) * (b - mu), 0);
    points.push({
      value,
      delta_mean: Math.round(mu * 1e6) / 1e6,
      delta_std: Math.round(Math.sqrt(ss / deltas.length) * 1e6) / 1e6,
      seeds_positive: perSeed.filter((p) => p.delta > 0).length,
      seeds_total: deltas.length,
      per_seed: perSeed,
    });
  }
  return {
    param,
    from,
    to,
    steps: points.length,
    points,
    runs_executed: points.length * 2 * seeds.length,
    duration_ms: Math.round(performance.now() - t0),
    note: "every point is a full paired-seed run of the engine · mean ± population std · nothing interpolated",
  };
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, Number.isFinite(v) ? v : lo));
