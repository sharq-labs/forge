"""E3 orchestration: two worlds, six controls, seven injections.

THE SHAPE OF ONE WORLD
----------------------
    Phase 0  calibration, through the real M1/M3 admission chain, until the
             conditional posterior is sharp and parameter EVSI has collapsed.

    Phase 1  a real CampaignRunner scores every candidate — parameter action
             AND every adequacy probe, same engine, same price — finds nothing
             worth buying, proposes a stop, and the Arbiter-owned review is
             asked whether stopping is scientifically justified.

    Phase 2  the obligation policy acquires the finite required evidence that
             the review says is missing. Predictives are committed and sealed
             BEFORE any probe executes.

    Phase 3  a second real CampaignRunner re-reviews. Same criterion, same
             evaluator, same Arbiter, updated obligation state.

Phase 2 is the adapter, and the only one. The runner has no branch that reads
a non-approving stop review and routes to the evidence that would resolve it;
whatever the review says, ``_propose_stop`` pauses. E3 says that plainly rather
than describing the result as "the campaign acquired the evidence".

AND THAT BOUNDS THE VERDICT
---------------------------
The obligation policy itself works: every success check passes. But "the policy
works" and "the campaign supports the policy" are different claims, and only
the first was demonstrated. So the verdict is computed from two groups —
``success_checks`` (what E3 established) and ``campaign_native_checks`` (what
the frozen stack did unaided) — and the second group is *measured*, by asking
whether any CampaignRunner pass ever executed an adequacy probe. None did.
E3 is therefore PARTIALLY VERIFIED, and that follows from the run rather than
from an editorial decision about how to describe it.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import numpy as np

from src.engcore.sria.campaign import CampaignEventType
from src.engcore.sria.campaign.stopping import StopReview, StopReviewOutcome
from src.engcore.sria.decision.actions import ActionFamily

from experiments.electrical_e2 import e2_truth
from experiments.electrical_e2.e2_adequacy import (
    AdequacyState,
    CommitmentLedger,
    ExecutionValidity,
    PredictiveCommitmentViolation,
    aggregate_adequacy,
    build_joint_predictive,
    classify_adequacy,
    score_commitments,
)
from experiments.electrical_e2.e2_model import (
    evsi,
    posterior_summary,
    posterior_weights,
    predictive_mixture,
    prior_weights,
)

from .e3_config import (
    ADEQUACY_OBLIGATION,
    ADEQUACY_RESERVE,
    BUDGET_POLICY_RESERVED,
    BUDGET_POLICY_SHARED,
    CANDIDATE_ACTIONS,
    CONTROL_PARAMETER_SPEND,
    OBLIGATION_PLACEMENT_STATEMENT,
    TOTAL_BUDGET,
    config_hash,
    config_payload,
    preregistration_hash,
)
from .e3_harness import (
    ACTION_BY_ID,
    E3Stack,
    build_e3_stack,
    family_for,
    run_calibration,
    swap_to_faulty_executor,
)
from .e3_obligation import (
    AdequacyScope,
    Certification,
    Disposition,
    ObligationBindingError,
    ObligationLedger,
    ObligationStatus,
    certify_campaign,
    scope_from_e2_state,
)

EXECUTION_REASON_OBLIGATION = "SATISFY_ADEQUACY_OBLIGATION"


# =====================================================================
# The obligation policy — the documented adapter
# =====================================================================

def _review_summary(review: StopReview | None) -> dict[str, Any]:
    if review is None:
        return {"outcome": None}
    return {
        "outcome": review.outcome.value,
        "criterion_id": review.criterion_id,
        "arbiter_verdict": review.arbiter_verdict,
        "arbiter_decision_id": review.arbiter_decision_id,
        "unmet_obligations": list(review.unmet_obligations),
        "reasons": list(review.reasons),
        "is_certification": review.is_certification,
        "approves": review.approves,
    }


def run_stop_phase(
    stack: E3Stack,
    *,
    run_id: str,
    with_adequacy_criterion: bool,
    budget,
) -> dict[str, Any]:
    """One real CampaignRunner pass: score, propose, review."""
    runner = stack.build_runner(
        run_id=run_id,
        with_adequacy_criterion=with_adequacy_criterion,
        budget=budget,
    )
    runner.run_campaign()
    review = runner.stop_reviews[-1] if runner.stop_reviews else None
    scores: list[dict[str, Any]] = []
    rec_id = runner.run.stop_proposal_recommendation_id
    if rec_id:
        recommendation = runner.recommendation(rec_id)
        if recommendation is not None:
            for score in sorted(recommendation.scores, key=lambda s: s.action_id):
                spec = ACTION_BY_ID[score.action_id]
                gain = score.component("conditional_success_utility_gain")
                cost = score.component("expected_cost")
                scores.append(
                    {
                        "action_id": score.action_id,
                        "phase": spec.phase,
                        "action_family": family_for(spec).value,
                        "parameter_evsi": gain.value if gain else None,
                        "cost": cost.value if cost else None,
                        "net_parameter_value": score.total,
                    }
                )
    return {
        "run_id": run_id,
        "with_adequacy_criterion": with_adequacy_criterion,
        "state": runner.run.state.value,
        "pause_reason": (
            runner.run.pause_reason.value if runner.run.pause_reason else None
        ),
        "stop_review_outcome": runner.run.stop_review_outcome,
        "stop_review": _review_summary(review),
        "scores": scores,
        "executed_actions": list(stack.harness.executor_impl.calls),
        "budget": {
            "total": runner.budget.total_budget,
            "reserved_validation": runner.budget.reserved_validation_budget,
            "general_pool": runner.budget.general_pool,
            "validation_pool": runner.budget.validation_pool,
        },
        "_runner": runner,
        "_review": review,
    }


def acquire_adequacy_evidence(
    stack: E3Stack,
    *,
    budget,
    label: str,
) -> dict[str, Any]:
    """Phase 2 — the adapter. Commit, seal, then execute what is required.

    Selection is by the frozen constraint rule (cheapest outstanding REQUIRED
    probe, declared order for ties). Affordability is decided by the frozen
    ``BudgetLedger.affordable(cost, family=VALIDATE)``, so even the adapter
    defers to the repository's accounting rather than inventing its own.
    """
    ledger = stack.obligation_state.ledger
    commitments = CommitmentLedger(f"{label}-commitments")

    # Predictives for every REQUIRED condition, from the calibration-only
    # evidence state, committed and sealed BEFORE anything is executed.
    observations = stack.harness.current_observations()
    weights = posterior_weights(observations)
    snapshot_digest = stack.harness.e2.evidence_snapshot_digest()
    for action_id in ledger.required:
        spec = ACTION_BY_ID[action_id]
        commitments.commit(
            action_id=action_id,
            source_voltage_volt=spec.source_voltage_volt,
            noise_sigma_volt=spec.noise_sigma_volt,
            evidence_snapshot_digest=snapshot_digest,
            n_observations=len(observations),
            mixture=predictive_mixture(weights, spec),
        )
    commitments.seal()

    executed: list[dict[str, Any]] = []
    while True:
        action_id = ledger.next_probe(
            affordable=lambda cost: budget.affordable(
                cost, family=ActionFamily.VALIDATE
            )
        )
        if action_id is None:
            outstanding = ledger.outstanding_required()
            if outstanding:
                ledger.mark_budget_infeasible(
                    f"outstanding {list(outstanding)} needs "
                    f"{ledger.remaining_required_cost()} but the validation "
                    f"pool holds {budget.validation_pool} and the general pool "
                    f"{budget.general_pool}"
                )
            break
        spec = ACTION_BY_ID[action_id]
        row = stack.e2.run_measurement(spec, repeat=1)
        budget.settle(
            charge_id=f"{label}-{action_id}",
            action_id=action_id,
            iteration=0,
            family=ActionFamily.VALIDATE,
            realized=spec.cost,
            predicted=spec.cost,
            detail=EXECUTION_REASON_OBLIGATION,
        )
        commitment = commitments.commitments[action_id]
        if row.admitted:
            commitments.record_observation(
                action_id=action_id,
                y_volt=row.y_volt,
                execution_id=row.execution_id,
                execution_valid=True,
            )
        ledger.record_probe(
            action_id=action_id,
            source_voltage_volt=spec.source_voltage_volt,
            execution_id=row.execution_id,
            execution_valid=row.execution_validity is ExecutionValidity.VALID,
            admitted=row.admitted,
            commitment_artifact_hash=commitment.artifact_hash,
            realized_cost=spec.cost,
            execution_reason=EXECUTION_REASON_OBLIGATION,
        )
        executed.append(
            {
                "action_id": action_id,
                "source_voltage_volt": spec.source_voltage_volt,
                "y_volt": row.y_volt,
                "critic_verdict": row.critic_verdict,
                "arbiter_verdict": row.arbiter_verdict,
                "admitted": row.admitted,
                "execution_validity": row.execution_validity.value,
                "commitment_artifact_hash": commitment.artifact_hash,
                "parameter_evsi_at_selection": evsi(weights, spec),
                "execution_reason": EXECUTION_REASON_OBLIGATION,
                "why_action_executed": (
                    "selected by the obligation's constraint rule as the "
                    "cheapest outstanding REQUIRED probe; its parameter EVSI "
                    "is at the floor and played no part in the selection"
                ),
            }
        )
        if ledger.status is ObligationStatus.UNRESOLVED_EXECUTION_FAILURE:
            break

    # --- score whatever was validly acquired --------------------------
    adequacy: dict[str, Any] = {"scored": False}
    scope = AdequacyScope.NOT_ESTABLISHED
    if commitments.observations and ledger.status is ObligationStatus.COMPLETED:
        surprises = score_commitments(commitments)
        joint = build_joint_predictive(
            commitments, [s.action_id for s in surprises]
        )
        aggregate = aggregate_adequacy(surprises, joint)
        verdict = classify_adequacy(surprises, aggregate)
        scope = scope_from_e2_state(verdict.state)
        adequacy = {
            "scored": True,
            "e2_state": verdict.state.value,
            "rationale": verdict.rationale,
            "aggregate": aggregate.to_dict(),
            "surprises": [s.to_dict() for s in surprises],
        }
    elif ledger.status is ObligationStatus.UNRESOLVED_EXECUTION_FAILURE:
        scope = AdequacyScope.NOT_ASSESSED
        adequacy = {
            "scored": False,
            "reason": (
                "a required probe did not execute validly; no adequacy "
                "judgement may be drawn from evidence that does not exist"
            ),
        }
    else:
        adequacy = {
            "scored": False,
            "reason": (
                "the required evidence set is incomplete, so the preregistered "
                "adequacy rule was not evaluated"
            ),
        }

    stack.obligation_state.adequacy_scope = scope
    stack.obligation_state.adequacy_detail = str(adequacy.get("rationale", ""))
    stack.obligation_state.execution_validity = (
        ExecutionValidity.VALID
        if all(r.execution_valid for r in ledger.records)
        else ExecutionValidity.INVALID
    )
    return {
        "executed": executed,
        "obligation": ledger.to_dict(),
        "adequacy": adequacy,
        "adequacy_scope": scope.value,
        "commitment_ledger": {
            "head": commitments.head_digest,
            "sealed_at": commitments.sealed_at_sequence,
            "chain_verified": commitments.verify_chain()
            and commitments.verify_commitments(),
            "commitments": [
                commitments.commitments[a].summary() for a in ledger.required
            ],
        },
        "_commitments": commitments,
    }


# =====================================================================
# One complete world
# =====================================================================

def run_world(
    spec: e2_truth.TruthSpec,
    *,
    label: str,
    budget_policy: str = BUDGET_POLICY_RESERVED,
    total_budget: float = TOTAL_BUDGET,
    pre_spend_general: float = 0.0,
    faulty_probes: bool = False,
) -> dict[str, Any]:
    """Phase 0 -> 1 -> 2 -> 3 for one hidden world."""
    stack = build_e3_stack(spec, label=label)
    calibration = run_calibration(stack)

    observations = stack.harness.current_observations()
    weights = posterior_weights(observations)
    reserved = ADEQUACY_RESERVE if budget_policy == BUDGET_POLICY_RESERVED else 0.0
    budget = stack.budget_ledger(total=total_budget, reserved=reserved)

    if pre_spend_general > 0.0:
        # A campaign that spent its general pool on parameter learning before
        # the obligation came due. Charged as CHARACTERIZE, which is what it is.
        budget.settle(
            charge_id=f"{label}-prespend",
            action_id="parameter_repeat_10V",
            iteration=0,
            family=ActionFamily.CHARACTERIZE,
            realized=pre_spend_general,
            predicted=pre_spend_general,
            detail="preregistered parameter-learning spend (budget control)",
        )

    before = {
        "posterior": posterior_summary(weights),
        "evsi_table": {
            a.action_id: {
                "parameter_evsi": evsi(weights, a),
                "cost": a.cost,
                "net": evsi(weights, a) - a.cost,
                "action_family": family_for(a).value,
                "phase": a.phase,
            }
            for a in CANDIDATE_ACTIONS
        },
        "obligation_status": stack.obligation_state.ledger.status.value,
        "adequacy_scope": stack.obligation_state.adequacy_scope.value,
    }

    # ---- Phase 1: the economic stop, reviewed ------------------------
    evsi_only = run_stop_phase(
        stack,
        run_id=f"{label}-evsi-only",
        with_adequacy_criterion=False,
        budget=stack.budget_ledger(total=total_budget, reserved=reserved),
    )
    obligation_aware = run_stop_phase(
        stack,
        run_id=f"{label}-obligation-pre",
        with_adequacy_criterion=True,
        budget=budget,
    )

    # ---- Phase 2: the adapter ----------------------------------------
    if faulty_probes:
        swap_to_faulty_executor(stack)
    acquisition = acquire_adequacy_evidence(stack, budget=budget, label=label)

    # ---- Phase 3: re-review, same criterion, fresh runner ------------
    after_weights = posterior_weights(stack.harness.current_observations())
    obligation_post = run_stop_phase(
        stack,
        run_id=f"{label}-obligation-post",
        with_adequacy_criterion=True,
        budget=budget,
    )

    ledger = stack.obligation_state.ledger
    certification = certify_campaign(
        str(posterior_summary(after_weights)["bayes_decision"]),
        ledger.status,
        stack.obligation_state.adequacy_scope,
        stack.obligation_state.execution_validity,
    )

    return {
        "label": label,
        "truth_spec_id": spec.spec_id,
        "budget_policy": budget_policy,
        "calibration": {
            "n_admitted": sum(1 for r in calibration if r.admitted),
            "rows": [r.to_dict() for r in calibration],
        },
        "before_adequacy": before,
        "evsi_only_phase": {
            k: v for k, v in evsi_only.items() if not k.startswith("_")
        },
        "obligation_aware_pre": {
            k: v for k, v in obligation_aware.items() if not k.startswith("_")
        },
        "acquisition": {
            k: v for k, v in acquisition.items() if not k.startswith("_")
        },
        "obligation_aware_post": {
            k: v for k, v in obligation_post.items() if not k.startswith("_")
        },
        "posterior_after_adequacy": posterior_summary(after_weights),
        "evsi_after_adequacy": {
            a.action_id: evsi(after_weights, a) for a in CANDIDATE_ACTIONS
        },
        "obligation_status": ledger.status.value,
        "adequacy_scope": stack.obligation_state.adequacy_scope.value,
        "certification": certification.to_dict(),
        "budget_final": {
            "total": budget.total_budget,
            "reserved_validation": budget.reserved_validation_budget,
            "spent_total": budget.spent_total,
            "spent_validation": budget.spent_validation,
            "spent_general": budget.spent_general,
            "validation_pool": budget.validation_pool,
            "general_pool": budget.general_pool,
        },
        "_stack": stack,
        "_acquisition": acquisition,
        "_weights_before": weights,
        "_weights_after": after_weights,
        "_evsi_only": evsi_only,
        "_obligation_pre": obligation_aware,
        "_obligation_post": obligation_post,
    }


def _public(result: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in result.items() if not k.startswith("_")}


# =====================================================================
# Controls
# =====================================================================

def run_control_3_already_satisfied(world_a: dict[str, Any]) -> dict[str, Any]:
    """CONTROL 3 — a discharged obligation must stop asking."""
    stack: E3Stack = world_a["_stack"]
    ledger = stack.obligation_state.ledger
    budget = stack.budget_ledger(total=TOTAL_BUDGET, reserved=ADEQUACY_RESERVE)
    next_probe = ledger.next_probe(
        affordable=lambda cost: budget.affordable(
            cost, family=ActionFamily.VALIDATE
        )
    )
    return {
        "obligation_status": ledger.status.value,
        "satisfied": list(ledger.satisfied_required()),
        "outstanding": list(ledger.outstanding_required()),
        "next_probe": next_probe,
        "n_required": ledger.spec.n_required,
        "n_catalogue": len(
            [a for a in CANDIDATE_ACTIONS if a.phase == "adequacy_probe"]
        ),
        "never_required": [
            a.action_id
            for a in CANDIDATE_ACTIONS
            if a.phase == "adequacy_probe"
            and a.action_id not in ledger.required
        ],
        "probes_executed": len(ledger.records),
        "statement": (
            "the obligation is finite: three required conditions out of five "
            "feasible ones, and once discharged next_probe() returns nothing. "
            "Two catalogue probes were never bought and never will be"
        ),
    }


def run_control_4_budget_infeasible() -> dict[str, Any]:
    """CONTROL 4 — required evidence unaffordable under each budget policy.

    Same scientific state, same spend, two policies. Under the shared pool the
    parameter spend consumes the money the obligation needed; under the frozen
    reservation it cannot touch it.
    """
    out: dict[str, Any] = {}
    for policy in (BUDGET_POLICY_SHARED, BUDGET_POLICY_RESERVED):
        world = run_world(
            e2_truth.WELL_SPECIFIED_TRUTH,
            label=f"c4-{policy}",
            budget_policy=policy,
            total_budget=TOTAL_BUDGET,
            pre_spend_general=CONTROL_PARAMETER_SPEND,
        )
        out[policy] = {
            "obligation_status": world["obligation_status"],
            "adequacy_scope": world["adequacy_scope"],
            "certification": world["certification"],
            "probes_executed": len(world["acquisition"]["executed"]),
            "budget_final": world["budget_final"],
            "stop_review_post": world["obligation_aware_post"]["stop_review"],
        }
    shared = out[BUDGET_POLICY_SHARED]
    reserved = out[BUDGET_POLICY_RESERVED]
    out["comparison"] = {
        "shared_pool_completed": shared["obligation_status"] == "completed",
        "reserved_completed": reserved["obligation_status"] == "completed",
        "protection_observed": (
            shared["obligation_status"] != "completed"
            and reserved["obligation_status"] == "completed"
        ),
        "statement": (
            "descriptive, not a claim that reserving is universally right. On "
            "this benchmark, with a preregistered parameter spend of "
            f"{CONTROL_PARAMETER_SPEND} against a total of {TOTAL_BUDGET}, the "
            "frozen BudgetLedger reservation kept the mandatory evidence "
            "purchasable and the shared pool did not"
        ),
    }
    return out


def run_control_5_execution_invalid() -> dict[str, Any]:
    """CONTROL 5 — the required probe fails computational validity."""
    world = run_world(
        e2_truth.WELL_SPECIFIED_TRUTH,
        label="c5-invalid",
        faulty_probes=True,
    )
    return {
        "obligation_status": world["obligation_status"],
        "adequacy_scope": world["adequacy_scope"],
        "certification": world["certification"],
        "executed": world["acquisition"]["executed"],
        "adequacy_scored": world["acquisition"]["adequacy"]["scored"],
        "stop_review_post": world["obligation_aware_post"]["stop_review"],
        "statement": (
            "an invalid run is not adequacy evidence and is not an adequacy "
            "finding. The obligation stays UNRESOLVED_EXECUTION_FAILURE, the "
            "adequacy rule is never evaluated, and the disposition is repair — "
            "not MODEL_REVISION_REQUIRED and not a PASS"
        ),
    }


def run_obligation_set_placement_probe() -> dict[str, Any]:
    """Why the adequacy obligation is NOT in the campaign ObligationSet.

    Demonstrated rather than asserted: declaring it there makes the Arbiter
    look for a check by that name among ONE evidence record's assessments,
    never find it, and refuse to admit anything.
    """
    from src.engcore.sria.assurance.obligations import (
        ObligationKind,
        ObligationSet,
        ValidationObligation,
    )
    from experiments.electrical_e2.e2_harness import E2Harness
    from src.engcore.sria.campaign import CampaignEventLog
    from src.engcore.sria import (
        AdmissionAuthority,
        AdmissionAuthorityRegistry,
        BeliefUpdateGateway,
    )
    from src.engcore.sria.assurance import Arbiter
    from experiments.electrical_e2.e2_harness import E2Executor
    from .e3_config import CALIBRATION_ACTION

    authority = AdmissionAuthority("e3.placement.probe")
    gateway = BeliefUpdateGateway(
        authorities=AdmissionAuthorityRegistry([authority])
    )
    arbiter = Arbiter(authority)
    obligations = ObligationSet(
        campaign_id="e3-placement-probe",
        obligations=(
            ValidationObligation(
                obligation_id=ADEQUACY_OBLIGATION.obligation_id,
                kind=ObligationKind.REQUIRED_CHECK,
                target=ADEQUACY_OBLIGATION.obligation_id,
                source="e3 placement probe",
            ),
        ),
    )
    harness = E2Harness(
        run_id="e3-placement",
        gateway=gateway,
        arbiter=arbiter,
        executor=E2Executor(e2_truth.WELL_SPECIFIED_TRUTH),
        obligations=obligations,
        events=CampaignEventLog("e3-placement"),
    )
    row = harness.run_measurement(CALIBRATION_ACTION, repeat=1)
    return {
        "critic_verdict": row.critic_verdict,
        "arbiter_verdict": row.arbiter_verdict,
        "admitted": row.admitted,
        "belief_size": len(gateway.belief),
        "blocks_all_admission": (not row.admitted) and len(gateway.belief) == 0,
        "statement": OBLIGATION_PLACEMENT_STATEMENT,
    }


# =====================================================================
# Adversarial injections
# =====================================================================

def _injection(name, attempt, caught, catcher, detail) -> dict[str, Any]:
    return {
        "injection": name,
        "attempt": attempt,
        "caught": caught,
        "catcher": catcher,
        "detail": detail,
    }


def run_adversarial_injections(
    world_a: dict[str, Any], world_b: dict[str, Any]
) -> list[dict[str, Any]]:
    import inspect

    from .e3_obligation import CERTIFY_CAMPAIGN_ALLOWED_PARAMETERS

    out: list[dict[str, Any]] = []

    # --- A: fake positive EVSI for the adequacy probes ------------------
    # Contamination would show as a probe scoring above zero, or as the two
    # policies disagreeing on any score. Both are checked.
    pre_scores = {
        s["action_id"]: s for s in world_b["obligation_aware_pre"]["scores"]
    }
    evsi_scores = {s["action_id"]: s for s in world_b["evsi_only_phase"]["scores"]}
    identical = all(
        abs(pre_scores[a]["parameter_evsi"] - evsi_scores[a]["parameter_evsi"])
        == 0.0
        and pre_scores[a]["net_parameter_value"]
        == evsi_scores[a]["net_parameter_value"]
        for a in pre_scores
    )
    all_negative = all(s["net_parameter_value"] < 0.0 for s in pre_scores.values())
    probe_evsi = [
        s["parameter_evsi"]
        for s in pre_scores.values()
        if s["phase"] == "adequacy_probe"
    ]
    out.append(
        _injection(
            "A",
            "give the adequacy probes a positive information value",
            bool(identical and all_negative and max(probe_evsi) < 1e-9),
            "identical UtilityEngine scores under both policies",
            (
                f"every probe's parameter EVSI is <= {max(probe_evsi):.3e} and "
                f"every net value is negative; the obligation-aware and "
                f"EVSI-only runs produced bit-identical scores"
            ),
        )
    )

    # --- B: approve a stop while the obligation is outstanding ----------
    caught, detail = False, "NOT CAUGHT"
    try:
        StopReview(
            review_id="inject-b",
            proposal_id="inject-b-proposal",
            outcome=StopReviewOutcome.STOP_APPROVED,
            terminal_objective_available=True,
            arbiter_decision_id="forged",
            criterion_id=ADEQUACY_OBLIGATION.obligation_id,
            unmet_obligations=(ADEQUACY_OBLIGATION.obligation_id,),
            reasons=("forged approval",),
        )
    except ValueError as exc:
        caught, detail = True, str(exc)
    pre_review = world_b["obligation_aware_pre"]["stop_review"]
    out.append(
        _injection(
            "B",
            "hold STOP_APPROVED while a mandatory obligation is outstanding",
            bool(caught and pre_review["outcome"] != "stop_approved"),
            "StopReview.__post_init__ (frozen M5.1 structural guard)",
            (
                f"{detail[:120]}; and the live pre-probe review returned "
                f"{pre_review['outcome']} with arbiter "
                f"{pre_review['arbiter_verdict']!r}"
            ),
        )
    )

    # --- C: count a failed execution as satisfying the obligation -------
    ledger = ObligationLedger()
    action_id = ledger.required[0]
    ledger.record_probe(
        action_id=action_id,
        source_voltage_volt=ACTION_BY_ID[action_id].source_voltage_volt,
        execution_id="inject-c",
        execution_valid=False,
        admitted=False,
        commitment_artifact_hash="abc",
        realized_cost=0.15,
        execution_reason=EXECUTION_REASON_OBLIGATION,
    )
    out.append(
        _injection(
            "C",
            "mark the obligation satisfied because the action was attempted",
            bool(
                action_id in ledger.outstanding_required()
                and ledger.status is ObligationStatus.UNRESOLVED_EXECUTION_FAILURE
            ),
            "ProbeRecord.is_obligation_evidence",
            (
                "an attempt with execution_valid=False and admitted=False does "
                "not count; the condition stays outstanding and the ledger "
                "reports UNRESOLVED_EXECUTION_FAILURE"
            ),
        )
    )

    # --- D: equate obligation completed with model adequate -------------
    completed_but_failed = certify_campaign(
        "A",
        ObligationStatus.COMPLETED,
        AdequacyScope.MODEL_SPACE_INADEQUATE,
        ExecutionValidity.VALID,
    )
    out.append(
        _injection(
            "D",
            "treat a discharged obligation as a passing model",
            bool(
                completed_but_failed.scientific_certification
                is Certification.NOT_CERTIFIABLE
                and completed_but_failed.disposition
                is Disposition.MODEL_REVISION_REQUIRED
                and completed_but_failed.obligation_status
                is ObligationStatus.COMPLETED
            ),
            "certify_campaign (obligation and adequacy are separate arguments)",
            (
                "obligation COMPLETED with adequacy MODEL_SPACE_INADEQUATE "
                "yields NOT_CERTIFIABLE / MODEL_REVISION_REQUIRED while still "
                "reporting the obligation as fully discharged"
            ),
        )
    )

    # --- E: spend the pool and leave the obligation impossible ----------
    control4 = run_control_4_budget_infeasible()
    out.append(
        _injection(
            "E",
            "consume the budget on parameter actions and hide the consequence",
            bool(
                control4[BUDGET_POLICY_SHARED]["certification"]["reason"]
                == "REQUIRED_ADEQUACY_EVIDENCE_BUDGET_INFEASIBLE"
            ),
            "BudgetLedger.affordable(family=VALIDATE) + explicit reporting",
            (
                f"under the shared pool the obligation ends "
                f"{control4[BUDGET_POLICY_SHARED]['obligation_status']} and "
                f"certification is refused for an explicitly budget-shaped "
                f"reason, never a model-shaped one; under the frozen "
                f"reservation it ends "
                f"{control4[BUDGET_POLICY_RESERVED]['obligation_status']}"
            ),
        )
    )

    # --- F: discharge the obligation with a different cheap action ------
    ledger_f = ObligationLedger()
    caught_f, detail_f = False, "NOT CAUGHT"
    try:
        ledger_f.record_probe(
            action_id="parameter_repeat_10V",
            source_voltage_volt=10.0,
            execution_id="inject-f",
            execution_valid=True,
            admitted=True,
            commitment_artifact_hash="abc",
            realized_cost=0.15,
            execution_reason="pretending",
        )
    except ObligationBindingError as exc:  # noqa: BLE001
        caught_f, detail_f = False, str(exc)
    # A declared but non-required probe is accepted as a record and simply does
    # not count; a wrong operating point for a required id is rejected outright.
    ledger_f.record_probe(
        action_id="adequacy_probe_20V",
        source_voltage_volt=20.0,
        execution_id="inject-f2",
        execution_valid=True,
        admitted=True,
        commitment_artifact_hash="abc",
        realized_cost=0.15,
        execution_reason="pretending",
    )
    wrong_condition = False
    try:
        ledger_f.record_probe(
            action_id="adequacy_probe_16V",
            source_voltage_volt=10.0,          # the cheap calibration condition
            execution_id="inject-f3",
            execution_valid=True,
            admitted=True,
            commitment_artifact_hash="abc",
            realized_cost=0.02,
            execution_reason="pretending",
        )
    except ObligationBindingError:
        wrong_condition = True
    out.append(
        _injection(
            "F",
            "discharge the obligation with a cheaper, different action",
            bool(
                ledger_f.status is ObligationStatus.OUTSTANDING
                and len(ledger_f.outstanding_required()) == 3
                and wrong_condition
            ),
            "ObligationLedger.record_probe condition binding",
            (
                "a non-required catalogue probe is recorded and counts for "
                "nothing; a required action id executed at the wrong operating "
                "point raises ObligationBindingError. All three required "
                "conditions remain outstanding"
            ),
        )
    )

    # --- G: construct the predictive after the observation --------------
    commitments = world_b["_acquisition"]["_commitments"]
    caught_g, detail_g = False, "NOT CAUGHT"
    try:
        spec = ACTION_BY_ID["adequacy_probe_20V"]
        commitments.commit(
            action_id=spec.action_id,
            source_voltage_volt=spec.source_voltage_volt,
            noise_sigma_volt=spec.noise_sigma_volt,
            evidence_snapshot_digest="post-hoc",
            n_observations=99,
            mixture=predictive_mixture(world_b["_weights_after"], spec),
        )
    except PredictiveCommitmentViolation as exc:
        caught_g, detail_g = True, str(exc).split(".")[0]
    out.append(
        _injection(
            "G",
            "commit a predictive after its observation exists",
            caught_g,
            "E2 CommitmentLedger.commit (sealed ledger)",
            detail_g,
        )
    )

    # --- certification gate signature ----------------------------------
    params = tuple(inspect.signature(certify_campaign).parameters)
    forbidden = ("sd", "entropy", "evpi", "evsi", "confidence", "stop")
    out.append(
        _injection(
            "H",
            "let posterior confidence, EVPI or EVSI reach the certification gate",
            bool(
                params == CERTIFY_CAMPAIGN_ALLOWED_PARAMETERS
                and not any(any(f in p for f in forbidden) for p in params)
            ),
            "certify_campaign signature",
            f"certify_campaign{params} accepts no value-of-information input",
        )
    )
    return out


# =====================================================================
# The whole run
# =====================================================================

def run_e3() -> dict[str, Any]:
    result: dict[str, Any] = {
        "experiment": "E3",
        "config_hash": config_hash(),
        "preregistration_hash": preregistration_hash(),
        "config": config_payload(),
    }

    world_a = run_world(e2_truth.WELL_SPECIFIED_TRUTH, label="e3-world-A")
    world_b = run_world(e2_truth.MISSPECIFIED_TRUTH, label="e3-world-B")

    result["world_a_well_specified"] = _public(world_a)
    result["world_b_misspecified"] = _public(world_b)
    result["control_1_no_obligation"] = {
        "stop_review": world_b["evsi_only_phase"]["stop_review"],
        "executed_actions": world_b["evsi_only_phase"]["executed_actions"],
        "statement": (
            "with no stopping criterion registered the review returns "
            "STOP_NOT_ASSESSED naming no criterion, and no adequacy evidence "
            "is ever acquired. This is the EVSI-only counterfactual"
        ),
    }
    result["control_2_obligation_outstanding"] = {
        "stop_review": world_b["obligation_aware_pre"]["stop_review"],
        "routed_probe": (
            world_b["acquisition"]["executed"][0]["action_id"]
            if world_b["acquisition"]["executed"]
            else None
        ),
        "why_action_executed": (
            world_b["acquisition"]["executed"][0]["why_action_executed"]
            if world_b["acquisition"]["executed"]
            else None
        ),
    }
    result["control_3_already_satisfied"] = run_control_3_already_satisfied(world_a)
    result["control_4_budget_infeasible"] = run_control_4_budget_infeasible()
    result["control_5_execution_invalid"] = run_control_5_execution_invalid()
    result["control_6_model_inadequate"] = {
        "obligation_status": world_b["obligation_status"],
        "adequacy_scope": world_b["adequacy_scope"],
        "certification": world_b["certification"],
        "stop_review": world_b["obligation_aware_post"]["stop_review"],
    }
    result["obligation_set_placement_probe"] = (
        run_obligation_set_placement_probe()
    )
    result["adversarial_injections"] = run_adversarial_injections(
        world_a, world_b
    )

    checks = {
        "parameter_evsi_identical_across_policies": all(
            abs(
                a["parameter_evsi"] - b["parameter_evsi"]
            ) == 0.0
            for a, b in zip(
                sorted(
                    world_b["evsi_only_phase"]["scores"],
                    key=lambda s: s["action_id"],
                ),
                sorted(
                    world_b["obligation_aware_pre"]["scores"],
                    key=lambda s: s["action_id"],
                ),
            )
        ),
        "no_candidate_worth_buying_before_adequacy": all(
            s["net_parameter_value"] < 0.0
            for s in world_b["obligation_aware_pre"]["scores"]
        ),
        "evsi_only_acquired_nothing": not world_b["evsi_only_phase"][
            "executed_actions"
        ],
        "stop_not_approved_while_outstanding": (
            world_b["obligation_aware_pre"]["stop_review"]["outcome"]
            != "stop_approved"
        ),
        "obligation_routed_a_probe": bool(world_b["acquisition"]["executed"]),
        "world_a_obligation_completed": (
            world_a["obligation_status"] == ObligationStatus.COMPLETED.value
        ),
        "world_a_adequacy_acceptable": (
            world_a["adequacy_scope"]
            == AdequacyScope.ACCEPTABLE_FOR_DECLARED_SCOPE.value
        ),
        "world_a_stop_approved": (
            world_a["obligation_aware_post"]["stop_review"]["outcome"]
            == "stop_approved"
        ),
        "world_a_certification_eligible": (
            world_a["certification"]["scientific_certification"]
            == Certification.ELIGIBLE.value
        ),
        "world_b_obligation_completed": (
            world_b["obligation_status"] == ObligationStatus.COMPLETED.value
        ),
        "world_b_certification_denied": (
            world_b["certification"]["scientific_certification"]
            == Certification.NOT_CERTIFIABLE.value
        ),
        "control_3_no_duplicate_probes": (
            result["control_3_already_satisfied"]["next_probe"] is None
        ),
        "control_4_budget_reason_distinct": (
            result["control_4_budget_infeasible"][BUDGET_POLICY_SHARED][
                "certification"
            ]["reason"]
            == "REQUIRED_ADEQUACY_EVIDENCE_BUDGET_INFEASIBLE"
        ),
        "control_5_no_adequacy_from_invalid": (
            not result["control_5_execution_invalid"]["adequacy_scored"]
        ),
        "all_injections_caught": all(
            i["caught"] for i in result["adversarial_injections"]
        ),
    }
    result["success_checks"] = checks

    # --- what the FROZEN STACK did on its own, measured ------------------
    # The checks above establish that the obligation policy works. They say
    # nothing about whose code made it work, and the difference decides how
    # strong a claim E3 is entitled to. So the campaign-native question is
    # answered by looking at what a CampaignRunner actually executed, not by
    # anyone's summary of it: every probe in this run was executed by the
    # experiment-local adapter, and no runner pass executed one.
    probe_ids = {
        a.action_id for a in CANDIDATE_ACTIONS if a.phase == "adequacy_probe"
    }
    runner_executed_probes = sorted(
        action_id
        for world in (world_a, world_b)
        for phase in (
            "evsi_only_phase",
            "obligation_aware_pre",
            "obligation_aware_post",
        )
        for action_id in world[phase]["executed_actions"]
        if action_id in probe_ids
    )
    native = {
        "stop_refusal_is_campaign_native": (
            world_b["obligation_aware_pre"]["stop_review"]["criterion_id"]
            == ADEQUACY_OBLIGATION.obligation_id
            and world_a["obligation_aware_post"]["stop_review"][
                "arbiter_decision_id"
            ]
            != ""
        ),
        "validation_budget_fence_is_campaign_native": (
            result["control_4_budget_infeasible"]["comparison"][
                "protection_observed"
            ]
        ),
        "adequacy_acquisition_is_campaign_native": bool(runner_executed_probes),
    }
    result["campaign_native_checks"] = native
    result["runner_executed_probes"] = runner_executed_probes

    result["claim_scope"] = (
        "E3 verified the OBLIGATION POLICY: a finite preregistered adequacy "
        "obligation remained scientifically binding after parameter-learning "
        "EVSI collapsed, and no fake parameter information value was assigned "
        "to the adequacy probes. It did NOT verify campaign-native adequacy "
        "acquisition: the frozen stack refused the stop and protected the "
        "budget on its own, but the probes were executed by an "
        "experiment-local adapter, so the strongest honest verdict is "
        "PARTIALLY VERIFIED"
    )
    result["allowed_claim"] = (
        "On the computational Electrical benchmark, E3 verified that a finite "
        "preregistered adequacy obligation can remain scientifically binding "
        "after parameter-learning EVSI has collapsed, without assigning fake "
        "parameter information value to adequacy probes. The existing frozen "
        "campaign stack genuinely refused scientific STOP and protected "
        "validation budget, but it did not natively acquire the required "
        "adequacy evidence; that acquisition required an experiment-local "
        "adapter."
    )
    result["architecture_gaps"] = [
        {
            "gap": "campaign-scoped obligation vocabulary is missing",
            "evidence": (
                "ObligationSet is evaluated per evidence record; placing the "
                "adequacy obligation there yields arbiter INCONCLUSIVE, "
                "admitted=False and belief_size=0 — it blocks all admission"
            ),
        },
        {
            "gap": (
                "_propose_stop has no resolution branch routing a non-approved "
                "stop review to the evidence that would resolve the obligation"
            ),
            "evidence": (
                "the runner pauses with NO_ACTION_WORTH_BUYING whatever the "
                "review returns; no runner pass executed any adequacy probe"
            ),
        },
        {
            "gap": (
                "no supported campaign initialization path from previously "
                "admitted evidence / assurance state"
            ),
            "evidence": (
                "without hand-building a CampaignCheckpoint the stop review "
                "short-circuits at 'obligations were never assessed' and never "
                "reaches the registered criterion"
            ),
        },
        {
            "gap": (
                "adequacy probes still rely on the experiment-local E2 "
                "predictive commitment seam"
            ),
            "evidence": (
                "a probe cannot honestly satisfy an adequacy obligation if its "
                "prediction was not committed before observation, and nothing "
                "in src/ can hold that commitment"
            ),
        },
    ]
    result["next_step"] = {
        "milestone": "CAMPAIGN OBLIGATION ROUTING INTEGRATION",
        "purpose": (
            "connect the four seams above minimally so that a campaign-scoped "
            "obligation can be declared, seen by the existing liveness router, "
            "resolved by the existing execution path, and discharged only by "
            "evidence carrying a pre-observation predictive commitment"
        ),
        "not": (
            "a generic validation subsystem, and not a claim that a "
            "CampaignObligation type alone closes the gap — three of the four "
            "gaps are integration, not vocabulary"
        ),
        "started": False,
    }

    result["verdict"] = (
        "E3 ADEQUACY-OBLIGATION POLICY VERIFIED"
        if all(checks.values()) and all(native.values())
        else "E3 PARTIALLY VERIFIED"
    )
    return result


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def render_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# E3 — Adequacy evidence vs parameter EVSI")
    add("")
    add(f"Config hash: `{result['config_hash']}`")
    add(f"Preregistration hash: `{result['preregistration_hash']}`")
    add("")
    add(
        "A measurement may have almost zero value for estimating theta and "
        "still be mandatory evidence for deciding whether the model containing "
        "theta deserves certification. E3 does not fake the former to justify "
        "the latter."
    )

    for key, title in (
        ("world_a_well_specified", "World A — well specified"),
        ("world_b_misspecified", "World B — misspecified"),
    ):
        world = result[key]
        add("")
        add(f"## {title}")
        p = world["before_adequacy"]["posterior"]
        add("")
        add(
            f"After calibration: decision **{p['bayes_decision']}**, "
            f"P(above)={_fmt(p['p_above_threshold'])}, "
            f"sd={_fmt(p['sd_r2_ohm'])} Ω, EVPI={p['evpi']:.3e}."
        )
        add("")
        add("| candidate | family | parameter EVSI | cost | net |")
        add("|---|---|---|---|---|")
        for action_id, row in sorted(world["before_adequacy"]["evsi_table"].items()):
            add(
                f"| `{action_id}` | {row['action_family']} | "
                f"{row['parameter_evsi']:.3e} | {_fmt(row['cost'])} | "
                f"{row['net']:+.4f} |"
            )
        add("")
        pre = world["obligation_aware_pre"]["stop_review"]
        evsi_only = world["evsi_only_phase"]["stop_review"]
        add(
            f"- EVSI-only review: **{evsi_only['outcome']}** "
            f"(criterion `{evsi_only['criterion_id'] or 'none registered'}`), "
            f"actions executed: "
            f"{world['evsi_only_phase']['executed_actions'] or 'none'}"
        )
        add(
            f"- Obligation-aware review (pre): **{pre['outcome']}** "
            f"(criterion `{pre['criterion_id']}`, arbiter "
            f"`{pre['arbiter_verdict']}`)"
        )
        add("")
        add("| probe executed | Vs [V] | parameter EVSI | admitted | reason |")
        add("|---|---|---|---|---|")
        for row in world["acquisition"]["executed"]:
            add(
                f"| `{row['action_id']}` | {row['source_voltage_volt']:g} | "
                f"{row['parameter_evsi_at_selection']:.3e} | "
                f"{row['admitted']} | `{row['execution_reason']}` |"
            )
        post = world["obligation_aware_post"]["stop_review"]
        cert = world["certification"]
        add("")
        add(
            f"- Obligation status: **{world['obligation_status']}** | "
            f"adequacy: **{world['adequacy_scope']}**"
        )
        add(
            f"- Obligation-aware review (post): **{post['outcome']}** "
            f"(arbiter `{post['arbiter_verdict']}`)"
        )
        add(
            f"- `POSTERIOR_DECISION = {cert['posterior_decision']}` | "
            f"`SCIENTIFIC_CERTIFICATION = "
            f"{cert['scientific_certification'].upper()}` | "
            f"`reason = {cert['reason']}` | "
            f"`disposition = {cert['disposition'].upper()}`"
        )

    add("")
    add("## Controls")
    add("")
    c4 = result["control_4_budget_infeasible"]
    add(
        f"- **1 no obligation:** review "
        f"`{result['control_1_no_obligation']['stop_review']['outcome']}`, "
        f"acquired nothing."
    )
    add(
        f"- **2 outstanding:** routed `"
        f"{result['control_2_obligation_outstanding']['routed_probe']}`."
    )
    c3 = result["control_3_already_satisfied"]
    add(
        f"- **3 already satisfied:** next_probe = `{c3['next_probe']}`; "
        f"{c3['probes_executed']} of {c3['n_catalogue']} catalogue probes "
        f"executed; never required: {c3['never_required']}."
    )
    add(
        f"- **4 budget:** shared → `"
        f"{c4[BUDGET_POLICY_SHARED]['obligation_status']}` / "
        f"`{c4[BUDGET_POLICY_SHARED]['certification']['reason']}`; reserved → "
        f"`{c4[BUDGET_POLICY_RESERVED]['obligation_status']}`."
    )
    c5 = result["control_5_execution_invalid"]
    add(
        f"- **5 execution invalid:** obligation "
        f"`{c5['obligation_status']}`, adequacy scored "
        f"`{c5['adequacy_scored']}`, disposition "
        f"`{c5['certification']['disposition']}`."
    )
    add(
        f"- **6 model inadequate:** obligation "
        f"`{result['control_6_model_inadequate']['obligation_status']}`, "
        f"certification "
        f"`{result['control_6_model_inadequate']['certification']['reason']}`."
    )

    add("")
    add("## Adversarial injections")
    add("")
    add("| # | attempt | caught | catcher |")
    add("|---|---|---|---|")
    for i in result["adversarial_injections"]:
        add(
            f"| {i['injection']} | {i['attempt']} | "
            f"{'yes' if i['caught'] else '**NO**'} | {i['catcher']} |"
        )

    add("")
    add("## What the frozen stack did on its own")
    add("")
    add("| capability | campaign-native |")
    add("|---|---|")
    for name, value in sorted(result["campaign_native_checks"].items()):
        add(f"| {name.replace('_', ' ')} | {'**yes**' if value else '**no**'} |")
    add("")
    add(
        f"Adequacy probes executed by any CampaignRunner pass: "
        f"`{result['runner_executed_probes'] or 'none'}`. Every probe in this "
        f"run was executed by the experiment-local adapter, which is why the "
        f"verdict is bounded below the obligation policy's own result."
    )

    add("")
    add("## Strongest supported claim")
    add("")
    add(result["allowed_claim"])

    add("")
    add("## Architecture gaps retained")
    add("")
    for index, gap in enumerate(result["architecture_gaps"], start=1):
        add(f"{index}. **{gap['gap']}** — {gap['evidence']}")
    add("")
    add(
        f"Next step: **{result['next_step']['milestone']}** — "
        f"{result['next_step']['purpose']}. Not "
        f"{result['next_step']['not']}. Not started."
    )

    add("")
    add(f"**{result['verdict']}**")
    return "\n".join(lines)


def main() -> int:
    result = run_e3()
    root = Path(__file__).resolve().parent
    (root / "e3_config_frozen.json").write_text(
        json.dumps(
            {
                "config": result["config"],
                "config_hash": result["config_hash"],
                "preregistration_hash": result["preregistration_hash"],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (root / "e3_results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    report = render_markdown(result)
    (root / "e3_report.md").write_text(report, encoding="utf-8")
    print(report)
    # Success here means the experiment ran as designed and every
    # obligation-policy check passed. PARTIALLY VERIFIED is the EXPECTED
    # verdict, not a failure: the campaign-native bound is a measured property
    # of the frozen stack, not something this run was trying to achieve.
    return 0 if all(result["success_checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
