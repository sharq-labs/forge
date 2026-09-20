"""Typed values carried by multiphysics ports and run records."""

from __future__ import annotations

from typing import Any, Mapping, TypeAlias

from ..errors import InvalidScientificProblem
from ..fields import (
    FIELD_RECORD_SCHEMA,
    FieldRecord,
)
from ..fields.result import FIELD_RECORD_SCHEMA_V2
from ..results.uncertainty import Uncertainty, UncertaintyKind
from ..units.quantity import QUANTITY_SCHEMA, Quantity, dimensionality
from .ports import PortDefinition, PortKind

CouplingValue: TypeAlias = Quantity | FieldRecord


def coupling_value_to_dict(
    value: CouplingValue,
) -> dict[str, Any]:
    if not isinstance(value, (Quantity, FieldRecord)):
        raise InvalidScientificProblem(
            f"coupling value must be Quantity or FieldRecord, got "
            f"{type(value).__name__}"
        )
    return value.to_dict()


def coupling_value_from_dict(
    payload: Mapping[str, Any],
) -> CouplingValue:
    schema = payload.get("schema")
    if schema == QUANTITY_SCHEMA:
        return Quantity.from_dict(payload)
    if schema in (FIELD_RECORD_SCHEMA, FIELD_RECORD_SCHEMA_V2):
        return FieldRecord.from_dict(payload)
    raise InvalidScientificProblem(
        f"unknown coupling value schema {schema!r}"
    )


def validate_port_coupling_value(
    port: PortDefinition,
    value: CouplingValue,
) -> None:
    if port.kind is PortKind.SCALAR:
        if not isinstance(value, Quantity):
            raise InvalidScientificProblem(
                f"port {port.port_id!r} expects scalar Quantity, got "
                f"{type(value).__name__}"
            )
        if value.dimensionality != port.dimension:
            raise InvalidScientificProblem(
                f"port {port.port_id!r} expects [{port.dimension}], got "
                f"[{value.dimensionality}]"
            )
        return

    if not isinstance(value, FieldRecord):
        raise InvalidScientificProblem(
            f"port {port.port_id!r} expects FieldRecord, got "
            f"{type(value).__name__}"
        )
    assert port.field is not None
    if value.definition != port.field:
        raise InvalidScientificProblem(
            f"field value for port {port.port_id!r} carries definition "
            f"{value.definition.field_id!r} on "
            f"{value.definition.mesh_id!r}, expected exactly "
            f"{port.field.field_id!r} on {port.field.mesh_id!r}"
        )


def validate_port_uncertainty(
    port: PortDefinition,
    uncertainty: Uncertainty,
) -> None:
    if not isinstance(uncertainty, Uncertainty):
        raise InvalidScientificProblem(
            f"port {port.port_id!r} uncertainty must be Uncertainty"
        )

    if port.kind is PortKind.FIELD:
        if uncertainty.kind is not UncertaintyKind.UNKNOWN:
            raise InvalidScientificProblem(
                f"port {port.port_id!r} is a field; current core has no "
                "spatial uncertainty-field representation, so quantified "
                "scalar uncertainty would overstate what is known. "
                "Use UNKNOWN."
            )
        return

    if uncertainty.kind is UncertaintyKind.STANDARD:
        value = uncertainty.standard_uncertainty
        assert value is not None
        if value.dimensionality != port.dimension:
            raise InvalidScientificProblem(
                f"port {port.port_id!r} uncertainty is "
                f"[{value.dimensionality}], expected [{port.dimension}]"
            )
    elif uncertainty.kind is UncertaintyKind.INTERVAL:
        assert uncertainty.lower is not None
        assert uncertainty.upper is not None
        if (
            uncertainty.lower.dimensionality != port.dimension
            or uncertainty.upper.dimensionality != port.dimension
        ):
            raise InvalidScientificProblem(
                f"port {port.port_id!r} uncertainty interval dimension "
                f"does not match [{port.dimension}]"
            )

    if uncertainty.is_quantified and not str(
        uncertainty.source
    ).strip():
        raise InvalidScientificProblem(
            f"port {port.port_id!r} quantified uncertainty has no "
            "source attribution"
        )


__all__ = [
    "CouplingValue",
    "coupling_value_from_dict",
    "coupling_value_to_dict",
    "validate_port_coupling_value",
    "validate_port_uncertainty",
]
