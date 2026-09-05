"""Core V0.2 — SRIA trust-layer invariants the mutation probe found unguarded.

Companion to ``test_core_v02_invariants.py``, which covers the Scientific Core
results package. This one covers the layer that decides what gets admitted,
what gets spent and what may stop a campaign.

Method and honesty note. The probe ran in two phases. Phase 1 mutated each
module and ran a hand-mapped subset of tests; phase 2 re-ran every phase-1
survivor against the **entire** suite, because a wrong mapping invents
findings that do not exist. That mattered: 19 of 88 phase-1 "survivors" were
killed by tests phase 1 had not pointed at. Only the 69 that survived the full
suite are treated as real, and only those are addressed here.

The 69 are not all equally dangerous, and this file does not chase the count.
Three classes were worth pinning, and the reason is given per class below.
What was deliberately left is recorded at the bottom of this docstring so the
omission is visible rather than silent.

Addressed here:

  frozen=True on 20 SRIA record types. Same systemic hole as the results
      package: nothing anywhere asserted these records cannot be edited after
      construction. A mutable AdmissionDeclaration or StopReview is a signed
      decision that can be rewritten after it was signed.

  Budget gates. `affordable` is the gate, and its `<=` boundary -- cost
      exactly equal to the remaining pool -- was never exercised, so
      `<=`->`<` survived. So did `is_overrun`'s threshold and `has_charge`'s
      `==`, which is what makes charging idempotent on resume.

  Stopping authority. The most serious finding in the probe:
      * `obligation_state.get(o, False)` -> `.get(o, True)` survived. An
        obligation with no recorded state would default to SATISFIED.
      * `if unassessed or unresolved` -> `and` survived. Existing tests cover
        the unassessed case only with no criterion registered, so the run
        stops at the "no criterion" branch and the mutation is invisible. With
        an approving criterion present it is not invisible at all: it lets a
        stop be approved over obligations the campaign never assessed.
      * `StopProposal.is_certification` returns a documented "always False"
        that nothing asserted.

Deliberately NOT addressed, and why:

  The `bool/Or` cluster in evidence.py (511-566) and admission.py (633, 638)
  is `payload.get(k) or default` in deserialization and `x.rationale or
  "<fallback>"` in message construction. Mutating these changes a default
  string or a falsy-vs-missing distinction that carries no scientific claim.
  Pinning them would be exactly the test-count theater this milestone was
  told not to produce. Recorded as retained debt instead.

  uncertainty_budget.py's surviving comparisons are real but sit on the
  combination path, which no production caller currently drives with
  quantified channels -- both domain solvers report UNKNOWN. Tests written
  against it now would pin behaviour no evidence has exercised.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.engcore.sria.assurance.assessment import CriticVerdict
from src.engcore.sria.decision.actions import ActionFamily
from src.engcore.sria.admission import (
    AdmissionAttempt,
    AdmissionDeclaration,
    DecisionBinding,
)
from src.engcore.sria.assurance.obligations import (
    ObligationSet,
    ValidationObligation,
)
from src.engcore.sria.assurance.uncertainty_budget import (
    AggregationRecord,
    ChannelEntry,
    UncertaintyBudget,
)
from src.engcore.sria.campaign.budget import BudgetCharge, BudgetLedger
from src.engcore.sria.campaign.checkpoint import CampaignCheckpoint, IterationPlan
from src.engcore.sria.campaign.stopping import (
    StoppingCriterion,
    StopProposal,
    StopReview,
    StopReviewOutcome,
)
from src.engcore.sria.evidence import Assessment, ClaimBinding, Evidence, LifecycleEvent

from tests.sria_m5_benchmark import build_assurance, critic_obligation
from tests.test_sria_m51_durability import CRITERION, ToyStoppingEvaluator, review_with


# =====================================================================
# 1. Records that carry a decision must not be editable after it
# =====================================================================

#: Every frozen record type in the trust layer. Asserted as a set so that a
#: new mutable record added here later has to fail this test to get in.
TRUST_RECORD_TYPES = (
    DecisionBinding,
    AdmissionDeclaration,
    AdmissionAttempt,
    ClaimBinding,
    Assessment,
    LifecycleEvent,
    Evidence,
    StoppingCriterion,
    StopProposal,
    StopReview,
    BudgetCharge,
    IterationPlan,
    CampaignCheckpoint,
    ValidationObligation,
    ObligationSet,
    ChannelEntry,
    AggregationRecord,
    UncertaintyBudget,
)


@pytest.mark.parametrize("record_type", TRUST_RECORD_TYPES)
def test_every_trust_record_type_is_frozen(record_type: type) -> None:
    """`frozen=True` removal survived on all of these.

    It is not stylistic here. A ``StopReview`` refuses at construction to be
    STOP_APPROVED without an Arbiter decision id; if the record were mutable,
    that check could be passed with a rejection and the outcome reassigned
    afterwards. The constructor guard is only as strong as the immutability
    behind it.
    """
    assert dataclasses.is_dataclass(record_type)
    assert record_type.__dataclass_params__.frozen, (
        f"{record_type.__name__} is mutable; a record carrying a decision "
        f"must not be editable after that decision was taken"
    )


def test_an_approved_stop_cannot_be_forged_by_reassignment() -> None:
    """The concrete forgery frozenness prevents, stated as the attack.

    Constructing STOP_APPROVED without an Arbiter decision raises. The route
    around that guard is to build a legal rejection and overwrite the outcome.
    """
    with pytest.raises(ValueError):
        StopReview(
            review_id="forged",
            proposal_id="p1",
            outcome=StopReviewOutcome.STOP_APPROVED,
            terminal_objective_available=True,
            criterion_id="c",
            reasons=("looks finished to me",),
        )

    rejected = StopReview(
        review_id="honest",
        proposal_id="p1",
        outcome=StopReviewOutcome.STOP_REJECTED,
        terminal_objective_available=True,
        reasons=("obligations outstanding",),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        rejected.outcome = StopReviewOutcome.STOP_APPROVED  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        rejected.arbiter_decision_id = "made-up"  # type: ignore[misc]
    assert rejected.outcome is StopReviewOutcome.STOP_REJECTED


def test_a_stop_proposal_is_never_a_certification() -> None:
    """`is_certification` is a documented constant `False` that nothing
    asserted, so flipping it to True went unnoticed. A proposal is the loop
    asking a question; if it could read as a certification, the question
    would answer itself."""
    proposal = StopProposal(
        proposal_id="p1", campaign_id="c1", run_id="r1", iteration=1,
    )
    assert proposal.is_certification is False


# =====================================================================
# 2. Budget — the gate, its boundary, and idempotent charging
# =====================================================================

def test_affordable_admits_a_cost_exactly_equal_to_the_pool() -> None:
    """The `<=` boundary. Nothing exercised spending the pool to exactly zero,
    so `<=`->`<` survived: a charge that exactly exhausts the budget would
    have been refused as unaffordable."""
    ledger = BudgetLedger(total_budget=10.0)
    assert ledger.affordable(10.0, family=ActionFamily.OPTIMIZE)
    assert not ledger.affordable(10.000001, family=ActionFamily.OPTIMIZE)


def test_only_validation_may_draw_on_the_validation_reservation() -> None:
    """The reservation exists so validation cannot be crowded out. If a
    non-VALIDATE family could reach it, the reservation would be decorative."""
    ledger = BudgetLedger(total_budget=10.0, reserved_validation_budget=4.0)
    # 6.0 general + 4.0 reserved.
    assert ledger.affordable(6.0, family=ActionFamily.OPTIMIZE)
    assert not ledger.affordable(6.5, family=ActionFamily.OPTIMIZE)
    assert ledger.affordable(10.0, family=ActionFamily.VALIDATE)
    assert not ledger.affordable(10.5, family=ActionFamily.VALIDATE)


def test_spending_exactly_the_budget_is_not_an_overrun() -> None:
    """`>` vs `>=` on the overrun threshold. Landing exactly on budget is
    compliance, not a breach, and an overrun must not be declared for it."""
    ledger = BudgetLedger(total_budget=10.0)
    ledger.settle(
        charge_id="c1", action_id="a1", iteration=1,
        family=ActionFamily.OPTIMIZE, realized=10.0,
    )
    assert ledger.spent_total == pytest.approx(10.0)
    assert not ledger.is_overrun
    assert ledger.overrun == pytest.approx(0.0)


def test_a_realized_overrun_is_recorded_rather_than_refused() -> None:
    """M5.1 fixed a defect where the ledger refused to record an overrun that
    had already happened. Cost incurred is a fact; a ledger that rejects it
    is lying about what was spent."""
    ledger = BudgetLedger(total_budget=10.0)
    ledger.settle(
        charge_id="c1", action_id="a1", iteration=1,
        family=ActionFamily.OPTIMIZE, realized=14.0,
    )
    assert ledger.is_overrun
    assert ledger.overrun == pytest.approx(4.0)


def test_charging_the_same_charge_id_twice_is_idempotent() -> None:
    """`has_charge`/settle match charge ids with `==`; mutating it to `!=`
    survived. This equality is what stops a resumed campaign paying twice for
    one action, so it is load-bearing for restore, not just bookkeeping."""
    ledger = BudgetLedger(total_budget=10.0)
    first = ledger.settle(
        charge_id="c1", action_id="a1", iteration=1,
        family=ActionFamily.OPTIMIZE, realized=3.0,
    )
    assert ledger.has_charge("c1")
    assert not ledger.has_charge("c2")

    second = ledger.settle(
        charge_id="c1", action_id="a1", iteration=1,
        family=ActionFamily.OPTIMIZE, realized=3.0,
    )
    assert second == first
    assert len(ledger.charges) == 1
    assert ledger.spent_total == pytest.approx(3.0)


def test_a_zero_cost_charge_is_legal() -> None:
    """`realized < 0.0` vs `<= 0.0`. A free or cached action costs zero and
    must still be recordable; rejecting it would push real actions out of the
    ledger to avoid an exception."""
    ledger = BudgetLedger(total_budget=10.0)
    ledger.settle(
        charge_id="c0", action_id="a0", iteration=1,
        family=ActionFamily.OPTIMIZE, realized=0.0,
    )
    assert ledger.has_charge("c0")
    assert ledger.spent_total == pytest.approx(0.0)


def test_a_negative_cost_is_refused() -> None:
    ledger = BudgetLedger(total_budget=10.0)
    with pytest.raises(ValueError, match="non-negative"):
        ledger.settle(
            charge_id="cneg", action_id="a", iteration=1,
            family=ActionFamily.OPTIMIZE, realized=-1.0,
        )


def test_the_reservation_may_equal_but_not_exceed_the_total() -> None:
    """`>` vs `>=` on the reservation check. Reserving the whole budget for
    validation is a legal, if extreme, declaration; reserving more than exists
    is incoherent."""
    BudgetLedger(total_budget=10.0, reserved_validation_budget=10.0)
    with pytest.raises(ValueError, match="exceeds the total budget"):
        BudgetLedger(total_budget=10.0, reserved_validation_budget=10.5)


def test_an_enforced_cap_must_name_what_enforces_it() -> None:
    """A cap nobody enforces is a declaration wearing a stronger word, and the
    ledger's guarantee statement must not claim otherwise."""
    with pytest.raises(ValueError):
        BudgetLedger(total_budget=10.0, enforced_cap=5.0)
    with pytest.raises(ValueError, match="non-negative"):
        BudgetLedger(
            total_budget=10.0, enforced_cap=-1.0, enforced_cap_source="executor",
        )

    declared_only = BudgetLedger(total_budget=10.0)
    assert "no executor-enforced resource cap exists" in (
        declared_only.guarantee_statement
    )
    enforced = BudgetLedger(
        total_budget=10.0, enforced_cap=5.0, enforced_cap_source="slurm",
    )
    assert "executor-enforced cap" in enforced.guarantee_statement


