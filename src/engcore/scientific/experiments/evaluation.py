"""One evaluation of one candidate.

    candidate parameters -> solver execution -> ScientificResult

An evaluation records the outcome *including the ways it can fail*. A failed
or scientifically invalid evaluation is evidence, not a gap: it keeps its
candidate, its status and its reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..errors import ScientificCoreError
from ..ir.constraints import ConstraintCheck
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..results.result import ScientificResult

EVALUATION_SCHEMA = schema_string("scientific_evaluation")


class EvaluationStatus(str, Enum):
    """Outcome classes with genuinely different consumer semantics."""

    OK = "ok"                    # completed, values usable
    NOT_CONVERGED = "not_converged"  # completed, values present but untrusted
    INVALID = "invalid"          # scientifically invalid candidate/point
    FAILED = "failed"            # infrastructure failure, no information
    NOT_RUN = "not_run"          # proposed but never executed


@dataclass(frozen=True)
class ScientificEvaluation:
    """A candidate, what happened to it, and what came back."""

    evaluation_id: str
    candidate: Mapping[str, Quantity]
    status: EvaluationStatus = EvaluationStatus.NOT_RUN
    result: ScientificResult | None = None
    objective_values: Mapping[str, Quantity] = field(default_factory=dict)
    constraint_checks: tuple[ConstraintCheck, ...] = ()
    detail: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        evaluation_id = str(self.evaluation_id).strip()
        if not evaluation_id:
            raise ScientificCoreError("evaluation requires a non-empty id")
        object.__setattr__(self, "evaluation_id", evaluation_id)
        object.__setattr__(self, "status", EvaluationStatus(self.status))

        candidate = dict(self.candidate)
        for name, value in candidate.items():
            if not isinstance(value, Quantity):
                raise ScientificCoreError(
                    f"candidate value {name!r} must be a Quantity"
                )
        object.__setattr__(self, "candidate", candidate)

        objectives = dict(self.objective_values)
        for name, value in objectives.items():
            if not isinstance(value, Quantity):
                raise ScientificCoreError(
                    f"objective value {name!r} must be a Quantity"
                )
        object.__setattr__(self, "objective_values", objectives)
        object.__setattr__(self, "constraint_checks", tuple(self.constraint_checks))
        object.__setattr__(self, "metadata", dict(self.metadata))

        if self.status is EvaluationStatus.OK and self.result is None:
            raise ScientificCoreError(
                f"evaluation {evaluation_id!r} reports OK but carries no result"
            )
        if self.status is EvaluationStatus.FAILED and self.result is not None:
            raise ScientificCoreError(
                f"evaluation {evaluation_id!r} is FAILED but carries a result; "
                f"a failed run yields no scientific information"
            )

    @property
    def is_feasible(self) -> bool | None:
        """True/False when constraints were checked, None when they were not."""
        if not self.constraint_checks:
            return None
        return all(check.satisfied for check in self.constraint_checks)

    @property
    def consumed_budget(self) -> bool:
        """Whether this evaluation spent scientific budget.

        FAILED runs consume compute but produce no observation; the experiment
        counts them separately (see :class:`ScientificExperiment`).
        """
        return self.status in (
            EvaluationStatus.OK,
            EvaluationStatus.NOT_CONVERGED,
            EvaluationStatus.INVALID,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EVALUATION_SCHEMA,
            "evaluation_id": self.evaluation_id,
            "status": self.status.value,
            "candidate": {
                k: self.candidate[k].to_dict() for k in sorted(self.candidate)
            },
            "result": self.result.to_dict() if self.result else None,
            "objective_values": {
                k: self.objective_values[k].to_dict()
                for k in sorted(self.objective_values)
            },
            "constraint_checks": [c.to_dict() for c in self.constraint_checks],
            "detail": self.detail,
            "metadata": dict(sorted(self.metadata.items(), key=lambda kv: kv[0])),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificEvaluation":
        require_schema(payload, EVALUATION_SCHEMA)
        result = payload.get("result")
        return cls(
            evaluation_id=payload["evaluation_id"],
            status=EvaluationStatus(payload.get("status", "not_run")),
            candidate={
                k: Quantity.from_dict(v)
                for k, v in (payload.get("candidate") or {}).items()
            },
            result=ScientificResult.from_dict(result) if result else None,
            objective_values={
                k: Quantity.from_dict(v)
                for k, v in (payload.get("objective_values") or {}).items()
            },
            constraint_checks=tuple(
                ConstraintCheck.from_dict(c)
                for c in payload.get("constraint_checks", ())
            ),
            detail=payload.get("detail", ""),
            metadata=dict(payload.get("metadata", {})),
        )
