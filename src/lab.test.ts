/**
 * Laboratory endpoint tests — live parametric runs and the sensitivity sweep.
 * The headline property: ablation collapses the effect, sweep recovers it —
 * the engine's mechanisms are actually doing the work.
 */

import { describe, expect, test } from "bun:test";
import { runParams, sweep } from "./lab.ts";

describe("runParams (live lab runs)", () => {
  test("canonical params reproduce the shipped result", async () => {
    const r = await runParams({});
    expect(r.simulation_status).toBe("completed");
    expect(r.headline.delta_pp).toBeCloseTo(0.115, 6);
    expect(r.headline.seeds_positive).toBe(5);
    expect(r.per_seed.length).toBe(5);
  });

  test("ablation (dub_lift = 1) collapses the effect but not below the fit-modulation floor", async () => {
    const canonical = await runParams({});
    const ablated = await runParams({ dub_lift: 1.0 });
    expect(ablated.headline.delta_pp).toBeLessThan(canonical.headline.delta_pp);
    // the residual is the language-fit discovery channel — real, positive, smaller
    expect(ablated.headline.delta_pp).toBeGreaterThan(0);
    expect(ablated.parameters.dub_lift).toBe(1);
  });

  test("per-seed deltas are consistent with headline aggregates", async () => {
    const r = await runParams({ dub_lift: 2.0 });
    const deltas = r.per_seed.map((p) => p.delta);
    const mu = deltas.reduce((a, b) => a + b, 0) / deltas.length;
    expect(Math.abs(mu - r.headline.delta_pp)).toBeLessThan(1e-6);
    expect(r.headline.seeds_positive).toBe(deltas.filter((d) => d > 0).length);
  });

  test("custom seed set changes the draw but not the contract", async () => {
    const r = await runParams({ seeds: [7, 8, 9] });
    expect(r.per_seed.map((p) => p.seed)).toEqual([7, 8, 9]);
    expect(r.scenarios.length).toBe(2);
  });
});

describe("sweep (sensitivity analysis)", () => {
  test("effect grows with dub_lift and every point is a real paired run", async () => {
    const s = await sweep({ param: "dub_lift", from: 1, to: 2.2, steps: 7 });
    expect(s.points.length).toBe(7);
    expect(s.runs_executed).toBe(70);
    expect(s.points.at(-1)!.delta_mean).toBeGreaterThan(s.points[0].delta_mean);
    for (const p of s.points) {
      expect(p.per_seed.length).toBe(5);
      expect(p.seeds_total).toBe(5);
    }
  });

  test("sweeping word_of_mouth_boost to 0 flattens diffusion", async () => {
    const s = await sweep({ param: "word_of_mouth_boost", from: 0, to: 1.5, steps: 4 });
    expect(s.points[0].delta_mean).toBeLessThanOrEqual(s.points.at(-1)!.delta_mean);
  });

  test("unknown param is rejected", async () => {
    expect(sweep({ param: "vibes" as any })).rejects.toThrow();
  });
});
