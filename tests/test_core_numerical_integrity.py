"""Invalid numbers must never buy stronger scientific evidence than valid ones.

THE THREE DEFECTS THIS CLOSES
-----------------------------
All three are the same mistake wearing different clothes: a comparison was
asked to detect a value that defeats comparison.

**A threshold set could be edited after construction.** ``VerificationThresholds``
is ``frozen=True``, which protects the attribute and not the mapping behind it,
so ``thresholds.values["rel_tol"] = 1e9`` was accepted on the one record whose
whole purpose is to be the number a gate cannot be talked out of. It moved
``fingerprint`` -- so the evidence line in a report described numbers the gate
had not been judged against -- and it left ``derived_from`` empty, so ``award``
went on granting the level ``derive`` exists to withhold.

**Non-finite route values were recorded as exact agreement.**
``relative_difference`` returns NaN for every non-finite pairing, the worst-case
accumulator advances on ``difference > worst``, and ``nan > 0.0`` is False. So
the reading was not mishandled, it was *skipped*: ``worst`` stayed 0.0 and
``CROSS_SOLVER_VALIDATED`` was awarded. Two routes that both diverged to
infinity agreed to zero. So did NaN against a finite partner.

**A malformed tolerance disabled a gate silently.**
``abs(actual - expected) > atol + rtol * abs(expected)`` is False for every pair
of operands when either tolerance is NaN, and the operands themselves are
perfectly finite, so the finiteness check that already existed passed.

WHY THESE ARE ONE MODULE
------------------------
Because the fix is one rule -- **finiteness and well-formedness first, then
comparison** -- and because a reader who finds one of these wants to know the
other two were looked for. The rule is applied at the point where a number
becomes evidence, never afterwards.
"""

from __future__ import annotations

import json
import math

import pytest

from engcore.scientific.consensus import (
    ComponentKind,
    CrossSolverConsensus,
    IndependenceVerdict,
    SharedComponent,
    SolveRoute,
)
from engcore.scientific.errors import (
    ScientificCoreError,
    ScientificValidationError,
)
from engcore.scientific.results.thresholds import VerificationThresholds
from engcore.scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
)
from engcore.scientific.serialization import to_json
from engcore.scientific.solvers.admission import require_agreement
from engcore.scientific.solvers.protocol import SolverIdentity

NON_FINITE = (float("nan"), float("inf"), float("-inf"))


def _thresholds(**values: float) -> VerificationThresholds:
    return VerificationThresholds(
        gate_id="test.gate",
        version="1",
        values=values or {"rel_tol": 1e-6},
        basis="declared for this test",
    )


def _route(route_id: str, component: str) -> SolveRoute:
    return SolveRoute(
        route_id=route_id,
        solver=SolverIdentity(solver_id=route_id, version="1"),
        components=frozenset(
            {SharedComponent(kind=ComponentKind.IMPLEMENTATION, name=component)}
        ),
    )


def _consensus(values, *, tolerance: float = 1e-6) -> CrossSolverConsensus:
    """A consensus whose OUTPUT CONTRACT is satisfied, so finiteness is on trial.

    ``required_outputs`` is the set every route reported. That is deliberate
    here and is the point of the fixture: a consensus that declares nothing
    earns nothing for a completeness reason, which would make every refusal in
    this module pass for the wrong reason and prove nothing about non-finite
    values.
    """
    routes = [_route(name, f"impl-{name}") for name in sorted(values)]
    common: set[str] | None = None
    for produced in values.values():
        common = set(produced) if common is None else common & set(produced)
    return CrossSolverConsensus.over(
        consensus_id="test-consensus",
        routes=routes,
        values=values,
        thresholds=_thresholds(rel_tol=tolerance),
        tolerance_key="rel_tol",
        required_outputs=tuple(sorted(common or ())),
    )


# ===================================================================== B1


