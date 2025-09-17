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
from .drivers import (
    DEFAULT_DRIVER,
    BoxDesign,
    DriverParameters,
    PortGeometry,
    VentedBoxDesign,
    recommended_vented_alignment,
)
from .measurements import (
    MeasurementDelta,
    MeasurementStats,
    MeasurementTrace,
    compare_measurement_to_prediction,
    measurement_from_response,
    parse_klippel_dat,
    parse_rew_mdat,
)
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
    "DEFAULT_DRIVER",
    "recommended_vented_alignment",
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
    "MeasurementTrace",
    "MeasurementDelta",
    "MeasurementStats",
    "parse_klippel_dat",
    "parse_rew_mdat",
    "measurement_from_response",
    "compare_measurement_to_prediction",
]
