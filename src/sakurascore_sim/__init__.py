"""SakuraScore India — research & simulation subsystem.

Public interface:
    run_simulation(config) -> result          # dict-in, dict-out; never raises for config errors
    run_simulation_from_file(path) -> result
    SimulationConfigError                     # raised only in strict mode / programmatic use

See docs/INTEGRATION_GUIDE.md for the full input/output contract.
"""

__version__ = "0.1.0"

ENGINE_NAME = "sakura-abm"

from .models import (
    ConfigError,
    ErrorCodes,
    SimulationInput,
    ValidationError,
    validate_input,
)
from .simulation.runner import run_simulation, run_simulation_from_file
from .simulation.results import validate_output

__all__ = [
    "__version__",
    "ENGINE_NAME",
    "ConfigError",
    "ValidationError",
    "ErrorCodes",
    "SimulationInput",
    "validate_input",
    "validate_output",
    "run_simulation",
    "run_simulation_from_file",
]
