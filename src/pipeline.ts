/**
 * Backend bridge — persistent Python pipeline worker (line-JSON over stdio).
 *
 * The real SakuraScore pipeline (data aggregation → signals → scoring →
 * reporting with cultural compatibility, rupee economics and bilingual
 * briefings) runs as a long-lived python process; bun fronts it behind the
 * same /api/v1 contract as everything else. Crash-safe: the worker restarts
 * on exit; requests queue and resolve by id.
 */

import { join } from "node:path";
import { ROOT } from "./runtime.ts";

const BUN = (globalThis as any).Bun;
const WORKER = join(ROOT, "scripts", "backend", "worker.py");

type Pending = { resolve: (v: any) => void; reject: (e: any) => void; timer: ReturnType<typeof setTimeout> };

let proc: any = null;
let nextId = 1;
const pending = new Map<number, Pending>();
let bootPromise: Promise<any> | null = null;

function start(): any {
  const child = BUN.spawn(["python3", "-u", WORKER], {
    stdin: "pipe",
    stdout: "pipe",
    stderr: "pipe",
  });
  let buf = "";
  (async () => {
    try {
      const reader = child.stdout.getReader();
      const dec = new TextDecoder();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl: number;
        while ((nl = buf.indexOf("\n")) !== -1) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          try {
            const msg = JSON.parse(line);
            const p = pending.get(msg.id);
            if (p) {
              clearTimeout(p.timer);
              pending.delete(msg.id);
              msg.ok ? p.resolve(msg.result) : p.reject(new Error(msg.error));
            }
          } catch (e) {
            /* a malformed line desyncs the protocol — surface it so a wedged
               request is diagnosable instead of silently dropped */
            console.error(`[worker] malformed reply line (${String(e).slice(0, 80)}): ${line.slice(0, 120)}`);
          }
        }
      }
    } catch { /* stream closed */ }
  })();
  child.exited.then(() => {
    // worker died: fail everything pending and restart lazily on next request
    for (const [, p] of pending) { clearTimeout(p.timer); p.reject(new Error("pipeline worker exited")); }
    pending.clear();
    proc = null;
    bootPromise = null;
  });
  return child;
}

function request<T = any>(body: Record<string, unknown>, timeoutMs = 60_000): Promise<T> {
  if (!proc) proc = start();
  const id = nextId++;
  const child = proc;
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`pipeline timeout after ${timeoutMs}ms`));
    }, timeoutMs);
    pending.set(id, { resolve, reject, timer });
    child.stdin.write(JSON.stringify({ id, ...body }) + "\n");
  });
}

async function ensureBooted() {
  if (!bootPromise) bootPromise = request({ cmd: "boot" }, 120_000);
  return bootPromise;
}

export async function pipelineCatalog() {
  await ensureBooted();
  return request({ cmd: "catalog" });
}

export async function pipelineSearch(q: string) {
  await ensureBooted();
  return request({ cmd: "search", q });
}

export async function pipelineAnalyze(title: string) {
  await ensureBooted();
  return request({ cmd: "analyze", title });
}

export async function greenlight(body: { concept: string; title?: string; format?: string; episodes?: number }) {
  await ensureBooted();
  return request({ cmd: "greenlight", ...body }, 120_000);
}

export async function greenlightPresets() {
  await ensureBooted();
  return request({ cmd: "greenlight_presets" });
}

export async function voiceCast(script: string) {
  await ensureBooted();
  return request({ cmd: "voice_cast", script }, 60_000);
}

export async function sketchCheck(imageB64: string) {
  await ensureBooted();
  return request({ cmd: "sketch_check", image_b64: imageB64 }, 60_000);
}

export async function pipelineCompare(titles: string[]) {
  await ensureBooted();
  return request({ cmd: "compare", titles }, 90_000);
}

export async function pipelineClearCache() {
  await ensureBooted();
  return request({ cmd: "clear_cache" });
}

export async function pipelineRefresh() {
  const p = BUN.spawn(["python3", "-u", join(ROOT, "scripts", "backend", "refresh.py")], {
    stdout: "pipe", stderr: "pipe",
  });
  const out = JSON.parse(await new Response(p.stdout).text());
  await p.exited;
  await pipelineClearCache();
  return out;
}

export function pipelineAlive() {
  return proc !== null;
}
