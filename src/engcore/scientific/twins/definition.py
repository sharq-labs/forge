"""Domain-neutral Scientific Twin V0.1 contracts.

A ScientificTwin is a versioned declaration of one specific scientific system
instance. It sits between reusable scientific models/data and study-specific
experiments. It is not a solver, result, posterior, or physical-validation
claim.

V0.1 deliberately represents typed system declarations and evidence bindings
without inventing quantified parameter uncertainty before K3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem, ScientificCoreError
from ..ir.problem import ModelReference
from ..ir.values import (
    ScientificValue,
    as_context_value,
    decode_value,
    encode_value,
    require_scientific_value,
)
from ..serialization import require_schema, schema_string

TWIN_REFERENCE_SCHEMA = schema_string("scientific_twin_reference")
TWIN_DATUM_SCHEMA = schema_string("scientific_twin_datum")
SCIENTIFIC_TWIN_SCHEMA = schema_string("scientific_twin")


class TwinKind(str, Enum):
    """Scientific role/provenance of a twin, not a truth level."""

    CONCEPT = "concept"
    REFERENCE = "reference"
    CANDIDATE = "candidate"
    CALIBRATED = "calibrated"
    ENSEMBLE = "ensemble"
    DERIVED = "derived"


class TwinDatumRole(str, Enum):
    """Role a typed system declaration plays inside a twin."""

    PARAMETER = "parameter"
    STATE = "state"
    OPERATING_CONDITION = "operating_condition"
    CONTROL = "control"


@dataclass(frozen=True)
class TwinReference:
    """Stable reference to one exact twin version."""

    twin_id: str
    version: str

    def __post_init__(self) -> None:
        twin_id = str(self.twin_id).strip()
        version = str(self.version).strip()
        if not twin_id:
            raise InvalidScientificProblem("twin reference requires a non-empty twin_id")
        if not version:
            raise InvalidScientificProblem("twin reference requires a non-empty version")
        object.__setattr__(self, "twin_id", twin_id)
        object.__setattr__(self, "version", version)

    @property
    def key(self) -> tuple[str, str]:
        return (self.twin_id, self.version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TWIN_REFERENCE_SCHEMA,
            "twin_id": self.twin_id,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TwinReference":
        require_schema(payload, TWIN_REFERENCE_SCHEMA)
        return cls(twin_id=payload["twin_id"], version=payload["version"])


@dataclass(frozen=True)
class TwinDatum:
    """One typed scientific declaration carried by a twin.

    Bare Python numeric values are intentionally rejected. Dimensional values
    must be :class:`Quantity`; exact counts, flags, and categories use the
    existing typed ScientificValue union.
    """

    name: str
    value: ScientificValue
    role: TwinDatumRole = TwinDatumRole.PARAMETER
    description: str = ""

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise InvalidScientificProblem("twin datum requires a non-empty name")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "role", TwinDatumRole(self.role))
        require_scientific_value(self.value, context=f"twin datum {name!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TWIN_DATUM_SCHEMA,
            "name": self.name,
            "role": self.role.value,
            "value": encode_value(self.value),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TwinDatum":
        require_schema(payload, TWIN_DATUM_SCHEMA)
        return cls(
            name=payload["name"],
            value=decode_value(payload["value"]),
            role=TwinDatumRole(payload.get("role", "parameter")),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class ScientificTwin:
    """Immutable, versioned scientific declaration of one system instance."""

    twin_id: str
    version: str
    kind: TwinKind
    models: tuple[ModelReference, ...] = ()
    declarations: tuple[TwinDatum, ...] = ()
    name: str = ""
    description: str = ""
    assumptions: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    calibration_evidence_refs: tuple[str, ...] = ()
    parent: TwinReference | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        twin_id = str(self.twin_id).strip()
        version = str(self.version).strip()
        if not twin_id:
            raise InvalidScientificProblem("scientific twin requires a non-empty twin_id")
        if not version:
            raise InvalidScientificProblem("scientific twin requires a non-empty version")
        object.__setattr__(self, "twin_id", twin_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "kind", TwinKind(self.kind))

        models = tuple(self.models)
        declarations = tuple(self.declarations)
        assumptions = tuple(str(item).strip() for item in self.assumptions)
        evidence_refs = self._normalize_refs(self.evidence_refs, "evidence")
        calibration_refs = self._normalize_refs(
            self.calibration_evidence_refs, "calibration evidence"
        )

        if any(not isinstance(model, ModelReference) for model in models):
            raise ScientificCoreError("scientific twin models must be ModelReference records")
        if any(not isinstance(datum, TwinDatum) for datum in declarations):
            raise ScientificCoreError("scientific twin declarations must be TwinDatum records")
        if self.parent is not None and not isinstance(self.parent, TwinReference):
            raise ScientificCoreError("scientific twin parent must be a TwinReference")

        model_keys = [model.key for model in models]
        if len(model_keys) != len(set(model_keys)):
            raise InvalidScientificProblem("scientific twin contains duplicate model references")

        datum_names = [datum.name for datum in declarations]
        if len(datum_names) != len(set(datum_names)):
            raise InvalidScientificProblem(
                "scientific twin declaration names must be globally unique"
            )

        if self.kind is not TwinKind.CONCEPT and not models:
            raise InvalidScientificProblem(
                f"{self.kind.value} twin requires at least one model reference"
            )
        if self.kind is TwinKind.CALIBRATED and not calibration_refs:
            raise InvalidScientificProblem(
                "calibrated twin requires explicit calibration evidence"
            )
        if self.kind is TwinKind.ENSEMBLE and len(models) < 2:
            raise InvalidScientificProblem(
                "ensemble twin requires at least two distinct model references"
            )
        if self.kind is TwinKind.DERIVED and self.parent is None:
            raise InvalidScientificProblem("derived twin requires a parent twin reference")
        if self.parent is not None and self.parent.key == (twin_id, version):
            raise InvalidScientificProblem("scientific twin cannot be its own parent version")

        object.__setattr__(self, "models", models)
        object.__setattr__(self, "declarations", declarations)
        object.__setattr__(self, "assumptions", assumptions)
        object.__setattr__(self, "evidence_refs", evidence_refs)
        object.__setattr__(self, "calibration_evidence_refs", calibration_refs)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @staticmethod
    def _normalize_refs(values: tuple[str, ...], label: str) -> tuple[str, ...]:
        refs = tuple(str(value).strip() for value in values)
        if any(not value for value in refs):
            raise InvalidScientificProblem(f"{label} references must be non-empty")
        if len(refs) != len(set(refs)):
            raise InvalidScientificProblem(f"duplicate {label} references are not allowed")
        return refs

    @property
    def reference(self) -> TwinReference:
        return TwinReference(self.twin_id, self.version)

    def declaration(self, name: str) -> TwinDatum:
        for datum in self.declarations:
            if datum.name == name:
                return datum
        raise InvalidScientificProblem(
            f"scientific twin {self.twin_id!r} has no declaration {name!r}"
        )

    def declarations_by_role(self, role: TwinDatumRole) -> tuple[TwinDatum, ...]:
        wanted = TwinDatumRole(role)
        return tuple(datum for datum in self.declarations if datum.role is wanted)

    def scientific_context(self) -> dict[str, Any]:
        """Typed context for future binding/validity/study materialization.

        Metadata is deliberately excluded: it is descriptive storage, not a
        scientific input side channel.
        """
        return {
            datum.name: as_context_value(datum.value)
            for datum in self.declarations
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCIENTIFIC_TWIN_SCHEMA,
            "twin_id": self.twin_id,
            "version": self.version,
            "kind": self.kind.value,
            "name": self.name,
            "description": self.description,
            "models": [model.to_dict() for model in self.models],
            "declarations": [datum.to_dict() for datum in self.declarations],
            "assumptions": list(self.assumptions),
            "evidence_refs": list(self.evidence_refs),
            "calibration_evidence_refs": list(self.calibration_evidence_refs),
            "parent": self.parent.to_dict() if self.parent else None,
            "metadata": dict(sorted(self.metadata.items(), key=lambda item: item[0])),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificTwin":
        require_schema(payload, SCIENTIFIC_TWIN_SCHEMA)
        parent = payload.get("parent")
        return cls(
            twin_id=payload["twin_id"],
            version=payload["version"],
            kind=TwinKind(payload["kind"]),
            name=payload.get("name", ""),
            description=payload.get("description", ""),
            models=tuple(
                ModelReference.from_dict(model)
                for model in payload.get("models", ())
            ),
            declarations=tuple(
                TwinDatum.from_dict(datum)
                for datum in payload.get("declarations", ())
            ),
            assumptions=tuple(payload.get("assumptions", ())),
            evidence_refs=tuple(payload.get("evidence_refs", ())),
            calibration_evidence_refs=tuple(
                payload.get("calibration_evidence_refs", ())
            ),
            parent=TwinReference.from_dict(parent) if parent else None,
            metadata=dict(payload.get("metadata", {})),
        )
