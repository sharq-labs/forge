"""Boundary conditions that carry a law instead of a number.

Sprint 5, Phases 5 and 6. A condition's value slot now holds either a
``Quantity`` or a ``SpatialProfile``, and `law` answers for both so nothing
downstream branches on which spelling it was handed.

What is checked here is the binding: a law bound to a region has to vary along
the coordinate that region actually runs in, be defined across the whole of it,
and produce the dimension the field is measured in. And two prescribed values
meeting at a corner have to agree about the corner.
"""

from __future__ import annotations

import math

import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import (
    BoundaryEdge,
    ConstantProfile,
    FieldBoundaryCondition,
    FieldDefinition,
    HarmonicProfile1D,
    LinearProfile1D,
    ProfileAxis,
    StructuredMesh,
    TabulatedProfile1D,
    boundary_regions,
    require_complete_boundary,
)
from engcore.scientific.ir.conditions import BoundaryKind
from engcore.scientific.units.quantity import Quantity

K = "kelvin"
FLUX = "watt/meter**2"


def mesh(nx=9, ny=9, lx=1.0, ly=2.0):
    return StructuredMesh(
        "plate", Quantity(lx, "meter"), Quantity(ly, "meter"), nx, ny
    )


def field():
    return FieldDefinition("T", K, "plate")


def region(edge, support=None):
    return next(r for r in boundary_regions(support or mesh()) if r.edge is edge)


def bc(value, edge=BoundaryEdge.LEFT, kind=BoundaryKind.DIRICHLET, support=None):
    support = support or mesh()
    return FieldBoundaryCondition(
        name=f"T-{edge.value}",
        field_id="T",
        region_id=region(edge, support).region_id,
        kind=kind,
        value=value,
    )


def rising(intercept=300.0, slope=20.0, axis=ProfileAxis.Y, unit=K):
    return LinearProfile1D(
        axis, Quantity(intercept, unit), Quantity(slope, f"{unit}/meter")
    )


# ---- a condition can now carry a law -------------------------------------------------
def test_a_condition_accepts_a_profile_and_reports_it_as_its_law():
    condition = bc(rising())
    condition.require_consistent(field(), region(BoundaryEdge.LEFT), mesh())
    assert condition.law is condition.value
    assert not condition.is_uniform
    assert condition.law.evaluate(x=0.0, y=2.0) == pytest.approx(340.0)


def test_a_constant_is_a_law_too_and_says_it_is_uniform():
    condition = bc(Quantity(300.0, K))
    condition.require_consistent(field(), region(BoundaryEdge.LEFT), mesh())
    assert isinstance(condition.law, ConstantProfile)
    assert condition.is_uniform
    assert condition.law.evaluate(x=0.0, y=1.7) == 300.0


def test_a_condition_with_no_value_has_no_law():
    condition = FieldBoundaryCondition(
        name="T-left", field_id="T", region_id=region(BoundaryEdge.LEFT).region_id,
        kind=BoundaryKind.PERIODIC,
    )
    assert condition.is_uniform
    with pytest.raises(InvalidScientificProblem, match="prescribes no value"):
        condition.law


# ---- Phase 19: the Sprint 4 spelling is untouched ---------------------------------------
def test_a_constant_condition_serializes_exactly_as_it_did_before_profiles():
    """Backward compatibility asserted on the payload, not on the constructor.

    One value slot rather than two was chosen for this: a constant condition's
    payload gained no key, so anything written before profiles existed reads
    back unchanged and anything written now is readable by the same reader.
    """
    payload = bc(Quantity(300.0, K)).to_dict()
    assert set(payload) == {
        "schema", "name", "field_id", "region_id", "kind", "value",
        "coefficients", "description",
    }
    assert payload["value"] == {
        "schema": "quantity/1", "magnitude": 300.0, "units": K
    }


def test_a_profiled_condition_uses_the_same_slot():
    payload = bc(rising()).to_dict()
    assert set(payload) == {
        "schema", "name", "field_id", "region_id", "kind", "value",
        "coefficients", "description",
    }
    assert payload["value"]["schema"] == "spatial_profile/1"
    assert payload["value"]["kind"] == "linear_1d"


@pytest.mark.parametrize(
    "value",
    [
        Quantity(300.0, K),
        ConstantProfile(Quantity(300.0, K)),
        rising(),
        HarmonicProfile1D(ProfileAxis.Y, Quantity(5.0, K), Quantity(math.pi / 2, "1/meter")),
        TabulatedProfile1D(ProfileAxis.Y, (0.0, 1.0, 2.0), (300.0, 315.0, 320.0), unit=K),
    ],
)
def test_every_condition_round_trips(value):
    condition = bc(value)
    restored = FieldBoundaryCondition.from_dict(condition.to_dict())
    assert restored == condition
    assert restored.law.evaluate(x=0.0, y=1.0) == pytest.approx(
        condition.law.evaluate(x=0.0, y=1.0)
    )


