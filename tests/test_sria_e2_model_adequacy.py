"""E2 — Model adequacy / predictive surprise.

Runs under pytest, and standalone via
``python -m tests.test_sria_e2_model_adequacy``.

The claim under test: on the real Electrical DC domain, with the grader truth
deliberately placed outside the assumed constant-R family, SRIA's conditional
posterior can become sharp while preregistered pre-observation predictive
checks fail systematically — and the system separates that from execution
validity, refuses to certify, and does not throw the surprising evidence away.

The invariant every test in this file is ultimately protecting:

    A scientifically surprising observation may be the strongest valid
    evidence that the current model is wrong. Do not invalidate the evidence
    just because it invalidates the model.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import sys
from pathlib import Path

import numpy as np

from experiments.electrical_e2 import DECISION_PATH_MODULES, E2_VERSION
from experiments.electrical_e2 import e2_truth
from experiments.electrical_e2.e2_adequacy import (
    CERTIFY_ALLOWED_PARAMETERS,
    AdequacyState,
    Certification,
    CommitmentLedger,
    Disposition,
    ExecutionValidity,
    PredictiveCommitmentViolation,
    SurpriseLevel,
    aggregate_adequacy,
    build_joint_predictive,
    certify,
    chi2_upper_tail_log,
    classify_adequacy,
    score_commitments,
)
from experiments.electrical_e2.e2_config import (
    ALPHA_EXTREME,
    ALPHA_JOINT,
    CHALLENGE_ACTIONS,
    E1_CONFIG_HASH,
    E1_FROZEN_FILE_DIGESTS,
    EXPERIMENT_VERSION,
    K_MIN_EXTREME,
    NULL_SIMULATION_DRAWS,
    SUPERSEDED_CONFIG_HASH,
    THETA_POINTS,
    VERIFICATION_REL_TOL,
    config_hash,
    theta_grid,
)
from experiments.electrical_e2.e2_harness import (
    ACTION_BY_ID,
    E2FaultyExecutor,
    build_e2_harness,
    preregistration_hash,
)
from experiments.electrical_e2.e2_model import (
    E2Observation,
    forward_predictions,
    observations_digest,
    posterior_summary,
    posterior_weights,
    predictive_mixture,
    prior_weights,
    solver_vmid,
)
from experiments.electrical_e2.e2_run import run_e2, run_solver_verification
from src.engcore.sria import BeliefWriteViolation

TOL = 1e-12

#: The scored E2 run, executed once and shared (fully deterministic).
_RESULT = None


def e2_result():
    global _RESULT
    if _RESULT is None:
        _RESULT = run_e2()
    return _RESULT


def _scored():
    return e2_result()["scored_run"]


def _raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    except Exception as other:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(other).__name__}: {other}"
        ) from other
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


# =====================================================================
# 1. Preregistration
# =====================================================================

def test_1_frozen_e2_config_hash_is_stable():
    first = config_hash()
    assert config_hash() == first
    assert len(first) == 64
    pre = preregistration_hash()
    assert preregistration_hash() == pre
    assert pre != first              # it also covers the grader truth
    result = e2_result()
    assert result["config_hash"] == first
    assert result["preregistration_hash"] == pre
    # The adequacy rule is INSIDE the hash, so it cannot be retuned quietly.
    rule = result["config"]["predictive_adequacy"]
    assert rule["alpha_extreme"] == ALPHA_EXTREME
    assert rule["alpha_joint"] == ALPHA_JOINT
    assert rule["k_min_extreme"] == K_MIN_EXTREME
    assert rule["independence_assumed"] is False
    assert rule["aggregate_null_draws"] == NULL_SIMULATION_DRAWS
    assert rule["deprecated_v1_0_0"]["status"].startswith("INVALID")
    # The v1.0.0 hash is recorded, and is genuinely different.
    assert result["config"]["correction_record"]["superseded_config_hash"] == (
        SUPERSEDED_CONFIG_HASH
    )
    assert first != SUPERSEDED_CONFIG_HASH


def test_1b_package_version_matches_the_preregistered_config_version():
    """The package must not advertise a version the run did not use.

    E2_VERSION is duplicated in __init__ so the package can report itself
    without importing the config; a drift between the two would attribute a
    v1.1.0 result — produced under the corrected joint aggregate — to the
    superseded v1.0.0 Fisher/chi-square rule, which is the one claim this
    experiment must never make about itself.
    """
    assert E2_VERSION == EXPERIMENT_VERSION
    assert E2_VERSION == "1.1.0"
    # ...and the version the artifacts were produced under agrees with both.
    result = e2_result()
    assert result["config"]["experiment_version"] == E2_VERSION
    # The version is inside the config hash, so it cannot drift silently.
    assert result["config_hash"] == config_hash()
    assert result["config_hash"] != SUPERSEDED_CONFIG_HASH


# =====================================================================
# 2. E1 is untouched
# =====================================================================

def test_2_e1_frozen_files_are_unchanged():
    """Content digests, so this holds without consulting git."""
    from experiments.electrical_e1.e1_config import config_hash as e1_hash

    root = _repo_root()
    for name, expected in E1_FROZEN_FILE_DIGESTS.items():
        raw = (root / name).read_bytes().replace(b"\r\n", b"\n")
        actual = hashlib.sha256(raw).hexdigest()
        assert actual == expected, f"E1 file changed: {name}"
    assert e1_hash() == E1_CONFIG_HASH


# =====================================================================
# 3. Oracle isolation — the central no-leakage guarantee
# =====================================================================

def _module_imports(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    absolute: set[str] = set()
    siblings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                if node.module:
                    siblings.add(node.module.split(".")[0])
                else:
                    siblings.update(alias.name for alias in node.names)
            elif node.module:
                absolute.add(node.module)
    return absolute, siblings


def test_3_grader_truth_cannot_reach_the_decision_path():
    import experiments.electrical_e2 as package

    root = Path(package.__file__).resolve().parent
    for name in DECISION_PATH_MODULES:
        absolute, siblings = _module_imports(root / f"{name}.py")
        assert "e2_truth" not in siblings, (name, siblings)
        assert not any("e2_truth" in c for c in absolute), (name, absolute)
        # Transitively: every sibling reached is itself a decision-path module,
        # so there is no two-hop route to the truth either.
        assert siblings <= set(DECISION_PATH_MODULES), (name, siblings)
        # ...and no route through E1's grader half.
        assert not any("e1_truth" in c for c in absolute), (name, absolute)

    # The harness and grader ARE expected to import it — otherwise this test
    # would pass because nothing anywhere used the truth.
    _abs, harness_siblings = _module_imports(root / "e2_harness.py")
    assert "e2_truth" in harness_siblings
    _abs, run_siblings = _module_imports(root / "e2_run.py")
    assert "e2_truth" in run_siblings


# =====================================================================
# 4-5. The forward model and the solver gate
# =====================================================================

def test_4_assumed_forward_model_is_the_real_electrical_dc_solver():
    """Not a formula: cross-check a grid point against a fresh solver run."""
    import experiments.electrical_e2.e2_model as model

    source = Path(model.__file__).read_text(encoding="utf-8")
    assert "from src.engcore.domains.electrical.dc import" in source
    assert "solve_circuit" in source

    grid = theta_grid()
    predictions = forward_predictions(20.0)
    assert len(predictions) == THETA_POINTS
    index = 173
    fresh = solver_vmid(20.0, float(grid[index]), run_id="e2-crosscheck")
    assert predictions[index] == fresh

    # ...and the same solver produced the challenge executions.
    scored = _scored()
    assert scored["challenge"]["rows"]
    for row in scored["challenge"]["rows"]:
        names = {c["name"] for c in row["checks"]}
        assert "residual_evidence" in names


def test_5_solver_verification_remains_green():
    verification = e2_result()["solver_verification"]
    assert verification["passed"] is True
    assert verification["worst_rel_error"] <= VERIFICATION_REL_TOL
    assert len(verification["points"]) == 9
    assert verification["numerical_error_vs_noise"]["ratio"] < 1e-6
    # Run it fresh too — the gate is not a cached claim.
    assert run_solver_verification()["passed"] is True


def test_5b_solver_verification_does_not_imply_model_adequacy():
    """The two propositions are kept apart in the certificate, and in this run
    they genuinely disagree: the implementation is verified and the family is
    inadequate."""
    result = e2_result()
    rows = {r["proposition"]: r["status"] for r in result["certificate_assumptions"]}
    family = next(p for p in rows if p.startswith("ASSUMED MODEL FAMILY"))
    solver = next(p for p in rows if p.startswith("SOLVER IMPLEMENTATION"))
    assert rows[family] == "ASSERTED_FOR_BENCHMARK"
    assert rows[solver] == "ANALYTICALLY_CHECKED"
    assert result["solver_verification"]["passed"] is True
    assert (
        _scored()["adequacy"]["verdict"]["state"]
        == AdequacyState.MODEL_SPACE_INADEQUATE.value
    )


# =====================================================================
# 6. Calibration produces a concentrated conditional posterior
# =====================================================================

def test_6_calibration_produces_a_concentrated_conditional_posterior():
    scored = _scored()
    prior = scored["posterior_prior"]
    after = scored["posterior_after_calibration"]
    assert scored["calibration"]["n_admitted"] == 4
    assert prior["sd_r2_ohm"] > 500.0
    assert after["sd_r2_ohm"] < 25.0             # a >20x contraction
    assert after["entropy_nats"] < prior["entropy_nats"] - 3.0
    assert after["p_above_threshold"] > 0.999999
    assert after["evpi"] < 1e-20
    # It is a CONDITIONAL statement, and says so.
    assert after["conditional_on"] == "M_const (R2 constant)"


# =====================================================================
# 7-10. Prediction as commitment
# =====================================================================

def _fresh_two_phase(spec, label):
    """A live harness + ledger for tests that need to poke at the internals."""
    from experiments.electrical_e2.e2_run import run_experiment

    return run_experiment(spec, label=label)


def test_7_challenge_predictive_exists_before_the_challenge_observation():
    scored = _scored()
    adequacy = scored["adequacy"]
    assert adequacy["ledger_sealed_at"] is not None
    for surprise in adequacy["surprises"]:
        assert surprise["commitment_sequence"] < adequacy["ledger_sealed_at"]
        assert adequacy["ledger_sealed_at"] < surprise["observation_sequence"]
    # And independently, in the hash-chained campaign event log.
    ordering = scored["prediction_ordering"]
    assert ordering["prediction_preceded_observation"] is True
    assert max(ordering["decision_recommended_sequences"]) < min(
        ordering["challenge_execution_started_sequences"]
    )
    assert ordering["event_chain_verified"] is True
    assert ordering["ledger_chain_verified"] is True
    assert adequacy["chain_verified"] is True


def test_8_challenge_prediction_is_bound_to_the_correct_evidence_snapshot():
    live = _fresh_two_phase(e2_truth.MISSPECIFIED_TRUTH, "e2-bind-test")
    ledger: CommitmentLedger = live["_ledger"]
    calibration_digest = live["calibration"]["evidence_snapshot_digest"]
    final_digest = observations_digest(live["_harness"].current_observations())

    assert calibration_digest != final_digest
    for action in CHALLENGE_ACTIONS:
        commitment = ledger.commitments[action.action_id]
        assert commitment.evidence_snapshot_digest == calibration_digest
        assert commitment.n_observations == 4
        assert commitment.config_hash == config_hash()
        assert commitment.verify_integrity() is True
    # The digest is reproducible from the admitted calibration set alone.
    calibration_only = [
        E2Observation(
            action_id=str(r["action_id"]),
            source_voltage_volt=10.0,
            y_volt=float(r["y_volt"]),
            sigma_volt=0.05,
        )
        for r in live["calibration"]["rows"]
    ]
    assert observations_digest(calibration_only) == calibration_digest


def test_9_surprise_is_computed_from_the_frozen_pre_observation_predictive():
    live = _fresh_two_phase(e2_truth.MISSPECIFIED_TRUTH, "e2-frozen-test")
    ledger: CommitmentLedger = live["_ledger"]
    for surprise in live["adequacy"]["surprises"]:
        commitment = ledger.commitments[surprise["action_id"]]
        # Recomputed from the stored artifact, with no access to the harness.
        mixture = commitment.mixture()
        y = surprise["y_observed_volt"]
        assert abs(mixture.two_sided_tail(y) - surprise["tail_probability"]) <= (
            1e-15 + 1e-9 * surprise["tail_probability"]
        )
        assert abs(mixture.negative_log_density(y) - surprise["nlpd"]) < 1e-9
        assert surprise["commitment_artifact_hash"] == commitment.artifact_hash

    # And a POST-HOC predictive would have said something materially different,
    # which is exactly why it must not be the artifact.
    posthoc_weights = live["_weights_final"]
    action = ACTION_BY_ID["challenge_vmid_28V"]
    posthoc = predictive_mixture(posthoc_weights, action)
    frozen = ledger.commitments[action.action_id].mixture()
    observed = next(
        s["y_observed_volt"]
        for s in live["adequacy"]["surprises"]
        if s["action_id"] == action.action_id
    )
    assert posthoc.two_sided_tail(observed) > 1e4 * frozen.two_sided_tail(observed)


def test_10_no_post_hoc_predictive_overwrite_is_accepted():
    live = _fresh_two_phase(e2_truth.MISSPECIFIED_TRUTH, "e2-posthoc-test")
    ledger: CommitmentLedger = live["_ledger"]
    action = ACTION_BY_ID["challenge_vmid_28V"]
    assert ledger.is_sealed

    # (a) a brand-new commitment after the seal
    _raises(
        PredictiveCommitmentViolation,
        ledger.commit,
        action_id="challenge_vmid_28V_v2",
        source_voltage_volt=28.0,
        noise_sigma_volt=0.05,
        evidence_snapshot_digest=observations_digest(
            live["_harness"].current_observations()
        ),
        n_observations=10,
        mixture=predictive_mixture(live["_weights_final"], action),
    )
    # (b) overwriting an existing one
    _raises(
        PredictiveCommitmentViolation,
        ledger.commit,
        action_id=action.action_id,
        source_voltage_volt=28.0,
        noise_sigma_volt=0.05,
        evidence_snapshot_digest="whatever",
        n_observations=10,
        mixture=predictive_mixture(live["_weights_final"], action),
    )
    # (c) an unsealed ledger refuses to record observations at all
    empty = CommitmentLedger("e2-unsealed")
    _raises(
        PredictiveCommitmentViolation,
        empty.record_observation,
        action_id=action.action_id,
        y_volt=16.0,
        execution_id="x",
        execution_valid=True,
    )
    # (d) and an unsealed ledger cannot be scored
    empty.commit(
        action_id=action.action_id,
        source_voltage_volt=28.0,
        noise_sigma_volt=0.05,
        evidence_snapshot_digest="d",
        n_observations=0,
        mixture=predictive_mixture(prior_weights(), action),
    )
    _raises(PredictiveCommitmentViolation, score_commitments, empty)


# =====================================================================
# 11-13. The three adequacy outcomes
# =====================================================================

def test_11_well_specified_control_is_not_falsely_rejected():
    control = e2_result()["control_a_well_specified"]
    verdict = control["adequacy"]["verdict"]
    assert verdict["state"] == AdequacyState.MODEL_ADEQUACY_ACCEPTABLE.value
    aggregate = verdict["aggregate"]
    assert aggregate["n_extreme"] == 0
    assert aggregate["p_joint"] > 0.01
    # The complete vector sits INSIDE its own simulated null, not just past a
    # threshold: the joint score is below the null 99th percentile.
    assert aggregate["joint_log_score"] < aggregate["null_q99"]
    # Same machinery, same seeds, same challenge actions as the scored run —
    # only the hidden law differs.
    assert control["truth_spec_id"] == "A_well_specified"
    assert len(control["adequacy"]["surprises"]) == len(CHALLENGE_ACTIONS)
    assert (
        control["adequacy"]["certification"]["scientific_certification"]
        == Certification.CERTIFIABLE.value
    )


def test_12_single_isolated_surprise_does_not_trigger_the_strongest_verdict():
    control = e2_result()["control_b_single_outlier"]
    verdict = control["adequacy"]["verdict"]
    aggregate = verdict["aggregate"]
    assert aggregate["n_extreme"] == 1                     # genuinely extreme...
    assert aggregate["n_extreme"] < K_MIN_EXTREME          # ...and still not enough
    assert verdict["state"] != AdequacyState.MODEL_SPACE_INADEQUATE.value
    assert verdict["state"] == AdequacyState.MODEL_ADEQUACY_NOT_ESTABLISHED.value

    # The K_min clause is genuinely load-bearing here, not decorative: under
    # the CORRECTED aggregate a single 10-sigma outlier makes the complete
    # vector as joint-implausible as the systematically misspecified world, so
    # the aggregate alone would have condemned a family that is in fact right.
    assert aggregate["p_joint"] < ALPHA_JOINT
    scored_aggregate = _scored()["adequacy"]["verdict"]["aggregate"]
    assert scored_aggregate["p_joint"] < ALPHA_JOINT
    assert aggregate["joint_log_score"] > aggregate["null_q99"]
    # It is not certified either — an unexplained extreme point is a reason to
    # withhold the claim, just not a reason to condemn the family.
    assert (
        control["adequacy"]["certification"]["scientific_certification"]
        == Certification.NOT_CERTIFIABLE.value
    )
    assert (
        control["adequacy"]["certification"]["disposition"]
        == Disposition.ADEQUACY_EVIDENCE_REQUIRED.value
    )


def test_12b_one_extreme_point_can_never_reach_the_strongest_verdict():
    """Structural, not empirical: ONE arbitrarily extreme condition, five
    perfect ones, and an aggregate driven to the most damning value the rule
    can represent still cannot reach MODEL_SPACE_INADEQUATE."""
    live = _fresh_two_phase(e2_truth.WELL_SPECIFIED_TRUTH, "e2-structural")
    surprises = list(live["_surprises"])
    hammered = [
        dataclasses.replace(
            surprises[0], tail_probability=1e-300, level=SurpriseLevel.EXTREME
        )
    ] + [
        dataclasses.replace(s, tail_probability=0.9, level=SurpriseLevel.CONSISTENT)
        for s in surprises[1:]
    ]
    # p_joint forced to 0 — below any threshold that could ever be preregistered.
    worst_case = dataclasses.replace(
        live["_aggregate"],
        p_joint=0.0,
        p_joint_is_mc_floor=True,
        n_extreme=1,
        n_moderate=0,
    )
    verdict = classify_adequacy(hammered, worst_case)
    assert verdict.aggregate.p_joint == 0.0
    assert verdict.aggregate.n_extreme == 1
    assert verdict.state is AdequacyState.MODEL_ADEQUACY_NOT_ESTABLISHED
    # Two extreme conditions with the same aggregate DO escalate, so the
    # blocking above is the K_min clause and not an inert rule.
    with_two = dataclasses.replace(worst_case, n_extreme=2)
    assert (
        classify_adequacy(hammered, with_two).state
        is AdequacyState.MODEL_SPACE_INADEQUATE
    )


def test_13_systematic_misspecification_triggers_the_preregistered_criterion():
    scored = _scored()
    verdict = scored["adequacy"]["verdict"]
    aggregate = verdict["aggregate"]
    assert verdict["state"] == AdequacyState.MODEL_SPACE_INADEQUATE.value
    assert aggregate["n_extreme"] >= K_MIN_EXTREME
    assert aggregate["p_joint"] < ALPHA_JOINT
    assert aggregate["n_conditions"] == len(CHALLENGE_ACTIONS)
    # The complete vector is far outside its own simulated null, and the joint
    # score already let the family move theta anywhere its posterior allowed.
    assert aggregate["joint_log_score"] > aggregate["null_q99"]
    assert aggregate["joint_log_score"] > aggregate["null_mean"] + 10.0 * (
        aggregate["null_sd"]
    )

    # The failure is SYSTEMATIC: monotone in the distance from the calibrated
    # condition, and identical to the well-specified world at the internal null.
    by_voltage = {
        s["source_voltage_volt"]: s["standardized_residual"]
        for s in scored["adequacy"]["surprises"]
    }
    escalating = [by_voltage[v] for v in (10.0, 16.0, 20.0, 24.0, 28.0)]
    assert escalating == sorted(escalating)
    control_a = e2_result()["control_a_well_specified"]
    null_c = next(
        s["y_observed_volt"]
        for s in scored["adequacy"]["surprises"]
        if s["action_id"] == "challenge_vmid_10V"
    )
    null_a = next(
        s["y_observed_volt"]
        for s in control_a["adequacy"]["surprises"]
        if s["action_id"] == "challenge_vmid_10V"
    )
    assert null_c == null_a          # the law is exactly R0 at the null

    # And no constant could have fitted the scored world.
    diagnostic = e2_result()["misspecification_diagnostic"]
    assert diagnostic["well_specified_truth"]["worst_abs_residual_volt"] < 1e-9
    assert diagnostic["scored_truth"]["worst_abs_residual_volt"] > 0.1


# =====================================================================
# 14. VALID EVIDENCE MUST REMAIN VALID
# =====================================================================

def test_14_surprising_but_valid_evidence_remains_admissible_evidence():
    """The central invariant. The observation that most damages the model is
    still the observation with the best claim to be believed."""
    scored = _scored()
    worst = min(
        scored["adequacy"]["surprises"], key=lambda s: s["tail_probability"]
    )
    assert worst["tail_probability"] < ALPHA_EXTREME
    row = next(
        r
        for r in scored["challenge"]["rows"]
        if r["action_id"] == worst["action_id"]
    )
    assert row["critic_verdict"] == "pass"
    assert row["arbiter_verdict"] == "valid"
    assert row["admitted"] is True
    assert row["execution_validity"] == ExecutionValidity.VALID.value
    # EVERY challenge observation was admitted, not just the comfortable ones.
    assert scored["challenge"]["n_admitted"] == len(CHALLENGE_ACTIONS)
    assert all(r["admitted"] for r in scored["challenge"]["rows"])
    # The critic has no predictive-surprise check to fail it with.
    assert {c["name"] for c in row["checks"]} == {
        "solver_termination",
        "residual_evidence",
        "validation_report_status",
    }


# =====================================================================
# 15. Execution validity vs model adequacy
# =====================================================================

def test_15_computational_failure_and_model_inadequacy_are_distinct_states():
    control = e2_result()["control_d_computational_failure"]
    assert control["critic_verdict"] == "fail"
    assert control["arbiter_verdict"] == "invalid"
    assert control["admitted"] is False
    assert control["posterior_unchanged"] is True
    assert control["observations_after"] == control["observations_before"]

    assert control["failure_path"]["disposition"] == (
        Disposition.EXECUTION_REPAIR_REQUIRED.value
    )
    assert control["adequacy_path"]["disposition"] == (
        Disposition.MODEL_REVISION_REQUIRED.value
    )
    assert control["states_are_distinct"] is True

    # Two independent axes, exercised at all four corners that matter.
    assert (
        certify("A", AdequacyState.MODEL_ADEQUACY_ACCEPTABLE,
                ExecutionValidity.VALID).scientific_certification
        is Certification.CERTIFIABLE
    )
    for state in (
        AdequacyState.MODEL_ADEQUACY_ACCEPTABLE,
        AdequacyState.MODEL_SPACE_INADEQUATE,
    ):
        assert (
            certify("A", state, ExecutionValidity.INVALID).disposition
            is Disposition.EXECUTION_REPAIR_REQUIRED
        )
    assert (
        certify("A", AdequacyState.MODEL_SPACE_INADEQUATE,
                ExecutionValidity.VALID).disposition
        is Disposition.MODEL_REVISION_REQUIRED
    )


def test_15b_a_faulty_execution_is_refused_on_computational_grounds_only():
    """The faulty double returns a number close to the truth. It is still
    refused — because of the residual, not because of the value."""
    harness = build_e2_harness(
        e2_truth.WELL_SPECIFIED_TRUTH,
        run_id="e2-faulty-value",
        executor_class=E2FaultyExecutor,
    )
    row = harness.run_measurement(ACTION_BY_ID["calibrate_vmid_10V"], repeat=1)
    assert row.admitted is False
    assert row.execution_validity is ExecutionValidity.INVALID
    truth_value = e2_truth.truth_vmid(10.0, e2_truth.WELL_SPECIFIED_TRUTH)
    assert abs(row.y_volt - truth_value) < 0.3      # a perfectly plausible number
    residual_check = next(c for c in row.checks if c["name"] == "residual_evidence")
    assert residual_check["outcome"] == "fail"
    assert residual_check["observed"] > residual_check["threshold"]


# =====================================================================
# 16-19. Confidence, EVPI and EVSI cannot override adequacy
# =====================================================================

def test_16_posterior_may_contract_while_adequacy_fails():
    scored = _scored()
    calibrated = scored["posterior_after_calibration"]
    final = scored["posterior_after_challenge"]
    assert final["sd_r2_ohm"] < calibrated["sd_r2_ohm"]
    assert final["entropy_nats"] < calibrated["entropy_nats"]
    assert (
        scored["adequacy"]["verdict"]["state"]
        == AdequacyState.MODEL_SPACE_INADEQUATE.value
    )
    assert e2_result()["control_e_confidence_is_not_adequacy"][
        "posterior_contracted_while_adequacy_failed"
    ] is True


def test_17_low_posterior_sd_cannot_override_inadequacy():
    scored = _scored()
    assert scored["posterior_after_challenge"]["sd_r2_ohm"] < 10.0
    assert scored["posterior_after_challenge"]["p_above_threshold"] > 0.999999
    assert (
        scored["adequacy"]["certification"]["scientific_certification"]
        == Certification.NOT_CERTIFIABLE.value
    )
    # Structural: the gate has no parameter for posterior strength.
    parameters = tuple(inspect.signature(certify).parameters)
    assert parameters == CERTIFY_ALLOWED_PARAMETERS
    for name in parameters + tuple(inspect.signature(classify_adequacy).parameters):
        assert not any(
            token in name
            for token in ("sd", "entropy", "confidence", "evpi", "evsi", "sharp")
        )


def test_18_low_evpi_cannot_override_inadequacy():
    scored = _scored()
    assert scored["posterior_after_challenge"]["evpi"] <= 1e-30
    assert (
        certify(
            "A", AdequacyState.MODEL_SPACE_INADEQUATE, ExecutionValidity.VALID
        ).scientific_certification
        is Certification.NOT_CERTIFIABLE
    )
    # EVPI collapsed INSIDE the family; the family is what is in question.
    assert scored["posterior_prior"]["evpi"] > 0.5


def test_19_low_evsi_cannot_override_inadequacy():
    scored = _scored()
    after = scored["evsi_after_challenge"]
    assert after, "no EVSI table was produced"
    assert max(row["evsi"] for row in after.values()) < 1e-9
    # "Nothing is worth measuring" is a statement inside M_const...
    assert max(row["evsi"] for row in scored["evsi_prior"].values()) > 0.5
    # ...and it does not certify anything.
    assert (
        scored["adequacy"]["certification"]["scientific_certification"]
        == Certification.NOT_CERTIFIABLE.value
    )
    assert e2_result()["adversarial_injections"][3]["caught"] is True


# =====================================================================
# 20. Decision exists; certification is denied
# =====================================================================

def test_20_posterior_decision_exists_while_certification_is_denied():
    terminal = e2_result()["terminal_decision"]
    assert terminal["posterior_decision"] == "A"
    assert terminal["scientific_certification"] == (
        Certification.NOT_CERTIFIABLE.value
    )
    assert terminal["reason"] == AdequacyState.MODEL_SPACE_INADEQUATE.name
    assert terminal["disposition"] == Disposition.MODEL_REVISION_REQUIRED.value
    # The decision is reported as conditional, not suppressed and not promoted.
    assert "p(R2 | data, M_const)" in terminal["posterior_decision_reading"]
    assert "conditional" in terminal["posterior_decision_reading"]


# =====================================================================
# 21-23. The evidence boundary
# =====================================================================

def test_21_changing_grader_truth_does_not_alter_existing_inference():
    """Hold the admitted evidence fixed, change the hidden law, and every
    decision-path quantity must be bit-identical."""
    live = _fresh_two_phase(e2_truth.MISSPECIFIED_TRUTH, "e2-leak-runtime")
    observations = live["_harness"].current_observations()
    weights_before = posterior_weights(observations)
    summary_before = posterior_summary(weights_before)
    mixtures_before = [predictive_mixture(weights_before, a) for a in CHALLENGE_ACTIONS]
    from experiments.electrical_e2.e2_model import evsi

    evsi_before = [evsi(weights_before, a) for a in CHALLENGE_ACTIONS]

    for kappa in (0.0, 0.42, -0.25):
        altered = dataclasses.replace(
            e2_truth.MISSPECIFIED_TRUTH, kappa=kappa, spec_id=f"probe{kappa}"
        )
        # Actually exercise the altered law, so this is not a no-op.
        assert [
            altered.effective_resistance(a.source_voltage_volt)
            for a in CHALLENGE_ACTIONS
        ]
        weights_after = posterior_weights(observations)
        assert np.array_equal(weights_after, weights_before)
        assert posterior_summary(weights_after) == summary_before
        for before, action in zip(mixtures_before, CHALLENGE_ACTIONS):
            after = predictive_mixture(weights_after, action)
            assert after.means == before.means
            assert after.weights == before.weights
            assert after.sigma == before.sigma
        assert [evsi(weights_after, a) for a in CHALLENGE_ACTIONS] == evsi_before

    assert e2_result()["adversarial_injections"][4]["caught"] is True


def test_22_unadmitted_observation_changes_the_posterior_by_exactly_zero():
    harness = build_e2_harness(e2_truth.MISSPECIFIED_TRUTH, run_id="e2-unadmitted")
    harness.run_calibration_phase()
    before = harness.current_observations()
    weights_before = posterior_weights(before)

    action = ACTION_BY_ID["challenge_vmid_28V"]
    execution = harness.executor.execute(
        action, repeat=1, execution_id="e2-unadmitted-probe"
    )
    evidence = harness.build_evidence(execution, evidence_id="e2-ev-unadmitted")

    # Candidate evidence cannot enter the gateway, and neither can the raw
    # execution or its result.
    _raises(BeliefWriteViolation, harness.gateway.submit, evidence)
    _raises(BeliefWriteViolation, harness.gateway.submit, execution)
    _raises(BeliefWriteViolation, harness.gateway.submit, execution.result)

    after = harness.current_observations()
    assert after == before
    assert np.array_equal(posterior_weights(after), weights_before)


def test_23_admitted_surprising_observation_enters_the_posterior_normally():
    harness = build_e2_harness(e2_truth.MISSPECIFIED_TRUTH, run_id="e2-admit-path")
    harness.run_calibration_phase()
    before = harness.current_observations()
    weights_before = posterior_weights(before)

    row = harness.run_measurement(ACTION_BY_ID["challenge_vmid_28V"], repeat=1)
    assert row.admitted is True
    after = harness.current_observations()
    assert len(after) == len(before) + 1

    weights_after = posterior_weights(after)
    assert not np.array_equal(weights_after, weights_before)
    # Reconstructible from the admitted set alone — no side channel.
    assert np.array_equal(weights_after, posterior_weights(after))
    # It was surprising AND it updated belief in the ordinary way.
    mixture = predictive_mixture(weights_before, ACTION_BY_ID["challenge_vmid_28V"])
    assert mixture.two_sided_tail(row.y_volt) < ALPHA_EXTREME
    assert abs(float(weights_after.sum()) - 1.0) < 1e-12


# =====================================================================
# 24. E1 regression surface
# =====================================================================

def test_24_e1_regression_surface_is_intact():
    """E1's own suite runs alongside this file; this checks the surface E2
    depends on has not drifted underneath it."""
    from experiments.electrical_e1.e1_config import config_hash as e1_config_hash
    from experiments.electrical_e1.e1_run import (
        run_solver_verification as e1_verification,
    )

    assert e1_config_hash() == E1_CONFIG_HASH
    e1_gate = e1_verification()
    assert e1_gate["passed"] is True
    assert e1_gate["worst_rel_error"] <= 1e-9
    # E2 added no import into E1's decision path.
    root = _repo_root() / "experiments" / "electrical_e1"
    for name in ("e1_config", "e1_model"):
        absolute, siblings = _module_imports(root / f"{name}.py")
        assert not any("e2_" in c for c in absolute | siblings)


# =====================================================================
# Adversarial injections and the statistical machinery
# =====================================================================

def test_all_adversarial_injections_are_caught():
    injections = e2_result()["adversarial_injections"]
    assert [i["injection"] for i in injections] == ["A", "B", "C", "D", "E", "F"]
    for injection in injections:
        assert injection["caught"] is True, injection
        assert injection["catcher"], injection


def test_injection_f_tampered_artifact_is_rejected_at_score_time():
    live = _fresh_two_phase(e2_truth.MISSPECIFIED_TRUTH, "e2-tamper")
    ledger: CommitmentLedger = live["_ledger"]
    action_id = "challenge_vmid_20V"
    original = ledger.commitments[action_id]
    assert original.verify_integrity() is True

    tampered = dataclasses.replace(
        original, component_means=tuple(m + 1.0 for m in original.component_means)
    )
    assert tampered.verify_integrity() is False       # hash no longer matches
    ledger._commitments[action_id] = tampered
    assert ledger.verify_commitments() is False
    _raises(PredictiveCommitmentViolation, score_commitments, ledger)


def test_injection_a_predictive_after_observation_is_rejected():
    live = _fresh_two_phase(e2_truth.MISSPECIFIED_TRUTH, "e2-posthoc-inject")
    ledger: CommitmentLedger = live["_ledger"]
    assert ledger.observations                      # observations exist now
    _raises(
        PredictiveCommitmentViolation,
        ledger.commit,
        action_id="sneaky",
        source_voltage_volt=20.0,
        noise_sigma_volt=0.05,
        evidence_snapshot_digest="x",
        n_observations=99,
        mixture=predictive_mixture(
            live["_weights_final"], ACTION_BY_ID["challenge_vmid_20V"]
        ),
    )


def test_ledger_chain_detects_a_rewritten_history():
    live = _fresh_two_phase(e2_truth.WELL_SPECIFIED_TRUTH, "e2-chain")
    ledger: CommitmentLedger = live["_ledger"]
    assert ledger.verify_chain() is True
    victim = ledger._entries[2]
    ledger._entries[2] = dataclasses.replace(victim, payload_digest="rewritten")
    assert ledger.verify_chain() is False


def test_predictive_tails_are_exact_for_the_mixture():
    """The statistic is exact, not approximated — checked against a direct
    numerical integration of the same mixture density."""
    live = _fresh_two_phase(e2_truth.MISSPECIFIED_TRUTH, "e2-tail-math")
    mixture = live["_ledger"].commitments["challenge_vmid_20V"].mixture()
    y = mixture.mean + 2.0 * mixture.sd
    grid = np.linspace(mixture.mean - 14 * mixture.sd, y, 200001)
    means = np.asarray(mixture.means)
    weights = np.asarray(mixture.weights)
    density = (
        np.exp(-0.5 * ((grid[:, None] - means[None, :]) / mixture.sigma) ** 2)
        / (mixture.sigma * np.sqrt(2.0 * np.pi))
    ) @ weights
    numeric = float(np.trapezoid(density, grid))
    # The quadrature is the approximate side here; erfc is exact to rounding,
    # so the tolerance is set by the trapezoid rule, not by lower_tail.
    assert abs(mixture.lower_tail(y) - numeric) < 1e-10
    assert abs(mixture.lower_tail(y) + mixture.upper_tail(y) - 1.0) < 1e-12
    # ...and it stays accurate deep in the tail, where the rule actually reads.
    far = mixture.mean + 8.0 * mixture.sd
    assert 0.0 < mixture.upper_tail(far) < 1e-12


def test_chi2_closed_form_matches_scipy():
    from scipy.stats import chi2

    for df in (2, 6, 12, 20):
        for x in (0.5, 3.0, 12.0, 40.0, 90.0):
            expected = float(chi2.sf(x, df))
            actual = float(np.exp(chi2_upper_tail_log(x, df)))
            assert abs(actual - expected) <= 1e-12 + 1e-9 * expected, (df, x)
    # And it survives where scipy's sf has already underflowed to zero.
    assert chi2_upper_tail_log(4000.0, 12) < -1900.0


def test_adequacy_classifier_reads_only_tails_and_the_joint_aggregate():
    live = _fresh_two_phase(e2_truth.WELL_SPECIFIED_TRUTH, "e2-classifier")
    surprises = list(live["_surprises"])
    aggregate = live["_aggregate"]
    baseline = classify_adequacy(surprises, aggregate)
    assert baseline.state is AdequacyState.MODEL_ADEQUACY_ACCEPTABLE

    # Rewrite everything the classifier is NOT allowed to care about.
    disguised = [
        dataclasses.replace(
            s,
            y_observed_volt=s.y_observed_volt + 1000.0,
            predictive_mean_volt=-42.0,
            nlpd=-999.0,
            standardized_residual=99.0,
        )
        for s in surprises
    ]
    assert classify_adequacy(disguised, aggregate).state is baseline.state


# =====================================================================
# v1.1.0 statistical validity close-out
# =====================================================================

def test_challenge_tail_pvalues_are_not_independent():
    """STEP 1, executable. The conditions share one calibration posterior, so
    their marginal predictive tails are positively dependent — exactly, not
    approximately."""
    live = _fresh_two_phase(e2_truth.MISSPECIFIED_TRUTH, "e2-dependence")
    joint = live["_joint"]
    correlation = joint.correlation()
    k = correlation.shape[0]
    off = correlation[np.triu_indices(k, k=1)]

    assert (off > 0.0).all(), "every pair is positively dependent"
    assert off.max() > 0.5, "the high-drive pairs are strongly dependent"
    # It is the SHARED theta that does it: with a point-mass posterior the
    # conditions would be exactly independent.
    point_mass = dataclasses.replace(
        joint,
        weights=tuple(
            1.0 if i == len(joint.weights) // 2 else 0.0
            for i in range(len(joint.weights))
        ),
    )
    degenerate = point_mass.correlation()
    assert np.allclose(degenerate, np.eye(k), atol=1e-12)

    # ...and the run reports the same matrix it was told to report.
    reported = np.asarray(live["predictive_dependence"]["correlation_matrix"])
    assert np.allclose(reported, correlation, atol=1e-12)


def test_chi_square_independence_reference_is_anti_conservative():
    """STEP 1/2, executable. Under the TRUE null, Fisher's statistic referred
    to chi-square(2N) over-rejects — which is why v1.0.0's aggregate p-values
    were too small rather than merely imprecise."""
    audit = e2_result()["statistical_validity"]["chi_square_reference_audit"]
    assert audit["null_rejection_rate_at_nominal_0p05"] > 0.05
    assert audit["measured_null_variance_inflation"] > 1.2
    assert audit["verdict"] == "ANTI-CONSERVATIVE"

    # The size of the v1.0.0 error on the scored run, in orders of magnitude.
    aggregate = _scored()["adequacy"]["verdict"]["aggregate"]
    assert aggregate["fisher_p_chi2_independent"] < 1e-15      # what v1.0.0 said
    assert aggregate["fisher_p_simulated"] > 1e-6              # correctly calibrated
    assert aggregate["fisher_p_simulated"] > (
        1e6 * aggregate["fisher_p_chi2_independent"]
    )


def test_joint_log_score_is_exact():
    """No sampling in the statistic itself — only in its null calibration."""
    live = _fresh_two_phase(e2_truth.MISSPECIFIED_TRUTH, "e2-joint-math")
    joint = live["_joint"]
    y = np.array([s.y_observed_volt for s in live["_surprises"]], float)

    means = np.asarray(joint.component_means, float)
    sigmas = np.asarray(joint.sigmas, float)
    weights = np.asarray(joint.weights, float)
    # Direct, unvectorized reference: sum over grid of w * prod_j N(y_j).
    total = 0.0
    for i, w in enumerate(weights):
        block = 1.0
        for j in range(joint.n_conditions):
            z = (y[j] - means[j, i]) / sigmas[j]
            block *= np.exp(-0.5 * z * z) / (sigmas[j] * np.sqrt(2.0 * np.pi))
        total += w * block
    assert abs(joint.log_score(y) - (-np.log(total))) < 1e-9

    # The joint is NOT the product of marginals — that is the whole point.
    product_of_marginals = sum(
        joint.marginal(j).log_density(y[j]) for j in range(joint.n_conditions)
    )
    assert abs(product_of_marginals - joint.log_density(y)) > 1.0


def test_null_calibration_is_deterministic_and_validly_constructed():
    live = _fresh_two_phase(e2_truth.MISSPECIFIED_TRUTH, "e2-null-cal")
    first = aggregate_adequacy(live["_surprises"], live["_joint"])
    second = aggregate_adequacy(live["_surprises"], live["_joint"])
    assert first.p_joint == second.p_joint
    assert first.joint_log_score == second.joint_log_score

    # (1 + k) / (1 + N): never zero, and exactly valid in finite samples.
    expected = (1.0 + first.n_null_at_least_as_extreme) / (1.0 + first.null_draws)
    assert first.p_joint == expected
    assert first.p_joint >= 1.0 / (1.0 + NULL_SIMULATION_DRAWS)
    assert first.null_draws == NULL_SIMULATION_DRAWS

    # The simulation shares ONE theta per draw; a per-condition simulation
    # would destroy the dependence and give a different (wrong) null.
    draws = live["_joint"].simulate(4000, 1234)
    assert draws.shape == (4000, live["_joint"].n_conditions)
    empirical = np.corrcoef(draws, rowvar=False)
    assert np.allclose(empirical, live["_joint"].correlation(), atol=0.05)


def test_joint_predictive_refuses_mismatched_evidence_snapshots():
    live = _fresh_two_phase(e2_truth.MISSPECIFIED_TRUTH, "e2-joint-guard")
    ledger: CommitmentLedger = live["_ledger"]
    order = [s.action_id for s in live["_surprises"]]
    assert build_joint_predictive(ledger, order).n_conditions == len(order)

    victim = order[0]
    ledger._commitments[victim] = dataclasses.replace(
        ledger.commitments[victim], evidence_snapshot_digest="a-different-state"
    )
    _raises(PredictiveCommitmentViolation, build_joint_predictive, ledger, order)


def test_corrected_verdicts_are_stable_across_thresholds():
    """The conclusion must not depend on the particular alpha_joint chosen."""
    validity = e2_result()["statistical_validity"]
    assert validity["verdicts_stable_across_thresholds"] is True
    for threshold in ("1e-4", "1e-3", "1e-2"):
        row = validity["threshold_sweep"][threshold]
        assert row["control_a_well_specified"] == (
            AdequacyState.MODEL_ADEQUACY_ACCEPTABLE.value
        )
        assert row["control_b_single_outlier"] == (
            AdequacyState.MODEL_ADEQUACY_NOT_ESTABLISHED.value
        )
        assert row["scored_run"] == AdequacyState.MODEL_SPACE_INADEQUATE.value


def test_internal_null_claim_is_appropriately_hedged():
    """STEP 5. The Vs = 10 V null discriminates against ONE alternative
    explanation, not against every possible fault mechanism."""
    rows = {
        r["proposition"]: r
        for r in e2_result()["certificate_assumptions"]
    }
    row = next(r for p, r in rows.items() if p.startswith("internal null"))
    assert row["status"] == "ASSERTED_FOR_BENCHMARK"
    basis = row["basis"].lower()
    assert "constructed" in basis
    assert "does not exclude" in basis or "not exclude" in basis
    assert "condition-dependent" in basis

    import experiments.electrical_e2.e2_config as config_module

    source = " ".join(
        Path(config_module.__file__).read_text(encoding="utf-8").lower().split()
    )
    assert "would indicate an instrument or wiring fault" not in source
    assert "does not exclude alternative fault mechanisms" in source
    assert "constructed to vanish at the calibration condition" in source


def test_e2_overall_verdict_and_success_checks():
    result = e2_result()
    checks = result["success_checks"]
    for name, value in checks.items():
        assert value is True, name
    assert result["verdict"] == "E2 MODEL-INADEQUACY DETECTED CORRECTLY"


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA E2 — model adequacy / predictive surprise")
    print("=" * 72)
    failures = 0
    tests = _all_tests()
    for name, test in tests:
        try:
            test()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    print("=" * 72)
    if failures:
        print(f"E2: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"E2: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
