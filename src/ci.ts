/**
 * Competitive-intelligence data loader — parses data/ci/*.csv (RFC4180 quoted
 * fields) into typed JSON for the Battle Map / Demo Ops pages and the API.
 * Source: sakurascore-ci workspace, all rows checked 2026-10-24.
 */

import { join } from "node:path";
import { ROOT, readTextFile } from "./runtime.ts";

const CI_DIR = join(ROOT, "data", "ci");

/** Minimal RFC4180 parser: quoted fields, embedded commas/newlines, CRLF. */
export function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQuotes = false;
      } else field += c;
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ",") {
      row.push(field); field = "";
    } else if (c === "\n") {
      row.push(field); field = "";
      rows.push(row); row = [];
    } else if (c === "\r") {
      /* skip */
    } else field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  const nonEmpty = rows.filter((r) => r.some((v) => v.trim() !== ""));
  if (!nonEmpty.length) return [];
  const header = nonEmpty[0].map((h) => h.trim());
  return nonEmpty.slice(1).map((r) => {
    const obj: Record<string, string> = {};
    header.forEach((h, i) => (obj[h] = (r[i] ?? "").trim()));
    return obj;
  });
}

async function load(name: string): Promise<Record<string, string>[]> {
  const text = await readTextFile(join(CI_DIR, `${name}.csv`));
  if (text == null) return [];
  return parseCsv(text);
}

export type CiData = Awaited<ReturnType<typeof loadCi>>;

export async function loadCi() {
  const [
    commercialComparables,
    competitorMatrix,
    hackathonProjects,
    openSourceRepos,
    risks,
    priorityActions,
    eventsAndJudging,
    demoScript,
    sourcesLog,
  ] = await Promise.all([
    load("commercial_comparables"),
    load("competitor_matrix"),
    load("hackathon_projects_comparable"),
    load("opensource_repos"),
    load("risks_uncertainties"),
    load("priority_actions"),
    load("events_and_judging"),
    load("demo_script"),
    load("sources_log"),
  ]);
  return {
    generated: "2026-10-24",
    source: "sakurascore-ci workspace · every row carries a source url + checked date",
    commercialComparables,
    competitorMatrix,
    hackathonProjects,
    openSourceRepos,
    risks,
    priorityActions,
    eventsAndJudging,
    demoScript,
    sourcesLog,
  };
}
