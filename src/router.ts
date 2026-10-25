/**
 * SakuraScore HTTP router — one handler, two runtimes.
 *
 *   Bun  (local dev):  src/server.ts wraps this in Bun.serve, plus the
 *                      python pipeline worker bridge (stdio) lives here too.
 *   Node (Vercel):     api/v1/[[...route]].ts re-exports handleRequest as a
 *                      serverless function; the pipeline + greenlight paths
 *                      are owned by the Python functions in api/v1/**.py.
 *
 * No Bun.* APIs in here (gzip goes through runtime.ts, which no-ops on Node).
 */

import { runSimulation } from "./run_simulation.ts";
import { ENGINE_NAME, ENGINE_VERSION } from "./engine/engine.ts";
import { validateInput } from "./engine/validate.ts";
import { loadCi } from "./ci.ts";
import { buildMemo } from "./memo.ts";
import { buildReport } from "./report.ts";
import { buildStatus } from "./status.ts";
import { runParams, sweep } from "./lab.ts";
import { ROOT, IS_BUN, RUNTIME_LABEL, readJsonFile, readTextFile, gzipMaybe, reqURL } from "./runtime.ts";
import { pipelineAnalyze, pipelineCatalog, pipelineSearch, pipelineCompare, pipelineRefresh, greenlight, greenlightPresets, voiceCast, sketchCheck } from "./pipeline.ts";

const DASHBOARD = `${ROOT}/public/index.html`;
const SHIPPED_CONFIG = `${ROOT}/configs/example_experiment.json`;

const jsonBody = async (req: Request): Promise<any> => {
  try { return await req.json(); } catch { return {}; }
};

async function shippedResult(includeAgents = false) {
  const config = await readJsonFile<any>(SHIPPED_CONFIG);
  if (includeAgents) config.options = { ...(config.options ?? {}), include_agents: true };
  const result = await runSimulation(config, { configDir: `${ROOT}/configs`, strict: true });
  const parsed = validateInput(config);
  return { config, parsed, result };
}

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data, null, 1), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });

