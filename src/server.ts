/**
 * SakuraScore Bun server — serves the dashboard and the simulation API.
 *
 *   GET  /                    dashboard (static, from public/)
 *   GET  /api/v1/health       engine + runtime status
 *   GET  /api/v1/example      shipped experiment config
 *   GET  /api/v1/run-example  run the shipped experiment live (bun engine)
 *   POST /api/v1/run          body = experiment config → full result envelope
 *   …   all routing lives in src/router.ts (shared with the Vercel function)
 *
 * Zero npm dependencies. `bun run src/server.ts` then open http://localhost:8787
 */

import { ENGINE_VERSION } from "./engine/engine.ts";
import { handleRequest } from "./router.ts";
import { pipelineCatalog } from "./pipeline.ts";

const PORT = Number(process.env.PORT ?? 8787);

const server = Bun.serve({ port: PORT, fetch: handleRequest });

console.log(`SAKURASCORE.IN — sakura-abm ${ENGINE_VERSION} on bun ${Bun.version}`);
pipelineCatalog().then((c: any) => console.log(`  pipeline worker warm · ${c.titles.length} titles · showcase ${c.showcase.length}`)).catch(() => console.log("  pipeline worker cold-start deferred"));
console.log(`  dashboard  → http://localhost:${server.port}`);
console.log(`  run live   → POST /api/v1/run · /api/v1/analyze · GET /api/v1/run-example`);
console.log(`  product    → GET /api/v1/personas · /memo · /report · /status`);
console.log(`  laboratory → POST /api/v1/run-params · GET /api/v1/sweep?param=dub_lift&from=1&to=2.2&steps=7`);
console.log(`  greenlight → #/greenlight · POST /api/v1/greenlight · GET /api/v1/greenlight/presets`);
console.log(`  pipeline   → GET /api/v1/pipeline/analyze?title=… · /catalog · /search?q= (python worker)`);
console.log(`  intel      → GET /api/v1/ci · health → GET /api/v1/health`);
