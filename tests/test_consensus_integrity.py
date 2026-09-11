"""CROSS_SOLVER_VALIDATED must never claim more than the evidence supports.

THE DEFECT
----------
``_compare`` took the **intersection** of what the routes reported. A route
producing ``temperature``, ``stress`` and ``pressure`` and a route producing
``temperature`` alone were compared on ``temperature``, and agreement there
earned ``CROSS_SOLVER_VALIDATED`` for the whole consensus.

The record was honest about which quantities it compared. Nothing said which
ones it *should* have compared, so nothing could tell a complete confirmation
from a partial one -- and the partial one is by far the cheaper to produce. A
route that answers one third of the question and agrees is indistinguishable,
in the level it buys, from one that answers all of it.

WHAT IS ASSERTED HERE
---------------------
The exact conditions required to earn the level, each defeated on its own:

1. at least two routes, each declaring what it is made of, sharing nothing;
2. a declared ``required_outputs`` set -- empty is a refusal, not a wildcard;
3. every route reporting every required output;
4. finite values throughout;
5. agreement inside a threshold set the domain owns.

And the two things independence explicitly does NOT establish, so that nobody
has to rediscover them from a surprising verdict.
"""

from __future__ import annotations

import json

import pytest

from engcore.scientific.consensus import (
    CONSENSUS_SCHEMA,
    CONSENSUS_SCHEMA_V1,
    ComponentKind,
    CrossSolverConsensus,
    IndependenceVerdict,
    OutputCompleteness,
    SharedComponent,
    SolveRoute,
)
from engcore.domains.electrical.dc_consensus import DC_CONSENSUS_THRESHOLDS
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.results.thresholds import VerificationThresholds
from engcore.scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
)
from engcore.scientific.solvers.protocol import SolverIdentity

#: A declared gate's own set. This fixture used to invent a gate, and earned
#: levels with it until threshold authority was verified against the domain
#: layer's pins; a test of the awarding half now uses a real declaration.
THRESHOLDS = DC_CONSENSUS_THRESHOLDS

#: The three quantities the question is about, wherever a contract is needed.
CONTRACT = ("pressure", "stress", "temperature")

FULL = {"temperature": 350.0, "stress": 120.0, "pressure": 2.0}
PARTIAL = {"temperature": 350.0}


def _route(route_id: str, *components: str, solver: SolverIdentity | None = None):
    return SolveRoute(
        route_id=route_id,
        solver=solver or SolverIdentity(f"solver.{route_id}", "1.0", backend=route_id),
        components=frozenset(
            SharedComponent(kind=ComponentKind.IMPLEMENTATION, name=name)
            for name in components
        ),
    )


def _consensus(values, *, required=CONTRACT, routes=None, thresholds=THRESHOLDS):
    routes = routes or tuple(
        _route(route_id, f"impl-{route_id}") for route_id in sorted(values)
    )
    return CrossSolverConsensus.over(
        consensus_id="test",
        routes=routes,
        values=values,
        thresholds=thresholds,
        tolerance_key="agreement_rel_tol",
        required_outputs=required,
    )


# ================================================= E1: output completeness


def test_the_defect_a_partial_answer_no_longer_buys_the_whole_level():
    """The reproduction, as the round posed it.

    Route A produces temperature, stress and pressure. Route B produces
    temperature. Temperature agrees. Before this round that earned
    CROSS_SOLVER_VALIDATED.
    """
    consensus = _consensus({"A": FULL, "B": PARTIAL})

    assert consensus.routes_are_independent is True
    assert consensus.comparison.agreed is True, (
        "temperature really does agree; the refusal must come from "
        "completeness and not from a disagreement"
    )
    assert consensus.output_completeness is OutputCompleteness.INCOMPLETE
    assert consensus.missing_outputs == (("B", "pressure"), ("B", "stress"))
    assert consensus.establishes is None
    assert consensus.earned is False


def test_a_complete_matching_answer_is_eligible():
    """The positive case, so the refusal above is not a blanket."""
    consensus = _consensus({"A": FULL, "B": dict(FULL)})
    assert consensus.output_completeness is OutputCompleteness.COMPLETE
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    assert set(consensus.comparison.quantities) == set(CONTRACT)


def test_an_undeclared_required_output_set_earns_nothing():
    """Empty is a refusal, not a wildcard -- the same rule independence uses.

    An undeclared set intersects with everything to nothing and would otherwise
    be the cheapest possible route to a level: say nothing about what the
    routes owed and the arithmetic says they delivered it.
    """
    consensus = _consensus({"A": FULL, "B": dict(FULL)}, required=())
    assert consensus.output_completeness is OutputCompleteness.UNDECLARED
    assert consensus.comparison.agreed is True
    assert consensus.establishes is None
    assert "declares no required outputs" in consensus.reason


def test_a_route_that_reported_nothing_is_charged_for_the_whole_contract():
    """An absent route must not be overlooked by the completeness check.

    A route that supplied no values at all is short of every required output.
    Recording it with an empty tuple rather than omitting it is what makes that
    true; omitting it would have let a silent route pass the contract.
    """
    consensus = _consensus(
        {"A": FULL},
        routes=(_route("A", "impl-a"), _route("B", "impl-b")),
    )
    assert ("B", "temperature") in consensus.missing_outputs
    assert len(consensus.missing_outputs) == len(CONTRACT)
    assert consensus.establishes is None


