"""What a constant boundary value cannot say, and what that costs.

Sprint 5, Phase 1. Sprint 4 gave boundary conditions a region, a unit and a
support, and gave them exactly one number to carry. That is enough for a plate
held at one temperature and not enough for anything whose boundary data varies
along the edge it applies to:

    T_left(y) = 300 K + 20 K * y / Ly        a varying Dirichlet edge
    q_top(x)                                  a varying flux edge
    q'''(x, y)                                a varying volumetric source

These tests establish the limit before anything is built to remove it. Two
kinds of assertion are here and they have different lifetimes. The refusals of
callables and bare sequences are **permanent** — a spatial law that is an
executable Python object is the thing this sprint exists not to accept. The
single-number assertions describe the ceiling as it stands and are the ones a
later commit moves.

The fourth test is the one that matters. It is not an assertion about an API
shape: it measures what the missing representation costs, and shows that the
error does not fall under refinement, because it is not a discretisation error.
"""

from __future__ import annotations

import functools

import numpy as np
import pytest

from engcore.data.field import FieldValue
from engcore.domains.thermal_models.conduction2d import (
    plate_problem,
    node_grid,
    solve_steady_conduction,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import (
    BoundaryEdge,
    FieldBoundaryCondition,
    FieldDefinition,
    FieldTransferVerdict,
    StructuredMesh,
    boundary_regions,
    check_field_transfer,
)
from engcore.scientific.ir.conditions import BoundaryKind
from engcore.scientific.units.quantity import Quantity

LX = LY = 1.0
BASE = 300.0
RISE = 20.0
CONDUCTIVITY = Quantity(5.0, "watt/meter/kelvin")


def square(nodes: int, mesh_id: str = "plate") -> StructuredMesh:
    return StructuredMesh(
        mesh_id, Quantity(LX, "meter"), Quantity(LY, "meter"), nodes, nodes
    )


def condition(value, kind=BoundaryKind.DIRICHLET, mesh=None):
    mesh = mesh or square(9)
    left = next(r for r in boundary_regions(mesh) if r.edge is BoundaryEdge.LEFT)
    return FieldBoundaryCondition(
        name="T-left", field_id="T", region_id=left.region_id, kind=kind, value=value
    )


# ---- permanent: a spatial law is not an executable object -------------------------
def a_function(y):  # pragma: no cover - never called; that is the point
    return BASE + RISE * y / LY


class Callable:  # pragma: no cover - never called
    def __call__(self, y):
        return BASE + RISE * y / LY


@pytest.mark.parametrize(
    "law, label",
    [
        (lambda y: BASE + RISE * y / LY, "a lambda"),
        (a_function, "an ordinary function"),
        (functools.partial(a_function), "a partial"),
        (Callable(), "an object with __call__"),
    ],
)
def test_an_executable_object_is_not_a_boundary_value(law, label):
    """Phase 18, asserted from the first commit rather than added at the end.

    The tempting fix for a varying edge is to hand the record a function. It
    would work, and it would end the possibility of serializing, fingerprinting
    or reasoning about the boundary condition ever again.
    """
    with pytest.raises(InvalidScientificProblem, match="must be a Quantity"):
        condition(law)


@pytest.mark.parametrize(
    "values",
    [
        (300.0, 305.0, 310.0),
        [300.0, 305.0, 310.0],
        np.linspace(300.0, 320.0, 9),
        Quantity(300.0, "kelvin").__class__,
    ],
)
def test_a_bare_sequence_of_edge_values_is_not_a_boundary_value(values):
    """Nor is the evaluated answer a substitute for the law that produced it."""
    with pytest.raises(InvalidScientificProblem, match="must be a Quantity"):
        condition(values)


def test_a_quantity_cannot_carry_an_array_of_edge_values():
    """The other way round: one Quantity, many magnitudes. Also refused."""
    with pytest.raises(TypeError):
        Quantity(np.linspace(300.0, 320.0, 9), "kelvin")


# ---- the ceiling, as it stands ------------------------------------------------------
def test_a_boundary_condition_carries_exactly_one_number():
    """The whole of what an edge can say today.

    `value` is a single scalar `Quantity`, and the serialized condition holds
    one magnitude. There is nowhere in this record for a coordinate, a slope, a
    table or an axis — so `T_left(y)` has no representation, faithful or
    otherwise.
    """
    payload = condition(Quantity(BASE, "kelvin")).to_dict()
    assert payload["value"]["magnitude"] == BASE
    assert set(payload) == {
        "schema", "name", "field_id", "region_id", "kind", "value",
        "coefficients", "description",
    }
    assert "coordinate" not in payload and "profile" not in payload


# ---- what the missing representation actually costs ----------------------------------
def _exact_linear_edge(mesh: StructuredMesh) -> np.ndarray:
    """The field whose left edge rises linearly and whose right edge is fixed.

    ``T = BASE + RISE * (y/Ly) * (1 - x/Lx)`` is not harmonic, so it is not used
    as an oracle here. What is used is only its boundary data, which is what the
    current API cannot state.
    """
    x, y = node_grid(mesh)
    return BASE + RISE * (y / LY) * (1.0 - x / LX)


def _best_constant_plate(nodes: int):
    """The closest a Sprint 4 declaration can get: the edge's mean value."""
    mesh = square(nodes)
    problem = plate_problem(
        problem_id=f"constant-approximation-{nodes}",
        mesh=mesh,
        conductivity=CONDUCTIVITY,
        edge_values={
            # The left edge truly runs from BASE to BASE + RISE. One number has
            # to stand for all of it, and the mean is the kindest choice.
            BoundaryEdge.LEFT: Quantity(BASE + RISE / 2.0, "kelvin"),
            BoundaryEdge.RIGHT: Quantity(BASE, "kelvin"),
            BoundaryEdge.BOTTOM: Quantity(BASE, "kelvin"),
            BoundaryEdge.TOP: Quantity(BASE + RISE, "kelvin"),
        },
    )
    solved = solve_steady_conduction(problem, run_id=f"limit-{nodes}").values
    return mesh, solved.values


def test_a_constant_edge_cannot_represent_a_varying_one_and_refining_does_not_help():
    """The cost, measured on the boundary itself.

    This is the finding, and it is worse than "inaccurate". The error of a
    constant edge against the linear edge it stands in for is a
    *representation* error, so refinement does not remove it — it **converges
    to it**. The measured sequence rises toward `RISE / 2`, the largest
    distance from the edge's mean to its ends, because each refinement puts a
    node closer to the corner where the disagreement is greatest.

    A second-order discretisation error would have fallen by about four per
    step. This one does not fall at all, which is how a missing representation
    is told apart from a coarse mesh.
    """
    errors = []
    for nodes in (16, 32, 64):
        mesh, solved = _best_constant_plate(nodes)
        exact_edge = _exact_linear_edge(mesh)[:, 0]
        errors.append(float(np.max(np.abs(solved[:, 0] - exact_edge))))

    bound = RISE / 2.0
    assert all(error > 0.85 * bound for error in errors), (
        f"the constant edge should be near {bound} K wrong at every "
        f"resolution: {errors}"
    )
    assert errors == sorted(errors), (
        f"refining should not improve a representation error; it should "
        f"approach the bound from below: {errors}"
    )
    assert errors[-1] > 0.96 * bound and errors[-1] <= bound, (
        f"the finest run should be all but exactly {bound} K wrong: {errors}"
    )
    # What a discretisation error would have done over the same two steps.
    assert errors[0] / errors[-1] > 0.5, (
        f"the error fell by {errors[0] / errors[-1]:.2f}x, which would make it "
        f"a convergent discretisation error: {errors}"
    )


# ---- and what a pre-evaluated source cannot say --------------------------------------
def test_a_varying_source_can_only_enter_as_values_tied_to_one_support():
    """Sprint 4's field-valued source works, and carries no law.

    The array is the *answer* to `q'''(x, y)` at one resolution, not the
    question. Two consequences, both asserted here: the serialized source names
    bytes by digest and states nothing about what generated them, and the same
    source cannot be carried to a refined support — so a convergence study has
    to re-evaluate the law outside the platform, which is precisely where the
    law then lives.
    """
    coarse, fine = square(16), square(32, "fine")
    x, y = node_grid(coarse)
    source = FieldValue(
        FieldDefinition("q", "watt/meter**3", coarse.mesh_id),
        coarse,
        1000.0 * np.sin(np.pi * x / LX) * np.sin(np.pi * y / LY),
    )
    record, reference = source.store(__import__(
        "engcore.data.store", fromlist=["InMemoryBulkStore"]).InMemoryBulkStore())

    payload = record.to_dict()
    assert reference.digest and reference.count == 256
    for word in ("sin", "law", "expression", "coordinate", "profile"):
        assert word not in str(payload), (
            f"the source payload mentions {word!r}; if it described its own law "
            f"this test would be obsolete, which is the point"
        )

    verdict = check_field_transfer(
        source.definition, coarse,
        FieldDefinition("q", "watt/meter**3", "fine"), fine,
    ).verdict
    assert verdict is FieldTransferVerdict.REQUIRES_PROJECTION, (
        "the same declared source cannot simply be used on a refined support"
    )