# =====================================================================
# 3. Stopping authority — the probe's most serious finding
# =====================================================================

def test_an_unassessed_obligation_is_not_treated_as_satisfied() -> None:
    """`obligation_state.get(o, False)` -> `.get(o, True)` survived.

    Defaulting a missing obligation to satisfied is the same class of error
    the whole assurance layer exists to prevent: silence read as a pass.
    """
    _gateway, arbiter, _admission = build_assurance()
    review = review_with(arbiter, obligation_state={})
    declared = tuple(
        o.obligation_id for o in critic_obligation().obligations
    )
    assert declared, "the fixture must declare at least one obligation"
    assert review.unmet_obligations == declared
    assert review.outcome is not StopReviewOutcome.STOP_APPROVED


def test_unassessed_obligations_block_a_stop_an_approving_criterion_would_grant(
) -> None:
    """The hole that made `if unassessed or unresolved` -> `and` invisible.

    The existing coverage of the unassessed path registers no stopping
    criterion, so the review returns NOT_ASSESSED at the later "no criterion"
    branch whichever way the operator points. Supplying a criterion whose
    evaluator PASSES separates the two: with `or` the stop is refused because
    checks were never run; with `and` it is approved over them.
    """
    _gateway, arbiter, _admission = build_assurance()
    approving = {
        CRITERION.criterion_id: ToyStoppingEvaluator(
            CRITERION.criterion_id, CriticVerdict.PASS,
        )
    }

    # Control: with obligations assessed, this exact setup DOES approve.
    approved = review_with(
        arbiter, review_id="control",
        criteria=(CRITERION,), evaluators=approving,
    )
    assert approved.outcome is StopReviewOutcome.STOP_APPROVED

    # The same approving criterion must not carry a stop over checks that
    # were never run.
    withheld = review_with(
        arbiter, review_id="unassessed",
        obligation_state={},
        criteria=(CRITERION,), evaluators=approving,
    )
    assert withheld.outcome is not StopReviewOutcome.STOP_APPROVED
    assert withheld.arbiter_decision_id == ""
    assert any("never ran" in r or "never assessed" in r
               for r in withheld.reasons)