def test_an_output_outside_the_contract_can_only_make_agreement_harder():
    """Extra outputs must not falsely strengthen -- and must not be hidden.

    Both routes report ``drift``, which nobody required, and they differ on it
    wildly. The contract is met and agreed; the consensus still refuses,
    because two routes that differ that much have found something and a
    comparison that ignored it would be hiding a real disagreement to protect a
    claim.
    """
    consensus = _consensus(
        {
            "A": {**FULL, "drift": 1.0},
            "B": {**FULL, "drift": 500.0},
        }
    )
    assert consensus.output_completeness is OutputCompleteness.COMPLETE
    assert "drift" in consensus.comparison.quantities
    assert consensus.comparison.agreed is False
    assert consensus.establishes is None


def test_an_extra_output_that_agrees_does_not_change_the_verdict():
    """The complement: an extra agreeing quantity neither helps nor hurts."""
    consensus = _consensus(
        {"A": {**FULL, "drift": 1.0}, "B": {**FULL, "drift": 1.0}}
    )
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    assert "drift" in consensus.comparison.quantities


def test_an_optional_output_present_on_only_one_route_is_an_absence():
    """Behaviour for a non-required, non-shared output, stated explicitly.

    It is not compared -- an absence is not a disagreement -- and it does not
    affect completeness, because nothing required it. The contract is what
    decides, which is the entire point of declaring one.
    """
    consensus = _consensus(
        {"A": {**FULL, "diagnostic": 42.0}, "B": dict(FULL)}
    )
    assert consensus.output_completeness is OutputCompleteness.COMPLETE
    assert "diagnostic" not in consensus.comparison.quantities
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED


def test_the_refusal_names_the_route_and_the_missing_quantity():
    """A refusal a reader cannot act on is only half a refusal."""
    reason = _consensus({"A": FULL, "B": PARTIAL}).reason
    assert "B:stress" in reason and "B:pressure" in reason


# ================================================= E2: independence audit


def test_independence_still_rests_on_the_declaration_and_nothing_else():
    """The mechanism, restated where the completeness rule now sits beside it."""
    shared = _consensus(
        {"A": dict(FULL), "B": dict(FULL)},
        routes=(_route("A", "common-rhs"), _route("B", "common-rhs")),
    )
    assert shared.independence is IndependenceVerdict.SHARES_COMPONENTS
    assert shared.establishes is None

    silent = _consensus(
        {"A": dict(FULL), "B": dict(FULL)},
        routes=(_route("A"), _route("B", "impl-b")),
    )
    assert silent.independence is IndependenceVerdict.UNDECLARED
    assert silent.establishes is None


def test_a_shared_solver_identity_is_reported_without_being_judged():
    """The residual risk, made visible rather than closed.

    Two routes carrying one solver identity CAN be genuinely independent -- one
    integrator asked for two different methods is the module's own example --
    so this does not defeat the level. What it must not do is pass silently: a
    reviewer weighing the claim needs to see that two "independent" routes name
    one program.
    """
    same = SolverIdentity("solver.shared", "1.0", backend="one-binary")
    consensus = _consensus(
        {"A": dict(FULL), "B": dict(FULL)},
        routes=(
            _route("A", "impl-a", solver=same),
            _route("B", "impl-b", solver=same),
        ),
    )
    assert consensus.shared_solver_identities == ("solver.shared@1.0[one-binary]",)
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED, (
        "a shared identity is reported, not disqualifying; changing that would "
        "override a documented design decision rather than fix a defect"
    )
    assert "solver.shared@1.0[one-binary]" in json.dumps(consensus.to_dict())
    # And the backend reaches the evidence, since it is what names an external
    # provider and a consensus with two backends is the interesting case.
    assert any("[one-binary]" in line for line in consensus.evidence())


def test_distinct_solver_identities_report_nothing_shared():
    """The complement, so the property above is not constant."""
    consensus = _consensus({"A": dict(FULL), "B": dict(FULL)})
    assert consensus.shared_solver_identities == ()


def test_one_route_cannot_be_a_consensus():
    consensus = _consensus({"A": dict(FULL)}, routes=(_route("A", "impl-a"),))
    assert consensus.independence is IndependenceVerdict.TOO_FEW_ROUTES
    assert consensus.establishes is None


# ================================================= E3: propagation


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_route_cannot_reach_the_level_through_a_report(bad):
    """End to end: consensus -> check -> report -> attained_levels.

    Phase B closed the comparison. This asserts the closure survives every
    layer between it and the thing a consumer actually reads, because a level
    that cannot be earned in the record but appears in `attained_levels` is the
    same defect one storey up.
    """
    consensus = _consensus({"A": {**FULL, "temperature": bad}, "B": dict(FULL)})
    assert consensus.establishes is None

    check = consensus.to_check()
    assert check.outcome is ValidationOutcome.NOT_RUN
    assert check.establishes is None

    report = ValidationReport(checks=(check,))
    assert ValidationLevel.CROSS_SOLVER_VALIDATED not in report.attained_levels
    assert report.attained_levels == frozenset()


