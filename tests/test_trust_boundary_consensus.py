"""Consensus completeness is a property of the record, not of the factory.

TB-3 of the trust-boundary hardening sprint.

``CrossSolverConsensus.over()`` writes an entry into ``reported_outputs`` for
every route -- an empty tuple for a route that reported nothing -- and
``missing_outputs`` charged a route only through that entry. The public
constructor accepted ``required_outputs`` with no ``reported_outputs`` at all,
and ``missing_outputs`` read the absent mapping as "nothing is missing". The
record said COMPLETE and established ``CROSS_SOLVER_VALIDATED`` for outputs no
route was ever recorded as producing, and ``from_dict`` accepted the same state
from a hand-edited payload.

Absence of evidence is not evidence of completeness, whichever door the record
came in through. Every test here builds the same consensus both ways and
requires the same answer.
"""

from __future__ import annotations

import itertools
import json
from types import SimpleNamespace

import pytest

from engcore.scientific.consensus import (
    ComponentKind,
    CrossSolverConsensus,
    OutputCompleteness,
    RouteComparison,
    SharedComponent,
    SolveRoute,
)
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.results.thresholds import VerificationThresholds
from engcore.scientific.results.validation import ValidationLevel
from engcore.scientific.solvers.protocol import SolverIdentity

THRESHOLDS = VerificationThresholds(
    gate_id="test.trust_boundary.consensus",
    version="0.1.0",
    values={"agreement_rel_tol": 1e-9},
    basis="a test fixture, not a scientific declaration",
)
TOLERANCE = 1e-9


def _route(route_id: str) -> SolveRoute:
    return SolveRoute(
        route_id=route_id,
        solver=SolverIdentity(f"solver.{route_id}", "1.0"),
        components=frozenset(
            {SharedComponent(ComponentKind.RESIDUAL, f"{route_id}:rhs")}
        ),
    )


ROUTES = (_route("a"), _route("b"))
REQUIRED = ("A", "B")
VALIDATED = ValidationLevel.CROSS_SOLVER_VALIDATED


def _factory(values, required=REQUIRED, routes=ROUTES) -> CrossSolverConsensus:
    return CrossSolverConsensus.over(
        consensus_id="tb3",
        routes=routes,
        values=values,
        thresholds=THRESHOLDS,
        tolerance_key="agreement_rel_tol",
        required_outputs=required,
    )


def _direct(comparison, required=REQUIRED, reported=None, routes=ROUTES):
    kwargs = {} if reported is None else {"reported_outputs": reported}
    return CrossSolverConsensus(
        consensus_id="tb3",
        routes=routes,
        comparison=comparison,
        thresholds=THRESHOLDS,
        required_outputs=required,
        **kwargs,
    )


def _agreed(*quantities: str) -> RouteComparison:
    return RouteComparison(quantities, quantities[0], 0.0, TOLERANCE)


NOTHING_COMPARED = RouteComparison((), "", None, TOLERANCE)


def _verdict(consensus: CrossSolverConsensus):
    return (
        consensus.missing_outputs,
        consensus.output_completeness,
        consensus.earned,
        consensus.establishes,
    )


# ---- A: required {A, B}, nothing reported ----------------------------------
def test_a_direct_required_outputs_with_no_reports_is_incomplete():
    """The reproduced bypass: an agreeing comparison and no reports at all."""
    consensus = _direct(_agreed("A", "B"))

    assert consensus.output_completeness is OutputCompleteness.INCOMPLETE
    assert consensus.missing_outputs == (
        ("a", "A"), ("a", "B"), ("b", "A"), ("b", "B"),
    )
    assert consensus.earned is False
    assert consensus.establishes is None
    assert consensus.to_check().establishes is None


def test_a_factory_and_direct_agree_when_nothing_was_reported():
    factory = _factory({})
    direct = _direct(factory.comparison)

    assert factory.output_completeness is OutputCompleteness.INCOMPLETE
    assert _verdict(direct) == _verdict(factory)


# ---- B: required {A, B}, only A reported ------------------------------------
def test_b_partial_reports_are_incomplete_on_both_paths():
    factory = _factory({"a": {"A": 1.0}, "b": {"A": 1.0}})
    direct = _direct(_agreed("A"), reported={"a": ("A",), "b": ("A",)})

    for consensus in (factory, direct):
        assert consensus.output_completeness is OutputCompleteness.INCOMPLETE
        assert consensus.missing_outputs == (("a", "B"), ("b", "B"))
        assert consensus.establishes is None


