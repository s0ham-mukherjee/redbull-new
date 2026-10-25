"""engine_api - the neutral contract between a pre-existing engine and the
whitewashed provider modules in :mod:`providers`.

Engine code depends on this package only::

    from engine_api import registry, Query, Action

    source = registry.create("source", "reddit", subreddits=["AnimeIndia"])
    evidence = source.fetch(Query(text="Demon Slayer Hindi dub"))
"""

from .registry import KINDS, available, provider, registry
from .types import (
    Action,
    AgentTurn,
    Directive,
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
    content_hash,
    utcnow,
)

__all__ = [
    "KINDS",
    "available",
    "provider",
    "registry",
    "Action",
    "AgentTurn",
    "Directive",
    "Document",
    "EvaluationResult",
    "Evidence",
    "Forecast",
    "Interval",
    "IPNode",
    "Persona",
    "Query",
    "Relation",
    "Scenario",
    "Signal",
    "SimulationReport",
    "content_hash",
    "utcnow",
]
