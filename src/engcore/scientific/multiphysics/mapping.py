"""Declared field mapping semantics for multiphysics interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string

FIELD_MAPPING_SCHEMA = schema_string("multiphysics_field_mapping")
MAPPING_DIAGNOSTICS_SCHEMA = schema_string("multiphysics_mapping_diagnostics")


class FieldMappingMethod(str, Enum):
    IDENTITY = "identity"
    NEAREST = "nearest"
    BILINEAR = "bilinear"
    CONSERVATIVE_CELL = "conservative_cell"
    RBF = "rbf"
    MORTAR = "mortar"


class ExtrapolationPolicy(str, Enum):
    REFUSE = "refuse"
    NEAREST = "nearest"


@dataclass(frozen=True)
class FieldMappingDefinition:
    mapping_id: str
    method: str
    mapper_id: str
    mapper_version: str
    extrapolation: ExtrapolationPolicy = ExtrapolationPolicy.REFUSE
    verify_round_trip: bool = True
    relative_error_limit: float | None = None
    description: str = ""

    def __post_init__(self) -> None:
        mapping_id = str(self.mapping_id).strip()
        if not mapping_id:
            raise InvalidScientificProblem("field mapping requires mapping_id")
        object.__setattr__(self, "mapping_id", mapping_id)
        method = (
            self.method.value
            if isinstance(self.method, FieldMappingMethod)
            else str(self.method).strip().lower()
        )
        mapper_id = str(self.mapper_id).strip()
        mapper_version = str(self.mapper_version).strip()
        if not method or not mapper_id or not mapper_version:
            raise InvalidScientificProblem(
                "field mapping requires method, mapper_id and mapper_version"
            )
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "mapper_id", mapper_id)
        object.__setattr__(self, "mapper_version", mapper_version)
        object.__setattr__(self, "extrapolation", ExtrapolationPolicy(self.extrapolation))
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
            "method": self.method,
            "mapper_id": self.mapper_id,
            "mapper_version": self.mapper_version,
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
            method=payload["method"],
            mapper_id=payload["mapper_id"],
            mapper_version=payload["mapper_version"],
            extrapolation=ExtrapolationPolicy(payload.get("extrapolation", "refuse")),
            verify_round_trip=payload.get("verify_round_trip", True),
            relative_error_limit=payload.get("relative_error_limit"),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class MappingDiagnostics:
    mapping_id: str
    mapper_id: str
    mapper_version: str
    method: str
    source_count: int
    target_count: int
    extrapolated_count: int
    coverage_fraction: float
    round_trip_relative_l2: float | None = None
    conservation_relative_error: float | None = None

    def __post_init__(self) -> None:
        for label in ("mapping_id", "mapper_id", "mapper_version", "method"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise InvalidScientificProblem(
                    f"mapping diagnostics require {label}"
                )
            object.__setattr__(self, label, value)
        for label in ("source_count", "target_count", "extrapolated_count"):
            value = getattr(self, label)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise InvalidScientificProblem(f"{label} must be a non-negative int")
        coverage = float(self.coverage_fraction)
        if not 0.0 <= coverage <= 1.0:
            raise InvalidScientificProblem("coverage_fraction must lie in [0, 1]")
        object.__setattr__(self, "coverage_fraction", coverage)
        for label in ("round_trip_relative_l2", "conservation_relative_error"):
            value = getattr(self, label)
            if value is not None:
                value = float(value)
                if value < 0.0:
                    raise InvalidScientificProblem(f"{label} must be non-negative")
                object.__setattr__(self, label, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MAPPING_DIAGNOSTICS_SCHEMA,
            "mapping_id": self.mapping_id,
            "mapper_id": self.mapper_id,
            "mapper_version": self.mapper_version,
            "method": self.method,
            "source_count": self.source_count,
            "target_count": self.target_count,
            "extrapolated_count": self.extrapolated_count,
            "coverage_fraction": self.coverage_fraction,
            "round_trip_relative_l2": self.round_trip_relative_l2,
            "conservation_relative_error": self.conservation_relative_error,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MappingDiagnostics":
        require_schema(payload, MAPPING_DIAGNOSTICS_SCHEMA)
        return cls(
            mapping_id=payload["mapping_id"],
            mapper_id=payload["mapper_id"],
            mapper_version=payload["mapper_version"],
            method=payload["method"],
            source_count=payload["source_count"],
            target_count=payload["target_count"],
            extrapolated_count=payload["extrapolated_count"],
            coverage_fraction=payload["coverage_fraction"],
            round_trip_relative_l2=payload.get("round_trip_relative_l2"),
            conservation_relative_error=payload.get("conservation_relative_error"),
        )