export async function handleRequest(req: Request): Promise<Response> {
  const url = reqURL(req);
  const path = url.pathname;

  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });

  if (path === "/" || path === "/index.html") {
    const html = await readTextFile(DASHBOARD);
    if (html == null) return new Response("dashboard missing", { status: 500 });
    const accepts = req.headers.get("accept-encoding") ?? "";
    if (accepts.includes("gzip")) {
      const gz = gzipMaybe(new TextEncoder().encode(html));
      if (gz) {
        return new Response(gz as unknown as BodyInit, {
          headers: { "Content-Type": "text/html; charset=utf-8", "Content-Encoding": "gzip", "Cache-Control": "no-cache" },
        });
      }
    }
    return new Response(html, { headers: { "Content-Type": "text/html; charset=utf-8" } });
  }

  if (path === "/api/v1/health") {
    return json({
      ok: true,
      engine: ENGINE_NAME,
      engine_version: ENGINE_VERSION,
      runtime: RUNTIME_LABEL,
      uptime_s: Math.round(performance.now() / 1000),
    });
  }
  if (path === "/api/v1/example") {
    return json(await readJsonFile(SHIPPED_CONFIG));
  }
  if (path === "/api/v1/run-example") {
    const config = await readJsonFile<any>(SHIPPED_CONFIG);
    const result = await runSimulation(config, { configDir: `${ROOT}/configs` });
    return json(result);
  }
  if (path === "/api/v1/ci") {
    return json(await loadCi());
  }
  if (path === "/api/v1/personas") {
    const { parsed, result } = await shippedResult(true);
    const dub = result.scenarios.find((s: any) => s.id !== result.comparisons[0]?.baseline_id) ?? result.scenarios.at(-1);
    const base = result.scenarios.find((s: any) => s.id === result.comparisons[0]?.baseline_id) ?? result.scenarios[0];
    return json({
      ip: parsed.ip_id,
      seed: parsed.simulation.seed,
      network: dub.graph,
      segments: parsed.audience_segments.map((s: any) => ({ id: s.id, label: s.label, size_share: s.size_share, evidence_ids: s.evidence_ids, notes: s.notes })),
      agents: (dub.agents ?? []).map((a: any) => ({
        ...a,
        base: base.agents?.find((x: any) => x.agent_id === a.agent_id) ?? null,
      })),
    });
  }
  if (path === "/api/v1/memo") {
    const { parsed, result } = await shippedResult(true);
    return json(buildMemo(parsed, result));
  }
  if (path === "/api/v1/report") {
    const { parsed, result } = await shippedResult(true);
    return json(await buildReport(parsed, result));
  }
  if (path === "/api/v1/status") {
    const { parsed, result } = await shippedResult();
    return json(await buildStatus(parsed, result));
  }
  if (path === "/api/v1/analyze" && req.method === "POST") {
    try {
      const body = await jsonBody(req);
      const config = await readJsonFile<any>(SHIPPED_CONFIG);
      const title = String(body.title ?? "").trim();
      if (!title) return json({ simulation_status: "failed", errors: [{ code: "MISSING_FIELD", message: "field 'title' is required", context: "body" }] }, 400);
      config.title = title;
      config.ip_id = String(body.ip_id ?? title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")).slice(0, 60);
      const result = await runSimulation(config, { configDir: `${ROOT}/configs` });
      return json(result, result.simulation_status === "failed" ? 400 : 200);
    } catch (exc: any) {
      return json({ simulation_status: "failed", errors: [{ code: "BAD_REQUEST", message: String(exc) }] }, 400);
    }
  }
  if (path === "/api/v1/run-params" && req.method === "POST") {
    try {
      const body = await jsonBody(req);
      return json(await runParams(body ?? {}));
    } catch (exc: any) {
      return json({ simulation_status: "failed", errors: [{ code: "BAD_REQUEST", message: String(exc) }] }, 400);
    }
  }
  if (path === "/api/v1/sweep") {
    try {
      const q = url.searchParams;
      return json(await sweep({
        param: (q.get("param") ?? "dub_lift") as any,
        from: q.get("from") ? +q.get("from")! : undefined,
        to: q.get("to") ? +q.get("to")! : undefined,
        steps: q.get("steps") ? +q.get("steps")! : undefined,
        seeds: q.get("seeds") ? q.get("seeds")!.split(",").map(Number) : undefined,
      }));
    } catch (exc: any) {
      return json({ error: String(exc) }, 400);
    }
  }
  if (path === "/api/v1/run" && req.method === "POST") {
    try {
      const config = await jsonBody(req);
      const result = await runSimulation(config, { configDir: `${ROOT}/configs` });
      return json(result, result.simulation_status === "failed" ? 400 : 200);
    } catch (exc: any) {
      return json({ simulation_status: "failed", errors: [{ code: "BAD_REQUEST", message: String(exc) }] }, 400);
    }
  }

  /* ---- python-owned routes: live under Bun via the stdio worker; on Vercel
     these paths are served by the Python serverless functions instead ---- */
  if (path.startsWith("/api/v1/pipeline/") || path === "/api/v1/greenlight"
      || path === "/api/v1/greenlight/presets" || path === "/api/v1/voice-cast"
      || path === "/api/v1/sketch-check") {
    if (!IS_BUN) {
      return json({ ok: false, error: "this endpoint runs on the python serverless function — it should not have reached the node router" }, 501);
    }
    if (path === "/api/v1/pipeline/catalog") return json(await pipelineCatalog());
    if (path === "/api/v1/pipeline/search") {
      const q = url.searchParams.get("q") ?? "";
      return json(await pipelineSearch(q));
    }
    if (path === "/api/v1/pipeline/analyze") {
      const title = url.searchParams.get("title") ?? "";
      if (!title.trim()) return json({ ok: false, error: "missing ?title=" }, 400);
      try {
        return json({ ok: true, result: await pipelineAnalyze(title) });
      } catch (exc: any) {
        return json({ ok: false, error: String(exc.message || exc) }, 404);
      }
    }
    if (path === "/api/v1/pipeline/compare") {
      const q = url.searchParams.get("titles") ?? "";
      const titles = q.split("|").map(decodeURIComponent).filter(Boolean).slice(0, 4);
      if (titles.length < 2) return json({ ok: false, error: "need >=2 titles, | separated" }, 400);
      try { return json({ ok: true, result: await pipelineCompare(titles) }); }
      catch (exc: any) { return json({ ok: false, error: String(exc.message || exc) }, 500); }
    }
    if (path === "/api/v1/pipeline/refresh") {
      try { return json({ ok: true, result: await pipelineRefresh() }); }
      catch (exc: any) { return json({ ok: false, error: String(exc.message || exc) }, 500); }
    }
    if (path === "/api/v1/voice-cast" && req.method === "POST") {
      try {
        const body = await jsonBody(req);
        return json({ ok: true, result: await voiceCast(String(body?.script ?? "")) });
      } catch (exc: any) {
        return json({ ok: false, error: String(exc.message || exc) }, 400);
      }
    }
    if (path === "/api/v1/sketch-check" && req.method === "POST") {
      try {
        const body = await jsonBody(req);
        return json({ ok: true, result: await sketchCheck(String(body?.image_b64 ?? body?.image ?? "")) });
      } catch (exc: any) {
        return json({ ok: false, error: String(exc.message || exc) }, 400);
      }
    }
    if (path === "/api/v1/greenlight" && req.method === "POST") {
      try {
        const body = await jsonBody(req);
        const concept = String(body?.concept ?? body?.text ?? "");
        if (concept.trim().length < 12) {
          return json({ ok: false, error: "concept text too short — paste a logline, script excerpt, character design or any Japanese-media pitch (≥ 12 chars)" }, 400);
        }
        return json({ ok: true, result: await greenlight({
          concept,
          title: body?.title ? String(body.title) : undefined,
          format: body?.format ? String(body.format) : undefined,
          episodes: body?.episodes != null ? Number(body.episodes) : undefined,
          image_b64: body?.image_b64 ? String(body.image_b64) : undefined,
        }) });
      } catch (exc: any) {
        return json({ ok: false, error: String(exc.message || exc) }, 500);
      }
    }
    if (path === "/api/v1/greenlight/presets") {
      try { return json({ ok: true, result: await greenlightPresets() }); }
      catch (exc: any) { return json({ ok: false, error: String(exc.message || exc) }, 500); }
    }
  }

  if (path.startsWith("/api/")) return json({ error: "not found", path }, 404);
  return new Response("not found", { status: 404 });
}
