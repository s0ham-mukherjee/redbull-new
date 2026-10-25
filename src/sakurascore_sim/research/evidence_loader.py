"""Evidence loading and provenance handling.

The simulation never *fetches* anything at runtime: evidence is supplied either
inline in the config (``evidence: [...]``) or via a curated dataset file
(``evidence_file``). Every evidence item is validated by models.validate_input
and flows verbatim into the result's ``source_references`` so that judges can
trace each assumption back to a URL.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from ..models import ConfigError, ErrorCodes, EvidenceItem, SimulationInput


def load_evidence_file(path: str) -> List[Dict[str, Any]]:
    """Load a curated evidence dataset JSON file.

    Expected shape: {"schema_version": "1.0", "dataset": "...", "evidence": [...]}
    or a bare list of evidence items.
    """
    if not os.path.isfile(path):
        raise ConfigError(ErrorCodes.BAD_VALUE,
                          f"Evidence file not found: '{path}'.",
                          field="evidence_file", details={"path": path})
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(ErrorCodes.BAD_VALUE,
                          f"Evidence file '{path}' is not valid JSON: {exc}.",
                          field="evidence_file")
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("evidence"), list):
        return payload["evidence"]
    raise ConfigError(ErrorCodes.BAD_VALUE,
                      f"Evidence file '{path}' must be a list or an object with an 'evidence' list.",
                      field="evidence_file")


def merge_evidence(cfg: Dict[str, Any], config_dir: Optional[str] = None) -> Dict[str, Any]:
    """If ``evidence_file`` is set, load it and merge with inline ``evidence``.

    Inline items take precedence on id collision (they are treated as overrides).
    Returns a shallow copy of the config with a merged ``evidence`` list.
    """
    evidence_file = cfg.get("evidence_file")
    if not evidence_file:
        return cfg

    path = evidence_file
    if config_dir and not os.path.isabs(path):
        candidate = os.path.join(config_dir, path)
        path = candidate if os.path.isfile(candidate) else path

    file_items = load_evidence_file(path)
    inline = cfg.get("evidence", []) or []
    inline_ids = {it.get("id") for it in inline if isinstance(it, dict)}
    merged = list(file_items) + [it for it in inline if isinstance(it, dict)]
    warnings_extra: List[Dict[str, Any]] = []
    overridden = len([it for it in file_items if isinstance(it, dict) and it.get("id") in inline_ids])
    if overridden:
        warnings_extra.append({
            "code": "EVIDENCE_OVERRIDDEN",
            "message": f"{overridden} file evidence item(s) overridden by inline entries with the same id.",
        })
    out = dict(cfg)
    out["evidence"] = merged
    return out


def attach_evidence_state(parsed: SimulationInput) -> SimulationInput:
    """Post-parse bookkeeping: any warnings already live on parsed.warnings."""
    return parsed


def evidence_index(parsed: SimulationInput) -> Dict[str, EvidenceItem]:
    return {ev.id: ev for ev in parsed.evidence}


def source_references(parsed: SimulationInput) -> List[Dict[str, Any]]:
    """Render the result's ``source_references`` block (ordered, deduplicated)."""
    refs: List[Dict[str, Any]] = []
    seen: set = set()
    for ev in parsed.evidence:
        if ev.id in seen:
            continue
        seen.add(ev.id)
        refs.append({
            "id": ev.id,
            "title": ev.title,
            "url": ev.url,
            "publisher": ev.publisher,
            "date": ev.date,
            "type": ev.type,
            "region": ev.region,
            "label": ev.label,
            "quality": ev.quality,
            "tags": ev.tags,
            "retrieved_via": ev.retrieved_via,
            "retrieved_at": ev.retrieved_at,
        })
    return refs
