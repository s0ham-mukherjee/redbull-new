"""Provider modules: whitewashed, capability-oriented adapters.

Each module registers *lazy* factories with :mod:`engine_api.registry`.
Module import never pulls in heavy upstream dependencies; those load at
factory/use time from the ``external/`` clones (see ``_bootstrap``).

Importing this package registers every provider; nothing else is required::

    import providers
    from engine_api import registry, Query

    src = registry.create("source", "youtube", max_videos=5)
    evidence = src.fetch(Query(text="Naruto Hindi dub trailer"))
"""

from __future__ import annotations

from . import (  # noqa: F401
    anime_metadata,
    cache,
    evaluation,
    knowledge_graph,
    memory,
    nlp,
    pageviews,
    presentation,
    research_router,
    retail,
    scheduling,
    simulation,
    social,
    trends,
    uncertainty,
    web_extract,
)
from ._bootstrap import ProviderError

__all__ = ["ProviderError"]
