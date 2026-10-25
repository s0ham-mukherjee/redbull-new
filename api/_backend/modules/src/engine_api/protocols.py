"""Structural contracts (typing.Protocol) the pre-existing engine consumes.

Every provider module in :mod:`providers` implements one or more of these.
The engine should depend only on this package - never on upstream APIs.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .types import (
    Document,
    EvaluationResult,
    Evidence,
    Forecast,
    Interval,
    IPNode,
    Persona,
    Query,
    Relation,
    Scenario,
    Signal,
    SimulationReport,
)


@runtime_checkable
class EvidenceSource(Protocol):
    """Fetches provenance-bearing evidence (Reddit, YouTube, web, APIs...)."""

    name: str

    def fetch(self, query: Query) -> Sequence[Evidence]: ...


@runtime_checkable
class ContentExtractor(Protocol):
    """URL -> clean Document (markdown/plain text)."""

    def extract(self, url: str) -> Document: ...


@runtime_checkable
class ResearchRouter(Protocol):
    """Multi-backend research access with health/fallback awareness."""

    def research(self, query: Query) -> Sequence[Evidence]: ...

    def health(self) -> Mapping[str, Any]: ...


@runtime_checkable
class KnowledgeStore(Protocol):
    """IP graph + audit ledger (nodes, relations, provenance)."""

    def upsert_node(self, node: IPNode) -> str: ...

    def add_relation(self, relation: Relation) -> None: ...

    def get_node(self, node_id: str) -> IPNode | None: ...

    def evidence_for(self, node_id: str) -> Sequence[Evidence]: ...


@runtime_checkable
class MemoryStore(Protocol):
    """Long-term memory for simulation personas / research agents."""

    def remember(self, session_id: str, text: str, metadata: Mapping[str, Any] | None = None) -> None: ...

    def recall(self, session_id: str, query: str, k: int = 5) -> Sequence[Evidence]: ...


@runtime_checkable
class TimeSeriesSource(Protocol):
    """Produces normalized observation signals (trends, pageviews, views)."""

    name: str

    def series(self, query: Query) -> Sequence[Signal]: ...


@runtime_checkable
class Normalizer(Protocol):
    """De-trends / normalizes raw signals against a base index."""

    def normalize(self, signals: Sequence[Signal]) -> Sequence[Signal]: ...


@runtime_checkable
class SentimentAnalyzer(Protocol):
    def analyze(self, texts: Sequence[str]) -> Sequence[float]: ...


@runtime_checkable
class TextProcessor(Protocol):
    """Multilingual (Indic / Hinglish) text handling."""

    def normalize_text(self, text: str, language: str | None = None) -> str: ...

    def detect_language(self, text: str) -> str | None: ...


@runtime_checkable
class UncertaintyEstimator(Protocol):
    """Conformal prediction wrapper: fit once, emit intervals on demand."""

    def fit(self, X: Any, y: Any) -> "UncertaintyEstimator": ...

    def interval(self, X: Any, alpha: float = 0.10) -> Sequence[Interval]: ...


@runtime_checkable
class ProbabilityCalibrator(Protocol):
    def fit(self, probabilities: Sequence[float], labels: Sequence[int]) -> "ProbabilityCalibrator": ...

    def calibrate(self, probabilities: Sequence[float]) -> Sequence[float]: ...


@runtime_checkable
class ForecastGate(Protocol):
    """Decides whether target data is sufficient to issue a forecast."""

    def ready(self, n_samples: int, min_samples: int = 30) -> bool: ...

    def forecast(self, target: str, point: float, interval: Interval, n_samples: int) -> Forecast: ...


@runtime_checkable
class Simulator(Protocol):
    """Multi-agent social simulation run."""

    def run(
        self,
        scenario: Scenario,
        personas: Sequence[Persona],
        evidence: Sequence[Evidence] = (),
        seed: int = 0,
    ) -> SimulationReport: ...


@runtime_checkable
class Evaluator(Protocol):
    """Fidelity / hallucination / bias checks against grounded evidence."""

    def evaluate(self, report: SimulationReport, evidence: Sequence[Evidence]) -> EvaluationResult: ...


@runtime_checkable
class Scheduler(Protocol):
    """Workflow orchestration for continuous ingestion/research cadence."""

    def submit(self, name: str, fn: Any, cron: str | None = None) -> str: ...

    def run(self, name: str) -> Any: ...


@runtime_checkable
class Cache(Protocol):
    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...


@runtime_checkable
class RateLimiter(Protocol):
    """Blocking/token-bucket throttle keyed by e.g. 'jikan' or 'youtube'."""

    def acquire(self, key: str, cost: float = 1.0) -> bool: ...

    def wait(self, key: str, cost: float = 1.0) -> None: ...
