"""Adapters package: pluggable simulation engines.

Currently registered: sakura-abm (deterministic, stdlib-only).
The OASIS adapter path is documented in docs/REPOSITORY_EVALUATION.md — it is
deliberately NOT stubbed here (no dead code).
"""

from . import abm_engine

ENGINES = {
    abm_engine.ENGINE_NAME: abm_engine,
}

__all__ = ["ENGINES", "abm_engine"]
