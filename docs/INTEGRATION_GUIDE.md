# Integration Guide

**SakuraScore India — Simulation & Research Subsystem → 80-feature SakuraScore**

This subsystem is a **library**, not a service. It takes a JSON config, returns a JSON result. No database, no API keys, no network.

---

## 1. Quickstart (60 seconds)

```bash
# from the sakurascore-simulation/ directory — no install needed (Python ≥3.10, stdlib only)
python scripts/run_experiment.py                    # runs configs/example_experiment.json
# → results/regional-dubbing-test_output.json   (full structured result)
# → results/regional-dubbing-test_summary.md    (judge-readable summary)

python -m pytest tests/ -q                          # 43 tests, <1s
```

Programmatic use from the SakuraScore backend:

```python
import sys
sys.path.insert(0, "path/to/sakurascore-simulation/src")   # or copy the package

from sakurascore_sim import run_simulation

result = run_simulation(config_dict, config_dir="path/to/configs")
assert result["simulation_status"] == "completed"
```

`run_simulation` **never raises** in default mode: invalid configs come back as a
`simulation_status: "failed"` envelope with machine-readable error codes. Pass
`strict=True` to get exceptions (useful in your tests).

## 2. What the simulation needs from the SakuraScore team

### Mandatory input fields

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `"1.0"` | only this version is accepted |
| `ip_id` | kebab-case string | your IP registry id |
| `title` | string | canonical title |
| `audience_segments[]` | list ≥1 | segment hypotheses (see schema); `size_share` must sum to 1.0 |
| `scenarios[]` | list ≥1 | release strategies; `languages_available` from the closed set |
| `simulation` | object | `agent_count` [2,5000], `rounds` [1,100], `seed`, optional `seeds[]` for variability |

### Optional input fields

| Field | Default | Notes |
|---|---|---|
| `experiment_id` | `"experiment"` | your experiment tracker id |
| `media_type`, `genre` | `"anime_film"`, `"unspecified"` | metadata only (v1.0 does not alter dynamics) |
| `evidence[]` / `evidence_file` | none | curated evidence items; `evidence_file` resolves relative to the config dir; inline items override file items on id collision |
| `engine` | `"auto"` | `"auto"`/`"abm"` → sakura-abm; other values → `ENGINE_UNAVAILABLE` (see `docs/REPOSITORY_EVALUATION.md`) |
| `simulation.seeds` / `variability` | none/false | multi-seed ensemble (≤25 seeds) |
| `simulation.network_degree`, `word_of_mouth_boost`, `announcement_boost`, `dub_lift`, `discovery_cap` | 3 / 0.8 / 2.0 / 1.6 / 0.95 | engine assumptions — document any change in your experiment notes |
| scenario `is_baseline` / `counterfactual` | false | baseline selection / realism labelling |
| `notes` | `""` | free text, echoed nowhere (keep in your tracker) |

Segment parameter reference (`audience_segments[]` items): `id`, `label`, `size_share`, `base_interest`, `discovery_base`, `view_info_prob`, `share_prob`, `discuss_prob`, `language_affinity{ja,en,hi,ta,te,mr,bn,kn,ml}`, `channel_affinity{streaming,social,theatrical,search,tv,...}`, `evidence_ids[]` (must reference supplied evidence), `notes`.

Full contract: `schemas/input.schema.v1.json` (authoritative validator: `sakurascore_sim.models.validate_input`).

## 3. What the simulation returns

Top level (full contract: `schemas/output.schema.v1.json`):

```jsonc
{
  "schema_version": "1.0",
  "ip_id": "demon-slayer-infinity-castle",
  "experiment_id": "regional-dubbing-test",
  "simulation_status": "completed",          // completed | completed_with_warnings | failed
  "engine": "sakura-abm",
  "scenarios": [ /* per-scenario metrics, per_round, per_segment, per_language, variability */ ],
  "comparisons": [ /* paired deltas vs baseline + drivers + per-segment deltas */ ],
  "assumptions": [ /* every engine assumption with values + evidence ids */ ],
  "source_references": [ /* evidence with url/publisher/date/quality/label */ ],
  "limitations": [ /* always present, incl. the critical not-a-forecast clause */ ],
  "warnings": [ /* e.g. EVIDENCE_EMPTY */ ],
  "run_metadata": { "agent_count": 40, "rounds": 6, "seeds": [42,43,44,45,46], ... }
}
```