def test_threshold_values_cannot_be_mutated_through_the_mapping():
    """Every ordinary way of writing to a dict, refused.

    Enumerated rather than sampled: the guarantee is about the *container*, and
    a caller who found `update` working after `__setitem__` raised would have
    the whole defect back through a different name.
    """
    thresholds = _thresholds(rel_tol=1e-9, abs_tol=1e-12)

    with pytest.raises(TypeError):
        thresholds.values["rel_tol"] = 1e9
    with pytest.raises(TypeError):
        thresholds.values.update({"rel_tol": 1e9})
    with pytest.raises(TypeError):
        thresholds.values.pop("rel_tol")
    with pytest.raises(TypeError):
        thresholds.values.popitem()
    with pytest.raises(TypeError):
        thresholds.values.clear()
    with pytest.raises(TypeError):
        thresholds.values.setdefault("new_tol", 1.0)
    with pytest.raises(TypeError):
        del thresholds.values["rel_tol"]
    with pytest.raises(TypeError):
        thresholds.values |= {"rel_tol": 1e9}

    assert thresholds.values == {"abs_tol": 1e-12, "rel_tol": 1e-9}


def test_a_mutated_threshold_cannot_move_the_fingerprint_or_keep_the_award():
    """The two consequences the mutation actually had, asserted as consequences.

    A test that only checked `values` would pass over a future record that
    exposed the numbers somewhere else. These are the two things the numbers
    are FOR: the identity a report cites, and the claim a gate is allowed to
    make.
    """
    thresholds = _thresholds(rel_tol=1e-9)
    before_fingerprint = thresholds.fingerprint
    before_evidence = thresholds.evidence()

    with pytest.raises(TypeError):
        thresholds.values["rel_tol"] = 1e9

    assert thresholds.fingerprint == before_fingerprint
    assert thresholds.evidence() == before_evidence
    assert thresholds["rel_tol"] == 1e-9
    assert thresholds.is_declared is True
    assert (
        thresholds.award(ValidationLevel.CROSS_SOLVER_VALIDATED, earned=True)
        is ValidationLevel.CROSS_SOLVER_VALIDATED
    )


def test_the_sanctioned_override_path_still_works_and_still_withholds():
    """Immutability must not have closed `derive`, which is the legitimate door.

    The point was never to forbid exploring a tighter tolerance. It was to make
    exploration say so in the record. That distinction survives the freeze.
    """
    declared = _thresholds(rel_tol=1e-9)
    override = declared.derive(rel_tol=1e-3)

    assert override is not declared
    assert declared.values["rel_tol"] == 1e-9, "derive mutated its source"
    assert override.values["rel_tol"] == 1e-3
    assert override.is_declared is False
    assert override.derived_from == declared.identity
    assert (
        override.award(ValidationLevel.CROSS_SOLVER_VALIDATED, earned=True)
        is None
    )

    # A derive that changes nothing is still the declared set, and still awards.
    assert declared.derive(rel_tol=1e-9) is declared


def test_a_detached_payload_is_still_the_callers_to_edit():
    """Freezing internal state must not freeze the payload.

    `to_dict` returns a message, and messages are supposed to be editable. The
    record is the thing that must not move.
    """
    thresholds = _thresholds(rel_tol=1e-9)
    payload = thresholds.to_dict()

    payload["values"]["rel_tol"] = 123.0
    payload["values"]["invented"] = 456.0
    assert thresholds.values == {"rel_tol": 1e-9}

    restored = VerificationThresholds.from_dict(thresholds.to_dict())
    assert restored == thresholds
    assert restored.fingerprint == thresholds.fingerprint


def test_threshold_serialization_stays_deterministic_and_json_clean():
    """A frozen mapping still serializes as the dict it replaced."""
    thresholds = _thresholds(rel_tol=1e-9, abs_tol=1e-12, zeta=0.5)
    once = to_json(thresholds)
    twice = to_json(VerificationThresholds.from_dict(json.loads(once)))
    assert once == twice
    assert json.loads(once)["values"] == {
        "abs_tol": 1e-12, "rel_tol": 1e-9, "zeta": 0.5,
    }
    # Key order in the record is sorted, so two sets built in different orders
    # produce the same bytes and the same fingerprint.
    assert (
        _thresholds(b=2.0, a=1.0).fingerprint
        == _thresholds(a=1.0, b=2.0).fingerprint
    )


def test_a_non_finite_threshold_is_still_refused_at_construction():
    """The guard that already existed, kept exercised beside the new one."""
    for bad in NON_FINITE:
        with pytest.raises(ScientificValidationError):
            _thresholds(rel_tol=bad)


