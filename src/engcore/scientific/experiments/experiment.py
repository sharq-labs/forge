"""ScientificExperiment — a scientific study over one problem.

Deliberately not a scheduler. No threads, no processes, no distribution: it
records what a study is, what it has spent, and what it has observed, so that
an execution layer can be added later without changing the record format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..errors import ScientificCoreError
from ..ir.constraints import ConstraintDefinition
from ..ir.objectives import ObjectiveDefinition
from ..ir.problem import ScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from .evaluation import EvaluationStatus, ScientificEvaluation

EXPERIMENT_SCHEMA = schema_string("scientific_experiment")


@dataclass(frozen=True)
class ExperimentBudget:
    """Separate counters for what was observed and what was attempted.

    A crashed 3-hour simulation consumed real compute but produced no
    observation. Collapsing the two would misreport both the science and the
    cost, so they are distinct.
    """

    max_observations: int
    max_attempts: int | None = None

    def __post_init__(self) -> None:
        max_observations = int(self.max_observations)
        if max_observations <= 0:
            raise ScientificCoreError("max_observations must be positive")
        object.__setattr__(self, "max_observations", max_observations)
        if self.max_attempts is not None:
            max_attempts = int(self.max_attempts)
            if max_attempts < max_observations:
                raise ScientificCoreError(
                    "max_attempts must be >= max_observations"
                )
            object.__setattr__(self, "max_attempts", max_attempts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_observations": self.max_observations,
            "max_attempts": self.max_attempts,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExperimentBudget":
        return cls(
            max_observations=payload["max_observations"],
            max_attempts=payload.get("max_attempts"),
        )


class ScientificExperiment:
    """A study: one problem, a budget, and an ordered evaluation history.

    Mutable by design (a study accumulates), but mutation is confined to
    :meth:`record` so budget accounting cannot be bypassed.
    """

    def __init__(
        self,
        experiment_id: str,
        problem: ScientificProblem,
        budget: ExperimentBudget,
        *,
        objectives: tuple[ObjectiveDefinition, ...] | None = None,
        constraints: tuple[ConstraintDefinition, ...] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        experiment_id = str(experiment_id).strip()
        if not experiment_id:
            raise ScientificCoreError("experiment requires a non-empty id")
        if not isinstance(problem, ScientificProblem):
            raise ScientificCoreError("experiment requires a ScientificProblem")

        self.experiment_id = experiment_id
        self.problem = problem
        self.budget = budget
        # An experiment may narrow the problem's objectives/constraints, but
        # never invent ones the problem did not declare.
        self.objectives = tuple(objectives) if objectives is not None else problem.objectives
        self.constraints = (
            tuple(constraints) if constraints is not None else problem.constraints
        )
        self._validate_subset()
        self.metadata = dict(metadata or {})
        self._evaluations: list[ScientificEvaluation] = []

    def _validate_subset(self) -> None:
        declared_objectives = {o.name for o in self.problem.objectives}
        for objective in self.objectives:
            if objective.name not in declared_objectives:
                raise ScientificCoreError(
                    f"experiment objective {objective.name!r} is not declared "
                    f"by problem {self.problem.problem_id!r}"
                )
        declared_constraints = {c.name for c in self.problem.constraints}
        for constraint in self.constraints:
            if constraint.name not in declared_constraints:
                raise ScientificCoreError(
                    f"experiment constraint {constraint.name!r} is not declared "
                    f"by problem {self.problem.problem_id!r}"
                )

    # ---- history ---------------------------------------------------------
    @property
    def evaluations(self) -> tuple[ScientificEvaluation, ...]:
        return tuple(self._evaluations)

    @property
    def attempts(self) -> int:
        return len(self._evaluations)

    @property
    def observations(self) -> int:
        """Evaluations that produced scientific information."""
        return sum(1 for e in self._evaluations if e.consumed_budget)

    @property
    def failures(self) -> int:
        return sum(
            1 for e in self._evaluations if e.status is EvaluationStatus.FAILED
        )

    @property
    def remaining_observations(self) -> int:
        return max(0, self.budget.max_observations - self.observations)

    @property
    def is_exhausted(self) -> bool:
        if self.remaining_observations <= 0:
            return True
        if self.budget.max_attempts is not None:
            return self.attempts >= self.budget.max_attempts
        return False

    def record(self, evaluation: ScientificEvaluation) -> None:
        """Append an evaluation, enforcing budget accounting."""
        if not isinstance(evaluation, ScientificEvaluation):
            raise ScientificCoreError("record() expects a ScientificEvaluation")
        if any(e.evaluation_id == evaluation.evaluation_id for e in self._evaluations):
            raise ScientificCoreError(
                f"duplicate evaluation id {evaluation.evaluation_id!r}"
            )
        if evaluation.consumed_budget and self.remaining_observations <= 0:
            raise ScientificCoreError(
                f"observation budget exhausted "
                f"({self.budget.max_observations}); cannot record "
                f"{evaluation.evaluation_id!r}"
            )
        if (
            self.budget.max_attempts is not None
            and self.attempts >= self.budget.max_attempts
        ):
            raise ScientificCoreError(
                f"attempt cap reached ({self.budget.max_attempts})"
            )
        self._evaluations.append(evaluation)

    # ---- study state -----------------------------------------------------
    def best(self, objective_name: str) -> ScientificEvaluation | None:
        """Best usable evaluation for one declared objective.

        Only OK evaluations with a feasible-or-unchecked constraint state are
        eligible: a value obtained from a non-converged solve is not a
        candidate for "best".
        """
        objective = next(
            (o for o in self.objectives if o.name == objective_name), None
        )
        if objective is None:
            raise ScientificCoreError(f"unknown objective {objective_name!r}")

        eligible = [
            e
            for e in self._evaluations
            if e.status is EvaluationStatus.OK
            and objective.name in e.objective_values
            and e.is_feasible is not False
        ]
        if not eligible:
            return None

        def key(evaluation: ScientificEvaluation) -> float:
            value = evaluation.objective_values[objective.name]
            return objective.sense * value.to(objective.unit).magnitude

        return max(eligible, key=key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": EXPERIMENT_SCHEMA,
            "experiment_id": self.experiment_id,
            "problem": self.problem.to_dict(),
            "budget": self.budget.to_dict(),
            "objectives": [o.to_dict() for o in self.objectives],
            "constraints": [c.to_dict() for c in self.constraints],
            "evaluations": [e.to_dict() for e in self._evaluations],
            "accounting": {
                "attempts": self.attempts,
                "observations": self.observations,
                "failures": self.failures,
                "remaining_observations": self.remaining_observations,
            },
            "metadata": dict(sorted(self.metadata.items(), key=lambda kv: kv[0])),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScientificExperiment":
        require_schema(payload, EXPERIMENT_SCHEMA)
        problem = ScientificProblem.from_dict(payload["problem"])
        experiment = cls(
            experiment_id=payload["experiment_id"],
            problem=problem,
            budget=ExperimentBudget.from_dict(payload["budget"]),
            objectives=tuple(
                ObjectiveDefinition.from_dict(o)
                for o in payload.get("objectives", ())
            ),
            constraints=tuple(
                ConstraintDefinition.from_dict(c)
                for c in payload.get("constraints", ())
            ),
            metadata=dict(payload.get("metadata", {})),
        )
        for record in payload.get("evaluations", ()):
            experiment.record(ScientificEvaluation.from_dict(record))
        return experiment


def candidate_from_parameters(
    problem: ScientificProblem, values: Mapping[str, Quantity]
) -> dict[str, Quantity]:
    """Validate a candidate against the problem's design variables."""
    candidate: dict[str, Quantity] = {}
    for variable in problem.design_variables:
        if variable.name not in values:
            raise ScientificCoreError(
                f"candidate is missing design variable {variable.name!r}"
            )
        candidate[variable.name] = variable.require_within_bounds(
            values[variable.name]
        )
    return candidate
