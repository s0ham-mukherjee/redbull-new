/** CLI: bun run src/cli.ts <config.json> — prints the result JSON (or a compact summary with --summary). */

import { runSimulation } from "./run_simulation.ts";

const path = process.argv[2] ?? "configs/example_experiment.json";
const file = Bun.file(path);
if (!(await file.exists())) {
  console.error(`config not found: ${path}`);
  process.exit(1);
}
const config = await file.json();
const configDir = path.split("/").slice(0, -1).join("/");
const result = await runSimulation(config, { configDir: configDir || undefined });

if (process.argv.includes("--summary")) {
  console.log(`status:       ${result.simulation_status}`);
  console.log(`engine:       ${result.engine} ${result.engine_version} (bun ${Bun.version})`);
  console.log(`config hash:  ${result.run_metadata?.config_hash}`);
  console.log(`runtime:      ${result.run_metadata?.total_duration_ms} ms`);
  for (const s of result.scenarios ?? []) {
    console.log(`${s.id.padEnd(22)} engaged ${s.totals.engagement_rate} · reach ${s.totals.reach_rate} · shares ${s.totals.shares_total}`);
  }
  for (const c of result.comparisons ?? []) {
    const e = c.metrics.engagement_rate;
    console.log(`Δ ${c.scenario_id}: ${e.delta_mean} ± ${e.delta_std}pp over ${e.repetitions} paired seeds`);
  }
} else {
  console.log(JSON.stringify(result, null, 1));
}
