"""One evaluation of one candidate.

    candidate parameters -> solver execution -> ScientificResult

An evaluation records the outcome *including the ways it can fail*. A failed
or scientifically invalid evaluation is evidence, not a gap: it keeps its
candidate, its status and its reason.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..errors import ScientificCoreError
from ..ir.constraints import ConstraintCheck
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension
from ..results.result import ScientificResult
from ..results.immutable import freeze

EVALUATION_SCHEMA = schema_string("scientific_evaluation")

#: Relative agreement required between an objective value and the result
#: value it names, after unit conversion. Tight: the two are meant to be the
#: same number, and only a round trip through a unit conversion separates them.
_OBJECTIVE_AGREEMENT = 1e-9


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
        object.__setattr__(self, "candidate", freeze(candidate))

        objectives = dict(self.objective_values)
        for name, value in objectives.items():
            if not isinstance(value, Quantity):
                raise ScientificCoreError(
                    f"objective value {name!r} must be a Quantity"
                )
        object.__setattr__(self, "objective_values", freeze(objectives))
        object.__setattr__(self, "constraint_checks", tuple(self.constraint_checks))
        object.__setattr__(self, "metadata", freeze(dict(self.metadata)))

        if self.status is EvaluationStatus.OK and self.result is None:
            raise ScientificCoreError(
                f"evaluation {evaluation_id!r} reports OK but carries no result"
            )
        if self.status is EvaluationStatus.OK:
            self._require_a_result_that_supports_ok(evaluation_id, objectives)
        if self.status is EvaluationStatus.FAILED and self.result is not None:
            raise ScientificCoreError(
                f"evaluation {evaluation_id!r} is FAILED but carries a result; "
                f"a failed run yields no scientific information"
            )

    def _require_a_result_that_supports_ok(
        self, evaluation_id: str, objectives: Mapping[str, Quantity]
    ) -> None:
        """OK means "completed, values usable", so the result must be usable.

        The status is the only thing ``ScientificExperiment.best`` filters on,
        and it was taken on the producer's word: a DIVERGED result, one whose
        validation FAILED, or one whose model was assessed OUTSIDE its
        validated domain could all sit under OK -- constructed or read back --
        and be ranked as the best candidate. Each of those has a status that
        says so (NOT_CONVERGED, INVALID), and the record now requires the one
        that is true.

        And an objective value naming a quantity the result carries must be
        that quantity: the ranking reads ``objective_values`` and never the
        result, so a disagreement between the two was a way to rank a
        candidate on a number its own result contradicts. An objective the
        result does not carry is derived elsewhere and is not cross-checked.
        """
        result = self.result
        if not isinstance(result, ScientificResult):
            raise ScientificCoreError(
                f"evaluation {evaluation_id!r} reports OK over a "
                f"{type(result).__name__}; OK needs a ScientificResult"
            )
        if not result.is_usable:
            raise ScientificCoreError(
                f"evaluation {evaluation_id!r} reports OK over result "
                f"{result.result_id!r}, which is not usable (convergence "
                f"{result.convergence.value}, validation "
                f"{result.validation_status.value}). OK means the values are "
                f"usable; report NOT_CONVERGED or INVALID"
            )
        # Imported here, not at module scope: the models package reaches this
        # module during its own import, and a module-scope import closes that
        # cycle.
        from ..models.definition import ValidityStatus

        outside = sorted(
            model_id
            for model_id, assessment in result.validity.items()
            if assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
        )
        if outside:
            raise ScientificCoreError(
                f"evaluation {evaluation_id!r} reports OK over result "
                f"{result.result_id!r}, whose model(s) {outside} were assessed "
                f"outside their validated domain. A value computed by an "
                f"inapplicable model is not a usable one; report INVALID"
            )
        for name, objective in objectives.items():
            if name not in result.values:
                continue
            carried = result.values[name]
            require_same_dimension(
                objective,
                carried,
                context=(
                    f"evaluation {evaluation_id!r}: objective {name!r} must "
                    f"carry the dimension of the result value of that name"
                ),
            )
            stated = objective.magnitude_in(carried.units)
            if not math.isclose(
                stated, carried.magnitude, rel_tol=_OBJECTIVE_AGREEMENT, abs_tol=0.0
            ):
                raise ScientificCoreError(
                    f"evaluation {evaluation_id!r}: objective {name!r} is "
                    f"{objective}, but the result it names carries {carried}. "
                    f"An objective naming a result quantity must be that "
                    f"quantity; ranking on a number the result contradicts is "
                    f"ranking on nothing"
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
