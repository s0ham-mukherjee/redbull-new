#!/usr/bin/env python3
"""Debug: verify the stream-alignment invariant (engaged_B >= engaged_A per seed)."""
import sys, os, json
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from sakurascore_sim.models import validate_input
from sakurascore_sim.research.evidence_loader import merge_evidence
from sakurascore_sim.adapters import abm_engine

cfg = json.load(open(os.path.join(REPO_ROOT, "configs/example_experiment.json")))
merged = merge_evidence(cfg, config_dir=os.path.join(REPO_ROOT, "configs"))
parsed = validate_input(merged)

scen = {s.id: s for s in parsed.scenarios}
A, B = scen["baseline-subs-only"], scen["regional-dub"]

bad = []
for seed in range(42, 142):
    ra = abm_engine.run_scenario(parsed, A, seed)
    rb = abm_engine.run_scenario(parsed, B, seed)
    ea, eb = ra["totals"]["engaged"], rb["totals"]["engaged"]
    sa, sb = ra["totals"]["reach"], rb["totals"]["reach"]
    if eb < ea or sb < sa:
        bad.append((seed, sa, ea, sb, eb))

print(f"violations across seeds 42..141: {len(bad)}")
for row in bad[:10]:
    print("  seed=%d reachA=%d engA=%d reachB=%d engB=%d" % row)
