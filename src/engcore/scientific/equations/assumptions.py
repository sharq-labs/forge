"""Machine-checkable scientific assumptions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from .constraints import ExpressionConstraint, ConstraintEvaluation, evaluate_constraint
from .errors import EquationEvaluationError

ASSUMPTION_SCHEMA = schema_string("checkable_scientific_assumption")
ASSUMPTION_ASSESSMENT_SCHEMA = schema_string("scientific_assumption_assessment")


class AssumptionStatus(str, Enum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CheckableAssumption:
    assumption_id: str
    constraint: ExpressionConstraint
    statement: str = ""

    def __post_init__(self) -> None:
        aid = str(self.assumption_id).strip()
        if not aid:
            raise InvalidScientificProblem("checkable assumption requires an id")
        if not isinstance(self.constraint, ExpressionConstraint):
            raise InvalidScientificProblem("checkable assumption requires an ExpressionConstraint")
        object.__setattr__(self, "assumption_id", aid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ASSUMPTION_SCHEMA,
            "assumption_id": self.assumption_id,
            "constraint": self.constraint.to_dict(),
            "statement": self.statement,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CheckableAssumption":
        require_schema(payload, ASSUMPTION_SCHEMA)
        return cls(
            payload["assumption_id"],
            ExpressionConstraint.from_dict(payload["constraint"]),
            payload.get("statement", ""),
        )


@dataclass(frozen=True)
class AssumptionAssessment:
    assumption_id: str
    status: AssumptionStatus
    evaluation: ConstraintEvaluation | None = None
    problem: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", AssumptionStatus(self.status))
        if self.status is AssumptionStatus.UNKNOWN and not str(self.problem).strip():
            raise InvalidScientificProblem("unknown assumption assessment must state the problem")
        if self.status is not AssumptionStatus.UNKNOWN and self.evaluation is None:
            raise InvalidScientificProblem("decided assumption assessment requires an evaluation")
        if self.evaluation is not None:
            expected = AssumptionStatus.SATISFIED if self.evaluation.satisfied else AssumptionStatus.VIOLATED
            if self.status is not expected:
                raise InvalidScientificProblem("assumption status disagrees with its constraint evaluation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ASSUMPTION_ASSESSMENT_SCHEMA,
            "assumption_id": self.assumption_id,
            "status": self.status.value,
            "evaluation": None if self.evaluation is None else self.evaluation.to_dict(),
            "problem": self.problem,
        }

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"AssumptionAssessment":
        require_schema(payload,ASSUMPTION_ASSESSMENT_SCHEMA)
        evaluation=payload.get("evaluation")
        return cls(
            payload["assumption_id"],AssumptionStatus(payload["status"]),
            ConstraintEvaluation.from_dict(evaluation) if evaluation is not None else None,
            payload.get("problem",""),
        )


def assess_assumption(
    assumption: CheckableAssumption,
    bindings: Mapping[str, Quantity],
    *,
    derivative_bindings: Mapping[str, Quantity] | None = None,
) -> AssumptionAssessment:
    try:
        evaluation = evaluate_constraint(
            assumption.constraint, bindings, derivative_bindings=derivative_bindings
        )
    except (EquationEvaluationError, KeyError, ValueError) as exc:
        return AssumptionAssessment(
            assumption.assumption_id, AssumptionStatus.UNKNOWN, None, str(exc)
        )
    status = AssumptionStatus.SATISFIED if evaluation.satisfied else AssumptionStatus.VIOLATED
    return AssumptionAssessment(assumption.assumption_id, status, evaluation)


@dataclass(frozen=True)
class AssumptionSet:
    assumptions: tuple[CheckableAssumption, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        if any(not isinstance(a, CheckableAssumption) for a in self.assumptions):
            raise InvalidScientificProblem("AssumptionSet accepts only CheckableAssumption records")
        ids=[a.assumption_id for a in self.assumptions]
        if len(ids) != len(set(ids)):
            raise InvalidScientificProblem("AssumptionSet contains duplicate ids")

    def require_dimensions(self, symbol_units: Mapping[str, str]) -> None:
        for assumption in self.assumptions:
            assumption.constraint.require_dimensions(symbol_units)

    def assess(self, bindings: Mapping[str, Quantity], *,
               derivative_bindings: Mapping[str, Quantity] | None = None) -> tuple[AssumptionAssessment, ...]:
        return tuple(
            assess_assumption(a, bindings, derivative_bindings=derivative_bindings)
            for a in self.assumptions
        )
