"""Declared field mapping semantics for multiphysics interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..results.immutable import detach, freeze
from ..serialization import require_schema, schema_string

FIELD_MAPPING_SCHEMA = schema_string("multiphysics_field_mapping")
MAPPING_DIAGNOSTICS_SCHEMA = schema_string("multiphysics_mapping_diagnostics")


class FieldMappingMethod(str, Enum):
    IDENTITY = "identity"
    NEAREST = "nearest"
    BILINEAR = "bilinear"
    CONSERVATIVE_CELL = "conservative_cell"


class ExtrapolationPolicy(str, Enum):
    REFUSE = "refuse"
    NEAREST = "nearest"


@dataclass(frozen=True)
class FieldMappingDefinition:
    mapping_id: str
    method: FieldMappingMethod
    extrapolation: ExtrapolationPolicy = ExtrapolationPolicy.REFUSE
    verify_round_trip: bool = True
    relative_error_limit: float | None = None
    description: str = ""

    def __post_init__(self) -> None:
        mapping_id = str(self.mapping_id).strip()
        if not mapping_id:
            raise InvalidScientificProblem("field mapping requires mapping_id")
        object.__setattr__(self, "mapping_id", mapping_id)
        object.__setattr__(self, "method", FieldMappingMethod(self.method))
        object.__setattr__(self, "extrapolation", ExtrapolationPolicy(self.extrapolation))
        if (
            self.method is FieldMappingMethod.CONSERVATIVE_CELL
            and self.extrapolation is not ExtrapolationPolicy.REFUSE
        ):
            # A conservative transfer distributes each source cell's integral
            # over the target cells it overlaps.  A target cell outside the
            # source support receives a value no source integral accounts for.
            raise InvalidScientificProblem(
                "conservative_cell mapping cannot extrapolate; its extrapolation policy is 'refuse'"
            )
        if not isinstance(self.verify_round_trip, bool):
            raise InvalidScientificProblem("verify_round_trip must be boolean")
        if self.relative_error_limit is not None:
            value = float(self.relative_error_limit)
            if not math.isfinite(value) or value < 0.0:
                raise InvalidScientificProblem("relative_error_limit must be non-negative")
            object.__setattr__(self, "relative_error_limit", value)
        object.__setattr__(self, "description", str(self.description).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIELD_MAPPING_SCHEMA,
            "mapping_id": self.mapping_id,
            "method": self.method.value,
            "extrapolation": self.extrapolation.value,
            "verify_round_trip": self.verify_round_trip,
            "relative_error_limit": self.relative_error_limit,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FieldMappingDefinition":
        require_schema(payload, FIELD_MAPPING_SCHEMA)
        return cls(
            mapping_id=payload["mapping_id"],
            method=FieldMappingMethod(payload["method"]),
            extrapolation=ExtrapolationPolicy(payload.get("extrapolation", "refuse")),
            verify_round_trip=payload.get("verify_round_trip", True),
            relative_error_limit=payload.get("relative_error_limit"),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class MappingDiagnostics:
    """What one execution of a field mapping measured about itself.

    These are DIAGNOSTICS, not error bounds.  ``round_trip_relative_l2`` is the
    residual of mapping forward and back; it does not bound the error of the
    forward transfer.  ``conservation_relative_error`` is the computed
    integral imbalance of the transferred field; it says nothing about the
    field's pointwise accuracy.  ``provenance`` names the method, the supports
    and locations it was computed on and, for a conservative transfer, the
    measured coverage and conservation residuals.  Phase 2 BR9: every method of
    the runtime engine records it, so diagnostics -- and run records carrying
    them -- written before Phase 2 differ in form from new ones; a record without
    provenance still loads (the field is optional).
    """

    mapping_id: str
    source_count: int
    target_count: int
    extrapolated_count: int
    coverage_fraction: float
    round_trip_relative_l2: float | None = None
    conservation_relative_error: float | None = None
    provenance: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.provenance is not None:
            if not isinstance(self.provenance, Mapping) or not self.provenance.get("method"):
                raise InvalidScientificProblem("mapping provenance must be a mapping that names its method")
            object.__setattr__(self, "provenance", freeze(dict(self.provenance)))
        if not str(self.mapping_id).strip():
            raise InvalidScientificProblem("mapping diagnostics require mapping_id")
        for label in ("source_count", "target_count", "extrapolated_count"):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise InvalidScientificProblem(f"{label} must be a non-negative int")
        coverage = float(self.coverage_fraction)
        if not math.isfinite(coverage) or not 0.0 <= coverage <= 1.0:
            raise InvalidScientificProblem(
                "coverage_fraction must be finite and lie in [0, 1]"
            )
        object.__setattr__(self, "coverage_fraction", coverage)
        for label in ("round_trip_relative_l2", "conservation_relative_error"):
            value = getattr(self, label)
            if value is not None:
                value = float(value)
                if not math.isfinite(value) or value < 0.0:
                    raise InvalidScientificProblem(
                        f"{label} must be finite and non-negative"
                    )
                object.__setattr__(self, label, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MAPPING_DIAGNOSTICS_SCHEMA,
            "mapping_id": self.mapping_id,
            "source_count": self.source_count,
            "target_count": self.target_count,
            "extrapolated_count": self.extrapolated_count,
            "coverage_fraction": self.coverage_fraction,
            "round_trip_relative_l2": self.round_trip_relative_l2,
            "conservation_relative_error": self.conservation_relative_error,
            # absent unless recorded: earlier diagnostics keep their identity
            **({"provenance": detach(self.provenance)} if self.provenance is not None else {}),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MappingDiagnostics":
        require_schema(payload, MAPPING_DIAGNOSTICS_SCHEMA)
        return cls(
            mapping_id=payload["mapping_id"],
            source_count=payload["source_count"],
            target_count=payload["target_count"],
            extrapolated_count=payload["extrapolated_count"],
            coverage_fraction=payload["coverage_fraction"],
            round_trip_relative_l2=payload.get("round_trip_relative_l2"),
            conservation_relative_error=payload.get("conservation_relative_error"),
            provenance=payload.get("provenance"),
        )