def test_unresolved_assessments_block_a_stop_the_criterion_would_grant() -> None:
    """The other half of the same `or`: a mandatory assessment left unresolved
    must withhold approval even when the criterion is satisfied."""
    _gateway, arbiter, _admission = build_assurance()
    approving = {
        CRITERION.criterion_id: ToyStoppingEvaluator(
            CRITERION.criterion_id, CriticVerdict.PASS,
        )
    }
    withheld = review_with(
        arbiter, review_id="unresolved",
        criteria=(CRITERION,), evaluators=approving,
        unresolved_assessments=("critic:numerical:pending",),
    )
    assert withheld.outcome is not StopReviewOutcome.STOP_APPROVED
    assert any("unresolved" in r for r in withheld.reasons)


def test_an_approved_stop_always_names_the_authority_behind_it() -> None:
    """Approval must be traceable to an Arbiter decision and a named
    criterion. Without both, 'approved' is an opinion."""
    _gateway, arbiter, _admission = build_assurance()
    approved = review_with(
        arbiter, review_id="traceable",
        criteria=(CRITERION,),
        evaluators={
            CRITERION.criterion_id: ToyStoppingEvaluator(
                CRITERION.criterion_id, CriticVerdict.PASS,
            )
        },
    )
    assert approved.outcome is StopReviewOutcome.STOP_APPROVED
    assert approved.arbiter_decision_id
    assert approved.criterion_id == CRITERION.criterion_id
    assert approved.is_certification is False
