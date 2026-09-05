"""Run the Electrical V0.1 demo and write its three artifacts.

Two worlds through one system. Everything reported is read back out of the
frozen components — the event log, the belief store, the budget ledger, the
runner's own derived requirement status — rather than recorded on the way past,
so the report describes what the system did and not what the demo intended.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from experiments.electrical_e2 import e2_truth
from experiments.electrical_e2.e2_adequacy import (
    AdequacyState,
    ExecutionValidity,
    aggregate_adequacy,
    build_joint_predictive,
    score_commitments,
)
from experiments.electrical_e2.e2_harness import E2FaultyExecutor
from experiments.electrical_e2.e2_model import (
    evsi,
    posterior_summary,
    posterior_weights,
    prior_weights,
)
from src.engcore.sria.campaign import CampaignEventType
from src.engcore.sria.campaign.stopping import StopReviewOutcome

from . import BASE_COMMIT, DEMO_VERSION
from .demo_config import (
    ACTION_FAMILY_BY_PHASE,
    CANDIDATE_ACTIONS,
    DECLARED_SCOPE,
    PARAMETER_ACTION,
    REQUIRED_ACTION_IDS,
    REQUIREMENT_ID,
    RESERVED_VALIDATION_BUDGET,
    TOTAL_BUDGET,
    config_hash,
    config_payload,
    scenario_hash,
)
from .demo_lifecycle import ACTION_BY_ID, build_stack, family_for

SCIENTIFIC_QUESTION = (
    "In a two-resistor divider with a known 1000 ohm upper resistor, is the "
    "unknown lower resistance above 1200 ohm — and may that answer be "
    "certified for the declared operating range?"
)

PREDICTION_REF_LIMITATION = (
    "V0.1 production verifies exactly one thing about a required validation "
    "action: that a non-empty prediction_ref was recorded in the tamper-"
    "evident event log before the action executed. It does NOT verify in "
    "production that the reference names a real predictive distribution, that "
    "the prediction is bound to the correct evidence snapshot, that it was "
    "sealed against later modification, or that its content hash checks out. "
    "E2 demonstrated all four of those properties experiment-side, and this "
    "demo uses E2's sealed ledger to create the predictions — so the stronger "
    "properties hold here in fact, but they are NOT what production enforces. "
    "A campaign supplying a meaningless reference would satisfy the V0.1 "
    "contract and would have tested nothing."
)


# =====================================================================
# Tracing one world
# =====================================================================

def _selection_trace(runner) -> list[dict[str, Any]]:
    admitted_by_iteration = {
        e.iteration for e in runner.events.of_type(
            CampaignEventType.EVIDENCE_ADMITTED
        )
    }
    rejected_by_iteration = {
        e.iteration for e in runner.events.of_type(
            CampaignEventType.EVIDENCE_NOT_ADMITTED
        )
    }
    started = {
        e.iteration: e.sequence
        for e in runner.events.of_type(CampaignEventType.EXECUTION_STARTED)
    }
    out = []
    for event in runner.events.of_type(CampaignEventType.ACTION_SELECTED):
        action_id = str(event.payload["action_id"])
        spec = ACTION_BY_ID[action_id]
        out.append(
            {
                "iteration": event.iteration,
                "action_id": action_id,
                "phase": spec.phase,
                "action_family": str(event.payload["family"]),
                "execution_reason": str(event.payload["execution_reason"]),
                "prediction_ref": str(event.payload["prediction_ref"]),
                "action_selected_sequence": event.sequence,
                "execution_started_sequence": started.get(event.iteration),
                "prediction_precedes_execution": bool(
                    event.payload["prediction_ref"]
                    and started.get(event.iteration, 0) > event.sequence
                ),
                "admitted": event.iteration in admitted_by_iteration,
                "not_admitted": event.iteration in rejected_by_iteration,
            }
        )
    return out


def _score_trace(runner) -> list[dict[str, Any]]:
    out = []
    for event in runner.events.of_type(CampaignEventType.DECISION_RECOMMENDED):
        recommendation = runner.recommendation(
            str(event.payload["recommendation_id"])
        )
        if recommendation is None:
            continue
        rows = []
        for score in sorted(recommendation.scores, key=lambda s: s.action_id):
            gain = score.component("conditional_success_utility_gain")
            cost = score.component("expected_cost")
            spec = ACTION_BY_ID[score.action_id]
            rows.append(
                {
                    "action_id": score.action_id,
                    "phase": spec.phase,
                    "action_family": family_for(spec).value,
                    "parameter_evsi": gain.value if gain else None,
                    "cost": cost.value if cost else None,
                    "net_value": score.total,
                }
            )
        out.append(
            {
                "iteration": event.iteration,
                "outcome": str(event.payload["outcome"]),
                "chosen_action_id": str(event.payload["chosen_action_id"]),
                "scores": rows,
            }
        )
    return out


def _belief_counters(runner, gateway) -> dict[str, Any]:
    def count(kind) -> int:
        return len(runner.events.of_type(kind))

    return {
        "executions_started": count(CampaignEventType.EXECUTION_STARTED),
        "executions_completed": count(CampaignEventType.EXECUTION_COMPLETED),
        "evidence_records_created": count(CampaignEventType.EVIDENCE_CREATED),
        "evidence_admitted": count(CampaignEventType.EVIDENCE_ADMITTED),
        "evidence_rejected": count(CampaignEventType.EVIDENCE_NOT_ADMITTED),
        "belief_size": len(gateway.belief),
        "belief_action_ids": sorted(
            str(e.claim_payload["action_id"])
            for e in gateway.belief.active_view().values()
        ),
        "event_chain_verified": runner.events.verify_chain(),
    }


def _adequacy_detail(stack) -> dict[str, Any]:
    if not stack.commitments.observations:
        return {"scored": False, "reason": "required evidence incomplete"}
    surprises = score_commitments(stack.commitments)
    joint = build_joint_predictive(
        stack.commitments, [s.action_id for s in surprises]
    )
    aggregate = aggregate_adequacy(surprises, joint)
    return {
        "scored": True,
        "state": stack.evaluator.last_state.value,
        "surprises": [s.to_dict() for s in surprises],
        "aggregate": aggregate.to_dict(),
        "commitments": [
            stack.commitments.commitments[a].summary()
            for a in REQUIRED_ACTION_IDS
        ],
        "ledger_head": stack.commitments.head_digest,
        "ledger_sealed_at": stack.commitments.sealed_at_sequence,
        "chain_verified": (
            stack.commitments.verify_chain()
            and stack.commitments.verify_commitments()
        ),
    }


def run_world(spec: e2_truth.TruthSpec, *, label: str) -> dict[str, Any]:
    stack = build_stack(spec, label=label)
    prior = posterior_summary(prior_weights())
    stack.runner.run_campaign()

    final_weights = stack.harness.posterior()
    final = posterior_summary(final_weights)
    adequacy = _adequacy_detail(stack)
    review = stack.runner.stop_reviews[-1] if stack.runner.stop_reviews else None
    requirement_status = stack.runner.certification_status()[REQUIREMENT_ID]

    state = stack.evaluator.last_state
    if state is None:
        certification, reason, disposition = (
            "not_certifiable",
            "CERTIFICATION_EVIDENCE_OUTSTANDING",
            "adequacy_evidence_required",
        )
    elif state is AdequacyState.MODEL_ADEQUACY_ACCEPTABLE:
        certification, reason, disposition = (
            "eligible",
            "ADEQUACY_ACCEPTABLE_FOR_DECLARED_SCOPE",
            "certification_eligible",
        )
    else:
        certification, reason, disposition = (
            "not_certifiable",
            state.name,
            "model_revision_required",
        )

    # --- belief integrity: an invalid execution must change nothing --------
    before = len(stack.gateway.belief)
    weights_before = stack.harness.posterior()
    stack.e2.executor = E2FaultyExecutor(spec)
    faulty = stack.e2.run_measurement(ACTION_BY_ID["validate_vmid_20V"], repeat=1)
    after_weights = stack.harness.posterior()
    integrity = {
        "faulty_action_id": faulty.action_id,
        "critic_verdict": faulty.critic_verdict,
        "arbiter_verdict": faulty.arbiter_verdict,
        "admitted": faulty.admitted,
        "execution_validity": faulty.execution_validity.value,
        "belief_size_before": before,
        "belief_size_after": len(stack.gateway.belief),
        "belief_unchanged": before == len(stack.gateway.belief),
        "posterior_unchanged": bool(
            np.array_equal(weights_before, after_weights)
        ),
    }

    return {
        "label": label,
        "truth_spec_id": spec.spec_id,
        "truth_in_assumed_family": spec.is_well_specified,
        "posterior_prior": prior,
        "posterior_final": final,
        "score_trace": _score_trace(stack.runner),
        "selection_trace": _selection_trace(stack.runner),
        "executed_actions": list(stack.harness.executor_impl.calls),
        "routed_by_runner_for_certification": [
            row["action_id"]
            for row in _selection_trace(stack.runner)
            if row["execution_reason"] == "CERTIFICATION_REQUIREMENT"
        ],
        "certification_requirement_status": requirement_status,
        "adequacy": adequacy,
        "stop_review": {
            "outcome": review.outcome.value if review else None,
            "arbiter_verdict": review.arbiter_verdict if review else "",
            "arbiter_decision_id": review.arbiter_decision_id if review else "",
            "criterion_id": review.criterion_id if review else "",
            "approves": review.approves if review else False,
            "is_certification": review.is_certification if review else False,
        },
        "terminal": {
            "posterior_decision": final["bayes_decision"],
            "posterior_decision_reading": (
                "the decision preferred by p(R2 | data, constant-R model); a "
                "statement conditional on the family, not about the world"
            ),
            "parameter_evpi": final["evpi"],
            "parameter_evsi_max": max(
                evsi(final_weights, a) for a in CANDIDATE_ACTIONS
            ),
            "certification_requirement": requirement_status,
            "model_adequacy": (
                "acceptable_for_declared_scope"
                if state is AdequacyState.MODEL_ADEQUACY_ACCEPTABLE
                else (state.value if state else "not_assessed")
            ),
            "stop": review.outcome.value if review else None,
            "scientific_certification": certification,
            "reason": reason,
            "disposition": disposition,
            "declared_scope": DECLARED_SCOPE,
        },
        "belief": _belief_counters(stack.runner, stack.gateway),
        "belief_integrity_probe": integrity,
        "budget": {
            "total": stack.budget.total_budget,
            "reserved_validation": stack.budget.reserved_validation_budget,
            "spent_parameter_learning": stack.budget.spent_general,
            "spent_validation": stack.budget.spent_validation,
            "spent_total": stack.budget.spent_total,
            "remaining": stack.budget.remaining,
            "general_pool_left": stack.budget.general_pool,
            "validation_pool_left": stack.budget.validation_pool,
            "ledger": "frozen BudgetLedger",
        },
        "_stack": stack,
    }


def _public(world: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in world.items() if not k.startswith("_")}


# =====================================================================
# EVSI invariance
# =====================================================================

def evsi_invariance(spec, *, label: str) -> dict[str, Any]:
    """The same campaign with and without the requirement declared."""
    def first_scores(with_requirement: bool):
        stack = build_stack(
            spec,
            label=f"{label}-{'req' if with_requirement else 'noreq'}",
            with_requirement=with_requirement,
        )
        stack.runner.run_campaign()
        rows = {}
        for entry in _score_trace(stack.runner):
            for row in entry["scores"]:
                rows.setdefault(
                    (entry["iteration"], row["action_id"]),
                    (row["parameter_evsi"], row["cost"], row["net_value"]),
                )
        return rows, stack

    with_rows, with_stack = first_scores(True)
    without_rows, without_stack = first_scores(False)
    shared = sorted(set(with_rows) & set(without_rows))
    return {
        "shared_score_points": len(shared),
        "identical_on_shared_points": all(
            with_rows[k] == without_rows[k] for k in shared
        ),
        "with_requirement_executed": list(
            with_stack.harness.executor_impl.calls
        ),
        "without_requirement_executed": list(
            without_stack.harness.executor_impl.calls
        ),
        "without_requirement_stop_review": (
            without_stack.runner.stop_reviews[-1].outcome.value
            if without_stack.runner.stop_reviews
            else None
        ),
        "certification_action_scores": [
            {
                "action_id": action_id,
                "iteration": iteration,
                "parameter_evsi": with_rows[(iteration, action_id)][0],
                "cost": with_rows[(iteration, action_id)][1],
                "net_value": with_rows[(iteration, action_id)][2],
                "execution_reason": "CERTIFICATION_REQUIREMENT",
            }
            for (iteration, action_id) in shared
            if action_id in REQUIRED_ACTION_IDS and iteration == 2
        ],
        "statement": (
            "the certification requirement changed no parameter-learning "
            "score. The routed actions keep the negative net value the engine "
            "gave them, and are executed for a stated constraint reason"
        ),
    }


# =====================================================================
# The whole demo
# =====================================================================

def run_demo() -> dict[str, Any]:
    result: dict[str, Any] = {
        "demo": "electrical_v01",
        "demo_version": DEMO_VERSION,
        "base_commit": BASE_COMMIT,
        "config_hash": config_hash(),
        "scenario_hash": scenario_hash(),
        "config": config_payload(),
        "scientific_question": SCIENTIFIC_QUESTION,
        "prediction_ref_limitation": PREDICTION_REF_LIMITATION,
    }

    world_a = run_world(e2_truth.WELL_SPECIFIED_TRUTH, label="v01demo-A")
    world_b = run_world(e2_truth.MISSPECIFIED_TRUTH, label="v01demo-B")
    result["world_a_model_adequate"] = _public(world_a)
    result["world_b_model_inadequate"] = _public(world_b)
    result["evsi_invariance"] = evsi_invariance(
        e2_truth.MISSPECIFIED_TRUTH, label="v01demo-inv"
    )

    result["critical_distinctions"] = [
        {
            "distinction": "EXECUTION VALIDITY != MODEL ADEQUACY",
            "shown_by": (
                f"in World B every routed probe was computationally VALID and "
                f"ADMITTED "
                f"({world_b['belief']['evidence_admitted']} admitted, "
                f"{world_b['belief']['evidence_rejected']} rejected) while the "
                f"model was refused"
            ),
        },
        {
            "distinction": "PARAMETER POSTERIOR CONFIDENCE != MODEL ADEQUACY",
            "shown_by": (
                f"World B ends at sd = "
                f"{world_b['posterior_final']['sd_r2_ohm']:.4f} ohm and "
                f"P(decision) = "
                f"{world_b['posterior_final']['p_above_threshold']:.8f}, and is "
                f"still not certifiable"
            ),
        },
        {
            "distinction": "PARAMETER EVSI ~ 0 != ALL SCIENTIFIC EVIDENCE COMPLETE",
            "shown_by": (
                f"after iteration 1 every action scored net-negative, yet three "
                f"required probes remained outstanding and were then executed"
            ),
        },
        {
            "distinction": "CERTIFICATION REQUIREMENT SATISFIED != MODEL PASSED",
            "shown_by": (
                f"both worlds end with requirement "
                f"{world_a['certification_requirement_status']}, and adequacy "
                f"{world_a['terminal']['model_adequacy']} versus "
                f"{world_b['terminal']['model_adequacy']}"
            ),
        },
        {
            "distinction": "ECONOMIC NO-ACTION != SCIENTIFIC STOP APPROVED",
            "shown_by": (
                f"both runs pause with no_action_worth_buying; the stop review "
                f"returns {world_a['stop_review']['outcome']} in World A and "
                f"{world_b['stop_review']['outcome']} in World B"
            ),
        },
    ]

    checks = {
        "world_a_parameter_action_bought_first": (
            world_a["selection_trace"][0]["execution_reason"]
            == "POSITIVE_NET_VALUE"
        ),
        "world_b_parameter_action_bought_first": (
            world_b["selection_trace"][0]["execution_reason"]
            == "POSITIVE_NET_VALUE"
        ),
        "world_a_runner_routed_all_required": (
            world_a["routed_by_runner_for_certification"]
            == list(REQUIRED_ACTION_IDS)
        ),
        "world_b_runner_routed_all_required": (
            world_b["routed_by_runner_for_certification"]
            == list(REQUIRED_ACTION_IDS)
        ),
        "world_a_requirement_satisfied": (
            world_a["certification_requirement_status"] == "satisfied"
        ),
        "world_b_requirement_satisfied": (
            world_b["certification_requirement_status"] == "satisfied"
        ),
        "world_a_adequacy_acceptable": (
            world_a["terminal"]["model_adequacy"]
            == "acceptable_for_declared_scope"
        ),
        "world_b_adequacy_inadequate": (
            world_b["terminal"]["model_adequacy"] == "model_space_inadequate"
        ),
        "world_a_stop_approved": (
            world_a["stop_review"]["outcome"]
            == StopReviewOutcome.STOP_APPROVED.value
        ),
        "world_b_stop_rejected": (
            world_b["stop_review"]["outcome"]
            == StopReviewOutcome.STOP_REJECTED.value
        ),
        "world_a_certification_eligible": (
            world_a["terminal"]["scientific_certification"] == "eligible"
        ),
        "world_b_certification_denied": (
            world_b["terminal"]["scientific_certification"] == "not_certifiable"
        ),
        "evsi_unchanged_by_requirement": (
            result["evsi_invariance"]["identical_on_shared_points"]
        ),
        "certification_actions_are_net_negative": all(
            row["net_value"] < 0.0
            for row in result["evsi_invariance"]["certification_action_scores"]
        ),
        "predictions_precede_executions": all(
            row["prediction_precedes_execution"]
            for world in (world_a, world_b)
            for row in world["selection_trace"]
            if row["action_id"] in REQUIRED_ACTION_IDS
        ),
        "invalid_execution_left_belief_unchanged": all(
            world["belief_integrity_probe"]["belief_unchanged"]
            and world["belief_integrity_probe"]["posterior_unchanged"]
            and not world["belief_integrity_probe"]["admitted"]
            for world in (world_a, world_b)
        ),
        "budget_validation_spend_from_reservation": all(
            world["budget"]["spent_validation"] > 0.0
            and world["budget"]["spent_total"] <= TOTAL_BUDGET
            for world in (world_a, world_b)
        ),
        "event_chains_verified": all(
            world["belief"]["event_chain_verified"]
            for world in (world_a, world_b)
        ),
    }
    result["checks"] = checks
    result["verdict"] = (
        "ELECTRICAL V0.1 DEMO VERIFIED"
        if all(checks.values())
        else "ELECTRICAL V0.1 DEMO PARTIALLY VERIFIED"
    )
    result["result_digest"] = result_digest(result)
    return result


#: Fields excluded from the reproducibility digest because they are timing or
#: environment artefacts rather than scientific output.
NONDETERMINISTIC_FIELDS = ("wall_seconds",)


def _strip_nondeterministic(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _strip_nondeterministic(v)
            for k, v in value.items()
            if k not in NONDETERMINISTIC_FIELDS
        }
    if isinstance(value, list):
        return [_strip_nondeterministic(v) for v in value]
    return value


def result_digest(result: dict[str, Any]) -> str:
    """Deterministic digest of the scientific output."""
    payload = _strip_nondeterministic(
        {k: v for k, v in result.items() if k not in ("result_digest",)}
    )
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
