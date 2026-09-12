"""Solving problems that could not be declared before this sprint.

Sprint 5, Phases 9, 10 and 11. Three manufactured cases, each of which the
Sprint 4 API would have had to flatten to one number per edge — which is not an
approximation of these problems but a different problem.

The oracle is independent of the solver in the way that matters: each exact
field is a closed-form expression evaluated at the support's node coordinates,
sharing no code with `assemble`, no matrix, and no boundary handling. What the
solver is asked to do is recover it.

    sheared_plate           varying Dirichlet AND varying Neumann, exact
    harmonic_plate          one sinusoidal prescribed edge, convergent
    declared_source_plate   a source stated as a law rather than an array
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from engcore.domains.thermal_models.conduction2d import (
    CONDUCTIVITY_UNIT,
    FLUX_UNIT,
    solve_steady_conduction,
)
from engcore.scientific.fields import BoundaryEdge, ProfileAxis
from tests.manufactured_conduction2d import (
    CONDUCTIVITY,
    DECLARED_SOURCE_PLATE,
    HARMONIC_PLATE,
    SHEARED_PLATE,
    SINE_PLATE,
    errors,
    observed_order,
    spacing_of,
    square,
)

ORDER_FLOOR = 1.9


def solve(case, nodes):
    mesh = square(nodes)
    return mesh, solve_steady_conduction(
        case.problem(mesh), run_id=f"profiled:{case.name}:{nodes}"
    )


# ---- these cases genuinely need a law -------------------------------------------------
def test_each_new_case_declares_at_least_one_edge_that_varies():
    """Otherwise the suite would be testing the Sprint 4 API again."""
    varying = {}
    for case in (SHEARED_PLATE, HARMONIC_PLATE):
        problem = case.problem(square(16))
        varying[case.name] = [
            edge.value
            for edge, condition in problem.edges.items()
            if not condition.is_uniform
        ]
        assert varying[case.name], f"{case.name} has no varying edge"
    assert len(varying["sheared_plate"]) == 4, "every edge of the shear case varies"


def test_the_declared_source_case_varies_across_the_plate():
    problem = DECLARED_SOURCE_PLATE.problem(square(16))
    assert set(problem.source.axes) == {ProfileAxis.X, ProfileAxis.Y}
    assert all(condition.is_uniform for condition in problem.edges.values())


# ---- sheared_plate: exactness, not order -----------------------------------------------
@pytest.mark.parametrize("nodes", [16, 32, 64])
def test_a_bilinear_field_with_four_varying_edges_is_reproduced_exactly(nodes):
    """Two varying prescribed edges and two varying flux edges, all at once.

    The five-point operator is exact on a bilinear field and the ghost-node
    flux condition is exact on a normal derivative that does not vary along the
    normal, so anything above round-off here is a defect rather than truncation.
    """
    mesh, solution = solve(SHEARED_PLATE, nodes)
    exact = SHEARED_PLATE.exact_on(mesh)
    l2, linf = errors(solution.values.values, exact)
    scale = float(np.max(np.abs(exact)))
    assert linf / scale < 1e-9, f"Linf {linf:.3e} K is above round-off"
    assert l2 / scale < 1e-9


def test_the_solved_edges_match_the_laws_that_were_declared():
    """Phase 10: the boundary profile error, measured on the boundary.

    Not "the boundary is roughly right" — each prescribed node is compared
    against the law evaluated at that node's own physical coordinate.
    """
    mesh, solution = solve(SHEARED_PLATE, 32)
    values = solution.values.values
    problem = SHEARED_PLATE.problem(mesh)
    xs, ys = mesh.axis_coordinates()

    left = problem.edges[BoundaryEdge.LEFT].law
    worst_left = max(
        abs(values[j, 0] - left.evaluate(x=xs[0], y=y)) for j, y in enumerate(ys)
    )
    bottom = problem.edges[BoundaryEdge.BOTTOM].law
    worst_bottom = max(
        abs(values[0, i] - bottom.evaluate(x=x, y=ys[0])) for i, x in enumerate(xs)
    )
    scale = float(np.max(np.abs(values)))
    assert worst_left / scale < 1e-9, f"left edge is {worst_left:.3e} K from its law"
    assert worst_bottom / scale < 1e-9, f"bottom edge is {worst_bottom:.3e} K from its law"

    # And the laws really do vary, so the comparison is not vacuous.
    assert abs(left.evaluate(x=0.0, y=1.0) - left.evaluate(x=0.0, y=0.0)) > 1.0


def test_the_solved_flux_matches_the_flux_laws_that_were_declared():
    """Phase 10: the flux boundary error, computed from the solved field.

    The exact field's normal derivative does not vary along the normal, so a
    one-sided difference of the solution is an exact estimator of it — which
    makes this a genuine comparison against the declared law rather than a
    restatement of how the condition was assembled.
    """
    mesh, solution = solve(SHEARED_PLATE, 32)
    values = solution.values.values
    problem = SHEARED_PLATE.problem(mesh)
    k = CONDUCTIVITY.magnitude_in(CONDUCTIVITY_UNIT)
    xs, ys = mesh.axis_coordinates()
    dx = mesh.spacing_x.magnitude_in("meter")
    dy = mesh.spacing_y.magnitude_in("meter")

    right = problem.edges[BoundaryEdge.RIGHT].law
    worst_right = max(
        abs(
            -k * (values[j, -1] - values[j, -2]) / dx
            - right.evaluate(x=xs[-1], y=y)
        )
        for j, y in enumerate(ys)
    )
    top = problem.edges[BoundaryEdge.TOP].law
    worst_top = max(
        abs(-k * (values[-1, i] - values[-2, i]) / dy - top.evaluate(x=x, y=ys[-1]))
        for i, x in enumerate(xs)
    )
    scale = max(
        abs(right.evaluate(x=xs[-1], y=y)) for y in ys
    ) + max(abs(top.evaluate(x=x, y=ys[-1])) for x in xs)
    assert worst_right / scale < 1e-8, f"right flux is {worst_right:.3e} {FLUX_UNIT} out"
    assert worst_top / scale < 1e-8, f"top flux is {worst_top:.3e} {FLUX_UNIT} out"

    span = abs(right.evaluate(x=1.0, y=1.0) - right.evaluate(x=1.0, y=0.0))
    assert span > 1.0, "the flux law must vary or this proves nothing"


def test_a_constant_flux_could_not_have_passed_that_test():
    """The varying flux edge is not incidentally near-constant."""
    problem = SHEARED_PLATE.problem(square(32))
    law = problem.edges[BoundaryEdge.RIGHT].law
    ends = (law.evaluate(x=1.0, y=0.0), law.evaluate(x=1.0, y=1.0))
    mean = sum(ends) / 2.0
    assert max(abs(end - mean) for end in ends) > 100.0, (
        f"the best constant stand-in for this flux edge is {mean:g} and its "
        f"ends are {ends}; a constant is nowhere near it"
    )


# ---- harmonic_plate: Phase 11, measured order -------------------------------------------
@pytest.fixture(scope="module")
def harmonic_study():
    rows = []
    for nodes in (16, 32, 64, 128):
        mesh, solution = solve(HARMONIC_PLATE, nodes)
        l2, linf = errors(solution.values.values, HARMONIC_PLATE.exact_on(mesh))
        rows.append((spacing_of(mesh), l2, linf))
    return rows


@pytest.mark.parametrize("metric, column", [("l2", 1), ("linf", 2)])
def test_the_sinusoidal_edge_case_converges_at_second_order(harmonic_study, metric, column):
    orders = [
        observed_order(
            (harmonic_study[i - 1][0], harmonic_study[i - 1][column]),
            (harmonic_study[i][0], harmonic_study[i][column]),
        )
        for i in range(1, len(harmonic_study))
    ]
    assert all(order >= ORDER_FLOOR for order in orders), (
        f"harmonic_plate {metric} orders {[round(o, 3) for o in orders]} fall "
        f"below {ORDER_FLOOR}"
    )


def test_the_sinusoidal_edge_case_ends_close_in_absolute_terms(harmonic_study):
    _, l2, linf = harmonic_study[-1]
    assert linf < 1e-3, f"Linf at the finest support is {linf:.3e} K"
    assert l2 < 1e-3


# ---- declared_source_plate: a law where an array used to be ------------------------------
@pytest.mark.parametrize("nodes", [16, 32, 64])
def test_a_declared_source_reproduces_the_stored_array_it_replaces(nodes):
    """The law and the pre-evaluated array are the same source, to round-off.

    This is what makes the law a replacement rather than an alternative: the
    Sprint 4 case and this one differ only in whether the source was written
    down or handed over already evaluated.
    """
    mesh_a, stored = solve(SINE_PLATE, nodes)
    mesh_b, declared = solve(DECLARED_SOURCE_PLATE, nodes)
    assert mesh_a.fingerprint() == mesh_b.fingerprint()
    difference = float(
        np.max(np.abs(stored.values.values - declared.values.values))
    )
    scale = float(np.max(np.abs(stored.values.values)))
    assert difference / scale < 1e-9, (
        f"the declared law and the stored array disagree by {difference:.3e} K "
        f"on a field of {scale:.4g} K"
    )


def test_one_source_declaration_serves_every_resolution():
    """The Phase 1 complaint, answered.

    A stored source array belongs to the support it was evaluated on, so a
    refinement study had to re-evaluate the law outside the platform. The same
    declaration is used at all four resolutions here, and the errors fall.
    """
    declarations = set()
    l2s = []
    for nodes in (16, 32, 64, 128):
        mesh, solution = solve(DECLARED_SOURCE_PLATE, nodes)
        problem = DECLARED_SOURCE_PLATE.problem(mesh)
        declarations.add(problem.source.fingerprint())
        l2, _ = errors(solution.values.values, DECLARED_SOURCE_PLATE.exact_on(mesh))
        l2s.append(l2)

    assert len(declarations) == 1, (
        f"the source law changed between resolutions: {declarations}"
    )
    assert l2s == sorted(l2s, reverse=True), f"the error did not fall: {l2s}"
    orders = [
        observed_order(
            (spacing_of(square(n)), a), (spacing_of(square(m)), b)
        )
        for n, m, a, b in zip((16, 32, 64), (32, 64, 128), l2s, l2s[1:])
    ]
    assert all(order >= ORDER_FLOOR for order in orders), (
        f"declared_source_plate L2 orders {[round(o, 3) for o in orders]}"
    )


# ---- a law of the wrong dimension is still refused, wherever it is bound -------------------
def test_a_source_law_of_the_wrong_dimension_is_refused():
    """A law is not exempt from the unit check by being a law."""
    from engcore.domains.thermal_models.conduction2d import plate_problem
    from engcore.scientific.fields import LinearProfile1D
    from engcore.scientific.units.quantity import Quantity

    with pytest.raises(Exception, match="dimension of"):
        plate_problem(
            problem_id="wrong-source",
            mesh=square(16),
            conductivity=CONDUCTIVITY,
            edge_values={e: Quantity(300.0, "kelvin") for e in BoundaryEdge},
            source=LinearProfile1D(
                ProfileAxis.X, Quantity(1.0, "kelvin"), Quantity(1.0, "kelvin/meter")
            ),
        )


def test_a_flux_law_of_the_wrong_dimension_is_refused():
    from engcore.domains.thermal_models.conduction2d import plate_problem
    from engcore.scientific.fields import LinearProfile1D
    from engcore.scientific.ir.conditions import BoundaryKind
    from engcore.scientific.units.quantity import Quantity

    with pytest.raises(Exception, match="dimension of"):
        plate_problem(
            problem_id="wrong-flux",
            mesh=square(16),
            conductivity=CONDUCTIVITY,
            edge_values={
                BoundaryEdge.LEFT: Quantity(300.0, "kelvin"),
                BoundaryEdge.RIGHT: Quantity(300.0, "kelvin"),
                BoundaryEdge.BOTTOM: Quantity(300.0, "kelvin"),
                BoundaryEdge.TOP: LinearProfile1D(
                    ProfileAxis.X, Quantity(1.0, "volt"), Quantity(1.0, "volt/meter")
                ),
            },
            edge_kinds={BoundaryEdge.TOP: BoundaryKind.NEUMANN},
        )


def test_a_source_law_that_does_not_cover_the_plate_is_refused():
    from engcore.domains.thermal_models.conduction2d import SOURCE_UNIT, plate_problem
    from engcore.scientific.fields import TabulatedProfile1D
    from engcore.scientific.units.quantity import Quantity

    with pytest.raises(Exception, match="must cover"):
        plate_problem(
            problem_id="short-source",
            mesh=square(16),
            conductivity=CONDUCTIVITY,
            edge_values={e: Quantity(300.0, "kelvin") for e in BoundaryEdge},
            source=TabulatedProfile1D(
                ProfileAxis.X, (0.0, 0.5), (0.0, 100.0), unit=SOURCE_UNIT
            ),
        )


# ---- the criteria the profiled cases exposed ---------------------------------------------
@pytest.mark.parametrize("nodes", [16, 32, 64, 128])
@pytest.mark.parametrize(
    "case",
    [SINE_PLATE, HARMONIC_PLATE, SHEARED_PLATE, DECLARED_SOURCE_PLATE],
    ids=lambda case: case.name,
)
def test_every_manufactured_case_passes_its_own_validation_at_every_resolution(case, nodes):
    """The regression guard for a defect that shipped unnoticed in Sprint 4.

    `boundary_conditions_held` was judged against an **absolute** 1e-9 in the
    field's own unit, which asks for twelve significant digits of a field whose
    magnitudes are in the hundreds. Every manufactured case in the repository
    was failing it at every resolution — at Sprint 4's head too, verified there
    directly — and nothing caught it: the convergence study reads the error
    arrays and never the report, and the one test that reads the report uses a
    uniform plate whose boundary rows are all identical.

    So this asserts the thing that was never asserted.
    """
    _, solution = solve(case, nodes)
    failed = [
        (check.name, check.residual, check.tolerance)
        for check in solution.result.validation.checks
        if check.outcome.value != "pass"
    ]
    assert not failed, f"{case.name} at {nodes}: {failed}"


def test_the_relative_boundary_criterion_still_catches_a_boundary_that_is_wrong():
    """A looser bound is only defensible if it still discriminates.

    A prescribed value that never reached the matrix is wrong by order one
    relative, and the criterion sits seven orders below that.
    """
    from engcore.domains.thermal_models.conduction2d import (
        CONDUCTION2D_GATE_THRESHOLDS,
    )

    tolerance = CONDUCTION2D_GATE_THRESHOLDS["boundary_rel_tol"]
    assert tolerance < 1e-6, "the bound must stay far below a real failure"

    mesh, solution = solve(HARMONIC_PLATE, 32)
    values = solution.values.values
    problem = HARMONIC_PLATE.problem(mesh)
    law = problem.edges[BoundaryEdge.RIGHT].law
    xs, ys = mesh.axis_coordinates()

    # What the check would have measured had the varying edge been imposed as
    # the single number the Sprint 4 API would have forced.
    flattened = law.evaluate(x=xs[-1], y=ys[len(ys) // 2])
    worst = max(abs(values[j, -1] - flattened) for j in range(len(ys)))
    scale = max(abs(law.evaluate(x=xs[-1], y=y)) for y in ys)
    assert worst / scale > 1000 * tolerance, (
        f"flattening the varying edge to {flattened:.4g} K would be "
        f"{worst / scale:.3e} relative, and the criterion is {tolerance:.3e}"
    )


# ---- Phase 15: provenance identifies the declarations ------------------------------------
def test_the_result_records_which_laws_produced_it():
    _, solution = solve(SHEARED_PLATE, 16)
    metadata = solution.result.provenance.metadata
    laws = metadata["boundary_laws"]
    assert set(laws) == {"left", "right", "bottom", "top"}
    for edge, entry in laws.items():
        assert len(entry["fingerprint"]) == 64, edge
        assert entry["kind"] in ("linear_1d", "constant", "harmonic_1d", "tabulated_1d")
        assert entry["unit"]
        assert entry["varies_along"] in ("x", "y", None)


def test_the_source_law_is_identified_and_its_values_are_not_dumped():
    _, solution = solve(DECLARED_SOURCE_PLATE, 32)
    provenance = solution.result.provenance
    source = provenance.metadata["source_law"]
    assert source["kind"] == "separable_2d"
    assert len(source["fingerprint"]) == 64
    assert source["unit"] == "watt / meter ** 3"

    payload = str(solution.result.to_dict())
    assert len(payload) < 8000, "provenance must identify the law, not evaluate it"


def test_two_different_laws_give_two_different_provenances():
    _, one = solve(HARMONIC_PLATE, 16)
    _, other = solve(SHEARED_PLATE, 16)
    right_one = one.result.provenance.metadata["boundary_laws"]["right"]["fingerprint"]
    right_other = other.result.provenance.metadata["boundary_laws"]["right"]["fingerprint"]
    assert right_one != right_other
