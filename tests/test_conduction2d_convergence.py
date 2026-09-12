"""Does the discretisation actually solve the equation it claims to?

Sprint 4, Phases 8 and 9. A solver that returns a plausible-looking field is
not evidence of anything: the only claim worth making is that the error falls
at the rate the scheme predicts, measured against a solution that is known in
closed form.

The order is **computed from the measured errors** and asserted against a
floor. Nothing here asserts "second order" as a constant, and if the scheme
regresses to first order at a boundary the number moves and the test fails.
That is the point of the second case: an insulated plate and a plain Dirichlet
plate are both reproduced perfectly well by a first-order flux condition, so
neither would catch it.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.domains.thermal_models.conduction2d import solve_steady_conduction
from tests.manufactured_conduction2d import (
    COSINE_COLUMN,
    MANUFACTURED,
    REFINEMENTS,
    SINE_PLATE,
    errors,
    observed_order,
    spacing_of,
    square,
)

#: The scheme is formally second order. A floor rather than an equality: the
#: measured value approaches 2 from either side and is not exactly 2 at any
#: finite resolution.
ORDER_FLOOR = 1.9


def study(case, refinements=REFINEMENTS):
    """``[(h, l2, linf)]`` over a refinement sequence, coarsest first."""
    rows = []
    for nodes in refinements:
        mesh = square(nodes)
        solution = solve_steady_conduction(
            case.problem(mesh), run_id=f"convergence:{case.name}:{nodes}"
        )
        l2, linf = errors(solution.values.values, case.exact_on(mesh))
        rows.append((spacing_of(mesh), l2, linf))
    return rows


@pytest.fixture(scope="module")
def studies():
    return {case.name: study(case) for case in MANUFACTURED}


@pytest.mark.parametrize("case", MANUFACTURED, ids=lambda case: case.name)
def test_the_error_falls_monotonically_under_refinement(studies, case):
    rows = studies[case.name]
    l2 = [row[1] for row in rows]
    linf = [row[2] for row in rows]
    assert l2 == sorted(l2, reverse=True), f"L2 did not fall monotonically: {l2}"
    assert linf == sorted(linf, reverse=True), f"Linf did not fall monotonically: {linf}"


@pytest.mark.parametrize("case", MANUFACTURED, ids=lambda case: case.name)
@pytest.mark.parametrize("metric, column", [("l2", 1), ("linf", 2)])
def test_the_measured_order_is_second(studies, case, metric, column):
    rows = studies[case.name]
    orders = [
        observed_order(
            (rows[i - 1][0], rows[i - 1][column]), (rows[i][0], rows[i][column])
        )
        for i in range(1, len(rows))
    ]
    assert all(order >= ORDER_FLOOR for order in orders), (
        f"{case.name} {metric} orders {[round(o, 3) for o in orders]} "
        f"fall below {ORDER_FLOOR}"
    )


def test_the_finest_solution_is_close_in_absolute_terms(studies):
    """A rate with a large constant in front of it is still a wrong answer."""
    for case in MANUFACTURED:
        _, l2, linf = studies[case.name][-1]
        assert linf < 5e-3, f"{case.name} Linf at the finest support is {linf:.3e} K"
        assert l2 < 5e-3


def test_the_flux_edge_is_where_a_first_order_condition_would_show():
    """The discriminating case carries a non-zero flux, not an insulated edge."""
    mesh = square(32)
    problem = COSINE_COLUMN.problem(mesh)
    top = next(
        condition
        for edge, condition in problem.edges.items()
        if edge.value == "top"
    )
    assert top.kind.value == "neumann"
    assert top.value.magnitude_in("watt/meter**2") > 1.0

    solution = solve_steady_conduction(problem, run_id="flux-edge")
    exact = COSINE_COLUMN.exact_on(mesh)
    top_row_error = float(np.max(np.abs(solution.values.values[-1, :] - exact[-1, :])))
    interior_error = float(np.max(np.abs(solution.values.values[1:-1, :] - exact[1:-1, :])))
    assert top_row_error <= 4.0 * interior_error, (
        f"the flux edge carries {top_row_error:.3e} against {interior_error:.3e} "
        f"inside, which is the signature of a first-order boundary condition"
    )


def test_the_manufactured_source_is_a_field_not_a_number(studies):
    """The oracle exercises the field-valued source path, not a uniform shortcut."""
    problem = SINE_PLATE.problem(square(16))
    assert problem.source is not None
    assert problem.source.shape == (16, 16)
    assert problem.source.unit == "watt / meter ** 3"
    assert problem.source.values.std() > 0.0