# ===================================================================== B2


@pytest.mark.parametrize(
    "left,right",
    [
        (300.0, float("nan")),
        (float("nan"), float("nan")),
        (float("inf"), float("inf")),
        (float("inf"), 300.0),
        (float("-inf"), 300.0),
        (float("-inf"), float("inf")),
        (float("nan"), float("inf")),
    ],
)
def test_a_non_finite_route_value_never_produces_agreement(left, right):
    """The whole defect, over every pairing that reaches it.

    Each of these produced `agreed=True`, `worst=0.0` and
    `CROSS_SOLVER_VALIDATED` before the fix -- not because the comparison was
    lenient, but because the accumulator skipped the value entirely.
    """
    consensus = _consensus({"A": {"t": left}, "B": {"t": right}})

    assert consensus.routes_are_independent is True, (
        "the routes must be independent, or this would be refused for the "
        "wrong reason and prove nothing about finiteness"
    )
    assert consensus.comparison.agreed is False
    assert consensus.comparison.compared_anything is False
    assert consensus.comparison.worst_relative_difference is None
    assert consensus.establishes is None
    assert consensus.earned is False
    assert "non-finite" in consensus.comparison.detail


def test_the_refusal_names_the_route_and_the_quantity():
    """A refusal a reader cannot act on is only half a refusal."""
    consensus = _consensus(
        {"A": {"t": 300.0, "p": float("nan")}, "B": {"t": 300.0, "p": 2.0}}
    )
    assert consensus.establishes is None
    detail = consensus.comparison.detail
    assert "A.p" in detail
    assert "nan" in detail.lower()


def test_a_non_finite_value_outside_the_compared_set_still_refuses():
    """A route that did not finish corroborates nothing, including in part.

    `q` is reported by one route only, so it is not in the compared
    intersection and the old code would never have looked at it. But a route
    that produced a NaN anywhere did not finish, and crediting its OTHER
    numbers as independent confirmation would let a failed run corroborate a
    successful one.
    """
    consensus = _consensus(
        {"A": {"t": 300.0, "q": float("inf")}, "B": {"t": 300.0}}
    )
    assert consensus.establishes is None
    assert consensus.comparison.compared_anything is False
    assert "A.q" in consensus.comparison.detail


def test_a_non_finite_route_reports_not_run_rather_than_pass_or_fail():
    """The check a report carries says nothing was compared.

    NOT_RUN rather than FAIL: the routes did not disagree, they failed to
    produce comparable numbers, and recording that as a disagreement would
    claim a finding nobody made.
    """
    check = _consensus({"A": {"t": float("nan")}, "B": {"t": 300.0}}).to_check()
    assert check.outcome is ValidationOutcome.NOT_RUN
    assert check.establishes is None
    assert check.residual is None


def test_finite_routes_that_agree_still_earn_the_level():
    """The fix must not have closed the door it was guarding.

    A refusal that also refuses the legitimate case is not a guard, it is a
    breakage, and it would be invisible in a suite that only tested the
    refusals.
    """
    consensus = _consensus({"A": {"t": 300.0}, "B": {"t": 300.0 * (1 + 1e-9)}})
    assert consensus.comparison.compared_anything is True
    assert consensus.comparison.agreed is True
    assert consensus.independence is IndependenceVerdict.INDEPENDENT
    assert consensus.establishes is ValidationLevel.CROSS_SOLVER_VALIDATED
    assert consensus.to_check().outcome is ValidationOutcome.PASS


def test_finite_routes_that_disagree_still_fail_rather_than_go_quiet():
    """The other legitimate outcome, kept distinct from the refusal above."""
    consensus = _consensus({"A": {"t": 300.0}, "B": {"t": 450.0}})
    assert consensus.comparison.compared_anything is True
    assert consensus.comparison.agreed is False
    assert consensus.establishes is None
    assert consensus.to_check().outcome is ValidationOutcome.FAIL


