/**
 * Runtime helpers — the engine runs natively on Bun (local dev server) and on
 * Node (Vercel serverless). Everything here must behave identically on both;
 * node:fs / node:crypto are fully supported by Bun.
 */

import { fileURLToPath } from "node:url";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";

/** Project root, works on Bun (import.meta.url) and Node. */
export const ROOT = fileURLToPath(new URL("..", import.meta.url));

export const IS_BUN = typeof Bun !== "undefined";
/** Label baked into run metadata; under Bun the string is byte-identical to
 *  the original `bun ${Bun.version}` so the shipped config hash never changes. */
export const RUNTIME_LABEL = IS_BUN ? `bun ${Bun.version}` : `node ${process.versions.node}`;

export async function readTextFile(path: string): Promise<string | null> {
  try { return await readFile(path, "utf8"); } catch { return null; }
}

export async function readJsonFile<T = any>(path: string): Promise<T | null> {
  const t = await readTextFile(path);
  if (t == null) return null;
  try { return JSON.parse(t) as T; } catch { return null; }
}

/** sha256 of a canonical string, first 16 hex chars (config hash contract). */
export function shortSha256(s: string): string {
  return createHash("sha256").update(s).digest("hex").slice(0, 16);
}

/** gzip if the runtime supports it natively (bun); null → caller sends plain. */
export function gzipMaybe(bytes: Uint8Array): Uint8Array | null {
  if (IS_BUN) return Bun.gzipSync(bytes as any, { level: 6 });
  return null;
}

/**
 * Parse a request URL — some serverless runtimes hand the handler a relative
 * URL ("/api/..." with no origin), which `new URL()` rejects.
 */
export function reqURL(req: Request): URL {
  try { return new URL(req.url); } catch { return new URL(req.url, "https://sakurascore.local"); }
}
