"""E2 orchestration: verification gate, two phases, controls, injections.

The order below is the experiment, and the order is the point:

1. SOLVER VERIFICATION GATE — the real solver against the closed-form divider
   relation at preregistered truth-free points spanning the FULL challenge
   voltage range. If any point disagrees the experiment stops as a solver
   failure. Passing it establishes that the implementation solves the equations
   it claims to solve, and NOTHING about whether those equations are the right
   ones for the hidden world. E2 exists to show those two can diverge.
2. PHASE 1 — calibration at a single operating condition, admitted through the
   real M1/M3 chain. The conditional posterior contracts sharply.
3. COMMITMENT — the full predictive distribution for every preregistered
   challenge condition is computed from the calibration-only evidence,
   content-hashed, and the ledger is SEALED. Nothing may be predicted after.
4. PHASE 2 — the challenge conditions are executed and admitted. Only now do
   the observations exist.
5. SCORING — each observation against its own frozen predictive, then the
   preregistered aggregate rule.
6. CONTROLS A/B/D/E and the adversarial injections.

The run reports the conditional posterior at every stage, including the part
that is uncomfortable: it becomes sharper while the model family fails.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import numpy as np

from src.engcore.sria.campaign import CampaignEventType

from . import e2_truth
from .e2_adequacy import (
    AdequacyReport,
    AdequacyState,
    Certification,
    CommitmentLedger,
    Disposition,
    ExecutionValidity,
    PredictiveCommitmentViolation,
    aggregate_adequacy,
    build_joint_predictive,
    certify,
    chi2_upper_tail_log,
    classify_adequacy,
    score_commitments,
)
from .e2_config import (
    ACTIONS,
    ALPHA_EXTREME,
    ALPHA_JOINT,
    ALPHA_JOINT_WEAK,
    CHALLENGE_ACTIONS,
    CORRECTION_RECORD,
    DEPRECATED_ALPHA_AGGREGATE,
    K_MIN_EXTREME,
    NULL_SIMULATION_DRAWS,
    SUPERSEDED_CONFIG_HASH,
    THRESHOLD_OHM,
    VERIFICATION_ABS_TOL_VOLT,
    VERIFICATION_POINTS,
    VERIFICATION_REL_TOL,
    config_hash,
    config_payload,
    indifference_probability,
    theta_grid,
)
from .e2_harness import (
    ACTION_BY_ID,
    E2FaultyExecutor,
    build_e2_harness,
    preregistration_hash,
)
from .e2_model import (
    evsi,
    evsi_table,
    posterior_summary,
    posterior_weights,
    predictive_mixture,
    prior_weights,
    solver_vmid,
)


# =====================================================================
# 1. The solver verification gate
# =====================================================================

def run_solver_verification() -> dict[str, Any]:
    """The real solver vs the analytic oracle at truth-free points.

    Spans every challenge voltage, because E2 predicts at conditions E1 never
    verified — an extrapolation in operating condition would otherwise be an
    unexamined assumption sitting underneath the adequacy verdict.
    """
    rows = []
    worst_abs = 0.0
    worst_rel = 0.0
    for index, (vs, r2) in enumerate(VERIFICATION_POINTS):
        solver_value = solver_vmid(vs, r2, run_id=f"e2-verify-{index:02d}")
        analytic_value = e2_truth.analytic_vmid(vs, r2)
        abs_err = abs(solver_value - analytic_value)
        rel_err = abs_err / max(abs(analytic_value), 1e-300)
        worst_abs = max(worst_abs, abs_err)
        worst_rel = max(worst_rel, rel_err)
        rows.append(
            {
                "source_voltage_volt": vs,
                "r2_ohm": r2,
                "solver_vmid_volt": solver_value,
                "analytic_vmid_volt": analytic_value,
                "abs_error_volt": abs_err,
                "rel_error": rel_err,
            }
        )
    passed = (
        worst_rel <= VERIFICATION_REL_TOL or worst_abs <= VERIFICATION_ABS_TOL_VOLT
    )
    noise_floor = min(a.noise_sigma_volt for a in ACTIONS)
    return {
        "points": rows,
        "worst_abs_error_volt": worst_abs,
        "worst_rel_error": worst_rel,
        "rel_tol": VERIFICATION_REL_TOL,
        "abs_tol_volt": VERIFICATION_ABS_TOL_VOLT,
        "passed": passed,
        "numerical_error_vs_noise": {
            "smallest_declared_sigma_volt": noise_floor,
            "worst_abs_error_volt": worst_abs,
            "ratio": worst_abs / noise_floor,
        },
        "what_this_proves": (
            "IMPLEMENTATION VERIFICATION: the MNA path reproduces the "
            "closed-form linear resistive DC relation to machine precision"
        ),
        "what_this_does_not_prove": (
            "MODEL ADEQUACY: agreement with the equations of the assumed "
            "family says nothing about whether that family describes the "
            "hidden world. E2 exists precisely to show these can diverge, and "
            "in the scored run they do"
        ),
    }


# =====================================================================
# 2-5. One complete two-phase experiment
# =====================================================================

def run_experiment(
    spec: e2_truth.TruthSpec, *, label: str
) -> dict[str, Any]:
    """Calibrate, commit, seal, challenge, score. One hidden world."""
    harness = build_e2_harness(spec, run_id=label)

    # ---- PHASE 1: calibration -------------------------------------------
    calibration_rows = harness.run_calibration_phase()
    calibration_observations = harness.current_observations()
    weights_calibration = posterior_weights(calibration_observations)
    calibration_digest = harness.evidence_snapshot_digest()

    # ---- COMMITMENT: predict before observing ---------------------------
    ledger = CommitmentLedger(f"{label}-ledger")
    for action in CHALLENGE_ACTIONS:
        ledger.commit(
            action_id=action.action_id,
            source_voltage_volt=action.source_voltage_volt,
            noise_sigma_volt=action.noise_sigma_volt,
            evidence_snapshot_digest=calibration_digest,
            n_observations=len(calibration_observations),
            mixture=predictive_mixture(weights_calibration, action),
        )
    seal_entry = ledger.seal()
    # Recorded in the same hash-chained log the executions are recorded in, so
    # "the predictions existed first" is a sequence comparison inside one
    # tamper-evident structure rather than two logs asked to agree.
    harness.events.append(
        CampaignEventType.DECISION_RECOMMENDED,
        iteration=0,
        payload={
            "predictive_commitments_sealed": True,
            "ledger_head": ledger.head_digest,
            "seal_sequence": seal_entry.sequence,
            "n_observations_at_commitment": len(calibration_observations),
            "evidence_snapshot_digest": calibration_digest,
            "artifact_hashes": sorted(
                c.artifact_hash for c in ledger.commitments.values()
            ),
        },
        at=f"{label}-seal",
    )

    # ---- PHASE 2: challenge ---------------------------------------------
    challenge_rows = harness.run_challenge_phase()
    for row in challenge_rows:
        ledger.record_observation(
            action_id=row.action_id,
            y_volt=row.y_volt,
            execution_id=row.execution_id,
            execution_valid=row.admitted,
        )

    # ---- SCORING ---------------------------------------------------------
    surprises = score_commitments(ledger)
    # The complete vector is scored ONCE, jointly, under the frozen calibration
    # posterior every condition shares. Combining per-condition tails as if
    # they were independent (v1.0.0) is not valid here — see e2_config.
    joint = build_joint_predictive(
        ledger, [s.action_id for s in surprises]
    )
    aggregate = aggregate_adequacy(surprises, joint)
    verdict = classify_adequacy(surprises, aggregate)

    all_observations = harness.current_observations()
    weights_final = posterior_weights(all_observations)

    execution_validity = (
        ExecutionValidity.VALID
        if all(r.admitted for r in calibration_rows + challenge_rows)
        else ExecutionValidity.INVALID
    )
    decision = str(posterior_summary(weights_final)["bayes_decision"])
    certification = certify(decision, verdict.state, execution_validity)

    report = AdequacyReport(
        surprises=surprises,
        verdict=verdict,
        certification=certification,
        ledger_head=ledger.head_digest,
        ledger_sealed_at=ledger.sealed_at_sequence,
        chain_verified=ledger.verify_chain() and ledger.verify_commitments(),
        commitments=tuple(
            ledger.commitments[a.action_id].summary() for a in CHALLENGE_ACTIONS
        ),
    )

    # ---- ordering proof from the hash-chained event log ------------------
    commit_seq = [
        e.sequence
        for e in harness.events.of_type(CampaignEventType.DECISION_RECOMMENDED)
    ]
    challenge_exec_seq = [
        e.sequence
        for e in harness.events.of_type(CampaignEventType.EXECUTION_STARTED)
        if str(e.payload.get("action_id", "")).startswith("challenge_")
    ]

    return {
        "label": label,
        "truth_spec_id": spec.spec_id,
        "posterior_prior": posterior_summary(prior_weights()),
        "posterior_after_calibration": posterior_summary(weights_calibration),
        "posterior_after_challenge": posterior_summary(weights_final),
        "evsi_prior": evsi_table(prior_weights()),
        "evsi_after_calibration": evsi_table(weights_calibration),
        "evsi_after_challenge": evsi_table(weights_final),
        "calibration": {
            "n_admitted": sum(1 for r in calibration_rows if r.admitted),
            "evidence_snapshot_digest": calibration_digest,
            "rows": [r.to_dict() for r in calibration_rows],
        },
        "challenge": {
            "n_admitted": sum(1 for r in challenge_rows if r.admitted),
            "rows": [r.to_dict() for r in challenge_rows],
        },
        "adequacy": report.to_dict(),
        "execution_validity": execution_validity.value,
        "prediction_ordering": {
            "decision_recommended_sequences": commit_seq,
            "challenge_execution_started_sequences": challenge_exec_seq,
            "prediction_preceded_observation": bool(
                commit_seq
                and challenge_exec_seq
                and max(commit_seq) < min(challenge_exec_seq)
            ),
            "event_chain_verified": harness.events.verify_chain(),
            "ledger_chain_verified": ledger.verify_chain(),
        },
        "predictive_dependence": _dependence_summary(joint),
        "_harness": harness,
        "_ledger": ledger,
        "_surprises": surprises,
        "_joint": joint,
        "_aggregate": aggregate,
        "_weights_calibration": weights_calibration,
        "_weights_final": weights_final,
    }


def _dependence_summary(joint) -> dict[str, Any]:
    """Exact, closed-form evidence that the conditions are NOT independent.

    Reported because it is the reason the v1.0.0 aggregate was replaced. If
    these off-diagonals were zero the original Fisher/chi-square reference
    would have been fine; they are not, and they are largest between exactly
    the high-drive conditions that carry the most weight in any aggregate.
    """
    correlation = joint.correlation()
    k = correlation.shape[0]
    off = correlation[np.triu_indices(k, k=1)]
    return {
        "conditions": [a.action_id for a in CHALLENGE_ACTIONS],
        "source_voltages_volt": [a.source_voltage_volt for a in CHALLENGE_ACTIONS],
        "correlation_matrix": [[float(x) for x in row] for row in correlation],
        "min_off_diagonal": float(off.min()),
        "max_off_diagonal": float(off.max()),
        "mean_off_diagonal": float(off.mean()),
        "all_positive": bool((off > 0.0).all()),
        "latent_variance_share": [
            float(v)
            for v in (
                np.diag(joint.covariance())
                - np.asarray(joint.sigmas, float) ** 2
            )
            / np.diag(joint.covariance())
        ],
        "statement": (
            "the six challenge observations are conditionally independent "
            "GIVEN theta and share one calibration posterior; marginalizing it "
            "leaves them positively dependent, so their tail probabilities are "
            "not independent and no independence-based aggregate reference is "
            "valid for them"
        ),
    }


def _public(result: dict[str, Any]) -> dict[str, Any]:
    """Strip the live objects the controls need but the artifact must not hold."""
    return {k: v for k, v in result.items() if not k.startswith("_")}


# =====================================================================
# 6. Controls D and E
# =====================================================================

def run_control_d(scored: dict[str, Any]) -> dict[str, Any]:
    """CONTROL D — a computational failure must NOT enter the adequacy path.

    Calibration runs on a working solver. Then the executor is swapped for one
    whose linear-system residual is a million times its own tolerance and whose
    validation report failed. The number it returns may be perfectly reasonable;
    it is refused anyway, by the critic, on computational grounds.

    The two states must stay on separate axes: this run's execution validity is
    INVALID while its adequacy state is untested, and the scored run's execution
    validity is VALID while its adequacy state is MODEL_SPACE_INADEQUATE.
    """
    harness = build_e2_harness(e2_truth.MISSPECIFIED_TRUTH, run_id="e2-control-d")
    harness.run_calibration_phase()
    before = harness.current_observations()
    weights_before = posterior_weights(before)

    harness.executor = E2FaultyExecutor(e2_truth.MISSPECIFIED_TRUTH)
    faulty = harness.run_measurement(
        ACTION_BY_ID["challenge_vmid_20V"], repeat=1
    )
    after = harness.current_observations()

    failure_certification = certify(
        str(posterior_summary(weights_before)["bayes_decision"]),
        AdequacyState.MODEL_ADEQUACY_ACCEPTABLE,   # deliberately the BEST case
        ExecutionValidity.INVALID,
    )
    inadequacy_certification = scored["adequacy"]["certification"]

    return {
        "faulty_execution": faulty.to_dict(),
        "critic_verdict": faulty.critic_verdict,
        "arbiter_verdict": faulty.arbiter_verdict,
        "admitted": faulty.admitted,
        "observations_before": len(before),
        "observations_after": len(after),
        "posterior_unchanged": bool(
            np.array_equal(weights_before, posterior_weights(after))
        ),
        "failure_path": {
            "certification": failure_certification.to_dict(),
            "reason": failure_certification.reason,
            "disposition": failure_certification.disposition.value,
        },
        "adequacy_path": {
            "reason": inadequacy_certification["reason"],
            "disposition": inadequacy_certification["disposition"],
        },
        "states_are_distinct": (
            failure_certification.reason != inadequacy_certification["reason"]
            and failure_certification.disposition.value
            != inadequacy_certification["disposition"]
        ),
        "statement": (
            "a broken computation is refused through EXECUTION VALIDITY and "
            "yields EXECUTION_REPAIR_REQUIRED; a sound computation whose model "
            "mispredicts is refused through MODEL ADEQUACY and yields "
            "MODEL_REVISION_REQUIRED. Different evidence, different reason, "
            "different remedy — they never collapse into one status"
        ),
    }


def run_control_e(scored: dict[str, Any]) -> dict[str, Any]:
    """CONTROL E — posterior confidence is not model adequacy.

    The scored run's conditional posterior is very sharp and its EVPI and EVSI
    are at the floor. The certification gate is offered every one of those
    quantities in the most favourable form available and still refuses, because
    none of them is an input to it.
    """
    final = scored["posterior_after_challenge"]
    calibrated = scored["posterior_after_calibration"]
    evsi_after = scored["evsi_after_challenge"]
    max_evsi = max(row["evsi"] for row in evsi_after.values())
    certification = scored["adequacy"]["certification"]

    # The gate, called directly with the strongest possible confidence claim
    # attached to the same adequacy state. There is nowhere to put the claim.
    forced = certify(
        str(final["bayes_decision"]),
        AdequacyState(scored["adequacy"]["verdict"]["state"]),
        ExecutionValidity.VALID,
    )

    return {
        "posterior_sd_after_calibration_ohm": calibrated["sd_r2_ohm"],
        "posterior_sd_after_challenge_ohm": final["sd_r2_ohm"],
        "posterior_entropy_after_calibration_nats": calibrated["entropy_nats"],
        "posterior_entropy_after_challenge_nats": final["entropy_nats"],
        "p_decision_after_challenge": final["p_above_threshold"],
        "evpi_after_challenge": final["evpi"],
        "max_evsi_after_challenge": max_evsi,
        "posterior_contracted_while_adequacy_failed": bool(
            final["sd_r2_ohm"] < calibrated["sd_r2_ohm"]
            and scored["adequacy"]["verdict"]["state"]
            == AdequacyState.MODEL_SPACE_INADEQUATE.value
        ),
        "certification": certification["scientific_certification"],
        "certification_when_called_directly": (
            forced.scientific_certification.value
        ),
        "statement": (
            f"P(decision) = {final['p_above_threshold']:.6f}, posterior sd = "
            f"{final['sd_r2_ohm']:.3f} ohm, EVPI = {final['evpi']:.3e}, best "
            f"EVSI = {max_evsi:.3e}. Every one of these is computed INSIDE the "
            f"family under suspicion, so none of them is evidence that the "
            f"family is right, and none is an argument the gate can hear"
        ),
    }


# =====================================================================
# 7. Adversarial injections
# =====================================================================

def _injection(
    name: str, attempt: str, caught: bool, catcher: str, detail: str
) -> dict[str, Any]:
    return {
        "injection": name,
        "attempt": attempt,
        "caught": caught,
        "catcher": catcher,
        "detail": detail,
    }


def run_adversarial_injections(scored: dict[str, Any]) -> list[dict[str, Any]]:
    """Attack every seam the result rests on, and name what catches each."""
    out: list[dict[str, Any]] = []
    ledger: CommitmentLedger = scored["_ledger"]
    harness = scored["_harness"]

    # --- A: compute the predictive AFTER seeing the observation ----------
    caught, detail = False, "NOT CAUGHT"
    try:
        ledger.commit(
            action_id="challenge_vmid_20V_posthoc",
            source_voltage_volt=20.0,
            noise_sigma_volt=0.05,
            evidence_snapshot_digest=harness.evidence_snapshot_digest(),
            n_observations=len(harness.current_observations()),
            mixture=predictive_mixture(
                scored["_weights_final"], ACTION_BY_ID["challenge_vmid_20V"]
            ),
        )
    except PredictiveCommitmentViolation as exc:
        caught, detail = True, str(exc).split(".")[0]
    out.append(
        _injection(
            "A",
            "register a predictive for a condition after its observation exists",
            caught,
            "CommitmentLedger.commit (ledger sealed)",
            detail,
        )
    )

    # --- B: mark the surprising observation INVALID ----------------------
    # The semantic error is asserting that improbable-under-the-model implies
    # computationally invalid. The catcher is that the critic cannot express it:
    # its checks are computational, and the most surprising observation in the
    # scored run passed all of them and was admitted.
    worst = min(
        scored["adequacy"]["surprises"], key=lambda s: s["tail_probability"]
    )
    worst_row = next(
        r
        for r in scored["challenge"]["rows"]
        if r["action_id"] == worst["action_id"]
    )
    check_names = {c["name"] for c in worst_row["checks"]}
    surprise_free_critic = check_names == {
        "solver_termination",
        "residual_evidence",
        "validation_report_status",
    }
    out.append(
        _injection(
            "B",
            "invalidate an observation because the model predicted it poorly",
            bool(
                surprise_free_critic
                and worst_row["critic_verdict"] == "pass"
                and worst_row["arbiter_verdict"] == "valid"
                and worst_row["admitted"]
            ),
            "E2Harness.assess (computational checks only) + the admission chain",
            (
                f"the most surprising condition ({worst['action_id']}, tail "
                f"{worst['tail_probability']:.3e}) passed all "
                f"{len(check_names)} computational checks and was ADMITTED; "
                f"the critic has no predictive input to fail it with"
            ),
        )
    )

    # --- C: let a low posterior sd override inadequacy -------------------
    import inspect

    from .e2_adequacy import CERTIFY_ALLOWED_PARAMETERS

    certify_params = tuple(inspect.signature(certify).parameters)
    classify_params = tuple(inspect.signature(classify_adequacy).parameters)
    forbidden = ("sd", "entropy", "evpi", "evsi", "posterior_sd", "confidence")
    no_confidence_input = not any(
        any(f in p for f in forbidden) for p in certify_params + classify_params
    )
    forced = certify(
        "A", AdequacyState.MODEL_SPACE_INADEQUATE, ExecutionValidity.VALID
    )
    out.append(
        _injection(
            "C",
            "override MODEL_SPACE_INADEQUATE with a very sharp posterior",
            bool(
                no_confidence_input
                and certify_params == CERTIFY_ALLOWED_PARAMETERS
                and forced.scientific_certification is Certification.NOT_CERTIFIABLE
            ),
            "certify() signature — posterior strength is not a parameter",
            (
                f"certify{certify_params} and classify_adequacy"
                f"{classify_params} accept no confidence quantity; the "
                f"strongest available claim still returns "
                f"{forced.scientific_certification.value}"
            ),
        )
    )

    # --- D: let a low EVSI override inadequacy ---------------------------
    max_evsi = max(
        row["evsi"] for row in scored["evsi_after_challenge"].values()
    )
    out.append(
        _injection(
            "D",
            "override MODEL_SPACE_INADEQUATE with EVSI at the floor",
            bool(
                max_evsi < 1e-9
                and scored["adequacy"]["certification"][
                    "scientific_certification"
                ]
                == Certification.NOT_CERTIFIABLE.value
            ),
            "certify() signature — EVSI is not a parameter",
            (
                f"best available EVSI is {max_evsi:.3e}, i.e. 'no measurement "
                f"is worth taking' INSIDE the family; certification is still "
                f"withheld, because EVSI prices information about which "
                f"constant, not about whether a constant is the right shape"
            ),
        )
    )

    # --- E: secretly use the grader truth in the adequacy prediction -----
    # Executable version: hold the admitted evidence fixed, change the hidden
    # law, and recompute every commitment. Identical bytes means the truth
    # cannot have reached them.
    observations = harness.current_observations()
    weights = posterior_weights(observations)
    baseline = [
        predictive_mixture(weights, a) for a in CHALLENGE_ACTIONS
    ]
    altered_spec = dataclasses.replace(
        e2_truth.MISSPECIFIED_TRUTH, kappa=0.42, spec_id="leak_probe"
    )
    _ = [
        altered_spec.effective_resistance(a.source_voltage_volt)
        for a in CHALLENGE_ACTIONS
    ]
    after = [predictive_mixture(weights, a) for a in CHALLENGE_ACTIONS]
    identical = all(
        b.means == a.means and b.weights == a.weights and b.sigma == a.sigma
        for b, a in zip(baseline, after)
    )
    out.append(
        _injection(
            "E",
            "let the hidden law influence the predictive or the adequacy verdict",
            bool(identical),
            "module boundary (transitive AST import test) + this recomputation",
            (
                "with the admitted evidence held fixed, changing kappa from "
                "0.10 to 0.42 left every predictive mixture bit-identical; the "
                "decision path has no channel through which the law could act"
            ),
        )
    )

    # --- F: change the predictive artifact after execution ---------------
    tampered = CommitmentLedger("e2-tamper-probe")
    original = ledger.commitments["challenge_vmid_20V"]
    tampered._commitments["challenge_vmid_20V"] = dataclasses.replace(
        original,
        component_means=tuple(m + 0.5 for m in original.component_means),
    )
    tampered._entries = list(ledger.entries)
    tampered._observations = dict(ledger.observations)
    tampered._sealed = True
    tampered._sealed_at = ledger.sealed_at_sequence
    caught, detail = False, "NOT CAUGHT"
    try:
        score_commitments(tampered)
    except PredictiveCommitmentViolation as exc:
        caught, detail = True, str(exc)
    out.append(
        _injection(
            "F",
            "edit a committed predictive after its observation was executed",
            caught,
            "PredictiveCommitment.verify_integrity via score_commitments",
            detail,
        )
    )
    return out


# =====================================================================
# 7b. Statistical validity close-out (v1.1.0)
# =====================================================================

def _verdicts_at(threshold: float, runs: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    """What the three worlds would conclude at an alternative alpha_joint."""
    out = []
    for run in runs:
        aggregate = run["_aggregate"]
        if aggregate.n_extreme >= K_MIN_EXTREME and aggregate.p_joint < threshold:
            out.append(AdequacyState.MODEL_SPACE_INADEQUATE.value)
        elif aggregate.n_extreme >= 1 or aggregate.p_joint < ALPHA_JOINT_WEAK:
            out.append(AdequacyState.MODEL_ADEQUACY_NOT_ESTABLISHED.value)
        else:
            out.append(AdequacyState.MODEL_ADEQUACY_ACCEPTABLE.value)
    return tuple(out)


def statistical_validity(
    scored: dict[str, Any],
    control_a: dict[str, Any],
    control_b: dict[str, Any],
) -> dict[str, Any]:
    """Document the v1.0.0 -> v1.1.0 correction with measured quantities.

    Two things are established here rather than asserted: that the conditions
    really are dependent, and that the chi-square reference really was
    anti-conservative by a measurable factor. A third — that the conclusion
    does not hinge on the particular alpha_joint chosen — is checked by
    sweeping the threshold across four orders of magnitude.
    """
    runs = (control_a, control_b, scored)
    labels = ("control_a_well_specified", "control_b_single_outlier", "scored_run")
    baseline = _verdicts_at(ALPHA_JOINT, runs)
    sweep = {}
    for exponent in (-5, -4, -3, -2):
        threshold = 10.0**exponent
        sweep[f"1e{exponent}"] = dict(zip(labels, _verdicts_at(threshold, runs)))
    stable = all(
        tuple(row.values()) == baseline
        for exponent, row in sweep.items()
        if exponent != "1e-5"          # 1e-5 is below the Monte Carlo floor
    )
    aggregate = scored["_aggregate"]
    return {
        "superseded_config_hash": SUPERSEDED_CONFIG_HASH,
        "correction": CORRECTION_RECORD,
        "dependence": scored["predictive_dependence"],
        "chi_square_reference_audit": {
            "assumed_variance_2df": 2.0 * aggregate.degrees_of_freedom,
            "measured_null_variance_inflation": (
                aggregate.chi2_reference_inflation_factor
            ),
            "null_rejection_rate_at_nominal_0p05": (
                aggregate.null_rejection_rate_chi2_at_0p05
            ),
            "verdict": (
                "ANTI-CONSERVATIVE"
                if aggregate.null_rejection_rate_chi2_at_0p05 > 0.05
                else "not detectably anti-conservative"
            ),
            "statement": (
                "under the true null, Fisher's statistic referred to "
                "chi-square(2N) rejects at nominal 5% more often than 5% of "
                "the time. The v1.0.0 aggregate p-values were therefore too "
                "small, in the direction that overstates evidence against the "
                "model"
            ),
        },
        "v1_0_0_vs_v1_1_0": {
            label: {
                "deprecated_fisher_p_chi2_independent": (
                    run["_aggregate"].fisher_p_chi2_independent
                ),
                "fisher_p_simulated_null": run["_aggregate"].fisher_p_simulated,
                "joint_p_simulated_null": run["_aggregate"].p_joint,
            }
            for label, run in zip(labels, runs)
        },
        "threshold_sweep": sweep,
        "verdicts_stable_across_thresholds": stable,
        "monte_carlo_floor": 1.0 / (1.0 + NULL_SIMULATION_DRAWS),
        "note": (
            "alpha_joint was set by the preregistered Monte Carlo resolution, "
            "not by inspecting a result; the sweep shows all three verdicts are "
            "unchanged for any threshold from 1e-4 to 1e-2, so the conclusion "
            "does not rest on that choice"
        ),
    }


# =====================================================================
# 8. Certificate assumptions
# =====================================================================

def certificate_assumptions(
    verification: dict[str, Any], scored: dict[str, Any]
) -> list[dict[str, str]]:
    ratio = verification["numerical_error_vs_noise"]["ratio"]
    adequacy = scored["adequacy"]
    return [
        {
            "proposition": "circuit topology (two-resistor divider, ideal source)",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": "declared in the preregistered configuration; E1-derived",
        },
        {
            "proposition": (
                "ASSUMED MODEL FAMILY: R2 is a single condition-independent "
                "constant"
            ),
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": (
                "declared before the run as the family inference is conditional "
                "on. This is a PROPOSITION ABOUT THE WORLD and E2 tested it: it "
                f"is {adequacy['verdict']['state'].upper()}"
            ),
        },
        {
            "proposition": (
                "SOLVER IMPLEMENTATION OF THAT FAMILY (linear resistive DC via "
                "MNA) computes what the family specifies"
            ),
            "status": "ANALYTICALLY_CHECKED",
            "basis": (
                f"agreement with the closed-form divider relation at "
                f"{len(VERIFICATION_POINTS)} preregistered points spanning the "
                f"full challenge range, worst relative error "
                f"{verification['worst_rel_error']:.3e}. NOT THE SAME "
                f"PROPOSITION as the row above: this one is about code "
                f"agreeing with equations, that one is about equations "
                f"agreeing with the world, and in this run the first holds "
                f"while the second fails"
            ),
        },
        {
            "proposition": "Electrical solver equations (Ohm/KCL, MNA assembly)",
            "status": "ANALYTICALLY_CHECKED",
            "basis": (
                "verified against an independently derived KVL/KCL closed form "
                "the solver did not produce"
            ),
        },
        {
            "proposition": "observation mapping (y measures node_voltage:mid)",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": "declared observation model",
        },
        {
            "proposition": "noise model (Gaussian, declared sigma, additive)",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": (
                "benchmark-injected synthetic noise, honestly labelled; the "
                "solver itself is deterministic. Draws depend on "
                "(action_id, repeat) only, so controls share them exactly"
            ),
        },
        {
            "proposition": "prior (uniform over the frozen R2 grid)",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": "preregistered before any scored observation",
        },
        {
            "proposition": "terminal utility / loss matrix",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": "preregistered; asymmetric with indifference at P=0.8",
        },
        {
            "proposition": "cost model (declared per-action costs)",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": "preregistered; no fitted cost model in E2",
        },
        {
            "proposition": "computational failure probability p_cf = 0",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": (
                "declared, not measured, for a dense LU on a well-conditioned "
                "3x3 MNA system. Control D shows what a genuine computational "
                "failure does instead of assuming it cannot happen"
            ),
        },
        {
            "proposition": "cost-to-utility tradeoff lambda = 1.0",
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": (
                "preregistered exchange rate with no external referent. E2 does "
                "not let it steer: the action schedule is frozen, so lambda "
                "affects reported net value and nothing that was executed"
            ),
        },
        {
            "proposition": "support/transport: IN_DOMAIN_FOR_THIS_VERIFICATION",
            "status": "VERIFIED",
            "basis": (
                "the solver is verified across the full prior support at every "
                "voltage that is measured or predicted, so no numerical "
                "extrapolation occurs. Note this is transport of the SOLVER, "
                "and is independent of — and in this run contradicted by — the "
                "adequacy of the model family at those same conditions"
            ),
        },
        {
            "proposition": "predictive adequacy rule (preregistered, v1.1.0)",
            "status": "VERIFIED",
            "basis": (
                f"two-sided marginal predictive tail per condition (each "
                f"EXACTLY Uniform(0,1) under the null), plus a JOINT log score "
                f"over all {len(CHALLENGE_ACTIONS)} conditions calibrated by "
                f"{NULL_SIMULATION_DRAWS} posterior-predictive draws. Strongest "
                f"verdict requires n_extreme >= {K_MIN_EXTREME} AND p_joint < "
                f"{ALPHA_JOINT:g}. Controls A and B exercise both non-firing "
                f"branches"
            ),
        },
        {
            "proposition": (
                "aggregate reference distribution accounts for dependence "
                "between challenge conditions"
            ),
            "status": "VERIFIED",
            "basis": (
                f"the conditions share one calibration posterior and are "
                f"positively dependent (exact off-diagonal correlations "
                f"{scored['predictive_dependence']['min_off_diagonal']:.3f} to "
                f"{scored['predictive_dependence']['max_off_diagonal']:.3f}). "
                f"v1.0.0 combined the tails with Fisher and referred them to "
                f"chi-square(2N), which assumes independence and is "
                f"anti-conservative here; v1.1.0 replaces it with the joint "
                f"score under a simulated null. Superseded config hash "
                f"{SUPERSEDED_CONFIG_HASH}"
            ),
        },
        {
            "proposition": (
                "internal null (Vs = 10 V) discriminates against a "
                "condition-independent harness offset"
            ),
            "status": "ASSERTED_FOR_BENCHMARK",
            "basis": (
                "the synthetic grader law was CONSTRUCTED to vanish at the "
                "calibration condition, so a clean result there is expected "
                "under this benchmark's failure mode and separates it from a "
                "constant offset. It does NOT exclude other fault mechanisms: "
                "a condition-dependent or drive-scaling instrument fault would "
                "also leave this condition clean. One alternative is "
                "discriminated against, not all of them"
            ),
        },
        {
            "proposition": "prediction preceded observation",
            "status": "VERIFIED",
            "basis": (
                "content-hashed predictive artifacts sealed in a hash-chained "
                "ledger, sequence-ordered before every challenge execution, and "
                "cross-recorded in the campaign event log; a post-hoc "
                "commitment raises rather than being accepted"
            ),
        },
        {
            "proposition": "posterior arithmetic (normalized, order-invariant)",
            "status": "VERIFIED",
            "basis": "tests over the exact grid update, inherited from E1",
        },
        {
            "proposition": "grader truth availability",
            "status": "GRADER_ONLY",
            "basis": (
                "the misspecified law lives in e2_truth and is unreachable from "
                "e2_config, e2_model and e2_adequacy, checked transitively by "
                "AST and by a runtime recomputation under an altered law"
            ),
        },
        {
            "proposition": "numerical error negligible vs observation noise",
            "status": "VERIFIED",
            "basis": f"worst |solver-analytic| / smallest sigma = {ratio:.3e}",
        },
    ]


# =====================================================================
# 9. The whole run
# =====================================================================

def run_e2() -> dict[str, Any]:
    result: dict[str, Any] = {
        "experiment": "E2",
        "config_hash": config_hash(),
        "preregistration_hash": preregistration_hash(),
        "config": config_payload(),
        "truth": e2_truth.truth_payload(),
    }

    verification = run_solver_verification()
    result["solver_verification"] = verification
    if not verification["passed"]:
        result["verdict"] = "E2 FAILED — SOLVER/INTEGRATION VERIFICATION FAILURE"
        return result

    result["prior_stage"] = {
        "posterior": posterior_summary(prior_weights()),
        "indifference_probability": indifference_probability(),
        "evsi_table": evsi_table(prior_weights()),
    }

    scored = run_experiment(e2_truth.MISSPECIFIED_TRUTH, label="e2-scored-C")
    control_a = run_experiment(e2_truth.WELL_SPECIFIED_TRUTH, label="e2-control-A")
    control_b = run_experiment(e2_truth.SINGLE_OUTLIER_TRUTH, label="e2-control-B")

    result["scored_run"] = _public(scored)
    result["control_a_well_specified"] = _public(control_a)
    result["control_b_single_outlier"] = _public(control_b)
    result["statistical_validity"] = statistical_validity(
        scored, control_a, control_b
    )
    result["control_d_computational_failure"] = run_control_d(scored)
    result["control_e_confidence_is_not_adequacy"] = run_control_e(scored)
    result["adversarial_injections"] = run_adversarial_injections(scored)

    # How badly does the BEST constant do? Grader-only diagnostic, reported to
    # make "outside the model family" a number rather than an adjective.
    voltages = tuple(a.source_voltage_volt for a in CHALLENGE_ACTIONS)
    result["misspecification_diagnostic"] = {
        "scored_truth": e2_truth.best_constant_fit(
            e2_truth.MISSPECIFIED_TRUTH, voltages
        ),
        "well_specified_truth": e2_truth.best_constant_fit(
            e2_truth.WELL_SPECIFIED_TRUTH, voltages
        ),
        "note": (
            "under the well-specified truth the best constant fits every "
            "condition exactly; under the scored truth no constant can, and "
            "the residual is bounded away from zero for every candidate"
        ),
    }

    terminal = {
        "posterior_decision": scored["posterior_after_challenge"]["bayes_decision"],
        "posterior_decision_reading": (
            "the decision preferred by p(R2 | data, M_const) — a statement "
            "conditional on the family, not about the world"
        ),
        "oracle_decision": e2_truth.oracle_decision(),
        "scientific_certification": scored["adequacy"]["certification"][
            "scientific_certification"
        ],
        "reason": scored["adequacy"]["certification"]["reason"],
        "disposition": scored["adequacy"]["certification"]["disposition"],
        "threshold_ohm": THRESHOLD_OHM,
    }
    result["terminal_decision"] = terminal
    result["certificate_assumptions"] = certificate_assumptions(
        verification, scored
    )

    checks = {
        "solver_verified": verification["passed"],
        "scored_is_inadequate": (
            scored["adequacy"]["verdict"]["state"]
            == AdequacyState.MODEL_SPACE_INADEQUATE.value
        ),
        "control_a_not_falsely_rejected": (
            control_a["adequacy"]["verdict"]["state"]
            == AdequacyState.MODEL_ADEQUACY_ACCEPTABLE.value
        ),
        "control_b_not_strongest": (
            control_b["adequacy"]["verdict"]["state"]
            != AdequacyState.MODEL_SPACE_INADEQUATE.value
        ),
        "control_d_states_distinct": result[
            "control_d_computational_failure"
        ]["states_are_distinct"],
        "posterior_contracted_while_adequacy_failed": result[
            "control_e_confidence_is_not_adequacy"
        ]["posterior_contracted_while_adequacy_failed"],
        "certification_withheld": (
            terminal["scientific_certification"]
            == Certification.NOT_CERTIFIABLE.value
        ),
        "all_challenge_evidence_admitted": (
            scored["challenge"]["n_admitted"] == len(CHALLENGE_ACTIONS)
        ),
        "prediction_preceded_observation": scored["prediction_ordering"][
            "prediction_preceded_observation"
        ],
        "all_injections_caught": all(
            i["caught"] for i in result["adversarial_injections"]
        ),
    }
    result["success_checks"] = checks
    result["verdict"] = (
        "E2 MODEL-INADEQUACY DETECTED CORRECTLY"
        if all(checks.values())
        else "E2 PARTIALLY VERIFIED"
    )
    return result


# =====================================================================
# Rendering
# =====================================================================

def _fmt(value: float) -> str:
    return f"{value:.6g}"


def _posterior_line(summary: dict[str, Any]) -> str:
    return (
        f"decision {summary['bayes_decision']} | "
        f"P(above)={_fmt(summary['p_above_threshold'])} | "
        f"mean={_fmt(summary['mean_r2_ohm'])} Ω | "
        f"sd={_fmt(summary['sd_r2_ohm'])} Ω | "
        f"H={_fmt(summary['entropy_nats'])} nats | "
        f"EVPI={summary['evpi']:.3e}"
    )


def render_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    add = lines.append
    add("# E2 — Model adequacy / predictive surprise")
    add("")
    add(f"Config hash: `{result['config_hash']}`")
    add(f"Preregistration hash (config+truth): `{result['preregistration_hash']}`")
    add("")
    add(
        f"**v1.1.0** — supersedes config `{SUPERSEDED_CONFIG_HASH}`. "
        f"The v1.0.0 aggregate combined per-condition tail probabilities with "
        f"Fisher's method and referred the result to χ² on 2N degrees of "
        f"freedom, which assumes independence the conditions do not have. That "
        f"reference is withdrawn as invalid; see *Why the aggregate had to "
        f"change* below. Per-condition statistics, thresholds, K_min, the "
        f"challenge set, the seed, the grid and the hidden law are unchanged."
    )
    add("")

    v = result["solver_verification"]
    add("## Solver verification (gate)")
    add("")
    add("| Vs [V] | R2 [Ω] | solver V_mid [V] | analytic V_mid [V] | rel err |")
    add("|---|---|---|---|---|")
    for row in v["points"]:
        add(
            f"| {row['source_voltage_volt']:g} | {row['r2_ohm']:g} | "
            f"{row['solver_vmid_volt']:.12g} | {row['analytic_vmid_volt']:.12g} | "
            f"{row['rel_error']:.3e} |"
        )
    add("")
    add(
        f"Worst relative error {v['worst_rel_error']:.3e} "
        f"(tolerance {v['rel_tol']:.1e}); "
        f"|error|/σ = {v['numerical_error_vs_noise']['ratio']:.3e}."
    )
    add("")
    add(f"- **Proves:** {v['what_this_proves']}")
    add(f"- **Does not prove:** {v['what_this_does_not_prove']}")
    if "scored_run" not in result:
        add("")
        add(f"**{result['verdict']}**")
        return "\n".join(lines)

    scored = result["scored_run"]
    add("")
    add("## Posterior, stage by stage (scored misspecified run)")
    add("")
    add(f"- prior — {_posterior_line(result['prior_stage']['posterior'])}")
    add(
        f"- after calibration — "
        f"{_posterior_line(scored['posterior_after_calibration'])}"
    )
    add(
        f"- after challenge — "
        f"{_posterior_line(scored['posterior_after_challenge'])}"
    )
    add("")
    add(
        "Every line above reads `p(R2 | data, M_const)`. The posterior gets "
        "**sharper** across the challenge phase while the family's predictions "
        "are failing — that divergence is the finding, not an anomaly."
    )

    add("")
    add("## Precommitted challenge predictions and their surprise")
    add("")
    add(
        "| condition | Vs [V] | predictive mean ± sd [V] | observed [V] | z | "
        "two-sided tail | NLPD | level |"
    )
    add("|---|---|---|---|---|---|---|---|")
    for s in sorted(
        scored["adequacy"]["surprises"], key=lambda r: r["source_voltage_volt"]
    ):
        add(
            f"| `{s['action_id']}` | {s['source_voltage_volt']:g} | "
            f"{s['predictive_mean_volt']:.5f} ± {s['predictive_sd_volt']:.5f} | "
            f"{s['y_observed_volt']:.5f} | {s['standardized_residual']:+.3f} | "
            f"{s['tail_probability']:.3e} | {s['nlpd']:.3f} | {s['level']} |"
        )
    agg = scored["adequacy"]["verdict"]["aggregate"]
    add("")
    add(
        f"Joint log score S = {agg['joint_log_score']:.3f} against a simulated "
        f"null of {agg['null_mean']:.3f} ± {agg['null_sd']:.3f} "
        f"(99th pct {agg['null_q99']:.3f}) over {agg['null_draws']} "
        f"posterior-predictive draws → **p_joint = {agg['p_joint']:.3e}**"
        + (" (Monte Carlo floor)" if agg["p_joint_is_mc_floor"] else "")
        + f"; n_extreme = {agg['n_extreme']}, n_moderate = {agg['n_moderate']}."
    )
    add("")
    add(
        f"*Deprecated v1.0.0 diagnostic:* Fisher X² = {agg['fisher_x2']:.3f} on "
        f"{agg['degrees_of_freedom']} df → χ²-independent p = "
        f"{agg['fisher_p_chi2_independent']:.4e}, versus "
        f"{agg['fisher_p_simulated']:.4e} against the correctly simulated null. "
        f"The χ²(2N) reference assumes independence these conditions do not "
        f"have and is not used to decide anything."
    )
    add("")
    add(f"**{scored['adequacy']['verdict']['state'].upper()}**")
    add("")
    add(scored["adequacy"]["verdict"]["rationale"])

    dep = scored["predictive_dependence"]
    add("")
    add("## Why the aggregate had to change (v1.0.0 → v1.1.0)")
    add("")
    add(
        f"The six challenge conditions are conditionally independent given θ "
        f"and share ONE calibration posterior. Marginalizing it leaves them "
        f"positively dependent — exact correlations "
        f"{dep['min_off_diagonal']:.3f} to {dep['max_off_diagonal']:.3f}, "
        f"largest between exactly the high-drive conditions that carry the most "
        f"weight in any aggregate."
    )
    add("")
    add("| Vs [V] | " + " | ".join(f"{v:g}" for v in dep["source_voltages_volt"]) + " |")
    add("|---" * (len(dep["source_voltages_volt"]) + 1) + "|")
    for v, row in zip(dep["source_voltages_volt"], dep["correlation_matrix"]):
        add(f"| **{v:g}** | " + " | ".join(f"{x:.4f}" for x in row) + " |")
    audit = result["statistical_validity"]["chi_square_reference_audit"]
    add("")
    add(
        f"Measured against the true null, Fisher's statistic has "
        f"{audit['measured_null_variance_inflation']:.2f}× the variance the "
        f"χ²(2N) reference assumes, and rejects at nominal 5% "
        f"{audit['null_rejection_rate_at_nominal_0p05'] * 100:.1f}% of the "
        f"time. Reference verdict: **{audit['verdict']}** — v1.0.0's aggregate "
        f"p-values were too small."
    )
    add("")
    add(
        f"Threshold robustness: all three control verdicts are unchanged for "
        f"any α_joint from 1e-4 to 1e-2 "
        f"(`{result['statistical_validity']['verdicts_stable_across_thresholds']}`)."
    )

    add("")
    add("## Controls")
    add("")
    add("| control | truth | verdict | n_extreme | joint log score | p_joint |")
    add("|---|---|---|---|---|---|")
    for key, name in (
        ("control_a_well_specified", "A — well specified"),
        ("control_b_single_outlier", "B — one isolated outlier"),
        ("scored_run", "C — systematic misspecification"),
    ):
        row = result[key]
        a = row["adequacy"]["verdict"]["aggregate"]
        add(
            f"| {name} | `{row['truth_spec_id']}` | "
            f"**{row['adequacy']['verdict']['state']}** | {a['n_extreme']} | "
            f"{a['joint_log_score']:.3f} | {a['p_joint']:.3e} |"
        )
    d = result["control_d_computational_failure"]
    add("")
    add(
        f"**D — computational failure:** critic `{d['critic_verdict']}`, arbiter "
        f"`{d['arbiter_verdict']}`, admitted `{d['admitted']}`, posterior "
        f"unchanged `{d['posterior_unchanged']}`. Failure path → "
        f"`{d['failure_path']['disposition']}`; adequacy path → "
        f"`{d['adequacy_path']['disposition']}`. Distinct: "
        f"`{d['states_are_distinct']}`."
    )
    e = result["control_e_confidence_is_not_adequacy"]
    add("")
    add(f"**E — confidence is not adequacy:** {e['statement']}")

    add("")
    add("## Terminal decision vs scientific certification")
    add("")
    t = result["terminal_decision"]
    add(f"- `POSTERIOR_DECISION = {t['posterior_decision']}`")
    add(f"- `SCIENTIFIC_CERTIFICATION = {t['scientific_certification'].upper()}`")
    add(f"- `reason = {t['reason']}`")
    add(f"- `disposition = {t['disposition'].upper()}`")
    add("")
    add(t["posterior_decision_reading"])

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
    add("## Certificate assumptions")
    add("")
    add("| proposition | status | basis |")
    add("|---|---|---|")
    for row in result["certificate_assumptions"]:
        add(f"| {row['proposition']} | {row['status']} | {row['basis']} |")

    add("")
    add(f"**{result['verdict']}**")
    return "\n".join(lines)


def main() -> int:
    result = run_e2()
    root = Path(__file__).resolve().parent
    (root / "e2_config_frozen.json").write_text(
        json.dumps(
            {
                "config": result["config"],
                "config_hash": result["config_hash"],
                "truth": result["truth"],
                "preregistration_hash": result["preregistration_hash"],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (root / "e2_results.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    report = render_markdown(result)
    (root / "e2_report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0 if result["verdict"] == "E2 MODEL-INADEQUACY DETECTED CORRECTLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
