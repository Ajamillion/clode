"""Public interface for the Bagger-SPL simulation core."""

from .acoustics.sealed import (
    SealedAlignmentSummary,
    SealedBoxResponse,
    SealedBoxSolver,
)
from .acoustics.vented import (
    VentedAlignmentSummary,
    VentedBoxResponse,
    VentedBoxSolver,
)
from .drivers import BoxDesign, DriverParameters, PortGeometry, VentedBoxDesign
from .serialization import (
    dataclass_schema,
    sealed_simulation_request_schema,
    sealed_simulation_response_schema,
    sealed_simulation_schema,
    solver_json_schemas,
    vented_simulation_request_schema,
    vented_simulation_response_schema,
    vented_simulation_schema,
)
from .tolerances import (
    DEFAULT_TOLERANCES,
    MetricStats,
    ToleranceReport,
    ToleranceSpec,
    run_tolerance_analysis,
)

__all__ = [
    "DriverParameters",
    "BoxDesign",
    "PortGeometry",
    "VentedBoxDesign",
    "SealedBoxSolver",
    "SealedBoxResponse",
    "SealedAlignmentSummary",
    "VentedBoxSolver",
    "VentedBoxResponse",
    "VentedAlignmentSummary",
    "dataclass_schema",
    "sealed_simulation_request_schema",
    "sealed_simulation_response_schema",
    "sealed_simulation_schema",
    "vented_simulation_request_schema",
    "vented_simulation_response_schema",
    "vented_simulation_schema",
    "solver_json_schemas",
    "ToleranceSpec",
    "ToleranceReport",
    "MetricStats",
    "DEFAULT_TOLERANCES",
    "run_tolerance_analysis",
]