def test_a_serialized_consensus_over_non_finite_values_round_trips():
    """The record of a refusal is itself a record, and must survive.

    `from_dict` re-derives `establishes` and refuses a payload asserting a
    level its contents do not produce, so this also checks the refusal is
    reproduced on the way back in rather than being a property of the object
    that happened to be in memory.
    """
    consensus = _consensus({"A": {"t": float("nan")}, "B": {"t": 300.0}})
    payload = json.loads(to_json(consensus))
    assert payload["establishes"] is None
    restored = CrossSolverConsensus.from_dict(payload)
    assert restored.establishes is None
    assert restored.comparison.compared_anything is False


# ===================================================================== B3


@pytest.mark.parametrize("bad", NON_FINITE + (-1.0, -1e-30))
@pytest.mark.parametrize("which", ["atol", "rtol"])
def test_a_malformed_tolerance_is_refused_before_the_comparison(which, bad):
    """A bound that is not a bound cannot be used to admit anything.

    The operands here AGREE exactly, so nothing about this pair would raise on
    its own: what is being asserted is that the malformed bound is rejected on
    its own account, before it gets the chance to disable the comparison.
    """
    tolerances = {"atol": 0.0, "rtol": 0.0}
    tolerances[which] = bad
    with pytest.raises(ScientificCoreError) as raised:
        require_agreement(
            actual=1.0,
            expected=1.0,
            error=ScientificCoreError,
            detail="probe",
            **tolerances,
        )
    assert which in str(raised.value)


@pytest.mark.parametrize("which", ["atol", "rtol"])
@pytest.mark.parametrize("bad", NON_FINITE)
def test_a_non_finite_tolerance_cannot_admit_a_real_disagreement(which, bad):
    """The consequence, stated as the consequence.

    1 against 1000 is a disagreement by any standard. Before the fix a NaN
    tolerance admitted it silently -- the gate ran, compared, and said nothing.
    """
    tolerances = {"atol": 0.0, "rtol": 0.0}
    tolerances[which] = bad
    with pytest.raises(ScientificCoreError):
        require_agreement(
            actual=1.0,
            expected=1000.0,
            error=ScientificCoreError,
            detail="a disagreement that must not be admitted",
            **tolerances,
        )


def test_well_formed_tolerances_still_admit_and_still_refuse():
    """Both directions of the gate, so the check above is not vacuous."""
    require_agreement(
        actual=1.0, expected=1.0, atol=0.0, rtol=0.0,
        error=ScientificCoreError, detail="exactly equal",
    )
    require_agreement(
        actual=1.0 + 1e-9, expected=1.0, atol=0.0, rtol=1e-6,
        error=ScientificCoreError, detail="inside a relative bound",
    )
    require_agreement(
        actual=1.5, expected=1.0, atol=1.0, rtol=0.0,
        error=ScientificCoreError, detail="inside an absolute bound",
    )
    with pytest.raises(ScientificCoreError):
        require_agreement(
            actual=1.0, expected=1000.0, atol=0.0, rtol=1e-6,
            error=ScientificCoreError, detail="a real disagreement",
        )


def test_a_non_finite_operand_is_still_refused_after_the_bound_is_checked():
    """The pre-existing guard, kept exercised beside the new one.

    Ordering matters here and is asserted by the fact that both refusals are
    reachable: a well-formed bound with a NaN operand must still raise.
    """
    with pytest.raises(ScientificCoreError):
        require_agreement(
            actual=float("nan"), expected=1.0, atol=0.0, rtol=1e-6,
            error=ScientificCoreError, detail="non-finite actual",
        )
    with pytest.raises(ScientificCoreError):
        require_agreement(
            actual=1.0, expected=1.0, atol=0.0, rtol=1e-6,
            operands={"derived_from": float("inf")},
            error=ScientificCoreError, detail="non-finite operand",
        )


def test_the_arithmetic_this_all_rests_on_is_what_we_think_it_is():
    """The interpreter facts behind every guard above, asserted once.

    If any of these ever stopped being true, the guards would still pass while
    protecting against nothing. Cheap, and it makes the reasoning falsifiable
    rather than asserted in a comment.
    """
    nan = float("nan")
    assert not (nan > 0.0)
    assert not (abs(nan - 5.0) > 1e-6)
    assert math.isnan(abs(float("inf") - float("inf")))
    assert not (999.0 > (nan + 0.0 * 1000.0))
    assert 999.0 < float("inf")
