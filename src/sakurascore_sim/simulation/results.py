"""Result assembly and output-contract validation.

The output follows schemas/output.schema.v1.json and Part 9 of the project
brief. Every numeric block carries ``data_label``; the vocabulary is
(observed | inferred | simulated | unknown) — metrics produced by the engine are
always ``simulated``; evidence-derived references keep their own label.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..adapters.abm_engine import ENGINE_NAME, ENGINE_VERSION, engine_metadata
from ..models import DATA_LABELS, SimulationInput
from ..research.evidence_loader import source_references

SIMULATED_LABEL = "simulated"

BASE_LIMITATIONS = [
    {
        "id": "not-a-forecast",
        "statement": "Outputs are simulations of a hypothesised audience under explicit "
                     "assumptions. They are NOT predictions of real awareness, revenue, "
                     "viewership or streaming performance, and must never be presented as such.",
        "severity": "critical",
    },
    {
        "id": "synthetic-personas",
        "statement": "Agents are stochastic-threshold actors parameterised by segment "
                     "hypotheses. They do not represent real Indian consumers, and no survey "
                     "responses were collected or fabricated.",
        "severity": "critical",
    },
    {
        "id": "segment-hypotheses",
        "statement": "Audience segment sizes and behavioural parameters are modelling "
                     "hypotheses informed (where noted) by cited public evidence, not measured "
                     "demographics.",
        "severity": "high",
    },
    {
        "id": "engine-simplification",
        "statement": "sakura-abm is a compact scenario model. Unlike OASIS/MiroFish LLM agents "
                     "it cannot generate novel discourse; interaction structure (word-of-mouth "
                     "over a preferential-attachment graph) is a simplifying assumption.",
        "severity": "high",
    },
    {
        "id": "no-independent-validation",
        "statement": "Model outputs have not been validated against independent real-world "
                     "observations; only internal sanity checks and ablation tests are performed.",
        "severity": "high",
    },
]

ASSUMPTION_TEMPLATES = [
    {
        "id": "dub-lift",
        "statement": "Agents whose primary language is a regional language newly offered by a "
                     "scenario receive a multiplicative lift on interest, share and discuss "
                     "probabilities (simulation.dub_lift).",
        "role": "drives the regional-dubbing scenario effect",
        "type": "assumption",
    },
    {
        "id": "language-fit-modulation",
        "statement": "Discovery probability scales with language fit via 0.7 + 0.3*fit; "
                     "interest scales via 0.25 + 0.75*fit; agents without any offered-language "
                     "fit fall back to a 0.25 subtitle-tolerance floor.",
        "role": "translates language availability into behaviour",
        "type": "assumption",
    },
    {
        "id": "announcement-boost",
        "statement": "Round 0 models a release announcement: discovery probability is "
                     "multiplied by simulation.announcement_boost in the first round only.",
        "role": "release-attention spike",
        "type": "assumption",
    },
    {
        "id": "word-of-mouth",
        "statement": "Discovery probability is multiplied by "
                     "(1 + simulation.word_of_mouth_boost * engaged-neighbour share) over a "
                     "Barabasi-Albert preferential-attachment graph.",
        "role": "information diffusion structure",
        "type": "assumption",
    },
    {
        "id": "population-heterogeneity",
        "statement": "Personal susceptibility ~ U(0.7, 1.3) and vocalness ~ U(0.75, 1.25) are "
                     "unexplained heterogeneity drawn per agent from the seeded stream.",
        "role": "within-segment variance",
        "type": "assumption",
    },
    {
        "id": "segment-parameters",
        "statement": "Segment sizes, base_interest, discovery_base, view/share/discuss "
                     "probabilities, language and channel affinities are supplied by the "
                     "config and treated as hypotheses; each segment lists its evidence_ids.",
        "role": "audience model",
        "type": "assumption",
    },
]


def _config_hash(parsed: SimulationInput) -> str:
    canonical = json.dumps({
        "ip_id": parsed.ip_id,
        "experiment_id": parsed.experiment_id,
        "scenarios": [vars(s) for s in parsed.scenarios],
        "simulation": vars(parsed.simulation),
        "segments": [{k: v for k, v in vars(s).items() if k != "notes"} for s in parsed.audience_segments],
    }, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_assumptions(parsed: SimulationInput) -> List[Dict[str, Any]]:
    assumptions: List[Dict[str, Any]] = []
    sim = parsed.simulation
    values = {
        "dub-lift": {"dub_lift": sim.dub_lift},
        "language-fit-modulation": {"discovery": "0.7 + 0.3*fit", "interest": "0.25 + 0.75*fit",
                                     "floor": 0.25},
        "announcement-boost": {"announcement_boost": sim.announcement_boost},
        "word-of-mouth": {"word_of_mouth_boost": sim.word_of_mouth_boost,
                          "network_degree": sim.network_degree},
        "population-heterogeneity": {"susceptibility": "U(0.7,1.3)", "vocalness": "U(0.75,1.25)"},
    }
    for template in ASSUMPTION_TEMPLATES:
        entry = dict(template)
        entry["value"] = values.get(template["id"], {})
        entry["data_label"] = "simulated" if template["id"] != "segment-parameters" else "inferred"
        if template["id"] == "segment-parameters":
            evidence_ids = sorted({e for s in parsed.audience_segments for e in s.evidence_ids})
            entry["evidence_ids"] = evidence_ids
        else:
            entry["evidence_ids"] = []
        assumptions.append(entry)
    return assumptions


def _scenario_block(scenario_dict: Dict[str, Any], metrics: Dict[str, Any],
                    seed: int) -> Dict[str, Any]:
    block: Dict[str, Any] = {
        "id": scenario_dict["id"],
        "label": scenario_dict["label"],
        "description": scenario_dict.get("description", ""),
        "counterfactual": scenario_dict.get("counterfactual", False),
        "languages_available": scenario_dict["languages_available"],
        "marketing_reach": scenario_dict["marketing_reach"],
        "seed": seed,
        "data_label": SIMULATED_LABEL,
        "totals": {**metrics["totals"], "data_label": SIMULATED_LABEL},
        "per_round": metrics["per_round"],
        "per_segment": metrics["per_segment"],
        "per_language": metrics["per_language"],
        "graph": metrics["graph"],
        "duration_ms": metrics["duration_ms"],
    }
    return block


def build_output(parsed: SimulationInput,
                 runs: Dict[str, List[Dict[str, Any]]],
                 comparisons: List[Dict[str, Any]],
                 baseline_id: str,
                 total_duration_ms: int) -> Dict[str, Any]:
    """Assemble the final output dict for the Part 9 contract."""
    scenario_inputs = {s.id: vars(s) for s in parsed.scenarios}

    scenario_blocks: List[Dict[str, Any]] = []
    for scenario in parsed.scenarios:
        reps = runs.get(scenario.id, [])
        if not reps:
            continue
        primary = reps[0]  # first repetition is the headline run (seed = simulation.seed)
        block = _scenario_block(scenario_inputs[scenario.id], primary, primary["seed"])
        if len(reps) > 1:
            block["variability"] = {
                "repetitions": len(reps),
                "seeds": [r["seed"] for r in reps],
                "engagement_rate": _variability_stats([r["totals"]["engagement_rate"] for r in reps]),
                "reach_rate": _variability_stats([r["totals"]["reach_rate"] for r in reps]),
                "shares_total": _variability_stats([r["totals"]["shares_total"] for r in reps]),
                "data_label": SIMULATED_LABEL,
            }
        scenario_blocks.append(block)

    warnings = list(parsed.warnings)
    if not parsed.evidence:
        warnings.append({
            "code": "LIMITATION_STRENGTHENED",
            "message": "No evidence supplied: all assumptions are unsupported hypotheses; "
                       "results are for demonstration only.",
        })

    limitations = [dict(l) for l in BASE_LIMITATIONS]
    limitations.append({
        "id": "baseline-counterfactual",
        "statement": f"Scenario '{baseline_id}' is a counterfactual construct ({'labelled' if any(s.counterfactual for s in parsed.scenarios) else 'CHECK LABELLING'}); "
                     "it did not necessarily occur in the real world and is not derived from "
                     "observed history.",
        "severity": "high",
    })

    return {
        "schema_version": "1.0",
        "ip_id": parsed.ip_id,
        "title": parsed.title,
        "experiment_id": parsed.experiment_id,
        "simulation_status": "completed",
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "data_label_legend": {
            "observed": "figure/report taken from a cited public source",
            "inferred": "derived from cited sources by interpretation",
            "simulated": "produced by this simulation under stated assumptions",
            "unknown": "not known",
        },
        "scenarios": scenario_blocks,
        "comparisons": comparisons,
        "assumptions": build_assumptions(parsed),
        "source_references": source_references(parsed),
        "limitations": limitations,
        "warnings": warnings,
        "run_metadata": {
            **engine_metadata(),
            "agent_count": parsed.simulation.agent_count,
            "rounds": parsed.simulation.rounds,
            "seeds": sorted({seed for reps in runs.values() for r in reps for seed in [r["seed"]]}),
            "paired_design": parsed.simulation is not None and len(parsed.scenarios) > 1,
            "config_hash": _config_hash(parsed),
            "total_duration_ms": total_duration_ms,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    }


def _variability_stats(values: List[float]) -> Dict[str, Optional[float]]:
    import statistics
    if not values:
        return {"mean": None, "std": None, "min": None, "max": None}
    return {
        "mean": round(statistics.fmean(values), 6),
        "std": round(statistics.pstdev(values), 6) if len(values) > 1 else 0.0,
        "min": round(min(values), 6),
        "max": round(max(values), 6),
    }


def build_failure_output(config_or_none: Optional[Dict[str, Any]], error: Exception,
                         started_at: datetime) -> Dict[str, Any]:
    """Structured failure envelope (contract: failures never raise to the caller
    in non-strict mode)."""
    from datetime import datetime as _dt
    return {
        "schema_version": "1.0",
        "ip_id": (config_or_none or {}).get("ip_id", "unknown"),
        "experiment_id": (config_or_none or {}).get("experiment_id", "unknown"),
        "simulation_status": "failed",
        "engine": ENGINE_NAME,
        "engine_version": ENGINE_VERSION,
        "errors": [error.to_dict() if hasattr(error, "to_dict") else {"code": "INTERNAL", "message": str(error)}],
        "scenarios": [],
        "comparisons": [],
        "assumptions": [],
        "source_references": [],
        "limitations": BASE_LIMITATIONS,
        "run_metadata": {
            "failed_at": _dt.now(timezone.utc).isoformat(timespec="seconds"),
        },
    }


def validate_output(output: Dict[str, Any]) -> List[str]:
    """Validate the output contract. Returns a list of human-readable problems
    (empty list == valid). Kept dependency-free on purpose."""
    problems: List[str] = []

    for key in ("schema_version", "ip_id", "experiment_id", "simulation_status",
                "engine", "scenarios", "comparisons", "assumptions",
                "source_references", "limitations", "run_metadata"):
        if key not in output:
            problems.append(f"missing required key: {key}")
    if problems:
        return problems

    if output["schema_version"] != "1.0":
        problems.append("schema_version must be '1.0'")
    if output["simulation_status"] not in ("completed", "failed", "completed_with_warnings"):
        problems.append(f"invalid simulation_status: {output['simulation_status']}")
    if not isinstance(output["scenarios"], list):
        problems.append("'scenarios' must be a list")

    if output["simulation_status"] == "failed":
        if not output.get("errors"):
            problems.append("failed results must carry an 'errors' list")
        return problems

    if not output["scenarios"] and output["simulation_status"] == "completed":
        problems.append("completed simulation has no scenario results")

    for i, scenario in enumerate(output["scenarios"]):
        if scenario.get("data_label") != SIMULATED_LABEL:
            problems.append(f"scenarios[{i}] must be labelled '{SIMULATED_LABEL}'")
        for key in ("id", "label", "languages_available", "totals", "per_round",
                    "per_segment", "per_language"):
            if key not in scenario:
                problems.append(f"scenarios[{i}] missing key: {key}")
        if "engagement_rate" not in scenario.get("totals", {}):
            problems.append(f"scenarios[{i}].totals missing engagement_rate")
        if "data_label" not in scenario.get("totals", {}):
            problems.append(f"scenarios[{i}].totals missing data_label")

    for i, assumption in enumerate(output.get("assumptions", [])):
        if assumption.get("data_label") not in DATA_LABELS:
            problems.append(f"assumptions[{i}] has invalid data_label")

    for i, ref in enumerate(output.get("source_references", [])):
        if ref.get("label") not in ("observed", "inferred"):
            problems.append(f"source_references[{i}] label must be observed|inferred")
        if not ref.get("url", "").startswith(("http://", "https://")):
            problems.append(f"source_references[{i}] must carry an http(s) url")

    if output["simulation_status"] == "completed_with_warnings" and not output.get("warnings"):
        problems.append("status completed_with_warnings requires a 'warnings' list")

    return problems
