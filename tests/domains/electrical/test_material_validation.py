"""What a resistance evaluation establishes, and what it cannot.

``ResistancePropertySolver`` emitted one check, ``resistance_strictly_positive``,
and that check is an admissibility bound: it confirms a number is in the range
the surrounding linear DC formulation accepts, which is not verification
against anything. Every credibility package built on a resistance evaluation
was therefore ``INSUFFICIENT_EVIDENCE`` — correctly, and named as the second
casualty in ``NEEDS.md`` §1.8b.

The audit in ``docs/domains/evidentiary-levels.md`` resolved it the only way
available: not by relabelling the admissibility check, which would still
establish nothing, but by adding one that compares the emitted metric against a
reference outside the solver's own arithmetic — the ``ModelOutputSpec`` on the
model record.

These tests hold both halves: the level is attained, and the admissibility
check still attains nothing.
"""

from __future__ import annotations

import dataclasses

import pytest

from engcore.domains.electrical import material as mat
from engcore.scientific.solvers.protocol import ConvergenceState
from engcore.scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
)
from engcore.scientific.units.quantity import Quantity

K = "kelvin"

CONDUCTOR = mat.TemperatureDependentConductor(
    component_id="R1",
    reference_resistance=Quantity(10.0, "ohm"),
    temperature_coefficient=Quantity(0.00393, "1/kelvin"),
    reference_temperature=Quantity(293.15, K),
)


def evaluated(temperature=Quantity(340.0, K), conductor=CONDUCTOR):
    problem = mat.build_resistance_problem(conductor)
    solver = mat.ResistancePropertySolver()
    solver.bind_conductor(conductor, problem.problem_id, temperature=temperature)
    prepared = solver.prepare(problem)
    raw = solver.solve(prepared)
    return solver.validate(prepared, raw), solver, prepared, raw


def check(report, name):
    return next(c for c in report.checks if c.name == name)


def test_the_evaluation_now_attains_a_level_and_names_which_check_earned_it():
    report, _, _, _ = evaluated()
    assert report.attained_levels == frozenset(
        {ValidationLevel.DIMENSIONALLY_VALID}
    )
    dimensions = check(report, "metric_dimensions")
    assert dimensions.outcome is ValidationOutcome.PASS
    assert dimensions.establishes is ValidationLevel.DIMENSIONALLY_VALID


def test_the_admissibility_check_still_establishes_nothing():
    """The gap was closed by a new check, not by promoting the old one.

    A positive resistance is a precondition, not evidence. If the level had
    been attached here the report would have improved without anything new
    having been verified — the substitution the attained-level rule exists to
    refuse.
    """
    report, _, _, _ = evaluated()
    admissibility = check(report, "resistance_strictly_positive")
    assert admissibility.outcome is ValidationOutcome.PASS
    assert admissibility.establishes is None


def test_the_dimensional_check_reads_the_model_record_and_not_the_solver():
    """The reference is outside the arithmetic, which is why the level is earned.

    Displacing the declared exemplar to an incompatible dimension makes the
    check fail. If the check were comparing the solver against itself it could
    not notice, because nothing about the computed number changed.
    """
    report, solver, prepared, raw = evaluated()
    assert check(report, "metric_dimensions").outcome is ValidationOutcome.PASS

    displaced = dataclasses.replace(
        mat.LINEAR_TCR_MODEL,
        outputs=tuple(
            dataclasses.replace(spec, unit_exemplar="kelvin")
            for spec in mat.LINEAR_TCR_MODEL.outputs
        ),
    )
    rated = dataclasses.replace(
        mat.RATED_LINEAR_TCR_MODEL,
        outputs=tuple(
            dataclasses.replace(spec, unit_exemplar="kelvin")
            for spec in mat.RATED_LINEAR_TCR_MODEL.outputs
        ),
    )
    original = (mat.LINEAR_TCR_MODEL, mat.RATED_LINEAR_TCR_MODEL)
    try:
        mat.LINEAR_TCR_MODEL, mat.RATED_LINEAR_TCR_MODEL = displaced, rated
        moved = solver.validate(prepared, raw)
    finally:
        mat.LINEAR_TCR_MODEL, mat.RATED_LINEAR_TCR_MODEL = original

    failed = check(moved, "metric_dimensions")
    assert failed.outcome is ValidationOutcome.FAIL
    assert failed.establishes is None
    assert moved.attained_levels == frozenset()


@pytest.mark.parametrize("temperature", [200.0, 293.15, 340.0, 600.0])
def test_the_level_does_not_depend_on_whether_the_model_was_applicable(
    temperature,
):
    """Dimensions are a property of the metric, applicability is not.

    600 K is outside the rated model's declared domain. The dimensional check
    is unmoved by that, and must be: conflating "the number carries the right
    unit" with "the model applied here" is the substitution the platform keeps
    two separate records to prevent.
    """
    report, _, _, _ = evaluated(Quantity(temperature, K))
    assert report.attained_levels == frozenset(
        {ValidationLevel.DIMENSIONALLY_VALID}
    )


def test_a_failed_evaluation_still_reports_one_failing_check_and_no_level():
    """The unsuccessful path was not given a level by accident."""
    _, solver, prepared, raw = evaluated()
    failed = solver.validate(
        prepared,
        dataclasses.replace(raw, convergence=ConvergenceState.DIVERGED),
    )
    assert not failed.attained_levels
    assert [c.name for c in failed.checks] == ["resistance_strictly_positive"]
    assert failed.checks[0].outcome is ValidationOutcome.FAIL
