"""The faster assembly must build the same matrix, not a similar one.

Sprint 7, Phase 14. Profiling put 55 % of a 32x32 field solve in
``scipy.sparse.lil_matrix.__setitem__`` — a Python call per matrix element —
against 0.04 % in the factorisation it exists to feed. The loop now appends to
three coordinate lists and converts once.

That is a change to how a scientific result is computed, so "it still passes
the convergence study" is not the evidence required. The evidence required is
that the assembled operator is **the same operator, bit for bit**, and this
file provides it by keeping the previous construction and comparing against it
directly.

`legacy_assemble` below is the pre-Sprint-7 body, copied verbatim except for
the names it reaches for. It exists only to be compared against and is not used
anywhere else; if the two ever disagree, the one that is wrong is the new one.
"""

from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp

from engcore.data.field import evaluate_on_region
from engcore.domains.thermal_models.conduction2d import (
    CONDUCTIVITY_UNIT,
    FLUX_UNIT,
    _source_array,
    assemble,
    solve_steady_conduction,
)
from engcore.scientific.fields import BoundaryEdge
from engcore.scientific.ir.conditions import BoundaryKind
from tests.manufactured_conduction2d import (
    COSINE_COLUMN,
    DECLARED_SOURCE_PLATE,
    HARMONIC_PLATE,
    SHEARED_PLATE,
    SINE_PLATE,
    errors,
    square,
)

CASES = (SINE_PLATE, COSINE_COLUMN, SHEARED_PLATE, HARMONIC_PLATE, DECLARED_SOURCE_PLATE)


def legacy_assemble(problem):
    """The construction this replaced: one `lil_matrix` element at a time."""
    mesh, field = problem.mesh, problem.field
    nx, ny = mesh.nodes_x, mesh.nodes_y
    dx = mesh.spacing_x.magnitude_in("meter")
    dy = mesh.spacing_y.magnitude_in("meter")
    k = problem.conductivity.magnitude_in(CONDUCTIVITY_UNIT)
    q = _source_array(problem)
    edges = problem.edges

    n = nx * ny
    matrix = sp.lil_matrix((n, n), dtype=np.float64)
    rhs = np.zeros(n, dtype=np.float64)

    def index(i: int, j: int) -> int:
        return j * nx + i

    dirichlet: dict[int, float] = {}
    flux_laws: dict[BoundaryEdge, dict[int, float]] = {}
    for edge, condition in edges.items():
        region = next(r for r in problem.regions if r.edge is edge)
        if condition.kind is BoundaryKind.DIRICHLET:
            dirichlet.update(
                evaluate_on_region(condition.law, region, mesh, unit=field.unit)
            )
        else:
            flux_laws[edge] = evaluate_on_region(
                condition.law, region, mesh, unit=FLUX_UNIT
            )

    for j in range(ny):
        for i in range(nx):
            row = index(i, j)
            if row in dirichlet:
                matrix[row, row] = 1.0
                rhs[row] = dirichlet[row]
                continue
            centre = 2.0 * k / dx**2 + 2.0 * k / dy**2
            rhs[row] = q[j, i]
            for di, dj, spacing, edge_here in (
                (-1, 0, dx, BoundaryEdge.LEFT),
                (1, 0, dx, BoundaryEdge.RIGHT),
                (0, -1, dy, BoundaryEdge.BOTTOM),
                (0, 1, dy, BoundaryEdge.TOP),
            ):
                coefficient = -k / spacing**2
                ii, jj = i + di, j + dj
                if 0 <= ii < nx and 0 <= jj < ny:
                    matrix[row, index(ii, jj)] += coefficient
                    continue
                flux = flux_laws[edge_here][row]
                matrix[row, index(i - di, j - dj)] += coefficient
                rhs[row] += coefficient * 2.0 * spacing * flux / k
            matrix[row, row] += centre

    return matrix.tocsr(), rhs


def _bits(array: np.ndarray) -> bytes:
    return np.ascontiguousarray(array, dtype=np.float64).tobytes()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
