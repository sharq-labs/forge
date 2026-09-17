"""Core re-audit 2026-09-16, batch 27: a ratio needs a scale whose zero means something.

Problem R-52 (benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json), improvement I-22 part B of
three, under benchmarks/core_v4_false_confidence/BATCH27_THRESHOLD_PROTOCOL.json.

Recorded as strict xfails in commit <XFAIL-SHA>, each seen failing on its own assertion, before the fix.
"""

from __future__ import annotations

import pytest

from engcore.scientific.consensus import VerificationThresholds, CrossSolverConsensus
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.units.quantity import Quantity

from route_declarations_for_tests import (  # noqa: F401 - autouse fixture
    PINS,
    route,
    route_declarations_for_tests,
)

NAME = "temperature:node"
TOLERANCE_KEY = "agreement_rel_tol"
THRESHOLDS = VerificationThresholds(
    gate_id="electrical.dc.cross_solver",
    version="0.2.0",
    values={TOLERANCE_KEY: 1e-9, f"{TOLERANCE_KEY}.floor.temperature": 0.0},
)


def _results(routes, per_route):
    out = {}
    for item in routes:
        out[item.route_id] = ScientificResult(
            result_id=f"r:{item.route_id}",
            values={
                name: Quantity(magnitude, unit)
                for name, (magnitude, unit) in per_route[item.route_id].items()
            },
            provenance=ProvenanceRecord(
                run_id=f"run:{item.route_id}", solvers=(item.solver.key,)
            ),
            solver=item.solver,
        )
    return out


def _comparison(order, per_route, *, thresholds=THRESHOLDS, required=(NAME,)):
    """One consensus over two declared routes, in the order given."""
    declared = {"a": route("a"), "b": route("b")}
    routes = tuple(declared[key] for key in order)
    return CrossSolverConsensus.from_results(
        consensus_id="c",
        routes=routes,
        results=_results(routes, per_route),
        thresholds=thresholds,
        tolerance_key=TOLERANCE_KEY,
        required_outputs=tuple(required),
    ).comparison


#: The audited pair: 26.85 degC and 300.0000001 K are one ten-billionth of a kelvin apart.
ONE_TEMPERATURE_TWO_SCALES = {
    "a": {NAME: (26.85, "degC")},
    "b": {NAME: (300.0000001, "kelvin")},
}


# ---------------------------------------------------------------------------
# the_compared_unit_is_canonical_and_not_the_first_routes
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-52: the first declared route that reports a name fixes its unit")
def test_r52_the_verdict_does_not_depend_on_which_route_was_declared_first():
    forward = _comparison(("a", "b"), ONE_TEMPERATURE_TWO_SCALES)
    backward = _comparison(("b", "a"), ONE_TEMPERATURE_TWO_SCALES)
    assert forward.worst_relative_difference == backward.worst_relative_difference, (
        f"declaration order changed the measurement: {forward.worst_relative_difference} "
        f"one way, {backward.worst_relative_difference} the other, for the same two readings"
    )
    assert forward.agreed is backward.agreed, (
        f"declaration order decided whether two solvers agreed: {forward.agreed} vs {backward.agreed}"
    )


@pytest.mark.xfail(strict=True, reason="R-52: degC-first makes the pair disagree")
def test_r52_the_canonical_unit_is_the_kelvin_scale_and_the_pair_agrees():
    """Both readings are 300.0000001 K to within 1e-10 K, so they agree on the scale that means it."""
    comparison = _comparison(("a", "b"), ONE_TEMPERATURE_TWO_SCALES)
    assert comparison.agreed is True
    assert comparison.worst_relative_difference == pytest.approx(3.3333e-10, rel=1e-3)


def test_r52_core018_still_holds_a_metre_is_not_a_disagreement_with_a_thousand_millimetres():
    """The control for the rule that changed: CORE-018's own case must still pass."""
    comparison = _comparison(
        ("a", "b"),
        {"a": {"length:x": (1.0, "meter")}, "b": {"length:x": (1000.0, "millimeter")}},
        required=("length:x",),
    )
    assert comparison.agreed is True
    assert comparison.worst_relative_difference == pytest.approx(0.0, abs=1e-15)


