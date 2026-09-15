"""CONS-01: a consensus awards its level only under the threshold its routes declare.

The audit (probe ``agentD/ind1.py``) handed the two production DC routes values
40 % apart and judged them against ``CONDUCTION_GATE_THRESHOLDS`` read at
``min_contraction`` (1.5). That set IS declared -- for the conduction refinement
gate -- so ``VerificationThresholds.award`` granted ``CROSS_SOLVER_VALIDATED``,
the check read PASS, the record survived ``from_dict`` and the trusted gate
validated it. ``_verified_against_declaration`` only asks whether a set is its
OWN gate's declaration, never whether it is the gate this comparison belongs to.

The rule these tests pin: the route declarations the domain layer pins name the
threshold gate and the tolerance key their comparison is judged under, and a
consensus judged under any other declared set, or any other key of the right
set, establishes nothing -- on construction and on the way back in.
"""

from __future__ import annotations

import pytest

from engcore.domains.electrical import dc_consensus as dcc
from engcore.domains.kinetics.cstr.validation import CSTR_GATE_THRESHOLDS
from engcore.domains.thermal.conduction1d.validation import CONDUCTION_GATE_THRESHOLDS
from engcore.scientific.consensus import CrossSolverConsensus
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.results.validation import ValidationLevel, ValidationOutcome
from engcore.scientific.solvers.protocol import SolverIdentity
from tests.route_declarations_for_tests import (  # noqa: F401 - autouse fixture
    earned_consensus,
    route,
    route_declarations_for_tests,
)

NATIVE = SolverIdentity("electrical.dc.mna", "0.1.0", backend="scipy.linalg.solve")
EXTERNAL = SolverIdentity("engcore.electrical.dc.ngspice", "44", backend="ngspice")


def _dc_routes():
    return (dcc.native_route(NATIVE), dcc.external_route(EXTERNAL))


def _over(routes, values, thresholds, key, required=("v",)):
    return CrossSolverConsensus.over(
        consensus_id="cons-01",
        routes=routes,
        values=values,
        thresholds=thresholds,
        tolerance_key=key,
        required_outputs=required,
    )


def test_probe_ind1_routes_forty_percent_apart_under_another_gates_threshold_earn_nothing():
    consensus = _over(
        _dc_routes(),
        {dcc.NATIVE_ROUTE_ID: {"v": 1.0}, dcc.EXTERNAL_ROUTE_ID: {"v": 0.6}},
        CONDUCTION_GATE_THRESHOLDS,
        "min_contraction",
    )
    assert CONDUCTION_GATE_THRESHOLDS.is_declared  # declared -- for another gate
    assert consensus.routes_are_independent
    assert consensus.comparison.agreed  # 0.4 <= 1.5: the widened bound "agrees"
    assert consensus.establishes is None
    assert consensus.threshold_authority_gap is not None
    assert "electrical.dc.cross_solver" in consensus.threshold_authority_gap
    check = consensus.to_check()
    assert check.establishes is None
    assert "thermal.conduction1d.refinement" in consensus.reason


def test_the_probe_record_cannot_claim_the_level_on_the_way_back_in():
    consensus = _over(
        _dc_routes(),
        {dcc.NATIVE_ROUTE_ID: {"v": 1.0}, dcc.EXTERNAL_ROUTE_ID: {"v": 0.6}},
        CONDUCTION_GATE_THRESHOLDS,
        "min_contraction",
    )
    payload = consensus.to_dict()
    assert payload["establishes"] is None
    assert CrossSolverConsensus.from_dict(payload).establishes is None
    payload["establishes"] = ValidationLevel.CROSS_SOLVER_VALIDATED.value
    with pytest.raises(ScientificValidationError, match="may not assert"):
        CrossSolverConsensus.from_dict(payload)


