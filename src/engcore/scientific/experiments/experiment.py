"""ScientificExperiment — a scientific study over one problem.

Deliberately not a scheduler. No threads, no processes, no distribution: it
records what a study is, what it has spent, and what it has observed, so that
an execution layer can be added later without changing the record format.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..errors import ScientificCoreError
from ..ir.constraints import ConstraintCheck, ConstraintDefinition
from ..ir.objectives import ObjectiveDefinition
from ..ir.problem import ScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension
# `_OBJECTIVE_AGREEMENT` is reused rather than re-chosen (R-42): it is the tolerance the same
# comparison already declares one module over, between two records of a single computed number.
from .evaluation import _OBJECTIVE_AGREEMENT, EvaluationStatus, ScientificEvaluation

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


def _established(evaluation: ScientificEvaluation) -> bool:
    """CORE-015: the evaluation's result names a model and every model it names was assessed IN_DOMAIN."""
    from ..models.definition import ValidityStatus

    result = evaluation.result
    models = tuple(getattr(result, "models", ()) or ())
    validity = getattr(result, "validity", None) or {}
    return bool(models) and all(
        model_id in validity and validity[model_id].status is ValidityStatus.IN_DOMAIN for model_id, _version in models
    )


def _declared_or_refuse(payload: Mapping[str, Any], key: str):
    """R-41: the payload's declaration under ``key``, refusing a record that does not state one."""
    if key not in payload:
        raise ScientificCoreError(
            f"experiment payload has no {key!r} key. `to_dict` always writes one, so this record was not "
            f"written by this class, and reading a missing declaration as an empty one is the worst "
            f"available reading: it silently drops what the study said it was judging candidates against. "
            f"An explicitly empty list is a narrowing to none and is read as written"
        )
    return payload[key] or ()


def _feasibility_problems(evaluation: ScientificEvaluation,
                          constraints: tuple[ConstraintDefinition, ...]) -> list[str]:
    """R-41: why this candidate's declared constraints are not shown satisfied, or [] when they are.

    CORE-015 claims "declared constraints checked and satisfied" and the rule was `all(check.satisfied)`
    over whatever checks the evaluation happened to carry. `all()` over an empty or unrelated set is True, so
    a candidate that checked one of two declared constraints was feasible, and a check naming a constraint
    the study does not have counted the same way.

    Three things are required here. COVERAGE: exactly one check per declared constraint, no duplicates and no
    undeclared names. AGREEMENT: every check satisfied. RE-DERIVATION: where the declared constraint's metric
    is present in the result's own values, the check is recomputed from the constraint definition and that
    value and the stored verdict is ignored -- a stored verdict is integrity-only, and here the inputs are in
    the record.
    """
    problems: list[str] = []
    declared = {c.name: c for c in constraints}
    checked: dict[str, ConstraintCheck] = {}
    for check in evaluation.constraint_checks:
        if check.constraint in checked:
            problems.append(f"constraint {check.constraint!r} is checked more than once")
            continue
        checked[check.constraint] = check
    undeclared = sorted(set(checked) - set(declared))
    if undeclared:
        problems.append(f"checks name constraint(s) this study does not declare: {undeclared}")
    missing = sorted(set(declared) - set(checked))
    if missing:
        problems.append(f"declared constraint(s) were never checked: {missing}")
    values = getattr(evaluation.result, "values", {}) or {}
    for name, definition in declared.items():
        check = checked.get(name)
        if check is None:
            continue
        if definition.metric in values:
            check = definition.check(values[definition.metric])
        if not check.satisfied:
            problems.append(f"constraint {name!r} is not satisfied (margin {check.margin})")
    return problems


def _ranked_value_problem(evaluation: ScientificEvaluation,
                          objective: ObjectiveDefinition) -> str | None:
    """R-42: whether the value this candidate would be ranked on contradicts its own result.

    The guard in `ScientificEvaluation` looks the result up by the OBJECTIVE's name, and an objective names
    its quantity through `metric` -- 'minimize_load' for metric 'load' -- so for the canonical shape the
    comparison never ran, and an evaluation reporting 0.001 W was ranked best while its own result carried
    50 W. A result that does not carry the metric at all is ranked on the objective value, as before: the
    rule reaches as far as the record does.
    """
    values = getattr(evaluation.result, "values", {}) or {}
    if objective.metric not in values:
        return None
    ranked = evaluation.objective_values[objective.name]
    carried = values[objective.metric]
    require_same_dimension(
        ranked, carried,
        context=(f"evaluation {evaluation.evaluation_id!r}: objective {objective.name!r} ranks on a "
                 f"quantity that must have the dimension of its metric {objective.metric!r}"),
    )
    stated = ranked.magnitude_in(carried.units)
    if math.isclose(stated, carried.magnitude, rel_tol=_OBJECTIVE_AGREEMENT, abs_tol=0.0):
        return None
    return (f"evaluation {evaluation.evaluation_id!r} would be ranked on objective {objective.name!r} = "
            f"{ranked}, and the result it carries reports its metric {objective.metric!r} = {carried}. "
            f"Ranking on a number the result contradicts is ranking on nothing")


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
        """Best established evaluation for one declared objective.

        Only OK evaluations are eligible: a value obtained from a non-converged
        solve is not a candidate for "best". Since CORE-015 (scientific core
        audit 2026-09-16) an OK evaluation must also be established: its result
        names at least one model and every one was assessed IN_DOMAIN, and, when
        the experiment declares constraints, they were checked and satisfied.
        A candidate whose validity is UNKNOWN or unassessed, or whose
        feasibility was never checked, was ranked on a value nothing showed
        applies -- often the most extreme one, which is why it won.
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
            # R-41: coverage, agreement and re-derivation, in place of `all()` over whatever checks a
            # candidate carried. With no declared constraints this is vacuously satisfied, which is the
            # `is_feasible is None and not self.constraints` case it replaces.
            and not _feasibility_problems(e, self.constraints)
            and _established(e)
        ]
        if not eligible:
            return None

        # R-42: a candidate whose own result contradicts the number it would be ranked on is a record that
        # holds two answers for one quantity. Refused rather than filtered out: excluding it quietly would
        # leave the contradiction in the study and rank the rest over records nobody checked.
        for evaluation in eligible:
            problem = _ranked_value_problem(evaluation, objective)
            if problem is not None:
                raise ScientificCoreError(problem)

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
            # R-41: a MISSING key is not an empty declaration. `to_dict` always writes both, so a payload
            # without one was not written by this class -- and reading it as "narrowed to nothing" removes
            # the feasibility requirement and changes which candidate `best` returns, while the problem the
            # record carries still declares the constraint. An explicitly empty list keeps its meaning.
            objectives=tuple(
                ObjectiveDefinition.from_dict(o)
                for o in _declared_or_refuse(payload, "objectives")
            ),
            constraints=tuple(
                ConstraintDefinition.from_dict(c)
                for c in _declared_or_refuse(payload, "constraints")
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
