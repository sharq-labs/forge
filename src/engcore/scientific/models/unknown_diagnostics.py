"""Fine-grained diagnostics for validity conditions that remain UNKNOWN.

The persisted ``UnknownReason`` vocabulary is intentionally small and frozen:
changing it is a wire/API compatibility event.  That vocabulary answers the
stable cross-version question (missing input, unreadable shape, conservative
screen, prerequisite).  It is too coarse for an operator trying to repair a
modern field-aware assessment.

This module adds a second, additive diagnostic layer.  It never changes the
verdict and it never rewrites ``ValidityAssessment``.  Instead it refines an
existing UNKNOWN using the condition declaration and the exact context value
that produced it.  Consumers that only understand the frozen reason enum keep
working; newer consumers can distinguish non-finite typed fields from raw
arrays, a mesh passed to a scalar predicate, and other concrete causes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import ModelValidityError
from ..fields.mesh import StructuredMesh
from ..fields.result import FieldRecord
from ..serialization import require_schema, schema_string
from .definition import (
    RangeCondition,
    UnknownReason,
    ValidityAssessment,
    ValidityDomain,
)
from .structured_validity import (
    FieldFiniteCondition,
    FieldRangeCondition,
    FieldStructureCondition,
    MeshResolutionCondition,
)

UNKNOWN_DIAGNOSTIC_SCHEMA = schema_string("validity_unknown_diagnostic")


class UnknownCause(str, Enum):
    """Operational refinement of the stable :class:`UnknownReason` channel."""

    MISSING_INPUT = "missing_input"
    PREREQUISITE_NOT_ESTABLISHED = "prerequisite_not_established"
    CONSERVATIVE_SCREEN_NOT_CLEARED = "conservative_screen_not_cleared"
    NONFINITE_FIELD = "nonfinite_field"
    UNTYPED_STRUCTURED_VALUE = "untyped_structured_value"
    STRUCTURED_VALUE_FOR_SCALAR_CONDITION = "structured_value_for_scalar_condition"
    FIELD_RECORD_REQUIRED = "field_record_required"
    STRUCTURED_MESH_REQUIRED = "structured_mesh_required"
    WRONG_VALUE_TYPE = "wrong_value_type"
    UNSPECIFIED_UNREADABLE_VALUE = "unspecified_unreadable_value"


_ACTIONABLE = frozenset(
    {
        UnknownCause.MISSING_INPUT,
        UnknownCause.UNTYPED_STRUCTURED_VALUE,
        UnknownCause.FIELD_RECORD_REQUIRED,
        UnknownCause.STRUCTURED_MESH_REQUIRED,
        UnknownCause.WRONG_VALUE_TYPE,
    }
)


@dataclass(frozen=True)
class UnknownDiagnostic:
    condition: str
    stable_reason: UnknownReason
    cause: UnknownCause
    context_key: str
    value_type: str = ""
    detail: str = ""

    def __post_init__(self) -> None:
        condition = str(self.condition).strip()
        context_key = str(self.context_key).strip()
        if not condition or not context_key:
            raise ModelValidityError("UNKNOWN diagnostic requires condition and context_key")
        object.__setattr__(self, "condition", condition)
        object.__setattr__(self, "context_key", context_key)
        object.__setattr__(self, "stable_reason", UnknownReason(self.stable_reason))
        object.__setattr__(self, "cause", UnknownCause(self.cause))
        object.__setattr__(self, "value_type", str(self.value_type))
        object.__setattr__(self, "detail", str(self.detail))

    @property
    def actionable(self) -> bool:
        return self.cause in _ACTIONABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": UNKNOWN_DIAGNOSTIC_SCHEMA,
            "condition": self.condition,
            "stable_reason": self.stable_reason.value,
            "cause": self.cause.value,
            "context_key": self.context_key,
            "value_type": self.value_type,
            "detail": self.detail,
            "actionable": self.actionable,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "UnknownDiagnostic":
        require_schema(payload, UNKNOWN_DIAGNOSTIC_SCHEMA)
        item = cls(
            condition=payload["condition"],
            stable_reason=UnknownReason(payload["stable_reason"]),
            cause=UnknownCause(payload["cause"]),
            context_key=payload["context_key"],
            value_type=payload.get("value_type", ""),
            detail=payload.get("detail", ""),
        )
        claimed = payload.get("actionable", item.actionable)
        if bool(claimed) is not item.actionable:
            raise ModelValidityError(
                f"UNKNOWN diagnostic {item.condition!r} carries actionable={claimed!r}, "
                f"but cause {item.cause.value!r} implies {item.actionable}"
            )
        return item


def _context_key(condition: Any) -> str:
    # Structured conditions separate condition identity from source identity.
    # Scalar conditions historically use their own name as the context key.
    field = getattr(condition, "field", None)
    if isinstance(field, str) and field.strip():
        return field.strip()
    mesh = getattr(condition, "mesh", None)
    if isinstance(mesh, str) and mesh.strip():
        return mesh.strip()
    return str(condition.name)


def _looks_untyped_structured(value: Any) -> bool:
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        return False
    if hasattr(value, "shape") or hasattr(value, "__array_interface__"):
        return True
    return isinstance(value, (list, tuple))


def _unreadable_cause(condition: Any, value: Any) -> tuple[UnknownCause, str]:
    if isinstance(value, FieldRecord):
        if not value.is_finite:
            return (
                UnknownCause.NONFINITE_FIELD,
                "typed FieldRecord contains one or more non-finite values; the "
                "field exists, but it cannot support a range claim",
            )
        if isinstance(condition, RangeCondition):
            return (
                UnknownCause.STRUCTURED_VALUE_FOR_SCALAR_CONDITION,
                "a typed field was supplied to a scalar RangeCondition; use a "
                "field-aware condition instead of collapsing the field",
            )

    if isinstance(value, StructuredMesh):
        if not isinstance(condition, MeshResolutionCondition):
            return (
                UnknownCause.STRUCTURED_VALUE_FOR_SCALAR_CONDITION,
                "a StructuredMesh was supplied to a condition that does not "
                "declare mesh semantics",
            )

    if isinstance(condition, (FieldRangeCondition, FieldFiniteCondition, FieldStructureCondition)):
        if not isinstance(value, FieldRecord):
            if _looks_untyped_structured(value):
                return (
                    UnknownCause.UNTYPED_STRUCTURED_VALUE,
                    "structured data was supplied without a FieldRecord; raw arrays "
                    "are deliberately not admitted at the scientific boundary",
                )
            return (
                UnknownCause.FIELD_RECORD_REQUIRED,
                f"condition requires FieldRecord, got {type(value).__name__}",
            )

    if isinstance(condition, MeshResolutionCondition) and not isinstance(value, StructuredMesh):
        return (
            UnknownCause.STRUCTURED_MESH_REQUIRED,
            f"condition requires StructuredMesh, got {type(value).__name__}",
        )

    if _looks_untyped_structured(value):
        return (
            UnknownCause.UNTYPED_STRUCTURED_VALUE,
            "an untyped structured value reached a scalar/typed validity boundary",
        )

    if value is not None:
        return (
            UnknownCause.WRONG_VALUE_TYPE,
            f"value type {type(value).__name__} is not readable by this condition",
        )

    return (
        UnknownCause.UNSPECIFIED_UNREADABLE_VALUE,
        "the stable record says the value shape was unreadable, but no more "
        "specific additive diagnosis is available",
    )


def diagnose_unknowns(
    domain: ValidityDomain,
    assessment: ValidityAssessment,
    context: Mapping[str, Any],
) -> tuple[UnknownDiagnostic, ...]:
    """Refine every UNKNOWN in an existing assessment without changing it.

    ``context`` must be the same assembled mapping that was assessed.  The
    function does not reassess conditions and therefore cannot accidentally
    turn diagnostics into a second verdict implementation.
    """
    if not isinstance(domain, ValidityDomain):
        raise TypeError("diagnose_unknowns requires ValidityDomain")
    if not isinstance(assessment, ValidityAssessment):
        raise TypeError("diagnose_unknowns requires ValidityAssessment")
    if not isinstance(context, Mapping):
        raise TypeError("diagnose_unknowns context must be a mapping")

    by_name = {condition.name: condition for condition in domain.conditions}
    diagnostics: list[UnknownDiagnostic] = []
    for unknown in assessment.unknown_reasons:
        condition = by_name.get(unknown.name)
        if condition is None:
            raise ModelValidityError(
                f"assessment names unknown condition {unknown.name!r}, which is not "
                "present in the supplied ValidityDomain"
            )
        key = _context_key(condition)
        value = context.get(key)

        if unknown.reason is UnknownReason.NOT_SUPPLIED:
            cause = UnknownCause.MISSING_INPUT
            detail = f"context contains no value for {key!r}"
        elif unknown.reason is UnknownReason.PREREQUISITE_NOT_ESTABLISHED:
            cause = UnknownCause.PREREQUISITE_NOT_ESTABLISHED
            detail = unknown.detail or "one or more prerequisite conditions were not established"
        elif unknown.reason is UnknownReason.CONSERVATIVE_SCREEN:
            cause = UnknownCause.CONSERVATIVE_SCREEN_NOT_CLEARED
            detail = unknown.detail or "conservative screen did not establish applicability"
        else:
            cause, detail = _unreadable_cause(condition, value)

        diagnostics.append(
            UnknownDiagnostic(
                condition=unknown.name,
                stable_reason=unknown.reason,
                cause=cause,
                context_key=key,
                value_type="" if value is None else type(value).__name__,
                detail=detail,
            )
        )

    return tuple(diagnostics)


__all__ = ["UnknownCause", "UnknownDiagnostic", "diagnose_unknowns"]
