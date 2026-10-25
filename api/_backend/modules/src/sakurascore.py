"""Engine-facing facade: contracts + providers in one import.

Importing this package registers every provider (lazy factories only).
"""

from __future__ import annotations

import providers  # noqa: F401
from engine_api import (  # noqa: F401
    KINDS,
    Action,
    Directive,
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
    available,
    provider,
    registry,
)
