"""Material identity, material state, declared ranges and source-identity alignment."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import re
from typing import Any, Mapping

from ..scenarios.contracts import NamedQuantity
from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.knowledge.source import KnowledgeSource
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity, normalize_unit
from .ranges import ApplicabilityRange, _exact

MATERIAL_IDENTITY_SCHEMA = schema_string("material_identity")
MATERIAL_STATE_SCHEMA = schema_string("material_state")
STATE_SCHEMA_SCHEMA = schema_string("material_state_schema")

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")


def _identifier(value: object, label: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text or not _ID.fullmatch(text):
        raise InvalidScientificProblem(f"{label} must be a non-empty typed identifier")
    return text


def _strict_keys(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise InvalidScientificProblem(
            f"{label} shape mismatch; missing={sorted(expected - set(payload))}, extra={sorted(set(payload) - expected)}"
        )




# --------------------------------------------------------------------------
# Declared ranges
# --------------------------------------------------------------------------


def _ranges(values: Any, label: str) -> tuple[ApplicabilityRange, ...]:
    items = tuple(values)
    if any(not isinstance(r, ApplicabilityRange) for r in items) or len({r.variable_id for r in items}) != len(items):
        raise InvalidScientificProblem(f"{label} must be unique ApplicabilityRange records")
    return tuple(sorted(items, key=lambda r: r.variable_id))


# --------------------------------------------------------------------------
# Source identity alignment
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceIdentity:
    """The common meaning of Forge's source records, for exact provenance binding.

    Not a new source authority: it is a *view* over ``KnowledgeSource`` (the
    canonical scientific-data source) and ``EnvironmentSource`` (an imposed
    environment input), so a lifecycle or material record can bind any of them
    by the same fields without a serialized-contract migration.
    """

    record_type: str
    source_id: str
    issuer: str
    version: str
    content_digest: str
    classification: str

    def to_dict(self) -> dict[str, Any]:
        return {"record_type": self.record_type, "source_id": self.source_id, "issuer": self.issuer, "version": self.version, "content_digest": self.content_digest, "classification": self.classification}


def source_identity(record: Any) -> SourceIdentity:
    from ..scenarios.environment import EnvironmentSource

    if isinstance(record, KnowledgeSource):
        return SourceIdentity("knowledge_source", record.source_id, record.issuer, record.version, record.document_digest, record.source_class.value)
    if isinstance(record, EnvironmentSource):
        return SourceIdentity("environment_source", record.source_id, record.issuer, record.version, record.content_digest, record.classification)
    raise InvalidScientificProblem(f"{type(record).__name__} is not a recognised source record")


# --------------------------------------------------------------------------
# Material identity and state
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CompositionEntry:
    constituent: str
    fraction: NamedQuantity

    def __post_init__(self) -> None:
        object.__setattr__(self, "constituent", _identifier(self.constituent, "constituent"))
        if not isinstance(self.fraction, NamedQuantity) or not self.fraction.value.is_compatible_with("dimensionless"):
            raise InvalidScientificProblem("composition fractions are dimensionless NamedQuantity records")
        if not 0 <= self.fraction.value.magnitude_in("dimensionless") <= 1:
            raise InvalidScientificProblem("composition fraction must lie in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {"constituent": self.constituent, "fraction": self.fraction.to_dict()}


@dataclass(frozen=True)
class MaterialIdentity:
    """What a material *is*, as declared; never inferred from a common name.

    ``family`` alone is refused: at least one of specification, grade or
    composition must be declared.  Undeclared fields stay empty and are part
    of the identity -- "grade unknown" and "grade X" are different materials.
    """

    family: str
    specification: str = ""
    grade: str = ""
    condition: str = ""
    composition: tuple[CompositionEntry, ...] = ()
    form: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "family", _identifier(self.family, "material family"))
        for label in ("specification", "grade", "condition", "form"):
            object.__setattr__(self, label, str(getattr(self, label) or "").strip())
        comp = tuple(self.composition)
        if any(not isinstance(c, CompositionEntry) for c in comp) or len({c.constituent for c in comp}) != len(comp):
            raise InvalidScientificProblem("composition must be unique CompositionEntry records")
        object.__setattr__(self, "composition", tuple(sorted(comp, key=lambda c: c.constituent)))
        if not (self.specification or self.grade or comp):
            raise InvalidScientificProblem(
                f"material {self.family!r} is identified by family only; declare a specification, grade or composition"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"schema": MATERIAL_IDENTITY_SCHEMA, "family": self.family, "specification": self.specification, "grade": self.grade, "condition": self.condition, "composition": [c.to_dict() for c in self.composition], "form": self.form}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    @property
    def subject_key(self) -> str:
        """The ``KnowledgeClaim.subject`` that names exactly this material."""
        return f"material:{self.digest}"

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "MaterialIdentity":
        require_schema(p, MATERIAL_IDENTITY_SCHEMA)
        _strict_keys(p, {"schema", "family", "specification", "grade", "condition", "composition", "form"}, "material identity")
        return cls(p["family"], p["specification"], p["grade"], p["condition"], tuple(CompositionEntry(c["constituent"], NamedQuantity.from_dict(c["fraction"])) for c in p["composition"]), p["form"])


@dataclass(frozen=True)
class MaterialStateSchema:
    """The owning domain's declared state variables and their physical ranges.

    Non-physical state (a non-positive thickness, a moisture fraction above
    one) is refused here, by the contract that owns the variable -- not by a
    lifecycle heuristic.
    """

    schema_id: str
    ranges: tuple[ApplicabilityRange, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_id", _identifier(self.schema_id, "state schema_id"))
        object.__setattr__(self, "ranges", _ranges(self.ranges, "state schema ranges"))

    def check(self, values: Mapping[str, Quantity]) -> None:
        declared = {r.variable_id: r for r in self.ranges}
        unknown = sorted(set(values) - set(declared))
        if unknown:
            raise InvalidScientificProblem(f"state schema {self.schema_id!r} does not declare {unknown}")
        for key, value in values.items():
            if not declared[key].admits(value):
                raise InvalidScientificProblem(
                    f"state {key}={value.magnitude} {value.units} lies outside the physical range "
                    f"declared by {self.schema_id!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {"schema": STATE_SCHEMA_SCHEMA, "schema_id": self.schema_id, "ranges": [r.to_dict() for r in self.ranges]}


@dataclass(frozen=True)
class MaterialState:
    """Declared conditions of one identified material.  Nothing is defaulted."""

    material: MaterialIdentity
    conditions: tuple[NamedQuantity, ...] = ()
    phase: str = ""
    schema: MaterialStateSchema | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.material, MaterialIdentity):
            raise InvalidScientificProblem("material state requires a MaterialIdentity")
        conditions = tuple(self.conditions)
        if any(not isinstance(c, NamedQuantity) for c in conditions) or len({c.quantity_id for c in conditions}) != len(conditions):
            raise InvalidScientificProblem("material state conditions must be unique NamedQuantity records")
        object.__setattr__(self, "conditions", tuple(sorted(conditions)))
        object.__setattr__(self, "phase", str(self.phase or "").strip())
        if self.schema is not None:
            self.schema.check({c.quantity_id: c.value for c in conditions})

    def condition(self, variable_id: str) -> NamedQuantity | None:
        return next((c for c in self.conditions if c.quantity_id == variable_id), None)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": MATERIAL_STATE_SCHEMA, "material": self.material.to_dict(), "conditions": [c.to_dict() for c in self.conditions], "phase": self.phase, "state_schema": None if self.schema is None else self.schema.to_dict()}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())
