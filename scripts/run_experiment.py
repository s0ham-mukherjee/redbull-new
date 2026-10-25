#!/usr/bin/env python3
"""CLI: run the SakuraScore regional-dubbing experiment (or any config file).

Usage:
    python scripts/run_experiment.py [path/to/config.json] [--out results/]

Defaults to configs/example_experiment.json. Writes:
    <out>/<experiment_id>_output.json   full structured result (output schema v1.0)
    <out>/<experiment_id>_summary.md    human/judge-readable comparison summary
Exits non-zero if simulation_status == failed.
"""

from __future__ import annotations

import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from sakurascore_sim import run_simulation, run_simulation_from_file  # noqa: E402
from sakurascore_sim.simulation.results import validate_output  # noqa: E402


def make_summary(output: dict) -> str:
    lines: list[str] = []
    ip = output.get("title", output.get("ip_id", "?"))
    lines.append(f"# SakuraScore simulation summary — {ip}")
    lines.append("")
    lines.append(f"- Experiment: `{output.get('experiment_id')}` | Status: **{output.get('simulation_status')}** "
                 f"| Engine: `{output.get('engine')} v{output.get('engine_version')}`")
    lines.append(f"- ALL numeric results below are **SIMULATED** under stated assumptions "
                 f"(see output `assumptions` and `limitations`). They are not forecasts.")
    lines.append("")
    lines.append("## Scenario headline metrics (seed = configuration seed)")
    lines.append("")
    lines.append("| Scenario | Languages | Reach rate | View rate | Engagement rate | Shares | Discussions |")
    lines.append("|---|---|---|---|---|---|---|")
    for sc in output.get("scenarios", []):
        t = sc["totals"]
        langs = ", ".join(sc["languages_available"])
        lines.append(f"| {sc['label']} | {langs} | {t['reach_rate']:.1%} | {t['view_rate']:.1%} "
                     f"| {t['engagement_rate']:.1%} | {t['shares_total']} | {t['discussions_total']} |")
    lines.append("")
    for sc in output.get("scenarios", []):
        if "variability" in sc:
            v = sc["variability"]
            lines.append(f"**Variability** ({v['repetitions']} seeds {v['seeds']}): engagement_rate "
                         f"mean {v['engagement_rate']['mean']:.1%} ± {v['engagement_rate']['std']:.1%} "
                         f"[min {v['engagement_rate']['min']:.1%}, max {v['engagement_rate']['max']:.1%}] — simulated.")
            lines.append("")
    lines.append("## Paired scenario comparison (same seeds, identical populations)")
    lines.append("")
    for cmp in output.get("comparisons", []):
        lines.append(f"### {cmp['scenario_id']} vs {cmp['baseline_id']} ({cmp['repetitions']} paired repetitions)")
        lines.append("")
        lines.append("| Metric | Baseline mean | Comparison mean | Δ mean | Relative lift |")
        lines.append("|---|---|---|---|---|")
        for key, m in cmp["metrics"].items():
            bl = m["baseline_mean"]
            cl = m["comparison_mean"]
            dm = m["delta_mean"]
            rl = m["relative_lift_mean"]
            fmt = (lambda x: f"{x:.1%}") if key.endswith("rate") else (lambda x: f"{x:.2f}")
            lines.append(f"| {key} | {fmt(bl) if bl is not None else '—'} | {fmt(cl) if cl is not None else '—'} "
                         f"| {fmt(dm) if dm is not None else '—'} | {f'{rl:+.1%}' if rl is not None else '—'} |")
        lines.append("")
        for d in cmp.get("drivers", []):
            lines.append(f"- Driver: `{d['parameter']}` → {d['engine_assumption']}")
        lines.append("")
        seg = cmp.get("per_segment_engagement_delta", {})
        if seg:
            lines.append("Per-segment engagement-rate delta (simulated): " +
                         ", ".join(f"`{k}` {v['engagement_rate_delta_mean']:+.1%}" for k, v in sorted(seg.items())))
            lines.append("")
    lines.append("## Key assumptions (all labelled simulated/inferred in the JSON)")
    for a in output.get("assumptions", [])[:6]:
        ev = f" (evidence: {', '.join(a.get('evidence_ids', []))})" if a.get("evidence_ids") else ""
        lines.append(f"- **{a['id']}**: {a['statement']}{ev}")
    lines.append("")
    lines.append("## Limitations (excerpt)")
    for l in output.get("limitations", [])[:4]:
        lines.append(f"- [{l['severity']}] {l['statement']}")
    lines.append("")
    n_sources = len(output.get("source_references", []))
    lines.append(f"## Evidence base: {n_sources} cited source(s) in `source_references` "
                 f"(all labelled observed/inferred, with URL + date).")
    if output.get("warnings"):
        lines.append("")
        lines.append("## Warnings")
        for w in output["warnings"]:
            lines.append(f"- `{w.get('code')}`: {w.get('message')}")
    return "\n".join(lines)


def main() -> int:
    config_path = REPO_ROOT + "/configs/example_experiment.json"
    out_dir = os.path.join(REPO_ROOT, "results")
    args = [a for a in sys.argv[1:]]
    if args and not args[0].startswith("--"):
        config_path = os.path.abspath(args[0])
        args = args[1:]
    if "--out" in args:
        out_dir = os.path.abspath(args[args.index("--out") + 1])
    os.makedirs(out_dir, exist_ok=True)

    print(f"[sakurascore] config: {config_path}")
    output = run_simulation_from_file(config_path)

    problems = validate_output(output)
    if problems:
        print("[sakurascore] OUTPUT CONTRACT PROBLEMS:", *problems, sep="\n  - ")

    exp = output.get("experiment_id", "experiment")
    out_json = os.path.join(out_dir, f"{exp}_output.json")
    out_md = os.path.join(out_dir, f"{exp}_summary.md")
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write(make_summary(output))

    status = output.get("simulation_status")
    print(f"[sakurascore] status: {status}")
    print(f"[sakurascore] wrote: {out_json}")
    print(f"[sakurascore] wrote: {out_md}")

    for cmp in output.get("comparisons", []):
        m = cmp["metrics"]["engagement_rate"]
        print(f"[sakurascore] engagement_rate: {cmp['scenario_id']} vs baseline {cmp['baseline_id']}: "
              f"{m['baseline_mean']:.1%} -> {m['comparison_mean']:.1%} "
              f"(Δ {m['delta_mean']:+.1%} relative, mean of {m['repetitions']} paired seeds)")

    return 1 if status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
