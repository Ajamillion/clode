"""JSON schema helpers describing solver request/response contracts.

These helpers provide lightweight JSON Schema v2020-12 documents for the
analytical solvers so other services (FastAPI gateway, Studio UI, CLI) can
consume the same request/response contracts without duplicating structure.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import MISSING, fields, is_dataclass
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from .acoustics.sealed import SealedAlignmentSummary
from .acoustics.vented import VentedAlignmentSummary
from .drivers import BoxDesign, DriverParameters, PortGeometry, VentedBoxDesign

SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def dataclass_schema(
    cls: type[Any],
    *,
    field_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a JSON schema describing the given dataclass."""

    if not is_dataclass(cls):  # pragma: no cover - defensive guard
        raise TypeError(f"{cls!r} is not a dataclass")

    overrides: Mapping[str, Mapping[str, Any]] | None = field_overrides or _DATACLASS_OVERRIDES.get(cls)
    type_hints = get_type_hints(cls)

    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []

    for field in fields(cls):
        field_type = type_hints.get(field.name, field.type)
        schema = _schema_for_type(field_type)
        properties[field.name] = schema
        if field.default is MISSING and field.default_factory is MISSING:
            required.append(field.name)

    schema_doc: dict[str, Any] = {
        "title": cls.__name__,
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }

    if overrides:
        for name, override in overrides.items():
            prop = properties.get(name)
            if not prop:
                continue
            _apply_override(prop, override)

    return schema_doc


def sealed_simulation_request_schema() -> dict[str, Any]:
    """Return the JSON schema describing the sealed solver request payload."""

    return {
        "$schema": SCHEMA_DRAFT,
        "title": "SealedBoxSimulationRequest",
        "type": "object",
        "additionalProperties": False,
        "required": ["driver", "box", "frequencies_hz"],
        "properties": {
            "driver": dataclass_schema(DriverParameters),
            "box": dataclass_schema(BoxDesign),
            "frequencies_hz": _number_array_schema(
                title="Frequency bins (Hz)",
                min_items=1,
                description="Discrete frequencies to evaluate.",
            ),
            "mic_distance_m": _positive_number_schema(
                "Microphone distance (m)",
                description="Distance from driver to virtual microphone.",
            ),
            "drive_voltage": _positive_number_schema(
                "Drive voltage (Vrms)",
                description="Input voltage driving the system (RMS).",
            ),
        },
    }


def sealed_simulation_response_schema() -> dict[str, Any]:
    """Return the JSON schema for the sealed solver response payload."""

    summary_schema = dataclass_schema(SealedAlignmentSummary)
    schema = _base_response_schema(
        title="SealedBoxSimulationResponse",
        summary_schema=summary_schema,
        extra_properties={
            "fc_hz": {
                "type": "number",
                "description": "System resonance frequency (Fc).",
            },
            "qtc": {
                "type": "number",
                "description": "Total system Q including electrical damping.",
            },
        },
        extra_required=("fc_hz", "qtc"),
    )
    return schema


def vented_simulation_request_schema() -> dict[str, Any]:
    """Return the JSON schema describing the vented solver request payload."""

    return {
        "$schema": SCHEMA_DRAFT,
        "title": "VentedBoxSimulationRequest",
        "type": "object",
        "additionalProperties": False,
        "required": ["driver", "box", "frequencies_hz"],
        "properties": {
            "driver": dataclass_schema(DriverParameters),
            "box": dataclass_schema(VentedBoxDesign),
            "frequencies_hz": _number_array_schema(
                title="Frequency bins (Hz)",
                min_items=1,
                description="Discrete frequencies to evaluate.",
            ),
            "mic_distance_m": _positive_number_schema(
                "Microphone distance (m)",
                description="Distance from driver to virtual microphone.",
            ),
            "drive_voltage": _positive_number_schema(
                "Drive voltage (Vrms)",
                description="Input voltage driving the system (RMS).",
            ),
        },
    }


def vented_simulation_response_schema() -> dict[str, Any]:
    """Return the JSON schema for the vented solver response payload."""

    summary_schema = dataclass_schema(VentedAlignmentSummary)
    schema = _base_response_schema(
        title="VentedBoxSimulationResponse",
        summary_schema=summary_schema,
        extra_properties={
            "port_velocity_ms": _number_array_schema(
                title="Port air velocity (m/s)",
                min_items=1,
                description="Velocity magnitude of air inside the port.",
            ),
            "fb_hz": {
                "type": "number",
                "description": "Box tuning frequency (Fb).",
            },
            "max_port_velocity_ms": {
                "type": "number",
                "description": "Maximum port air velocity observed across frequencies.",
            },
        },
        extra_required=("port_velocity_ms", "fb_hz", "max_port_velocity_ms"),
    )
    return schema


def sealed_simulation_schema() -> dict[str, dict[str, Any]]:
    """Return both request and response schemas for the sealed solver."""

    return {
        "request": sealed_simulation_request_schema(),
        "response": sealed_simulation_response_schema(),
    }


def vented_simulation_schema() -> dict[str, dict[str, Any]]:
    """Return both request and response schemas for the vented solver."""

    return {
        "request": vented_simulation_request_schema(),
        "response": vented_simulation_response_schema(),
    }


def solver_json_schemas() -> dict[str, dict[str, dict[str, Any]]]:
    """Return a catalog of solver schemas keyed by solver family."""

    return {
        "sealed": sealed_simulation_schema(),
        "vented": vented_simulation_schema(),
    }


