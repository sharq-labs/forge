"""Core re-audit 2026-09-16, batch 28: two values meeting at a corner are compared on one scale.

Problem R-57 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-22 part C of
four, under benchmarks/core_v4_false_confidence/BATCH28_THRESHOLD_PROTOCOL.json.

Recorded as strict xfails in commit 6f4f27fd, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import (
    BoundaryEdge,
    FieldBoundaryCondition,
    FieldDefinition,
    LinearProfile1D,
    ProfileAxis,
    StructuredMesh,
    boundary_regions,
    require_complete_boundary,
)
from engcore.scientific.ir.conditions import BoundaryKind
from engcore.scientific.units.quantity import Quantity

K = "kelvin"


def _mesh():
    return StructuredMesh("plate", Quantity(1.0, "meter"), Quantity(2.0, "meter"), 9, 9)


def _condition(value, edge, support):
    region = next(r for r in boundary_regions(support) if r.edge is edge)
    return FieldBoundaryCondition(
        name=f"T-{edge.value}",
        field_id="T",
        region_id=region.region_id,
        kind=BoundaryKind.DIRICHLET,
        value=value,
    )


def _check(values, *, unit=K):
    support = _mesh()
    conditions = tuple(_condition(v, e, support) for e, v in values.items())
    require_complete_boundary(
        FieldDefinition("T", unit, "plate"), support, boundary_regions(support), conditions
    )


#: A uniform plate at 300 K, stated on all four edges, which agrees at every corner.
FLAT_KELVIN = {edge: Quantity(300.0, K) for edge in BoundaryEdge}


# ---------------------------------------------------------------------------
# corner_values_are_compared_in_one_canonical_unit
# ---------------------------------------------------------------------------
def test_r57_a_273_kelvin_corner_conflict_is_refused():
    """300 degC is 573.15 K. Meeting 300 K, that is a 273.15 K contradiction at two corners."""
    with pytest.raises(InvalidScientificProblem, match="meet at corner"):
        _check({**FLAT_KELVIN, BoundaryEdge.BOTTOM: Quantity(300.0, "degC")})


def test_r57_two_edges_that_agree_physically_are_accepted_however_they_are_spelled():
    """26.85 degC IS 300.0 K, and `require_consistent` accepts any unit of the right dimension."""
    _check({**FLAT_KELVIN, BoundaryEdge.BOTTOM: Quantity(26.85, "degC")})


def test_r57_a_law_in_another_unit_agrees_at_the_corner_it_agrees_at():
    """The law path, not only the constant path: T = 26.85 degC + 20 delta_degC/m up the side."""
    rising = LinearProfile1D(
        ProfileAxis.Y, Quantity(26.85, "degC"), Quantity(20.0, "delta_degC/meter")
    )
    _check(
        {
            BoundaryEdge.LEFT: rising,
            BoundaryEdge.RIGHT: rising,
            BoundaryEdge.BOTTOM: Quantity(300.0, K),
            BoundaryEdge.TOP: Quantity(340.0, K),
        }
    )


def test_r57_the_same_physical_pair_gets_the_same_verdict_in_either_declaration():
    """`CORNER_AGREEMENT_REL_TOL` is a RELATIVE tolerance, so it belongs on the scale whose zero is zero.

    1000 degC and 1000.00000115 degC are 1273.15 K and 1273.15000115 K: 1.15e-6 apart, which is inside
    1e-9 relative of 1273.15 and OUTSIDE 1e-9 relative of 1000. So the verdict used to depend on which
    unit the field happened to be declared in, for one physical pair. Both must now be accepted, and it
    is the kelvin judgement that is the right one -- a ratio of two Celsius numbers is not a ratio of
    two temperatures.
    """
    _check(
        {edge: Quantity(1273.15, K) for edge in BoundaryEdge}
        | {BoundaryEdge.BOTTOM: Quantity(1273.15000115, K)},
    )
    _check(
        {edge: Quantity(1000.0, "degC") for edge in BoundaryEdge}
        | {BoundaryEdge.BOTTOM: Quantity(1000.00000115, "degC")},
        unit="degC",
    )


def test_r57_the_existing_cases_still_do_what_they_did():
    """Controls: an agreeing plate is accepted and a one-kelvin conflict is still refused."""
    _check(FLAT_KELVIN)
    with pytest.raises(InvalidScientificProblem, match="meet at corner"):
        _check({**FLAT_KELVIN, BoundaryEdge.BOTTOM: Quantity(299.0, K)})


# ---------------------------------------------------------------------------
# the_refusal_names_the_unit_each_value_was_written_in
# ---------------------------------------------------------------------------
def test_r57_the_refusal_does_not_label_two_scales_with_one_unit():
    with pytest.raises(InvalidScientificProblem) as raised:
        _check({**FLAT_KELVIN, BoundaryEdge.BOTTOM: Quantity(300.0, "degC")})
    message = str(raised.value)
    assert "573.15" in message, (
        f"the refusal must report what the degC edge prescribes on the compared scale; got {message!r}"
    )
    assert "300 and 26.85" not in message
    assert "as written" in message and "degree_Celsius" in message, (
        f"a value written on another scale must be reported in the unit it was written in too; "
        f"got {message!r}"
    )
