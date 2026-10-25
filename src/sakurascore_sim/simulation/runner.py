"""Top-level orchestrator: the ``run_simulation(config) -> result`` contract.

Design:
  * dict in, dict out. In non-strict mode (default) invalid configurations do
    NOT raise — they return a structured failure envelope with machine-readable
    error codes. strict=True raises ConfigError instead (useful in tests).
  * Engine selection: ``engine: "auto" | "abm"`` -> sakura-abm. Other engines
    are rejected with a code pointing at the evaluation docs (adapter path).
  * Paired design: for repetition i, EVERY scenario runs with seeds[i] so the
    population, graph and RNG stream are identical across scenarios.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..adapters import abm_engine
from ..models import ConfigError, SimulationInput, validate_input
from ..research import evidence_loader
from . import results, scenarios as scenarios_mod


def _resolve_baseline(parsed: SimulationInput) -> str:
    """Comparison baseline: an explicitly ``is_baseline: true`` scenario wins;
    otherwise the FIRST scenario in the list (documented convention).
    ``counterfactual`` only labels realism (did this occur?), it does not select
    the baseline."""
    explicit = next((s.id for s in parsed.scenarios if s.is_baseline), None)
    if explicit:
        return explicit
    return parsed.scenarios[0].id


def run_simulation(config: Dict[str, Any], *,
                   config_dir: Optional[str] = None,
                   strict: bool = False) -> Dict[str, Any]:
    """Execute the SakuraScore audience simulation.

    Parameters
    ----------
    config: raw input dict (schemas/input.schema.v1.json)
    config_dir: base directory for resolving relative ``evidence_file`` paths
    strict: if True, raise ConfigError on invalid input instead of returning a
            failure envelope.

    Returns
    -------
    dict following schemas/output.schema.v1.json with simulation_status
    "completed", "completed_with_warnings" or "failed".
    """
    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    try:
        merged = evidence_loader.merge_evidence(config, config_dir=config_dir)
        parsed = validate_input(merged)
    except ConfigError as exc:
        if strict:
            raise
        return results.build_failure_output(config if isinstance(config, dict) else None,
                                            exc, started_at)

    try:
        seeds: List[int] = list(parsed.simulation.seeds or [parsed.simulation.seed])
        # Headline seed must be the configured seed.
        if parsed.simulation.seeds and parsed.simulation.seed not in seeds:
            seeds = [parsed.simulation.seed] + seeds

        runs: Dict[str, List[Dict[str, Any]]] = {}
        for scenario in parsed.scenarios:
            reps: List[Dict[str, Any]] = []
            for seed in seeds:
                metrics = abm_engine.run_scenario(parsed, scenario, seed)
                metrics["seed"] = seed
                reps.append(metrics)
            runs[scenario.id] = reps

        baseline_id = _resolve_baseline(parsed)
        comparisons = scenarios_mod.compare_scenarios(parsed, runs, baseline_id)

        total_ms = int((time.perf_counter() - t0) * 1000)
        output = results.build_output(parsed, runs, comparisons, baseline_id, total_ms)

        if output.get("warnings"):
            output["simulation_status"] = "completed_with_warnings"
        problems = results.validate_output(output)
        if problems:  # defensive: contract self-check
            output.setdefault("warnings", []).append({
                "code": "OUTPUT_CONTRACT_CHECK",
                "message": "Output self-validation flagged: " + "; ".join(problems),
            })
            output["simulation_status"] = "completed_with_warnings"
        return output

    except Exception as exc:  # engine failure -> structured envelope
        if strict:
            raise
        return results.build_failure_output(config if isinstance(config, dict) else None,
                                            exc, started_at)


def run_simulation_from_file(path: str, *, strict: bool = False) -> Dict[str, Any]:
    """Load a JSON config from disk and run. Relative evidence_file paths are
    resolved against the config file's directory."""
    import json
    import os

    with open(path, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    return run_simulation(config, config_dir=os.path.dirname(os.path.abspath(path)),
                          strict=strict)