def test_an_incomplete_consensus_cannot_reach_the_level_through_a_report():
    """The same closure for the completeness half."""
    consensus = _consensus({"A": FULL, "B": PARTIAL})
    report = ValidationReport(checks=(consensus.to_check(),))
    assert ValidationLevel.CROSS_SOLVER_VALIDATED not in report.attained_levels


def test_a_complete_finite_agreeing_consensus_does_reach_it():
    """The one path that earns, asserted end to end.

    Without this the four refusals above would pass over a mechanism that had
    stopped awarding anything at all.
    """
    consensus = _consensus({"A": FULL, "B": dict(FULL)})
    report = ValidationReport(checks=(consensus.to_check(),))
    assert report.attained_levels == frozenset(
        {ValidationLevel.CROSS_SOLVER_VALIDATED}
    )


# ================================================= serialization


def test_the_contract_travels_in_the_record():
    """A level a reader cannot audit is a level they have to take on trust."""
    consensus = _consensus({"A": FULL, "B": PARTIAL})
    payload = json.loads(json.dumps(consensus.to_dict()))

    assert payload["schema"] == CONSENSUS_SCHEMA
    assert payload["required_outputs"] == list(CONTRACT)
    assert payload["reported_outputs"]["B"] == ["temperature"]
    assert payload["output_completeness"] == "incomplete"
    assert payload["missing_outputs"] == ["B:pressure", "B:stress"]
    assert payload["establishes"] is None
    assert CrossSolverConsensus.from_dict(payload) == consensus


def test_a_payload_cannot_assert_a_level_its_contract_denies():
    """The recompute-and-verify rule, applied to the new condition.

    Editing `establishes` was already refused. This is the same refusal reached
    by the completeness route, so a hand-edited record cannot claim a level by
    deleting the evidence that it was incomplete.
    """
    consensus = _consensus({"A": FULL, "B": PARTIAL})
    payload = dict(consensus.to_dict())
    payload["establishes"] = "cross_solver_validated"
    with pytest.raises(ScientificValidationError, match="may not assert one"):
        CrossSolverConsensus.from_dict(payload)

    # And deleting the requirement does not restore the level either: it turns
    # the record into an UNDECLARED one, which still establishes nothing.
    payload = dict(consensus.to_dict())
    payload["required_outputs"] = []
    payload["establishes"] = "cross_solver_validated"
    with pytest.raises(ScientificValidationError):
        CrossSolverConsensus.from_dict(payload)


def test_a_version_one_record_is_read_only_where_it_claims_no_level():
    """The compatibility rule, and the reason for it.

    A /1 record has no field naming what the routes owed, so a level it claims
    was awarded under a rule that could not see completeness. The requirement
    cannot be reconstructed and must not be defaulted -- an empty set is
    exactly the state this version refuses to award on.
    """
    consensus = _consensus({"A": FULL, "B": dict(FULL)})
    legacy = dict(consensus.to_dict())
    legacy["schema"] = CONSENSUS_SCHEMA_V1
    legacy.pop("required_outputs")
    legacy.pop("reported_outputs")

    with pytest.raises(ScientificValidationError, match="was awarded under a rule"):
        CrossSolverConsensus.from_dict(legacy)

    # The same legacy record claiming nothing loads, and still claims nothing.
    legacy["establishes"] = None
    restored = CrossSolverConsensus.from_dict(legacy)
    assert restored.establishes is None
    assert restored.output_completeness is OutputCompleteness.UNDECLARED


def test_the_declared_conditions_are_exactly_five_and_each_one_is_load_bearing():
    """The summary this module exists to make checkable.

    Each condition is removed on its own from an otherwise-earning consensus,
    and each removal must defeat the level. A condition that could be dropped
    without changing the verdict would be decoration.
    """
    earning = _consensus({"A": FULL, "B": dict(FULL)})
    assert earning.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED

    # 1. two routes
    assert _consensus(
        {"A": dict(FULL)}, routes=(_route("A", "impl-a"),)
    ).establishes is None
    # 2. a declared contract
    assert _consensus({"A": FULL, "B": dict(FULL)}, required=()).establishes is None
    # 3. every required output present
    assert _consensus({"A": FULL, "B": PARTIAL}).establishes is None
    # 4. finite values
    assert _consensus(
        {"A": {**FULL, "stress": float("nan")}, "B": dict(FULL)}
    ).establishes is None
    # 5. agreement, judged against the domain's own thresholds
    assert _consensus(
        {"A": FULL, "B": {**FULL, "stress": 999.0}}
    ).establishes is None
    assert _consensus(
        {"A": FULL, "B": dict(FULL)},
        thresholds=THRESHOLDS.derive(agreement_rel_tol=1e-3),
    ).establishes is None
    # ...and independence, which the E2 block covers.
    assert _consensus(
        {"A": dict(FULL), "B": dict(FULL)},
        routes=(_route("A", "same"), _route("B", "same")),
    ).establishes is None
