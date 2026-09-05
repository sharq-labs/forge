"""D0 — immutable design candidate identity and lineage.

A candidate is a declared choice set bound to one exact Scientific Twin. It is
not itself evidence, a solver result, a feasibility decision, or a validation
claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.values import (
    ScientificValue,
    decode_value,
    encode_value,
    require_scientific_value,
)
from ..scientific.serialization import require_schema, schema_string
from ..scientific.twins.definition import TwinReference
from .space import DesignSpace, DesignSpaceReference

DESIGN_CANDIDATE_REFERENCE_SCHEMA = schema_string("design_candidate_reference")
DESIGN_CANDIDATE_SCHEMA = schema_string("design_candidate")


@dataclass(frozen=True)
class DesignCandidateReference:
    """Stable reference to a candidate identity."""

    candidate_id: str

    def __post_init__(self) -> None:
        candidate_id = str(self.candidate_id).strip()
        if not candidate_id:
            raise InvalidScientificProblem("candidate reference requires candidate_id")
        object.__setattr__(self, "candidate_id", candidate_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DESIGN_CANDIDATE_REFERENCE_SCHEMA,
            "candidate_id": self.candidate_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DesignCandidateReference":
        require_schema(payload, DESIGN_CANDIDATE_REFERENCE_SCHEMA)
        return cls(candidate_id=payload["candidate_id"])


@dataclass(frozen=True)
class DesignCandidate:
    """One exact design choice set represented by one exact Scientific Twin."""

    candidate_id: str
    design_space: DesignSpaceReference
    twin: TwinReference
    assignments: Mapping[str, ScientificValue]
    generation: int = 0
    parents: tuple[DesignCandidateReference, ...] = ()
    operator: str = "declared"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        candidate_id = str(self.candidate_id).strip()
        if not candidate_id:
            raise InvalidScientificProblem("design candidate requires candidate_id")
        if not isinstance(self.design_space, DesignSpaceReference):
            raise InvalidScientificProblem(
                "design candidate requires an exact DesignSpaceReference"
            )
        if not isinstance(self.twin, TwinReference):
            raise InvalidScientificProblem(
                "design candidate requires an exact TwinReference"
            )
        if isinstance(self.generation, bool) or not isinstance(self.generation, int):
            raise InvalidScientificProblem("candidate generation must be an integer")
        if self.generation < 0:
            raise InvalidScientificProblem("candidate generation cannot be negative")

        assignments = dict(self.assignments)
        for name, value in assignments.items():
            if not isinstance(name, str) or not name.strip():
                raise InvalidScientificProblem(
                    "design assignment names must be non-empty strings"
                )
            require_scientific_value(
                value, context=f"design assignment {name!r}"
            )

        parents = tuple(self.parents)
        if any(not isinstance(parent, DesignCandidateReference) for parent in parents):
            raise InvalidScientificProblem(
                "candidate parents must be DesignCandidateReference records"
            )
        parent_ids = [parent.candidate_id for parent in parents]
        if len(parent_ids) != len(set(parent_ids)):
            raise InvalidScientificProblem("candidate parent references must be unique")
        if candidate_id in parent_ids:
            raise InvalidScientificProblem("design candidate cannot be its own parent")
        if self.generation == 0 and parents:
            raise InvalidScientificProblem(
                "generation-zero candidate cannot declare parent candidates"
            )
        if self.generation > 0 and not parents:
            raise InvalidScientificProblem(
                "derived generation requires at least one parent candidate"
            )

        operator = str(self.operator).strip()
        if not operator:
            raise InvalidScientificProblem("candidate operator must be non-empty")

        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "assignments", assignments)
        object.__setattr__(self, "parents", parents)
        object.__setattr__(self, "operator", operator)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def reference(self) -> DesignCandidateReference:
        return DesignCandidateReference(self.candidate_id)

    def validate_against(self, space: DesignSpace) -> "DesignCandidate":
        """Prove structural/type compatibility with the referenced design space."""
        if not isinstance(space, DesignSpace):
            raise InvalidScientificProblem("candidate validation requires DesignSpace")
        if self.design_space.key != space.reference.key:
            raise InvalidScientificProblem(
                "candidate design-space reference does not match supplied DesignSpace"
            )
        space.validate_assignments(self.assignments)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DESIGN_CANDIDATE_SCHEMA,
            "candidate_id": self.candidate_id,
            "design_space": self.design_space.to_dict(),
            "twin": self.twin.to_dict(),
            "assignments": {
                name: encode_value(value)
                for name, value in sorted(self.assignments.items(), key=lambda item: item[0])
            },
            "generation": self.generation,
            "parents": [parent.to_dict() for parent in self.parents],
            "operator": self.operator,
            "metadata": dict(sorted(self.metadata.items(), key=lambda item: item[0])),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DesignCandidate":
        require_schema(payload, DESIGN_CANDIDATE_SCHEMA)
        return cls(
            candidate_id=payload["candidate_id"],
            design_space=DesignSpaceReference.from_dict(payload["design_space"]),
            twin=TwinReference.from_dict(payload["twin"]),
            assignments={
                name: decode_value(value)
                for name, value in payload.get("assignments", {}).items()
            },
            generation=payload.get("generation", 0),
            parents=tuple(
                DesignCandidateReference.from_dict(parent)
                for parent in payload.get("parents", ())
            ),
            operator=payload.get("operator", "declared"),
            metadata=dict(payload.get("metadata", {})),
        )
