"""Scenario comparison logic.

Comparisons are PAIRED: for repetition i, scenario X and the baseline run with
the SAME seed (identical population, graph and RNG stream). Deltas are computed
per repetition first, then aggregated across repetitions (mean / std / min / max).
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Dict, List, Optional

from ..models import Scenario, SimulationInput

METRIC_KEYS = ("reach_rate", "engagement_rate", "view_rate",
               "shares_total", "discussions_total")


def _mean(values: List[float]) -> Optional[float]:
    return round(statistics.fmean(values), 6) if values else None


def _std(values: List[float]) -> Optional[float]:
    return round(statistics.pstdev(values), 6) if len(values) > 1 else None


def _rel_lift(base: float, value: float) -> Optional[float]:
    if base == 0:
        return None
    return round((value - base) / base, 6)


def differing_parameters(baseline: Scenario, scenario: Scenario) -> List[Dict[str, Any]]:
    """List the input parameters that differ between two scenarios and the engine
    assumption each one activates."""
    drivers: List[Dict[str, Any]] = []
    added = [l for l in scenario.languages_available if l not in baseline.languages_available]
    removed = [l for l in baseline.languages_available if l not in scenario.languages_available]
    if added or removed:
        drivers.append({
            "parameter": "languages_available",
            "baseline": baseline.languages_available,
            "comparison": scenario.languages_available,
            "added": added,
            "removed": removed,
            "engine_assumption": (
                "dub_lift applied to agents whose primary language is regional and newly "
                "offered (simulation.dub_lift); language-fit modulation of discovery/interest "
                "(constants in adapters/abm_engine.py)."
                if added else "reduced language coverage (language-fit modulation)."
            ),
        })
    base_mkt = baseline.marketing_reach
    comp_mkt = scenario.marketing_reach
    if base_mkt != comp_mkt:
        changed = {k: {"baseline": base_mkt.get(k), "comparison": comp_mkt.get(k)}
                   for k in sorted(set(base_mkt) | set(comp_mkt))
                   if base_mkt.get(k) != comp_mkt.get(k)}
        drivers.append({
            "parameter": "marketing_reach",
            "baseline": base_mkt,
            "comparison": comp_mkt,
            "changed_channels": changed,
            "engine_assumption": "channel-affinity-weighted marketing multiplier in discovery probability.",
        })
    return drivers


def compare_single_run(baseline_metrics: Dict[str, Any],
                       comparison_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Paired delta for one repetition (same seed)."""
    deltas: Dict[str, Any] = {}
    for key in METRIC_KEYS:
        b = baseline_metrics["totals"][key]
        c = comparison_metrics["totals"][key]
        deltas[key] = {
            "baseline": b,
            "comparison": c,
            "delta": round(c - b, 6),
            "relative_lift": _rel_lift(b, c),
        }
    return deltas


def compare_scenarios(parsed: SimulationInput,
                      runs: Dict[str, List[Dict[str, Any]]],
                      baseline_id: str) -> List[Dict[str, Any]]:
    """Build the result ``comparisons`` block.

    ``runs`` maps scenario_id -> list of per-repetition metric dicts (one per seed).
    """
    scenarios = {s.id: s for s in parsed.scenarios}
    if baseline_id not in scenarios:
        return []
    baseline = scenarios[baseline_id]
    baseline_runs = runs.get(baseline_id, [])

    comparisons: List[Dict[str, Any]] = []
    for scenario in parsed.scenarios:
        if scenario.id == baseline_id:
            continue
        scen_runs = runs.get(scenario.id, [])
        if not baseline_runs or not scen_runs:
            continue

        paired = list(zip(baseline_runs, scen_runs))
        per_rep = [compare_single_run(b, c) for b, c in paired]

        aggregate: Dict[str, Any] = {}
        for key in METRIC_KEYS:
            deltas = [rep[key]["delta"] for rep in per_rep]
            lifts = [rep[key]["relative_lift"] for rep in per_rep if rep[key]["relative_lift"] is not None]
            base_vals = [rep[key]["baseline"] for rep in per_rep]
            comp_vals = [rep[key]["comparison"] for rep in per_rep]
            aggregate[key] = {
                "baseline_mean": _mean(base_vals),
                "comparison_mean": _mean(comp_vals),
                "delta_mean": _mean(deltas),
                "delta_std": _std(deltas),
                "delta_min": round(min(deltas), 6) if deltas else None,
                "delta_max": round(max(deltas), 6) if deltas else None,
                "relative_lift_mean": _mean(lifts),
                "repetitions": len(paired),
            }

        # per-segment engagement lift (mean across repetitions)
        seg_lift: Dict[str, Any] = {}
        seg_ids = sorted({sid for rep in scen_runs for sid in rep["per_segment"]})
        for sid in seg_ids:
            lifts = []
            for b, c in paired:
                b_seg = b["per_segment"].get(sid)
                c_seg = c["per_segment"].get(sid)
                if not b_seg or not c_seg:
                    continue
                lifts.append(c_seg["engagement_rate"] - b_seg["engagement_rate"])
            if lifts:
                seg_lift[sid] = {
                    "engagement_rate_delta_mean": _mean(lifts),
                    "delta_std": _std(lifts),
                }

        comparisons.append({
            "baseline_id": baseline_id,
            "scenario_id": scenario.id,
            "scenario_label": scenario.label,
            "is_counterfactual_baseline": baseline.counterfactual,
            "paired_seeds": True,
            "repetitions": len(paired),
            "metrics": aggregate,
            "per_segment_engagement_delta": seg_lift,
            "drivers": differing_parameters(baseline, scenario),
        })
    return comparisons