def test_b_a_route_absent_from_reports_is_charged_for_every_required_output():
    """Route b has no entry at all, which is what it reported: nothing."""
    direct = _direct(_agreed("A", "B"), reported={"a": ("A", "B")})
    factory = _factory({"a": {"A": 1.0, "B": 2.0}})

    assert direct.missing_outputs == (("b", "A"), ("b", "B"))
    assert direct.output_completeness is OutputCompleteness.INCOMPLETE
    assert direct.establishes is None
    assert factory.missing_outputs == direct.missing_outputs
    assert factory.output_completeness is direct.output_completeness


# ---- C: required {A, B}, everything reported --------------------------------
def test_c_complete_reports_and_agreement_establish_on_both_paths():
    values = {"a": {"A": 1.0, "B": 2.0}, "b": {"A": 1.0, "B": 2.0}}
    factory = _factory(values)
    direct = _direct(
        _agreed("A", "B"), reported={"a": ("A", "B"), "b": ("A", "B")}
    )

    for consensus in (factory, direct):
        assert consensus.missing_outputs == ()
        assert consensus.output_completeness is OutputCompleteness.COMPLETE
        assert consensus.establishes is VALIDATED
    assert _verdict(direct) == _verdict(factory)


# ---- D: nothing required, nothing reported ----------------------------------
def test_d_an_undeclared_requirement_is_undeclared_on_both_paths():
    """The contract: an empty required set is a refusal, not a wildcard."""
    factory = _factory({"a": {"A": 1.0}, "b": {"A": 1.0}}, required=())
    direct = _direct(NOTHING_COMPARED, required=())
    direct_agreeing = _direct(
        _agreed("A"), required=(), reported={"a": ("A",), "b": ("A",)}
    )

    for consensus in (factory, direct, direct_agreeing):
        assert consensus.output_completeness is OutputCompleteness.UNDECLARED
        assert consensus.missing_outputs == ()
        assert consensus.establishes is None


# ---- E/F: the answer does not depend on the construction API ----------------
@pytest.mark.parametrize(
    "values",
    [
        {},
        {"a": {"A": 1.0}},
        {"a": {"A": 1.0}, "b": {"A": 1.0}},
        {"a": {"A": 1.0, "B": 2.0}},
        {"a": {"A": 1.0, "B": 2.0}, "b": {"A": 1.0}},
        {"a": {"A": 1.0, "B": 2.0}, "b": {"A": 1.0, "B": 2.0}},
        {"a": {"A": 1.0, "B": 2.0}, "b": {"A": 1.0, "B": 2.5}},
    ],
    ids=["none", "a:A", "both:A", "a:AB", "a:AB,b:A", "both:AB", "disagree"],
)
def test_e_f_direct_reconstruction_matches_the_factory(values):
    factory = _factory(values)
    direct = CrossSolverConsensus(
        consensus_id=factory.consensus_id,
        routes=factory.routes,
        comparison=factory.comparison,
        thresholds=factory.thresholds,
        required_outputs=factory.required_outputs,
        reported_outputs=dict(factory.reported_outputs),
    )
    without_empty_entries = CrossSolverConsensus(
        consensus_id=factory.consensus_id,
        routes=factory.routes,
        comparison=factory.comparison,
        thresholds=factory.thresholds,
        required_outputs=factory.required_outputs,
        reported_outputs={
            route: names
            for route, names in factory.reported_outputs.items()
            if names
        },
    )

    assert _verdict(direct) == _verdict(factory)
    assert _verdict(without_empty_entries) == _verdict(factory)
    assert direct.to_dict() == factory.to_dict()
    assert CrossSolverConsensus.from_dict(factory.to_dict()).to_dict() == (
        factory.to_dict()
    )


def test_no_routes_is_not_a_complete_answer():
    """Nobody answered, so nobody answered the whole question."""
    factory = _factory({}, routes=())
    direct = _direct(NOTHING_COMPARED, routes=())

    for consensus in (factory, direct):
        assert consensus.output_completeness is OutputCompleteness.INCOMPLETE
        assert consensus.establishes is None


# ---- the record may not describe reports that cannot have happened ----------
def test_a_report_from_an_undeclared_route_is_refused():
    with pytest.raises(ScientificValidationError, match="not a declared route"):
        _direct(
            _agreed("A", "B"),
            reported={"a": ("A", "B"), "b": ("A", "B"), "ghost": ("A", "B")},
        )


def test_a_comparison_over_a_quantity_a_route_did_not_report_is_refused():
    with pytest.raises(ScientificValidationError, match="did not report"):
        _direct(
            _agreed("A", "Z"),
            required=("A",),
            reported={"a": ("A",), "b": ("A",)},
        )


