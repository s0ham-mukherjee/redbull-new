"""Provider registry.

Modules register *lazy* factories, so importing the provider package never
pulls in heavy third-party dependencies. The pre-existing engine only ever
sees this registry plus the protocols in :mod:`engine_api.protocols`.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable

# The closed set of capability kinds the engine can request.
KINDS: tuple[str, ...] = (
    "source",        # EvidenceSource        - fetch provenance-bearing evidence
    "extractor",     # ContentExtractor      - URL -> clean Document
    "router",        # ResearchRouter        - multi-backend research routing
    "store",         # KnowledgeStore        - IP graph + provenance ledger
    "memory",        # MemoryStore           - long-term agent memory
    "timeseries",    # TimeSeriesSource      - trends / pageviews signals
    "sentiment",     # SentimentAnalyzer     - text -> sentiment score(s)
    "text",          # TextProcessor         - Indic/Hinglish text handling
    "uncertainty",   # UncertaintyEstimator  - conformal intervals
    "calibrator",    # ProbabilityCalibrator - Platt / isotonic calibration
    "simulator",     # Simulator             - multi-agent swarm runs
    "evaluator",     # Evaluator             - fidelity / hallucination checks
    "scheduler",     # Scheduler             - workflow orchestration
    "cache",         # Cache                 - response / state cache
    "limiter",       # RateLimiter           - token-bucket throttling
    "normalizer",    # Normalizer            - raw trend/pageview normalization
    "gate",          # ForecastGate          - target-data readiness gate
    "app",           # FastAPI app factory   - HTTP glue for the engine
    "ui",            # Dashboard builders    - Streamlit presentation helpers
    # --- wave 2 (expanded repo set) ---
    "embedder",      # Embedder              - text/vision embeddings (IP similarity)
    "audio",         # AudioAnalyzer         - transcription & audio features
    "geo",           # GeoSource             - India boundaries / census / maps
    "drift",         # DriftDetector         - distribution/fairness monitoring
    "tracker",       # RunTracker            - experiment/version logging
    "scorer",        # ModelScorer           - attribution & causal scoring
    "forecaster",    # Forecaster            - statistical/ML forecast builders
    "preprocessor",  # Preprocessor          - dedup, language ID, cleaning
)

Factory = Callable[..., Any]


class Registry:
    def __init__(self) -> None:
        self._factories: Dict[str, Dict[str, Factory]] = {k: {} for k in KINDS}

    def register(self, kind: str, name: str, factory: Factory) -> None:
        if kind not in self._factories:
            raise KeyError(f"unknown capability kind: {kind!r} (known: {sorted(self._factories)})")
        self._factories[kind][name] = factory

    def create(self, kind: str, name: str, /, **config: Any) -> Any:
        try:
            factory = self._factories[kind][name]
        except KeyError as exc:
            raise KeyError(
                f"no provider registered for kind={kind!r} name={name!r}; "
                f"available: {sorted(self._factories.get(kind, {}))}"
            ) from exc
        return factory(**config)

    def names(self, kind: str) -> list[str]:
        return sorted(self._factories.get(kind, {}))

    def __contains__(self, item: tuple[str, str]) -> bool:
        kind, name = item
        return name in self._factories.get(kind, {})


registry = Registry()


def provider(kind: str, name: str) -> Callable[[Factory], Factory]:
    """Decorator: ``@provider("source", "reddit")`` registers a lazy factory."""

    def decorate(factory: Factory) -> Factory:
        registry.register(kind, name, factory)
        return factory

    return decorate


def available(kind: str | None = None) -> dict[str, list[str]]:
    if kind is not None:
        return {kind: registry.names(kind)}
    return {k: registry.names(k) for k in KINDS}


def iter_registered() -> Iterable[tuple[str, str]]:
    for kind in KINDS:
        for name in registry.names(kind):
            yield kind, name
