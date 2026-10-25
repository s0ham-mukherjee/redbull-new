"""Core data models and strict input validation for the SakuraScore simulation subsystem.

The input contract (schema v1.0) mirrors docs/INTEGRATION_GUIDE.md and
schemas/input.schema.v1.json. Validation errors raise ConfigError with a stable
machine-readable ``code`` so teammates can branch on failures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_VERSION = "1.0"

# Language codes accepted in ``languages_available`` and segment language maps.
# BCP-47 style; extend only with a documented reason (see SIMULATION_METHODOLOGY.md).
KNOWN_LANGUAGES = {
    "ja": "Japanese (original, subbed)",
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "bn": "Bengali",
    "kn": "Kannada",
    "ml": "Malayalam",
}

# Non-original, non-English languages are treated as "regional" for the dub-lift rule.
REGIONAL_LANGUAGES = {"hi", "ta", "te", "mr", "bn", "kn", "ml"}

# Labelling vocabulary (Part 13 of the project brief): every displayed number must
# carry exactly one of these labels.
DATA_LABELS = ("observed", "inferred", "simulated", "unknown")

SCENARIO_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-_]{0,63}$")
IP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-_]{1,63}$")
DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")  # YYYY | YYYY-MM | YYYY-MM-DD


class ValidationError(Exception):
    """Raised for programmer-facing internal invariant violations."""


class ConfigError(Exception):
    """Input configuration is invalid. Carries a stable machine-readable code."""

    def __init__(self, code: str, message: str, field: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "field": self.field,
                "details": self.details}


class ErrorCodes:
    SCHEMA_VERSION = "SCHEMA_VERSION_UNSUPPORTED"
    MISSING_FIELD = "MISSING_REQUIRED_FIELD"
    BAD_TYPE = "BAD_FIELD_TYPE"
    BAD_VALUE = "BAD_FIELD_VALUE"
    BAD_ID = "BAD_IDENTIFIER"
    DUPLICATE = "DUPLICATE_ID"
    EMPTY_SEGMENTS = "AUDIENCE_SEGMENTS_EMPTY"
    SEGMENT_SHARES = "SEGMENT_SHARES_NOT_1"
    BAD_LANGUAGE = "UNKNOWN_LANGUAGE"
    BAD_SCENARIO = "INVALID_SCENARIO"
    EVIDENCE_REF = "UNKNOWN_EVIDENCE_REFERENCE"
    EVIDENCE_ITEM = "INVALID_EVIDENCE_ITEM"
    SIM_PARAMS = "INVALID_SIMULATION_PARAMS"
    ENGINE_UNAVAILABLE = "ENGINE_UNAVAILABLE"


@dataclass
class EvidenceItem:
    id: str
    title: str
    url: str
    publisher: str
    date: str
    finding: str
    type: str                      # market_report | news | box_office | survey | community | official
    region: str                    # "India" | "global" | ...
    label: str                     # observed | inferred  (evidence itself is never "simulated")
    quality: str                   # high | medium | low
    tags: List[str] = field(default_factory=list)
    source_id: Optional[str] = None
    retrieved_via: Optional[str] = None
    retrieved_at: Optional[str] = None


@dataclass
class AudienceSegment:
    id: str
    label: str
    size_share: float
    base_interest: float
    discovery_base: float
    view_info_prob: float
    share_prob: float
    discuss_prob: float
    language_affinity: Dict[str, float]
    channel_affinity: Dict[str, float]
    evidence_ids: List[str] = field(default_factory=list)
    notes: str = ""
    hypothesis_label: str = "modelling hypothesis"


@dataclass
class Scenario:
    id: str
    label: str
    languages_available: List[str]
    marketing_reach: Dict[str, float]
    counterfactual: bool = False
    is_baseline: bool = False
    description: str = ""


@dataclass
class SimulationParams:
    agent_count: int = 20
    rounds: int = 5
    seed: int = 42
    seeds: Optional[List[int]] = None          # variability ensemble; None => [seed]
    network_degree: int = 3
    word_of_mouth_boost: float = 0.8
    announcement_boost: float = 2.0
    dub_lift: float = 1.6
    discovery_cap: float = 0.95
    variability: bool = False


@dataclass
class SimulationInput:
    schema_version: str
    ip_id: str
    title: str
    experiment_id: str
    media_type: str
    genre: str
    evidence: List[EvidenceItem]
    audience_segments: List[AudienceSegment]
    scenarios: List[Scenario]
    simulation: SimulationParams
    engine: str = "auto"
    notes: str = ""
    options: Dict[str, Any] = field(default_factory=dict)
    warnings: List[Dict[str, Any]] = field(default_factory=list)


# --------------------------------------------------------------------------
# validation helpers
# --------------------------------------------------------------------------

def _require(data: Dict[str, Any], key: str, expected_type, ctx: str) -> Any:
    if key not in data or data[key] is None:
        raise ConfigError(ErrorCodes.MISSING_FIELD,
                          f"'{key}' is required in {ctx}.", field=f"{ctx}.{key}")
    value = data[key]
    if expected_type is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if expected_type is not bool and isinstance(value, bool):
        raise ConfigError(ErrorCodes.BAD_TYPE, f"'{key}' in {ctx} must be {expected_type.__name__}.",
                          field=f"{ctx}.{key}")
    if not isinstance(value, expected_type):
        raise ConfigError(ErrorCodes.BAD_TYPE, f"'{key}' in {ctx} must be {expected_type.__name__}.",
                          field=f"{ctx}.{key}")
    return value


def _prob(value: float, name: str, ctx: str) -> float:
    if not (0.0 <= value <= 1.0):
        raise ConfigError(ErrorCodes.BAD_VALUE,
                          f"'{name}' in {ctx} must be within [0, 1]; got {value}.",
                          field=f"{ctx}.{name}", details={"got": value})
    return float(value)


def _id(value: str, name: str, ctx: str, pattern=SCENARIO_ID_RE) -> str:
    if not isinstance(value, str) or not pattern.match(value):
        raise ConfigError(ErrorCodes.BAD_ID,
                          f"'{name}' in {ctx} must match {pattern.pattern} (lowercase, digits, '-', '_').",
                          field=f"{ctx}.{name}", details={"got": value})
    return value


def _validate_evidence_item(item: Dict[str, Any], index: int) -> EvidenceItem:
    ctx = f"evidence[{index}]"
    for req in ("id", "title", "url", "publisher", "date", "finding", "type", "region", "label", "quality"):
        _require(item, req, str, ctx)
    ev_id = item["id"].strip()
    if not ev_id or not re.match(r"^[a-z0-9][a-z0-9-]{1,63}$", ev_id):
        raise ConfigError(ErrorCodes.BAD_ID, f"evidence id {item['id']!r} must be kebab-case.",
                          field=f"{ctx}.id")
    if not str(item["url"]).startswith(("http://", "https://")):
        raise ConfigError(ErrorCodes.BAD_VALUE, f"evidence '{ev_id}' url must be http(s).",
                          field=f"{ctx}.url")
    if not DATE_RE.match(str(item["date"])):
        raise ConfigError(ErrorCodes.BAD_VALUE, f"evidence '{ev_id}' date must be YYYY-MM or YYYY-MM-DD.",
                          field=f"{ctx}.date")
    if item["label"] not in ("observed", "inferred"):
        raise ConfigError(ErrorCodes.BAD_VALUE,
                          f"evidence '{ev_id}' label must be 'observed' or 'inferred'.",
                          field=f"{ctx}.label", details={"got": item["label"]})
    if item["quality"] not in ("high", "medium", "low"):
        raise ConfigError(ErrorCodes.BAD_VALUE,
                          f"evidence '{ev_id}' quality must be high|medium|low.",
                          field=f"{ctx}.quality")
    tags = item.get("tags", [])
    if not isinstance(tags, list):
        raise ConfigError(ErrorCodes.BAD_TYPE, f"evidence '{ev_id}' tags must be a list.",
                          field=f"{ctx}.tags")
    return EvidenceItem(
        id=ev_id, title=item["title"], url=item["url"], publisher=item["publisher"],
        date=str(item["date"]), finding=item["finding"], type=item["type"],
        region=item["region"], label=item["label"], quality=item["quality"],
        tags=[str(t) for t in tags], source_id=item.get("source_id"),
        retrieved_via=item.get("retrieved_via"), retrieved_at=item.get("retrieved_at"),
    )


def _validate_segment(seg: Dict[str, Any], index: int, evidence_ids: set) -> AudienceSegment:
    ctx = f"audience_segments[{index}]"
    _require(seg, "id", str, ctx)
    _require(seg, "label", str, ctx)
    sid = _id(seg["id"], "id", ctx)
    size = _require(seg, "size_share", float, ctx)
    if not (0.0 < size <= 1.0):
        raise ConfigError(ErrorCodes.SEGMENT_SHARES,
                          f"segment '{sid}' size_share must be in (0, 1]; got {size}.",
                          field=f"{ctx}.size_share", details={"got": size})
    base_interest = _prob(_require(seg, "base_interest", float, ctx), "base_interest", ctx)
    discovery = _prob(_require(seg, "discovery_base", float, ctx), "discovery_base", ctx)
    view_p = _prob(_require(seg, "view_info_prob", float, ctx), "view_info_prob", ctx)
    share_p = _prob(_require(seg, "share_prob", float, ctx), "share_prob", ctx)
    disc_p = _prob(_require(seg, "discuss_prob", float, ctx), "discuss_prob", ctx)

    lang = _require(seg, "language_affinity", dict, ctx)
    if not lang:
        raise ConfigError(ErrorCodes.BAD_VALUE, f"segment '{sid}' language_affinity must be non-empty.",
                          field=f"{ctx}.language_affinity")
    for code, val in lang.items():
        if code not in KNOWN_LANGUAGES:
            raise ConfigError(ErrorCodes.BAD_LANGUAGE,
                              f"segment '{sid}' uses unknown language '{code}'. Known: {sorted(KNOWN_LANGUAGES)}.",
                              field=f"{ctx}.language_affinity", details={"got": code})
        _prob(float(val), f"language_affinity.{code}", ctx)

    chan = _require(seg, "channel_affinity", dict, ctx)
    if not chan:
        raise ConfigError(ErrorCodes.BAD_VALUE, f"segment '{sid}' channel_affinity must be non-empty.",
                          field=f"{ctx}.channel_affinity")
    for chan_name, val in chan.items():
        if not isinstance(chan_name, str) or not chan_name:
            raise ConfigError(ErrorCodes.BAD_VALUE, f"segment '{sid}' has invalid channel name.",
                              field=f"{ctx}.channel_affinity")
        _prob(float(val), f"channel_affinity.{chan_name}", ctx)

    ev_refs = seg.get("evidence_ids", [])
    if not isinstance(ev_refs, list):
        raise ConfigError(ErrorCodes.BAD_TYPE, f"segment '{sid}' evidence_ids must be a list.",
                          field=f"{ctx}.evidence_ids")
    for ref in ev_refs:
        if ref not in evidence_ids:
            raise ConfigError(ErrorCodes.EVIDENCE_REF,
                              f"segment '{sid}' references unknown evidence id '{ref}'.",
                              field=f"{ctx}.evidence_ids", details={"got": ref})

    return AudienceSegment(
        id=sid, label=seg["label"], size_share=size, base_interest=base_interest,
        discovery_base=discovery, view_info_prob=view_p, share_prob=share_p,
        discuss_prob=disc_p, language_affinity={k: float(v) for k, v in lang.items()},
        channel_affinity={k: float(v) for k, v in chan.items()},
        evidence_ids=[str(r) for r in ev_refs], notes=str(seg.get("notes", "")),
    )


def _validate_scenario(sc: Dict[str, Any], index: int) -> Scenario:
    ctx = f"scenarios[{index}]"
    _require(sc, "id", str, ctx)
    scid = _id(sc["id"], "id", ctx)
    label = _require(sc, "label", str, ctx)

    langs = _require(sc, "languages_available", list, ctx)
    if not langs:
        raise ConfigError(ErrorCodes.BAD_SCENARIO,
                          f"scenario '{scid}' must offer at least one language.",
                          field=f"{ctx}.languages_available")
    for code in langs:
        if code not in KNOWN_LANGUAGES:
            raise ConfigError(ErrorCodes.BAD_LANGUAGE,
                              f"scenario '{scid}' offers unknown language '{code}'.",
                              field=f"{ctx}.languages_available", details={"got": code})

    marketing = _require(sc, "marketing_reach", dict, ctx)
    if not marketing:
        raise ConfigError(ErrorCodes.BAD_SCENARIO,
                          f"scenario '{scid}' marketing_reach must be non-empty.",
                          field=f"{ctx}.marketing_reach")
    for chan_name, mult in marketing.items():
        if not isinstance(chan_name, str) or not chan_name:
            raise ConfigError(ErrorCodes.BAD_VALUE, f"scenario '{scid}' has invalid marketing channel.",
                              field=f"{ctx}.marketing_reach")
        if not (0.0 <= float(mult)):
            raise ConfigError(ErrorCodes.BAD_VALUE,
                              f"scenario '{scid}' marketing_reach['{chan_name}'] must be >= 0.",
                              field=f"{ctx}.marketing_reach")

    return Scenario(
        id=scid, label=label, languages_available=[str(c) for c in langs],
        marketing_reach={k: float(v) for k, v in marketing.items()},
        counterfactual=bool(sc.get("counterfactual", False)),
        is_baseline=bool(sc.get("is_baseline", False)),
        description=str(sc.get("description", "")),
    )


def _validate_simulation_params(sim: Dict[str, Any]) -> Tuple[SimulationParams, List[Dict[str, Any]]]:
    if not isinstance(sim, dict):
        raise ConfigError(ErrorCodes.SIM_PARAMS, "'simulation' must be an object.", field="simulation")
    warnings: List[Dict[str, Any]] = []

    agent_count = sim.get("agent_count", 20)
    if not isinstance(agent_count, int) or isinstance(agent_count, bool) or not (2 <= agent_count <= 5000):
        raise ConfigError(ErrorCodes.SIM_PARAMS,
                          "simulation.agent_count must be an integer in [2, 5000].",
                          field="simulation.agent_count", details={"got": agent_count})
    rounds = sim.get("rounds", 5)
    if not isinstance(rounds, int) or isinstance(rounds, bool) or not (1 <= rounds <= 100):
        raise ConfigError(ErrorCodes.SIM_PARAMS,
                          "simulation.rounds must be an integer in [1, 100].",
                          field="simulation.rounds", details={"got": rounds})
    seed = sim.get("seed", 42)
    if not isinstance(seed, int) or isinstance(seed, bool) or not (0 <= seed < 2**31):
        raise ConfigError(ErrorCodes.SIM_PARAMS,
                          "simulation.seed must be an integer in [0, 2^31).",
                          field="simulation.seed", details={"got": seed})

    seeds = sim.get("seeds")
    variability = bool(sim.get("variability", False))
    if seeds is not None:
        if not isinstance(seeds, list) or not all(isinstance(s, int) and not isinstance(s, bool) for s in seeds):
            raise ConfigError(ErrorCodes.SIM_PARAMS, "simulation.seeds must be a list of integers.",
                              field="simulation.seeds")
        if len(seeds) > 25:
            warnings.append({"code": "SEEDS_TRUNCATED",
                             "message": "simulation.seeds capped at 25 entries for runtime."})
            seeds = seeds[:25]
    elif variability:
        seeds = [seed + i for i in range(5)]

    degree = sim.get("network_degree", 3)
    if not isinstance(degree, int) or isinstance(degree, bool) or not (1 <= degree <= 20):
        raise ConfigError(ErrorCodes.SIM_PARAMS, "simulation.network_degree must be an integer in [1, 20].",
                          field="simulation.network_degree")
    wom = float(sim.get("word_of_mouth_boost", 0.8))
    if not (0.0 <= wom <= 3.0):
        raise ConfigError(ErrorCodes.SIM_PARAMS, "simulation.word_of_mouth_boost must be in [0, 3].",
                          field="simulation.word_of_mouth_boost")
    ann = float(sim.get("announcement_boost", 2.0))
    if not (0.0 <= ann <= 10.0):
        raise ConfigError(ErrorCodes.SIM_PARAMS, "simulation.announcement_boost must be in [0, 10].",
                          field="simulation.announcement_boost")
    dub = float(sim.get("dub_lift", 1.6))
    if not (1.0 <= dub <= 3.0):
        raise ConfigError(ErrorCodes.SIM_PARAMS, "simulation.dub_lift must be in [1, 3] (a lift, never a penalty).",
                          field="simulation.dub_lift")
    cap = float(sim.get("discovery_cap", 0.95))
    if not (0.0 < cap <= 1.0):
        raise ConfigError(ErrorCodes.SIM_PARAMS, "simulation.discovery_cap must be in (0, 1].",
                          field="simulation.discovery_cap")

    params = SimulationParams(
        agent_count=agent_count, rounds=rounds, seed=seed, seeds=seeds,
        network_degree=degree, word_of_mouth_boost=wom, announcement_boost=ann,
        dub_lift=dub, discovery_cap=cap, variability=variability,
    )
    return params, warnings


def validate_input(data: Dict[str, Any]) -> SimulationInput:
    """Validate a raw config dict and return a typed SimulationInput.

    Raises ConfigError (stable .code) on any invalid input. Non-fatal issues are
    collected into SimulationInput.warnings (e.g. empty evidence list).
    """
    if not isinstance(data, dict):
        raise ConfigError(ErrorCodes.BAD_TYPE, "Configuration root must be a JSON object.")

    version = _require(data, "schema_version", str, "root")
    if version != SCHEMA_VERSION:
        raise ConfigError(ErrorCodes.SCHEMA_VERSION,
                          f"schema_version must be '{SCHEMA_VERSION}'; got '{version}'. "
                          f"This subsystem implements schema {SCHEMA_VERSION} only.",
                          field="schema_version", details={"got": version, "supported": [SCHEMA_VERSION]})

    ip_id = data.get("ip_id")
    if not isinstance(ip_id, str) or not IP_ID_RE.match(ip_id):
        raise ConfigError(ErrorCodes.BAD_ID,
                          "'ip_id' must match " + IP_ID_RE.pattern + " (kebab-case).",
                          field="ip_id", details={"got": ip_id})
    title = _require(data, "title", str, "root")
    experiment_id = data.get("experiment_id", "experiment")
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ConfigError(ErrorCodes.BAD_ID, "'experiment_id' must be a non-empty string.",
                          field="experiment_id")
    media_type = data.get("media_type", "anime_film")
    genre = data.get("genre", "unspecified")
    engine = data.get("engine", "auto")
    if engine not in ("auto", "abm"):
        raise ConfigError(ErrorCodes.ENGINE_UNAVAILABLE,
                          f"engine '{engine}' is not available. Installed engines: ['abm']. "
                          "See docs/REPOSITORY_EVALUATION.md for the OASIS/MiroFish adapter path.",
                          field="engine", details={"got": engine, "available": ["abm"]})

    # --- evidence ---------------------------------------------------------
    evidence_raw = data.get("evidence", [])
    if not isinstance(evidence_raw, list):
        raise ConfigError(ErrorCodes.BAD_TYPE, "'evidence' must be a list.", field="evidence")
    evidence: List[EvidenceItem] = []
    seen_ev: set = set()
    for i, item in enumerate(evidence_raw):
        ev = _validate_evidence_item(item, i)
        if ev.id in seen_ev:
            raise ConfigError(ErrorCodes.DUPLICATE, f"duplicate evidence id '{ev.id}'.",
                              field=f"evidence[{i}].id")
        seen_ev.add(ev.id)
        evidence.append(ev)

    warnings: List[Dict[str, Any]] = []
    if not evidence:
        warnings.append({
            "code": "EVIDENCE_EMPTY",
            "message": "No evidence entries supplied; segment assumptions will carry no "
                       "source references and result limitations will be strengthened.",
        })

    # --- audience segments -------------------------------------------------
    segs_raw = data.get("audience_segments", [])
    if not isinstance(segs_raw, list) or not segs_raw:
        raise ConfigError(ErrorCodes.EMPTY_SEGMENTS,
                          "'audience_segments' must be a non-empty list: the simulation cannot "
                          "run without audience assumptions.",
                          field="audience_segments")
    segments: List[AudienceSegment] = []
    seen_seg: set = set()
    for i, seg in enumerate(segs_raw):
        s = _validate_segment(seg, i, seen_ev)
        if s.id in seen_seg:
            raise ConfigError(ErrorCodes.DUPLICATE, f"duplicate audience segment id '{s.id}'.",
                              field=f"audience_segments[{i}].id")
        seen_seg.add(s.id)
        segments.append(s)
    total_share = sum(s.size_share for s in segments)
    if abs(total_share - 1.0) > 0.01:
        raise ConfigError(ErrorCodes.SEGMENT_SHARES,
                          f"audience_segments size_share must sum to 1.0 (tolerance 0.01); sum is {total_share:.4f}.",
                          field="audience_segments", details={"sum": round(total_share, 4)})

    # --- scenarios ---------------------------------------------------------
    scen_raw = data.get("scenarios", [])
    if not isinstance(scen_raw, list) or not scen_raw:
        raise ConfigError(ErrorCodes.BAD_SCENARIO,
                          "'scenarios' must be a non-empty list (at least a baseline).",
                          field="scenarios")
    scenarios: List[Scenario] = []
    seen_sc: set = set()
    for i, sc in enumerate(scen_raw):
        s = _validate_scenario(sc, i)
        if s.id in seen_sc:
            raise ConfigError(ErrorCodes.DUPLICATE, f"duplicate scenario id '{s.id}'.",
                              field=f"scenarios[{i}].id")
        seen_sc.add(s.id)
        scenarios.append(s)

    sim_params, sim_warnings = _validate_simulation_params(data.get("simulation", {}))
    warnings.extend(sim_warnings)

    return SimulationInput(
        schema_version=version, ip_id=ip_id, title=title, experiment_id=experiment_id,
        media_type=media_type, genre=genre, evidence=evidence, audience_segments=segments,
        scenarios=scenarios, simulation=sim_params, engine=engine,
        notes=str(data.get("notes", "")), options=dict(data.get("options", {})),
        warnings=warnings,
    )