Key blocks for the scoring team:

- `scenarios[i].totals.engagement_rate` / `reach_rate` — headline simulated metrics.
- `comparisons[j].metrics[k]` — `baseline_mean`, `comparison_mean`, `delta_mean`, `delta_std`, `relative_lift_mean` (paired across seeds).
- `comparisons[j].drivers` — which inputs differ and which assumption each activates. **Use this, not vibes, when explaining a scenario gap.**
- `assumptions[]` + `source_references[]` — the explainability chain for judges.

### Failure representation

```jsonc
{
  "simulation_status": "failed",
  "errors": [ { "code": "AUDIENCE_SEGMENTS_EMPTY", "message": "...", "field": "audience_segments", "details": {} } ],
  "scenarios": [], "comparisons": [], ...
}
```

Error codes (stable, branch on them): `SCHEMA_VERSION_UNSUPPORTED`, `MISSING_REQUIRED_FIELD`, `BAD_FIELD_TYPE`, `BAD_FIELD_VALUE`, `BAD_IDENTIFIER`, `DUPLICATE_ID`, `AUDIENCE_SEGMENTS_EMPTY`, `SEGMENT_SHARES_NOT_1`, `UNKNOWN_LANGUAGE`, `INVALID_SCENARIO`, `UNKNOWN_EVIDENCE_REFERENCE`, `INVALID_EVIDENCE_ITEM`, `INVALID_SIMULATION_PARAMS`, `ENGINE_UNAVAILABLE`.

## 4. Sample experiment (shipped, reproducible)

`configs/example_experiment.json` — Demon Slayer: Infinity Castle India,
baseline (JP+EN, counterfactual) vs regional-dub (JP+EN+HI+TA+TE, mirroring the
observed 2025-09-12 release), identical marketing, 40 agents, 6 rounds, seeds
42–46, 18 cited evidence sources. Shipped results in `results/`:

- engagement_rate 49.0% → 60.5% (+24.5% relative; positive in **all 5 paired seeds**; Δ std 5.1pp)
- lift concentrated in `regional-language-first` (+28.0pp) and `film-event-audiences` (+15.0pp); exactly 0 for `manga-first-readers` (already high EN/JA fit — mechanism sanity check)
- shares +81.9% relative (WOM amplification)

**All numbers are simulated.** Quote them only with the labelling and assumptions attached.

## 5. What is safe to display to judges

| Content | Safe? | Condition |
|---|---|---|
| Scenario comparison deltas + drivers + assumptions | ✓ | always display the `data_label_legend` and the `limitations` excerpt |
| Evidence table (source_references) | ✓ | these are observed/inferred citations with URLs |
| Absolute engagement/reach numbers as "expected outcomes" | ✗ | they are simulation outputs of hypothesised parameters |
| Any claim of predictive accuracy | ✗ | no independent validation exists |
| Segment names/sizes as "Indian demographics" | ✗ | they are modelling hypotheses |

Rule of thumb: every number shown must sit under a heading containing the word **simulated**, with the assumption panel one click away.

## 6. Dependencies & credentials

- Core: **Python ≥3.10, stdlib only. No pip installs. No env vars. No network.**
- Dev only: `pytest` (already ubiquitous) for the test suite.
- Planned (not required): Agent-Reach CLI + YouTube API key for the repeatable evidence pipeline (see `docs/RESEARCH_SOURCE_MAP.md` §4).

## 7. Coordination rules with the 80-feature roadmap

1. This subsystem does NOT own: IP registry, market data pipeline, scoring engine, frontend. It consumes a JSON config and returns a JSON result — wire it wherever "scenario simulation" appears in the roadmap.
2. Keep simulation results **separate from opportunity scores** unless we explicitly agree on a fusion contract (e.g. "simulation_engagement_delta" as one scoring feature). Nothing here writes to your score store.
3. If you need an HTTP API around this, wrap `run_simulation` yourself (FastAPI/Flask, 20 lines) — v1.0 deliberately ships a function interface to avoid process/lifecycle coupling.
4. Sample dataset for integration before real data exists: `data/evidence/india_anime_evidence.json` + `configs/example_experiment.json` are the reference fixtures.
5. Schema evolution: bump `schema_version` + add a migration note here; never reinterpret v1.0 fields silently.
