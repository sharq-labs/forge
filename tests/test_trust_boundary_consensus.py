"""Consensus evidence is a property of the record, not of the factory.

TB-3 of the trust-boundary hardening sprint, in two halves.

**Completeness.** ``CrossSolverConsensus.over()`` writes an entry into
``reported_outputs`` for every route -- an empty tuple for a route that reported
nothing -- and ``missing_outputs`` charged a route only through that entry. The
public constructor accepted ``required_outputs`` with no ``reported_outputs`` at
all, and ``missing_outputs`` read the absent mapping as "nothing is missing":
the record said COMPLETE and established ``CROSS_SOLVER_VALIDATED`` for outputs
no route was ever recorded as producing.

**Agreement.** Found by the sprint's own sweep for the same shape (TB-4). A
``/2`` record kept a comparison's *conclusion* -- the worst difference and the
tolerance it met -- and not the numbers it was computed from or the threshold
the tolerance was read from. So the constructor accepted a comparison claiming
a worst difference of 0.0 for routes whose real numbers differ by 23 %, and one
carrying its own tolerance of 1.0 under a declared set whose number is 1e-9,
and both established ``CROSS_SOLVER_VALIDATED``. A ``/3`` record carries the
numbers and the threshold key, and its constructor recomputes the comparison
and refuses one that does not follow; a record without the numbers can carry a
comparison but cannot establish a level.

Absence of evidence is not evidence, whichever door the record came in through.
"""

from __future__ import annotations

import itertools
import json
from types import SimpleNamespace

import pytest