def test_a_tight_declared_set_of_another_gate_awards_nothing_either():
    # Not only a loose set: the rule is about WHOSE threshold it is.
    consensus = _over(
        _dc_routes(),
        {dcc.NATIVE_ROUTE_ID: {"v": 1.0}, dcc.EXTERNAL_ROUTE_ID: {"v": 1.0}},
        CSTR_GATE_THRESHOLDS,
        "invariant_rel_tol",
    )
    assert consensus.comparison.agreed
    assert consensus.establishes is None


def test_the_right_gate_under_a_key_the_routes_do_not_declare_awards_nothing():
    a = route("a", threshold_gate_id=CSTR_GATE_THRESHOLDS.gate_id, tolerance_key="tolerance_rel_tol")
    b = route("b", threshold_gate_id=CSTR_GATE_THRESHOLDS.gate_id, tolerance_key="tolerance_rel_tol")
    wrong_key = earned_consensus(
        (a, b), {"a": {"v": 1.0}, "b": {"v": 1.0}},
        thresholds=CSTR_GATE_THRESHOLDS, tolerance_key="steady_state_rel_tol",
        required=("v",),
    )
    assert wrong_key.comparison.agreed
    assert wrong_key.establishes is None
    assert "steady_state_rel_tol" in wrong_key.threshold_authority_gap
    right_key = earned_consensus(
        (a, b), {"a": {"v": 1.0}, "b": {"v": 1.0}},
        thresholds=CSTR_GATE_THRESHOLDS, tolerance_key="tolerance_rel_tol",
        required=("v",),
    )
    assert right_key.threshold_authority_gap is None
    assert right_key.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED


def test_routes_whose_declarations_name_different_gates_award_nothing():
    a = route("a")  # the default test pin: the DC gate
    b = route("b", threshold_gate_id=CSTR_GATE_THRESHOLDS.gate_id, tolerance_key="tolerance_rel_tol")
    consensus = earned_consensus(
        (a, b), {"a": {"v": 1.0}, "b": {"v": 1.0}},
        thresholds=dcc.DC_CONSENSUS_THRESHOLDS, tolerance_key="agreement_rel_tol",
        required=("v",),
    )
    assert consensus.establishes is None
    assert "b" in consensus.threshold_authority_gap


def test_a_route_pin_that_names_no_threshold_gate_awards_nothing(route_declarations_for_tests):
    a, b = route("a"), route("b")
    del route_declarations_for_tests["b"]["threshold_gate_id"]
    consensus = earned_consensus(
        (a, b), {"a": {"v": 1.0}, "b": {"v": 1.0}},
        thresholds=dcc.DC_CONSENSUS_THRESHOLDS, tolerance_key="agreement_rel_tol",
        required=("v",),
    )
    assert consensus.establishes is None


def test_production_route_pins_name_their_own_gate_and_key():
    from engcore.domains import SCIENTIFIC_ROUTE_DECLARATIONS as pins

    for route_id in (dcc.NATIVE_ROUTE_ID, dcc.EXTERNAL_ROUTE_ID):
        assert pins[route_id]["threshold_gate_id"] == dcc.DC_CONSENSUS_THRESHOLDS.gate_id
        assert pins[route_id]["tolerance_key"] == "agreement_rel_tol"
    for method in ("BDF", "Radau"):
        pin = pins[f"kinetics.cstr.integration:{method}"]
        assert pin["threshold_gate_id"] == CSTR_GATE_THRESHOLDS.gate_id
        assert pin["tolerance_key"] == "tolerance_rel_tol"


def test_positive_control_the_declared_gate_and_key_still_award_the_level():
    a, b = route("a"), route("b")
    consensus = earned_consensus(
        (a, b), {"a": {"v": 1.0}, "b": {"v": 1.0}},
        thresholds=dcc.DC_CONSENSUS_THRESHOLDS, tolerance_key="agreement_rel_tol",
        required=("v",),
    )
    assert consensus.threshold_authority_gap is None
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    assert consensus.to_check().outcome is ValidationOutcome.PASS
    assert CrossSolverConsensus.from_dict(consensus.to_dict()).establishes is (
        ValidationLevel.CROSS_SOLVER_VALIDATED
    )