def test_the_evidence_must_be_the_types_that_enforce_their_own_rules():
    """A stand-in object carries ``agreed``, ``award`` or ``components`` past
    the rules :class:`RouteComparison`, :class:`VerificationThresholds` and
    :class:`SolveRoute` enforce, because their constructors never ran."""
    reported = {"a": ("A", "B"), "b": ("A", "B")}
    duck_comparison = SimpleNamespace(
        quantities=("A", "B"), worst_quantity="A", worst_relative_difference=0.0,
        tolerance=TOLERANCE, agreed=True, compared_anything=True, detail="",
    )
    with pytest.raises(ScientificValidationError, match="not a RouteComparison"):
        _direct(duck_comparison, reported=reported)

    duck_thresholds = SimpleNamespace(award=lambda level, *, earned: level)
    with pytest.raises(ScientificValidationError, match="not VerificationThresholds"):
        CrossSolverConsensus(
            consensus_id="tb3", routes=ROUTES, comparison=_agreed("A", "B"),
            thresholds=duck_thresholds, required_outputs=REQUIRED,
            reported_outputs=reported,
        )

    duck_route = SimpleNamespace(
        route_id="b", components=frozenset({"b:rhs"}), declares_nothing=False
    )
    with pytest.raises(ScientificValidationError, match="not a SolveRoute"):
        _direct(_agreed("A", "B"), reported=reported, routes=(ROUTES[0], duck_route))


def test_complete_reports_with_a_required_output_left_uncompared_are_refused():
    """Agreement on A cannot stand in for agreement on A and B."""
    with pytest.raises(ScientificValidationError, match="was not compared"):
        _direct(_agreed("A"), reported={"a": ("A", "B"), "b": ("A", "B")})


# ---- deserialization is a public construction path too ----------------------
def test_a_payload_with_its_reports_removed_cannot_keep_its_level():
    payload = json.loads(
        json.dumps(
            _factory(
                {"a": {"A": 1.0, "B": 2.0}, "b": {"A": 1.0, "B": 2.0}}
            ).to_dict()
        )
    )
    assert payload["establishes"] == VALIDATED.value
    payload["reported_outputs"] = {}

    with pytest.raises(ScientificValidationError, match="may not assert one"):
        CrossSolverConsensus.from_dict(payload)

    payload["establishes"] = None
    loaded = CrossSolverConsensus.from_dict(payload)
    assert loaded.output_completeness is OutputCompleteness.INCOMPLETE
    assert loaded.establishes is None


# ---- promotion safety, over every combination the constructor accepts -------
_REPORT_VARIANTS = (
    None,
    {},
    {"a": ()},
    {"a": ("A",)},
    {"a": ("A", "B")},
    {"a": ("A", "B"), "b": ("A",)},
    {"a": ("A", "B"), "b": ("A", "B")},
    {"a": ("A", "B", "C"), "b": ("A", "B", "C")},
)
_COMPARISON_VARIANTS = (
    NOTHING_COMPARED,
    _agreed("A"),
    _agreed("A", "B"),
    _agreed("A", "B", "C"),
    RouteComparison(("A", "B"), "B", 1e-3, TOLERANCE),
)
_REQUIRED_VARIANTS = ((), ("A",), ("A", "B"))


def test_cross_solver_validated_requires_every_completeness_invariant():
    """No accepted direct construction reaches the level without the evidence.

    Walks every combination of reports, comparison and requirement through the
    public constructor. Whatever the constructor accepts, a record that
    establishes ``CROSS_SOLVER_VALIDATED`` -- directly, through ``to_check``,
    or after a serialization round trip -- must have declared its required
    outputs, recorded every route as reporting all of them, compared all of
    them, and agreed.
    """
    awarded = 0
    for reported, comparison, required in itertools.product(
        _REPORT_VARIANTS, _COMPARISON_VARIANTS, _REQUIRED_VARIANTS
    ):
        try:
            consensus = _direct(comparison, required=required, reported=reported)
        except ScientificValidationError:
            continue
        levels = {
            consensus.establishes,
            consensus.to_check().establishes,
            CrossSolverConsensus.from_dict(consensus.to_dict()).establishes,
        }
        assert len(levels) == 1, (reported, comparison, required, levels)
        if consensus.establishes is not VALIDATED:
            continue
        awarded += 1
        case = (reported, comparison.quantities, required)
        assert required, case
        assert consensus.output_completeness is OutputCompleteness.COMPLETE, case
        for route in consensus.routes:
            assert set(required) <= set(
                (reported or {}).get(route.route_id, ())
            ), case
        assert set(required) <= set(comparison.quantities), case
        assert comparison.agreed, case
        assert consensus.routes_are_independent, case
    # Not vacuous: the honest combinations still earn the level.
    assert awarded > 0
