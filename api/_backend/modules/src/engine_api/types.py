"""Neutral data contracts shared by the engine and every provider module.

No upstream project names appear here; providers translate their native
outputs into these types at the boundary.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Query:
    """A provider-agnostic research request."""

    text: str
    ip_id: str | None = None
    region: str | None = None
    languages: tuple[str, ...] = ()
    since: datetime | None = None
    limit: int = 50
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Evidence:
    """One provenance-bearing observation from a single source."""

    source: str
    url: str
    content: str
    retrieved_at: datetime = field(default_factory=utcnow)
    content_hash: str = ""
    title: str | None = None
    published_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.content_hash:
            object.__setattr__(self, "content_hash", content_hash(self.content))


@dataclass(frozen=True)
class Document:
    """A crawled page rendered to clean text/markdown."""

    url: str
    text: str
    status: int = 200
    crawled_at: datetime = field(default_factory=utcnow)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Signal:
    """A single normalized time-series observation (trend, pageviews, ...)."""

    name: str
    value: float
    region: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    source: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Knowledge graph
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class IPNode:
    """Canonical node for one intellectual property (title/franchise)."""

    id: str
    title: str
    kind: str = "anime"  # anime | manga | light_novel | movie | franchise
    genres: tuple[str, ...] = ()
    studio: str | None = None
    adaptation_of: str | None = None
    aliases: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Relation:
    src: str
    dst: str
    kind: str  # adapted_from | sequel | produced_by | ...
    provenance: Evidence | None = None


# --------------------------------------------------------------------------
# Forecasting & decisions
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Interval:
    """A conformal / calibrated prediction interval for one target."""

    point: float
    lower: float
    upper: float
    alpha: float = 0.10


@dataclass(frozen=True)
class Forecast:
    target: str
    interval: Interval
    n_calibration_samples: int = 0
    ready: bool = True
    reason: str | None = None  # why not ready, when ready is False


class Action(str, Enum):
    PILOT = "pilot"
    INVESTIGATE = "investigate"
    WAIT = "wait"
    ABSTAIN = "abstain"


@dataclass(frozen=True)
class Directive:
    """Final output of the decision layer."""

    ip_id: str
    action: Action
    opportunity_score: float
    rationale: str
    forecast: Forecast | None = None
    evidence: tuple[Evidence, ...] = ()


# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Persona:
    """A synthetic audience member (regional Indian profile by default)."""

    id: str
    tier: str = "tier_2"  # tier_1 | tier_2 | tier_3
    location: str | None = None
    languages: tuple[str, ...] = ("hi",)
    preferred_formats: tuple[str, ...] = ("dub",)  # dub | sub | manga
    genres: tuple[str, ...] = ("shonen",)
    disposable_income_inr: float = 8000.0
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    """What the swarm is asked to debate / forecast."""

    id: str
    ip_id: str
    prompt: str
    price_points_inr: Mapping[str, float] = field(default_factory=dict)
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentTurn:
    agent_id: str
    stance: str
    text: str
    cited_evidence: tuple[str, ...] = ()  # Evidence.content_hash values
    step: int = 0


@dataclass(frozen=True)
class SimulationReport:
    scenario_id: str
    seed: int
    turns: tuple[AgentTurn, ...]
    demand_distribution: Mapping[str, float] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationResult:
    passed: bool
    score: float
    details: Mapping[str, Any] = field(default_factory=dict)