# ---- Phase 6: binding a law to a region ------------------------------------------------
def test_a_law_of_the_wrong_coordinate_is_refused_on_an_edge():
    """A profile of x on a left edge would evaluate to one value all the way down."""
    with pytest.raises(InvalidScientificProblem, match="does not become a profile of the other"):
        bc(rising(axis=ProfileAxis.X)).require_consistent(
            field(), region(BoundaryEdge.LEFT), mesh()
        )


def test_the_same_law_is_accepted_on_the_edge_it_does_vary_along():
    bc(rising(axis=ProfileAxis.X), edge=BoundaryEdge.BOTTOM).require_consistent(
        field(), region(BoundaryEdge.BOTTOM), mesh()
    )


def test_a_constant_binds_to_every_edge():
    for edge in BoundaryEdge:
        bc(Quantity(300.0, K), edge=edge).require_consistent(
            field(), region(edge), mesh()
        )


def test_a_table_that_does_not_span_the_edge_is_refused():
    """The support runs 0 to 2 m in y; this table stops at 1 m."""
    short = TabulatedProfile1D(ProfileAxis.Y, (0.0, 1.0), (300.0, 310.0), unit=K)
    with pytest.raises(InvalidScientificProblem, match="must cover"):
        bc(short).require_consistent(field(), region(BoundaryEdge.LEFT), mesh())

    covering = TabulatedProfile1D(
        ProfileAxis.Y, (0.0, 1.0, 2.0), (300.0, 310.0, 320.0), unit=K
    )
    bc(covering).require_consistent(field(), region(BoundaryEdge.LEFT), mesh())


def test_a_law_of_the_wrong_dimension_is_refused_on_a_prescribed_edge():
    with pytest.raises(InvalidScientificProblem, match="the wrong law"):
        bc(rising(unit="volt")).require_consistent(
            field(), region(BoundaryEdge.LEFT), mesh()
        )


def test_a_flux_law_is_not_checked_against_the_field_unit():
    """A flux is not a value of the field, so its dimension is the domain's business."""
    flux = rising(intercept=50.0, slope=10.0, unit=FLUX)
    bc(flux, kind=BoundaryKind.NEUMANN).require_consistent(
        field(), region(BoundaryEdge.LEFT), mesh()
    )


# ---- Phase 6: corners -------------------------------------------------------------------
def complete(values, support=None):
    """Check a full set of four prescribed edges against the corner rule."""
    support = support or mesh()
    conditions = tuple(bc(v, edge=e, support=support) for e, v in values.items())
    require_complete_boundary(field(), support, boundary_regions(support), conditions)


#: Four edges of the plate `T = 300 K + 20 K/m * y`, each stated separately and
#: therefore agreeing at all four corners by construction: 300 K along the
#: bottom, 340 K along the top, and the same rise up both sides.
AGREEING = {
    BoundaryEdge.LEFT: rising(300.0, 20.0),
    BoundaryEdge.RIGHT: rising(300.0, 20.0),
    BoundaryEdge.BOTTOM: Quantity(300.0, K),
    BoundaryEdge.TOP: Quantity(340.0, K),
}


def test_two_prescribed_edges_meeting_at_a_corner_must_agree_there():
    with pytest.raises(InvalidScientificProblem, match="meet at corner"):
        complete({**AGREEING, BoundaryEdge.BOTTOM: Quantity(299.0, K)})


def test_edges_that_do_agree_at_their_corners_are_accepted():
    """A law and a constant can agree; this one is 300 K at y = 0."""
    complete(AGREEING)


def test_a_flux_edge_never_conflicts_with_a_prescribed_one():
    """A flux constrains a derivative and imposes nothing at the point itself."""
    support = mesh()
    conditions = (
        bc(rising(300.0, 20.0), edge=BoundaryEdge.LEFT, support=support),
        bc(Quantity(0.0, FLUX), edge=BoundaryEdge.BOTTOM,
           kind=BoundaryKind.NEUMANN, support=support),
        bc(Quantity(0.0, FLUX), edge=BoundaryEdge.TOP,
           kind=BoundaryKind.NEUMANN, support=support),
        bc(Quantity(300.0, K), edge=BoundaryEdge.RIGHT, support=support),
    )
    require_complete_boundary(field(), support, boundary_regions(support), conditions)


def test_a_corner_conflict_is_found_however_small_the_support():
    """It is a question about the declarations, so the node count is irrelevant."""
    for nodes in (2, 3, 9):
        support = mesh(nx=nodes, ny=nodes)
        with pytest.raises(InvalidScientificProblem, match="meet at corner"):
            complete(
                {**AGREEING, BoundaryEdge.BOTTOM: Quantity(299.0, K)},
                support=support,
            )


def test_two_laws_that_agree_at_one_end_and_diverge_by_the_other_are_refused():
    """The bottom edge starts at 300 K where the left edge does, and rises away.

    The catch a spot check at the origin would miss: these two laws agree
    exactly at the corner they share, and the bottom edge then disagrees with
    the *right* edge at the far end.
    """
    with pytest.raises(InvalidScientificProblem, match="meet at corner"):
        complete(
            {**AGREEING, BoundaryEdge.BOTTOM: rising(300.0, 5.0, axis=ProfileAxis.X)}
        )
