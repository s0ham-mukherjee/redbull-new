/**
 * Vercel serverless entry — every /api/v1/* route except the python-owned
 * pipeline + greenlight paths (those live in api/py/index.py via rewrites).
 *
 * The @vercel/node runtime expects a named `fetch` export (Web-standard);
 * a default export is treated as the legacy (req, res) signature and its
 * return value is ignored — hence no `export default` here.
 */

import { handleRequest } from "../../src/router.ts";

export async function fetch(request: Request): Promise<Response> {
  try {
    return await handleRequest(request);
  } catch (e: any) {
    return new Response(JSON.stringify({ ok: false, error: String(e?.message || e), stack: String(e?.stack).slice(0, 500) }), {
      status: 500,
      headers: { "Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": "*" },
    });
  }
}