def _base_response_schema(
    *,
    title: str,
    summary_schema: dict[str, Any],
    extra_properties: Mapping[str, dict[str, Any]] | None = None,
    extra_required: Sequence[str] = (),
) -> dict[str, Any]:
    properties: dict[str, dict[str, Any]] = {
        "frequency_hz": _number_array_schema(
            title="Frequency bins (Hz)",
            min_items=1,
            description="Frequencies where SPL/impedance were evaluated.",
        ),
        "spl_db": _number_array_schema(
            title="Sound pressure level (dB)",
            min_items=1,
            description="Predicted on-axis SPL magnitude.",
        ),
        "impedance_real": _number_array_schema(
            title="Electrical impedance (real)",
            min_items=1,
            description="Real component of electrical impedance (ohms).",
        ),
        "impedance_imag": _number_array_schema(
            title="Electrical impedance (imag)",
            min_items=1,
            description="Imaginary component of electrical impedance (ohms).",
        ),
        "cone_velocity_ms": _number_array_schema(
            title="Cone velocity (m/s)",
            min_items=1,
            description="Voice-coil/cone velocity magnitude.",
        ),
        "summary": summary_schema,
    }

    required = [
        "frequency_hz",
        "spl_db",
        "impedance_real",
        "impedance_imag",
        "cone_velocity_ms",
        "summary",
    ]

    if extra_properties:
        for name, prop in extra_properties.items():
            properties[name] = dict(prop)
    if extra_required:
        required.extend(extra_required)

    return {
        "$schema": SCHEMA_DRAFT,
        "title": title,
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _schema_for_type(tp: Any) -> dict[str, Any]:
    origin = get_origin(tp)

    if origin is None:
        if tp in (float,):
            return {"type": "number"}
        if tp in (int,):
            return {"type": "integer"}
        if tp in (str,):
            return {"type": "string"}
        if tp in (bool,):
            return {"type": "boolean"}
        if tp is type(None):
            return {"type": "null"}
        if isinstance(tp, type) and is_dataclass(tp):
            return dataclass_schema(tp)
        return {}

    if origin in (list, Sequence, Iterable):
        args = get_args(tp)
        item_type = args[0] if args else Any
        item_schema = _schema_for_type(item_type)
        return {
            "type": "array",
            "items": item_schema or {},
        }

    if origin is tuple:
        args = get_args(tp)
        if len(args) == 2 and args[1] is Ellipsis:
            return {
                "type": "array",
                "items": _schema_for_type(args[0]) or {},
            }
        return {
            "type": "array",
            "prefixItems": [_schema_for_type(arg) or {} for arg in args],
            "items": False,
        }

    if origin in (dict, Mapping):
        args = get_args(tp)
        key_schema = _schema_for_type(args[0]) if args else {"type": "string"}
        value_schema = _schema_for_type(args[1]) if len(args) > 1 else {}
        return {
            "type": "object",
            "propertyNames": key_schema or {"type": "string"},
            "additionalProperties": value_schema or {},
        }

    if origin is Union or origin is UnionType:
        options = [_schema_for_type(arg) for arg in get_args(tp)]
        # Collapse trivial unions like Union[T] back to T
        options = [opt for opt in options if opt]
        if not options:
            return {}
        if len(options) == 1:
            return options[0]
        return {"anyOf": options}

    return {}


def _number_array_schema(
    *,
    title: str | None = None,
    min_items: int = 0,
    description: str | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "array",
        "items": {"type": "number"},
    }
    if min_items:
        schema["minItems"] = min_items
    if title:
        schema["title"] = title
    if description:
        schema["description"] = description
    return schema


def _positive_number_schema(title: str | None = None, *, description: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "number",
        "exclusiveMinimum": 0.0,
    }
    if title:
        schema["title"] = title
    if description:
        schema["description"] = description
    return schema


def _apply_override(schema: dict[str, Any], override: Mapping[str, Any]) -> None:
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            if option.get("type") == "null":
                continue
            option.update(override)
    else:
        schema.update(override)


_DRIVER_FIELD_OVERRIDES: dict[str, dict[str, Any]] = {
    "fs_hz": {"exclusiveMinimum": 0.0},
    "qts": {"exclusiveMinimum": 0.0},
    "re_ohm": {"exclusiveMinimum": 0.0},
    "bl_t_m": {"exclusiveMinimum": 0.0},
    "mms_kg": {"exclusiveMinimum": 0.0},
    "sd_m2": {"exclusiveMinimum": 0.0},
    "le_h": {"minimum": 0.0},
}

_BOX_FIELD_OVERRIDES: dict[str, dict[str, Any]] = {
    "volume_l": {"exclusiveMinimum": 0.0},
    "leakage_q": {"exclusiveMinimum": 0.0},
}

_PORT_FIELD_OVERRIDES: dict[str, dict[str, Any]] = {
    "diameter_m": {"exclusiveMinimum": 0.0},
    "length_m": {"exclusiveMinimum": 0.0},
    "count": {"minimum": 1},
    "flare_factor": {"minimum": 0.0},
    "loss_q": {"exclusiveMinimum": 0.0},
}

_VENTED_BOX_FIELD_OVERRIDES: dict[str, dict[str, Any]] = {
    "volume_l": {"exclusiveMinimum": 0.0},
    "leakage_q": {"exclusiveMinimum": 0.0},
}

_DATACLASS_OVERRIDES: dict[type[Any], dict[str, dict[str, Any]]] = {
    DriverParameters: _DRIVER_FIELD_OVERRIDES,
    BoxDesign: _BOX_FIELD_OVERRIDES,
    PortGeometry: _PORT_FIELD_OVERRIDES,
    VentedBoxDesign: _VENTED_BOX_FIELD_OVERRIDES,
}


__all__ = [
    "dataclass_schema",
    "sealed_simulation_request_schema",
    "sealed_simulation_response_schema",
    "sealed_simulation_schema",
    "vented_simulation_request_schema",
    "vented_simulation_response_schema",
    "vented_simulation_schema",
    "solver_json_schemas",
]
