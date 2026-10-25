/**
 * Top-level orchestrator: runSimulation(config) -> result.
 * Port of src/sakurascore_sim/simulation/runner.py.
 *
 * dict in, dict out. In non-strict mode invalid configurations do NOT throw —
 * they return a structured failure envelope with machine-readable error codes.
 * Paired design: for repetition i, EVERY scenario runs with seeds[i].
 */

import { runScenario } from "./engine/engine.ts";
import { compareScenarios } from "./engine/compare.ts";
import { buildFailureOutput, buildOutput, validateOutput } from "./engine/output.ts";
import { validateInput } from "./engine/validate.ts";
import { mergeEvidence } from "./evidence.ts";

function resolveBaseline(parsed: ReturnType<typeof validateInput>): string {
  const explicit = parsed.scenarios.find((s) => s.is_baseline);
  return explicit ? explicit.id : parsed.scenarios[0].id;
}

export async function runSimulation(config: any, opts?: { configDir?: string; strict?: boolean }) {
  const strict = opts?.strict ?? false;
  const t0 = performance.now();
  try {
    const merged = await mergeEvidence(config, opts?.configDir);
    const parsed = validateInput(merged);

    let seeds: number[] = parsed.simulation.seeds?.length ? [...parsed.simulation.seeds] : [parsed.simulation.seed];
    if (parsed.simulation.seeds?.length && !seeds.includes(parsed.simulation.seed)) {
      seeds = [parsed.simulation.seed, ...seeds];
    }

    const runs: Record<string, Record<string, any>[]> = {};
    const includeAgents = !!(parsed.options as any)?.include_agents;
    for (const scenario of parsed.scenarios) {
      const reps: Record<string, any>[] = [];
      for (const seed of seeds) {
        const metrics = runScenario(parsed, scenario, seed, includeAgents && seed === parsed.simulation.seed);
        reps.push({ ...metrics, seed });
      }
      runs[scenario.id] = reps;
    }

    const baselineId = resolveBaseline(parsed);
    const comparisons = compareScenarios(parsed, runs, baselineId);
    const totalMs = Math.round(performance.now() - t0);
    const output = buildOutput(parsed, runs, comparisons, baselineId, totalMs);

    if (output.warnings?.length) output.simulation_status = "completed_with_warnings";
    const problems = validateOutput(output);
    if (problems.length) {
      output.warnings = [...(output.warnings ?? [])];
      output.warnings.push({
        code: "OUTPUT_CONTRACT_CHECK",
        message: "Output self-validation flagged: " + problems.join("; "),
      });
      output.simulation_status = "completed_with_warnings";
    }
    return output;
  } catch (exc: any) {
    if (strict) throw exc;
    return buildFailureOutput(typeof config === "object" && config ? config : null, exc);
  }
}

export async function runSimulationFromJson(jsonText: string, configDir?: string, strict = false) {
  const config = JSON.parse(jsonText);
  return runSimulation(config, { configDir, strict });
}