# ---------------------------------------------------------------------------
# a_relative_difference_needs_a_ratio_scale
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-52: the ratio is taken on whatever scale arrived")
def test_r52_a_true_disagreement_near_absolute_zero_is_not_flattered_by_celsius():
    """-273.14 degC against -273.14000000001 degC is 0.01 K against 0.01 K + 1e-8 relative."""
    celsius = _comparison(
        ("a", "b"),
        {"a": {NAME: (-273.14, "degC")}, "b": {NAME: (-273.14000000001, "degC")}},
    )
    kelvin = _comparison(
        ("a", "b"),
        {"a": {NAME: (0.01, "kelvin")}, "b": {NAME: (0.01 * (1 + 1e-8), "kelvin")}},
    )
    assert celsius.worst_relative_difference == pytest.approx(
        kelvin.worst_relative_difference, rel=1e-6
    ), (
        f"the same physical pair scored {celsius.worst_relative_difference} written in degC and "
        f"{kelvin.worst_relative_difference} written in kelvin"
    )
    assert celsius.agreed is False, "a 1e-8 relative disagreement was agreed to at 1e-9"


# ---------------------------------------------------------------------------
# a_declared_floor_is_read_in_that_canonical_unit
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-52: a bare floor takes its unit from declaration order")
def test_r52_a_declared_floor_means_the_same_thing_in_either_order():
    """The audited loosening: 1e-15 read in megaampere is 1e-9 A, so 5e-10 A 'agrees'."""
    thresholds = VerificationThresholds(
        gate_id="electrical.dc.cross_solver",
        version="0.2.0",
        values={TOLERANCE_KEY: 1e-9, f"{TOLERANCE_KEY}.floor.current": 1e-15},
    )
    per_route = {
        "a": {"current:bridge": (5.0e-16, "megaampere")},
        "b": {"current:bridge": (0.0, "ampere")},
    }
    forward = _comparison(("a", "b"), per_route, thresholds=thresholds, required=("current:bridge",))
    backward = _comparison(("b", "a"), per_route, thresholds=thresholds, required=("current:bridge",))
    assert forward.agreed is backward.agreed, (
        f"the same declared floor decided differently by order: {forward.agreed} vs {backward.agreed}"
    )
    assert forward.agreed is False, (
        "5e-10 A apart on a zero current is not agreement at a declared floor of 1e-15 A"
    )


def test_r52_the_floor_still_does_what_it_was_written_for():
    """The control: two routes agreeing to round-off on a zero current still agree."""
    thresholds = VerificationThresholds(
        gate_id="electrical.dc.cross_solver",
        version="0.2.0",
        values={TOLERANCE_KEY: 1e-9, f"{TOLERANCE_KEY}.floor.current": 1e-15},
    )
    comparison = _comparison(
        ("a", "b"),
        {"a": {"current:bridge": (1.2e-17, "ampere")}, "b": {"current:bridge": (0.0, "ampere")}},
        thresholds=thresholds,
        required=("current:bridge",),
    )
    assert comparison.agreed is True


# ---------------------------------------------------------------------------
# an_operating_point_is_compared_on_a_ratio_scale_too
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-52: the operating point is compared in the stated unit")
def test_r52_an_operating_point_is_the_same_point_whatever_unit_states_it():
    from engcore.scientific import oracles

    same = oracles._same_operating_point
    assert same(Quantity(0.02, "degC"), Quantity(0.020000001, "degC")) is True, (
        "0.02 degC and 0.020000001 degC are 273.17 K and 273.170000001 K -- a 4e-12 relative "
        "difference, inside the 1e-9 tolerance"
    )


def test_r52_an_operating_point_is_a_relation_and_not_a_claim_one_side_makes():
    """Symmetry, which comparing in `stated.units` did not give."""
    from engcore.scientific import oracles

    same = oracles._same_operating_point
    a, b = Quantity(300.0, "kelvin"), Quantity(26.85, "degC")
    assert same(a, b) is same(b, a)
    assert same(a, b) is True, "26.85 degC IS 300.0 K"


def test_r52_a_genuinely_different_operating_point_is_still_different():
    """The control: the rule must not turn into 'every temperature is every other temperature'."""
    from engcore.scientific import oracles

    same = oracles._same_operating_point
    assert same(Quantity(300.0, "kelvin"), Quantity(301.0, "kelvin")) is False
    assert same(Quantity(300.0, "kelvin"), Quantity(300.0, "ampere")) is False
    assert same(Quantity(300.0, "kelvin"), 300.0) is False


# ---------------------------------------------------------------------------
# the_docstring_says_what_the_code_does
# ---------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="R-52: the docstring describes the pre-CORE-018 behaviour")
def test_r52_the_docstring_no_longer_claims_each_value_is_read_in_its_own_unit():
    doc = CrossSolverConsensus.from_results.__doc__ or ""
    assert "in its own unit" not in doc, (
        "the docstring still says a route returning the right number in another unit shows up as a "
        "disagreement, which CORE-018 made false and this batch makes canonical"
    )
    assert "base unit" in doc or "canonical" in doc
