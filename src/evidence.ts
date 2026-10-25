/** Evidence loading — port of research/evidence_loader.py (no network I/O). */

import type { EvidenceItem } from "./engine/types.ts";
import { readJsonFile } from "./runtime.ts";

export async function loadEvidenceFile(path: string): Promise<EvidenceItem[]> {
  const data = await readJsonFile<any>(path);
  if (data == null) return [];
  const items = Array.isArray(data) ? data : (data.evidence ?? data.items ?? data.sources ?? []);
  return items as EvidenceItem[];
}

/** Merge config-inline evidence with an evidence_file reference (file wins for retrieval metadata). */
export async function mergeEvidence(config: any, configDir?: string): Promise<any> {
  let evidence = Array.isArray(config.evidence) ? [...config.evidence] : [];
  if (config.evidence_file) {
    const base = configDir ?? process.cwd();
    const path = config.evidence_file.startsWith("../") || config.evidence_file.startsWith("./")
      ? `${base}/${config.evidence_file}`
      : config.evidence_file;
    const loaded = await loadEvidenceFile(path);
    if (loaded.length) {
      // config-inline evidence that isn't already in the file dataset is appended
      const known = new Set(loaded.map((e) => e.id));
      evidence = [...loaded, ...evidence.filter((e) => !known.has(e.id))];
    }
  }
  return { ...config, evidence };
}