@pytest.mark.parametrize("nodes", [2, 3, 5, 16, 33])
def test_the_assembled_operator_is_bit_identical(case, nodes):
    """Every entry, every right-hand side value, on every manufactured case.

    Small supports are in the list on purpose: at `nodes = 2` a ghost node's
    mirror coincides with a real neighbour, so a coordinate is written twice
    and the duplicate-summation behaviour is what is actually under test.
    """
    problem = case.problem(square(nodes))
    expected_matrix, expected_rhs = legacy_assemble(problem)
    actual_matrix, actual_rhs = assemble(problem)

    assert actual_matrix.shape == expected_matrix.shape
    assert _bits(expected_rhs) == _bits(actual_rhs), "right-hand side differs"
    assert _bits(expected_matrix.toarray()) == _bits(actual_matrix.toarray()), (
        "assembled operator differs"
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_the_solved_field_is_bit_identical(case):
    """The operator is the input to a factorisation, so the output is checked too."""
    mesh = square(16)
    problem = case.problem(mesh)

    import scipy.sparse.linalg as spla

    legacy_matrix, legacy_rhs = legacy_assemble(problem)
    legacy_solution = spla.spsolve(legacy_matrix.tocsc(), legacy_rhs)
    solved = solve_steady_conduction(problem, run_id="assembly").values.values

    assert _bits(legacy_solution.reshape(solved.shape)) == _bits(solved)


def test_the_sparsity_pattern_is_the_same_too():
    """Not only the values: the same coordinates, and no explicit zeros added."""
    for case in CASES:
        problem = case.problem(square(9))
        expected, _ = legacy_assemble(problem)
        actual, _ = assemble(problem)
        assert expected.nnz == actual.nnz, case.name
        assert (expected != actual).nnz == 0, case.name


def test_duplicate_coordinates_really_do_occur():
    """A guard on the guard.

    The bit-identity argument rests on a coordinate being written at most twice
    and the sum of two floats being order-independent. If no coordinate were
    ever written twice the tests above would be passing on a case that does not
    exercise the behaviour they exist to check, so this asserts the duplicates
    are real.
    """
    problem = COSINE_COLUMN.problem(square(4))
    matrix, _ = assemble(problem)
    coo = matrix.tocoo()
    seen: dict[tuple[int, int], int] = {}
    for row, column in zip(coo.row.tolist(), coo.col.tolist()):
        seen[(row, column)] = seen.get((row, column), 0) + 1

    # After conversion duplicates are already summed, so the direct evidence is
    # that a flux edge's mirror lands on an existing neighbour. Rebuild the
    # triplets the way `assemble` emits them and count.
    nx = problem.mesh.nodes_x
    ny = problem.mesh.nodes_y
    emitted: dict[tuple[int, int], int] = {}
    for j in range(ny):
        for i in range(nx):
            row = j * nx + i
            for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ii, jj = i + di, j + dj
                column = (
                    jj * nx + ii
                    if 0 <= ii < nx and 0 <= jj < ny
                    else (j - dj) * nx + (i - di)
                )
                emitted[(row, column)] = emitted.get((row, column), 0) + 1

    duplicates = {key: n for key, n in emitted.items() if n > 1}
    assert duplicates, "no coordinate is written twice; the argument is untested"
    assert max(duplicates.values()) == 2, (
        f"a coordinate is written {max(duplicates.values())} times; the "
        f"order-independence argument only covers two"
    )


def test_the_convergence_study_still_holds_after_the_change():
    """The scientific property, re-measured rather than assumed from the above."""
    previous = None
    for nodes in (16, 32, 64):
        mesh = square(nodes)
        solution = solve_steady_conduction(
            HARMONIC_PLATE.problem(mesh), run_id=f"assembly-{nodes}"
        )
        l2, _ = errors(solution.values.values, HARMONIC_PLATE.exact_on(mesh))
        if previous is not None:
            assert l2 < previous, "the error stopped falling under refinement"
        previous = l2