from engcore.scientific.consensus import (
    CONSENSUS_SCHEMA,
    CONSENSUS_SCHEMA_V2,
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
AGREEING = {"a": {"A": 1.0, "B": 2.0}, "b": {"A": 1.0, "B": 2.0}}
DISAGREEING = {"a": {"A": 1.0, "B": 2.0}, "b": {"A": 1.3, "B": 2.0}}
COMPLETE_REPORTS = {"a": ("A", "B"), "b": ("A", "B")}


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
    """Through the public constructor with a comparison and no numbers."""
    kwargs = {} if reported is None else {"reported_outputs": reported}
    return CrossSolverConsensus(
        consensus_id="tb3",
        routes=routes,
        comparison=comparison,
        thresholds=THRESHOLDS,
        required_outputs=required,
        **kwargs,
    )


def _rebuilt(made: CrossSolverConsensus, **changes) -> CrossSolverConsensus:
    """A factory record through the public constructor, field for field."""
    fields = dict(
        consensus_id=made.consensus_id,
        routes=made.routes,
        comparison=made.comparison,
        thresholds=made.thresholds,
        required_outputs=made.required_outputs,
        reported_outputs=dict(made.reported_outputs),
        tolerance_key=made.tolerance_key,
        reported_values={r: dict(v) for r, v in made.reported_values.items()},
        notes=made.notes,
    )
    fields.update(changes)
    return CrossSolverConsensus(**fields)


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


# ======================================================== completeness
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
    assert _verdict(_rebuilt(factory)) == _verdict(factory)


# ---- B: required {A, B}, only A reported ------------------------------------
def test_b_partial_reports_are_incomplete_on_both_paths():
    factory = _factory({"a": {"A": 1.0}, "b": {"A": 1.0}})
    direct = _direct(_agreed("A"), reported={"a": ("A",), "b": ("A",)})

    for consensus in (factory, direct, _rebuilt(factory)):
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
    factory = _factory(AGREEING)
    direct = _rebuilt(factory)

    for consensus in (factory, direct):
        assert consensus.missing_outputs == ()
        assert consensus.output_completeness is OutputCompleteness.COMPLETE
        assert consensus.establishes is VALIDATED
    assert _verdict(direct) == _verdict(factory)


def test_c_the_same_comparison_without_its_numbers_establishes_nothing():
    claimed = _direct(_agreed("A", "B"), reported=COMPLETE_REPORTS)

    assert claimed.output_completeness is OutputCompleteness.COMPLETE
    assert claimed.comparison.agreed is True
    assert claimed.comparison_is_derived is False
    assert claimed.earned is False
    assert claimed.establishes is None
    assert "without the numbers" in claimed.reason


# ---- D: nothing required, nothing reported ----------------------------------
def test_d_an_undeclared_requirement_is_undeclared_on_both_paths():
    """The contract: an empty required set is a refusal, not a wildcard."""
    factory = _factory({"a": {"A": 1.0}, "b": {"A": 1.0}}, required=())
    direct = _direct(NOTHING_COMPARED, required=())
    direct_agreeing = _direct(
        _agreed("A"), required=(), reported={"a": ("A",), "b": ("A",)}
    )

    for consensus in (factory, direct, direct_agreeing, _rebuilt(factory)):
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
        AGREEING,
        {"a": {"A": 1.0, "B": 2.0}, "b": {"A": 1.0, "B": 2.5}},
    ],
    ids=["none", "a:A", "both:A", "a:AB", "a:AB,b:A", "both:AB", "disagree"],
)
def test_e_f_direct_reconstruction_matches_the_factory(values):
    factory = _factory(values)
    direct = _rebuilt(factory)
    without_empty_entries = _rebuilt(
        factory,
        reported_outputs={
            route: names for route, names in factory.reported_outputs.items() if names
        },
    )
    without_numbers = _rebuilt(factory, reported_values={}, tolerance_key="")

    assert _verdict(direct) == _verdict(factory)
    assert _verdict(without_empty_entries) == _verdict(factory)
    assert direct.to_dict() == factory.to_dict()
    assert CrossSolverConsensus.from_dict(factory.to_dict()).to_dict() == (
        factory.to_dict()
    )
    # Completeness is the same without the numbers; a level never is.
    assert without_numbers.missing_outputs == factory.missing_outputs
    assert without_numbers.output_completeness is factory.output_completeness
    assert without_numbers.establishes is None


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
            reported={**COMPLETE_REPORTS, "ghost": ("A", "B")},
        )
    with pytest.raises(ScientificValidationError, match="not a declared route"):
        _rebuilt(
            _factory(AGREEING),
            reported_values={**AGREEING, "ghost": {"A": 1.0, "B": 2.0}},
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
    duck_comparison = SimpleNamespace(
        quantities=("A", "B"), worst_quantity="A", worst_relative_difference=0.0,
        tolerance=TOLERANCE, agreed=True, compared_anything=True, detail="",
    )
    with pytest.raises(ScientificValidationError, match="not a RouteComparison"):
        _direct(duck_comparison, reported=COMPLETE_REPORTS)

    duck_thresholds = SimpleNamespace(award=lambda level, *, earned: level)
    with pytest.raises(ScientificValidationError, match="not VerificationThresholds"):
        CrossSolverConsensus(
            consensus_id="tb3", routes=ROUTES, comparison=_agreed("A", "B"),
            thresholds=duck_thresholds, required_outputs=REQUIRED,
            reported_outputs=COMPLETE_REPORTS,
        )

    duck_route = SimpleNamespace(
        route_id="b", components=frozenset({"b:rhs"}), declares_nothing=False
    )
    with pytest.raises(ScientificValidationError, match="not a SolveRoute"):
        _direct(_agreed("A", "B"), reported=COMPLETE_REPORTS, routes=(ROUTES[0], duck_route))


def test_complete_reports_with_a_required_output_left_uncompared_are_refused():
    """Agreement on A cannot stand in for agreement on A and B."""
    with pytest.raises(ScientificValidationError, match="was not compared"):
        _direct(_agreed("A"), reported=COMPLETE_REPORTS)


# ======================================================== agreement
def test_a_comparison_carrying_its_own_tolerance_cannot_establish_a_level():
    """Reproduced by the sprint's TB-4 sweep: tolerance 1.0 under a 1e-9 set."""
    loose = RouteComparison(("A", "B"), "A", 0.3, 1.0)
    assert _direct(loose, reported=COMPLETE_REPORTS).establishes is None

    with pytest.raises(ScientificValidationError, match="does not follow"):
        _rebuilt(_factory(DISAGREEING), comparison=loose)


def test_a_forged_worst_difference_cannot_establish_a_level():
    """Reproduced by the sprint's TB-4 sweep: worst 0.0 for routes 23 % apart."""
    honest = _factory(DISAGREEING)
    assert honest.comparison.agreed is False and honest.establishes is None

    forged = _agreed("A", "B")
    assert _direct(forged, reported=COMPLETE_REPORTS).establishes is None
    with pytest.raises(ScientificValidationError, match="does not follow"):
        _rebuilt(honest, comparison=forged)


def test_the_comparison_is_recomputed_from_the_recorded_numbers():
    agreeing = _factory(AGREEING)
    with pytest.raises(ScientificValidationError, match="does not follow"):
        _rebuilt(agreeing, reported_values=DISAGREEING)


def test_the_tolerance_key_must_name_a_threshold_of_the_set():
    with pytest.raises(ScientificValidationError, match="is not a threshold"):
        _rebuilt(_factory(AGREEING), tolerance_key="some_other_bound")


def test_recorded_numbers_and_recorded_outputs_must_agree():
    with pytest.raises(ScientificValidationError, match="carries numbers for"):
        _rebuilt(_factory(AGREEING), reported_outputs={"a": ("A",), "b": ("A", "B")})


def test_non_finite_recorded_numbers_are_refused():
    with pytest.raises(ScientificValidationError, match="non-finite"):
        _rebuilt(
            _factory(AGREEING),
            reported_values={"a": {"A": float("nan"), "B": 2.0}, "b": {"A": 1.0, "B": 2.0}},
        )
    # A route that returned one did not finish: the factory keeps the refusal
    # in the comparison, keeps no numbers, and establishes nothing.
    diverged = _factory({"a": {"A": float("inf"), "B": 2.0}, "b": {"A": 1.0, "B": 2.0}})
    assert diverged.reported_values == {}
    assert diverged.comparison.compared_anything is False
    assert diverged.establishes is None


def test_the_numbers_and_the_threshold_key_travel_in_the_record():
    made = _factory(AGREEING)
    payload = json.loads(json.dumps(made.to_dict(), allow_nan=False))

    assert payload["schema"] == CONSENSUS_SCHEMA == "cross_solver_consensus/3"
    assert payload["tolerance_key"] == "agreement_rel_tol"
    assert payload["reported_values"] == AGREEING
    assert CrossSolverConsensus.from_dict(payload) == made


def test_a_version_two_record_is_read_only_where_it_claims_no_level():
    payload = _factory(AGREEING).to_dict()
    payload["schema"] = CONSENSUS_SCHEMA_V2
    payload.pop("reported_values")
    payload.pop("tolerance_key")
    assert payload["establishes"] == VALIDATED.value

    with pytest.raises(ScientificValidationError, match="was awarded under a rule"):
        CrossSolverConsensus.from_dict(payload)

    payload["establishes"] = None
    loaded = CrossSolverConsensus.from_dict(payload)
    assert loaded.comparison_is_derived is False
    assert loaded.establishes is None


# ---- deserialization is a public construction path too ----------------------
def test_a_payload_with_its_evidence_removed_cannot_keep_its_level():
    payload = json.loads(json.dumps(_factory(AGREEING).to_dict()))
    assert payload["establishes"] == VALIDATED.value
    payload["reported_outputs"] = {}
    payload["reported_values"] = {}

    with pytest.raises(ScientificValidationError, match="may not assert one"):
        CrossSolverConsensus.from_dict(payload)

    payload["establishes"] = None
    loaded = CrossSolverConsensus.from_dict(payload)
    assert loaded.output_completeness is OutputCompleteness.INCOMPLETE
    assert loaded.establishes is None


# ======================================================== promotion safety
_REPORT_VARIANTS = (
    None,
    {},
    {"a": ()},
    {"a": ("A",)},
    {"a": ("A", "B")},
    {"a": ("A", "B"), "b": ("A",)},
    COMPLETE_REPORTS,
    {"a": ("A", "B", "C"), "b": ("A", "B", "C")},
)
_COMPARISON_VARIANTS = (
    NOTHING_COMPARED,
    _agreed("A"),
    _agreed("A", "B"),
    _agreed("A", "B", "C"),
    RouteComparison(("A", "B"), "B", 1e-3, TOLERANCE),
    RouteComparison(("A", "B"), "A", 0.3, 1.0),
)
_REQUIRED_VARIANTS = ((), ("A",), ("A", "B"))
_VALUE_VARIANTS = (
    {},
    {"a": {"A": 1.0}},
    {"a": {"A": 1.0, "B": 2.0}, "b": {"A": 1.0}},
    AGREEING,
    DISAGREEING,
    {"a": {"A": 1.0, "B": 2.0, "C": 3.0}, "b": {"A": 1.0, "B": 2.0, "C": 3.0}},
)


def _assert_every_invariant(consensus: CrossSolverConsensus, case) -> None:
    required = consensus.required_outputs
    assert required, case
    assert consensus.output_completeness is OutputCompleteness.COMPLETE, case
    for route in consensus.routes:
        assert set(required) <= set(consensus.reported_outputs.get(route.route_id, ())), case
    assert consensus.comparison_is_derived, case
    recomputed = CrossSolverConsensus.over(
        consensus_id=consensus.consensus_id,
        routes=consensus.routes,
        values=consensus.reported_values,
        thresholds=consensus.thresholds,
        tolerance_key=consensus.tolerance_key,
        required_outputs=required,
    )
    assert consensus.comparison == recomputed.comparison, case
    assert consensus.comparison.tolerance == consensus.thresholds[consensus.tolerance_key], case
    assert set(required) <= set(consensus.comparison.quantities), case
    assert consensus.comparison.agreed, case
    assert consensus.routes_are_independent, case


def test_a_comparison_without_numbers_never_establishes_a_level():
    """Every combination the constructor accepts without recorded numbers."""
    for reported, comparison, required in itertools.product(
        _REPORT_VARIANTS, _COMPARISON_VARIANTS, _REQUIRED_VARIANTS
    ):
        try:
            consensus = _direct(comparison, required=required, reported=reported)
        except ScientificValidationError:
            continue
        case = (reported, comparison, required)
        assert consensus.establishes is None, case
        assert consensus.to_check().establishes is None, case
        assert CrossSolverConsensus.from_dict(consensus.to_dict()).establishes is None, case


def test_cross_solver_validated_requires_every_evidence_invariant():
    """No accepted construction reaches the level without the evidence.

    Every value set and requirement through the factory, and then every forged
    comparison and every altered report through the public constructor on top
    of the factory's own numbers. Wherever ``CROSS_SOLVER_VALIDATED`` is
    established -- directly, through ``to_check``, or after a round trip -- the
    record must have declared its outputs, recorded every route reporting all
    of them, carried the numbers its comparison recomputes from at the threshold
    set's own tolerance, compared every required output, and agreed.
    """
    awarded = 0
    for values, required in itertools.product(_VALUE_VARIANTS, _REQUIRED_VARIANTS):
        factory = _factory(values, required=required)
        candidates = [lambda f=factory: f, lambda f=factory: _rebuilt(f)]
        candidates += [
            (lambda f=factory, c=c: _rebuilt(f, comparison=c)) for c in _COMPARISON_VARIANTS
        ]
        candidates += [
            (lambda f=factory, r=r: _rebuilt(f, reported_outputs=r or {}))
            for r in _REPORT_VARIANTS
        ]
        for build in candidates:
            try:
                consensus = build()
            except ScientificValidationError:
                continue
            levels = {
                consensus.establishes,
                consensus.to_check().establishes,
                CrossSolverConsensus.from_dict(consensus.to_dict()).establishes,
            }
            case = (values, required, consensus.comparison, dict(consensus.reported_outputs))
            assert len(levels) == 1, (case, levels)
            if consensus.establishes is VALIDATED:
                awarded += 1
                _assert_every_invariant(consensus, case)
    # Not vacuous: the honest records still earn the level.
    assert awarded > 0
