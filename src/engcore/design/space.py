"""D0 — domain-neutral design-space contracts.

A design space declares *what may vary*. It does not generate candidates,
score them, execute solvers, or decide feasibility. Scientific typing stays in
the existing Scientific Core; this module only composes those contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.values import (
    BooleanValue,
    CategoricalValue,
    IntegerValue,
    ScientificValue,
    decode_value,
    encode_value,
    require_scientific_value,
)
from ..scientific.ir.variables import ScientificVariable, VariableKind, VariableRole
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity

DESIGN_SPACE_REFERENCE_SCHEMA = schema_string("design_space_reference")
DESIGN_SPACE_SCHEMA = schema_string("design_space")


@dataclass(frozen=True)
class DesignSpaceReference:
    """Stable reference to one exact design-space version."""

    space_id: str
    version: str

    def __post_init__(self) -> None:
        space_id = str(self.space_id).strip()
        version = str(self.version).strip()
        if not space_id:
            raise InvalidScientificProblem("design-space reference requires space_id")
        if not version:
            raise InvalidScientificProblem("design-space reference requires version")
        object.__setattr__(self, "space_id", space_id)
        object.__setattr__(self, "version", version)

    @property
    def key(self) -> tuple[str, str]:
        return (self.space_id, self.version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DESIGN_SPACE_REFERENCE_SCHEMA,
            "space_id": self.space_id,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DesignSpaceReference":
        require_schema(payload, DESIGN_SPACE_REFERENCE_SCHEMA)
        return cls(space_id=payload["space_id"], version=payload["version"])


@dataclass(frozen=True)
class DesignSpace:
    """Immutable declaration of the choices a design study may vary.

    D0 validates representation only. ``constraint_refs`` are identifiers for
    rules owned by a domain/system layer; this class deliberately does not
    execute arbitrary predicates or import product-specific logic.
    """

    space_id: str
    version: str
    variables: tuple[ScientificVariable, ...]
    constraint_refs: tuple[str, ...] = ()
    name: str = ""
    description: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        space_id = str(self.space_id).strip()
        version = str(self.version).strip()
        if not space_id:
            raise InvalidScientificProblem("design space requires a non-empty space_id")
        if not version:
            raise InvalidScientificProblem("design space requires a non-empty version")

        variables = tuple(self.variables)
        if not variables:
            raise InvalidScientificProblem("design space requires at least one variable")
        if any(not isinstance(v, ScientificVariable) for v in variables):
            raise InvalidScientificProblem(
                "design-space variables must be ScientificVariable records"
            )
        if any(v.role is not VariableRole.DESIGN for v in variables):
            raise InvalidScientificProblem(
                "design-space variables must all have role DESIGN"
            )
        names = [v.name for v in variables]
        if len(names) != len(set(names)):
            raise InvalidScientificProblem("design-space variable names must be unique")

        refs = tuple(str(ref).strip() for ref in self.constraint_refs)
        if any(not ref for ref in refs):
            raise InvalidScientificProblem("design constraint references must be non-empty")
        if len(refs) != len(set(refs)):
            raise InvalidScientificProblem("duplicate design constraint references")

        object.__setattr__(self, "space_id", space_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "variables", variables)
        object.__setattr__(self, "constraint_refs", refs)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def reference(self) -> DesignSpaceReference:
        return DesignSpaceReference(self.space_id, self.version)

    @property
    def variable_map(self) -> dict[str, ScientificVariable]:
        return {variable.name: variable for variable in self.variables}

    def validate_assignments(
        self, assignments: Mapping[str, ScientificValue]
    ) -> dict[str, ScientificValue]:
        """Validate a complete candidate assignment, failing closed.

        The returned mapping follows design-space variable order. No search
        encoding is implied by this validation; all four represented variable
        kinds remain typed scientific values.
        """
        supplied = dict(assignments)
        expected_names = [variable.name for variable in self.variables]
        expected = set(expected_names)
        actual = set(supplied)

        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing:
            raise InvalidScientificProblem(
                f"design candidate is missing variables: {missing}"
            )
        if extra:
            raise InvalidScientificProblem(
                f"design candidate contains undeclared variables: {extra}"
            )

        validated: dict[str, ScientificValue] = {}
        for variable in self.variables:
            value = supplied[variable.name]
            require_scientific_value(
                value, context=f"design assignment {variable.name!r}"
            )
            self._validate_value(variable, value)
            validated[variable.name] = value
        return validated

    @staticmethod
    def _validate_value(variable: ScientificVariable, value: ScientificValue) -> None:
        if variable.kind is VariableKind.CONTINUOUS:
            if not isinstance(value, Quantity):
                raise InvalidScientificProblem(
                    f"continuous design variable {variable.name!r} requires Quantity"
                )
            variable.require_within_bounds(value)
            return

        if variable.kind is VariableKind.INTEGER:
            if not isinstance(value, IntegerValue):
                raise InvalidScientificProblem(
                    f"integer design variable {variable.name!r} requires IntegerValue"
                )
            # ScientificVariable owns dimensional/bound semantics. IntegerValue
            # owns discreteness; wrapping only for the existing bound check does
            # not turn the stored candidate value into a Quantity.
            variable.require_within_bounds(Quantity(value.value, variable.unit))
            return

        if variable.kind is VariableKind.CATEGORICAL:
            if not isinstance(value, CategoricalValue):
                raise InvalidScientificProblem(
                    f"categorical design variable {variable.name!r} requires CategoricalValue"
                )
            if value.value not in variable.categories:
                raise InvalidScientificProblem(
                    f"category {value.value!r} is not allowed for design variable "
                    f"{variable.name!r}: {list(variable.categories)!r}"
                )
            return

        if variable.kind is VariableKind.BOOLEAN:
            if not isinstance(value, BooleanValue):
                raise InvalidScientificProblem(
                    f"boolean design variable {variable.name!r} requires BooleanValue"
                )
            return

        raise InvalidScientificProblem(
            f"unsupported design variable kind {variable.kind!r}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DESIGN_SPACE_SCHEMA,
            "space_id": self.space_id,
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "variables": [variable.to_dict() for variable in self.variables],
            "constraint_refs": list(self.constraint_refs),
            "metadata": dict(sorted(self.metadata.items(), key=lambda item: item[0])),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DesignSpace":
        require_schema(payload, DESIGN_SPACE_SCHEMA)
        return cls(
            space_id=payload["space_id"],
            version=payload["version"],
            name=payload.get("name", ""),
            description=payload.get("description", ""),
            variables=tuple(
                ScientificVariable.from_dict(item)
                for item in payload.get("variables", ())
            ),
            constraint_refs=tuple(payload.get("constraint_refs", ())),
            metadata=dict(payload.get("metadata", {})),
        )
