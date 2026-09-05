"""E1 — Electrical quantitative verification.

Runs under pytest, and standalone via ``python -m tests.test_sria_e1_electrical``.

The claim under test: the existing Electrical DC solver can participate as the
forward model in quantitative inference, real EVPI/EVSI are computed from its
predictions, action selection runs through the frozen CampaignRunner, and the
executed result reaches the posterior only through the M1 evidence/admission
path — with the analytic oracle confined to the grader.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np

from experiments.electrical_e1 import DECISION_PATH_MODULES
from experiments.electrical_e1.e1_config import (
    ACTIONS,
    THRESHOLD_OHM,
    VERIFICATION_REL_TOL,
    config_hash,
    theta_grid,
)
from experiments.electrical_e1.e1_harness import (
    ACTION_BY_ID,
    build_e1_campaign,
    preregistration_hash,
)
from experiments.electrical_e1.e1_model import (
    E1Observation,
    best_decision,
    evpi,
    evsi,
    forward_predictions,
    posterior_weights,
    prior_weights,
)
from experiments.electrical_e1.e1_run import run_e1, run_solver_verification
from src.engcore.sria import BeliefWriteViolation
from src.engcore.sria.errors import BeliefWriteViolation as _BWV  # noqa: F401

TOL = 1e-9

#: The scored E1 run, executed once and shared (deterministic).
_RESULT = None


def e1_result():
    global _RESULT
    if _RESULT is None:
        _RESULT = run_e1()
    return _RESULT


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


def _synthetic_observations() -> list[E1Observation]:
    """Property-test observations. Plain numbers; no truth involved."""
    return [
        E1Observation("measure_vmid_10V", 10.0, 5.60, 0.05),
        E1Observation("measure_vmid_10V", 10.0, 5.72, 0.05),
        E1Observation("measure_vmid_0V01", 0.01, 0.006, 0.05),
    ]


# =====================================================================
# 1. Preregistration
# =====================================================================

def test_1_preregistered_config_hash_is_stable():
    first = config_hash()
    assert config_hash() == first
    assert len(first) == 64
    pre = preregistration_hash()
    assert preregistration_hash() == pre
    assert pre != first          # it also covers the grader truth
    result = e1_result()
    assert result["config_hash"] == first
    assert result["preregistration_hash"] == pre


# =====================================================================
# 2. Oracle isolation
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


def test_2_analytic_oracle_is_inaccessible_from_the_decision_path():
    import experiments.electrical_e1 as package

    root = Path(package.__file__).resolve().parent
    for name in DECISION_PATH_MODULES:
        absolute, siblings = _module_imports(root / f"{name}.py")
        assert "e1_truth" not in siblings, (name, siblings)
        assert not any("e1_truth" in c for c in absolute), (name, absolute)
        # Transitively: any sibling reached is itself a decision-path module.
        assert siblings <= set(DECISION_PATH_MODULES), (name, siblings)

    # The harness and grader are EXPECTED to import it — otherwise this test
    # would pass because nothing anywhere used the oracle.
    _abs, harness_siblings = _module_imports(root / "e1_harness.py")
    assert "e1_truth" in harness_siblings
    _abs, run_siblings = _module_imports(root / "e1_run.py")
    assert "e1_truth" in run_siblings


# =====================================================================
# 3. Solver verification gate
# =====================================================================

def test_3_solver_matches_the_analytic_oracle_on_the_frozen_set():
    verification = e1_result()["solver_verification"]
    assert verification["passed"] is True
    assert verification["worst_rel_error"] <= VERIFICATION_REL_TOL
    assert len(verification["points"]) == 8
    # And the numerical error is quantitatively negligible next to the noise.
    assert verification["numerical_error_vs_noise"]["ratio"] < 1e-6


def test_3b_raw_output_adapter_is_faithful_to_the_public_wrapper():
    """The re-derived RawSolverOutput matches the ScientificResult exactly."""
    from experiments.electrical_e1.e1_config import VMID_METRIC

    _runner, harness, _gateway, _arbiter = _fresh_campaign()
    executor = harness.executor_impl
    assert executor.raw_by_execution, "campaign executed nothing"
    for execution_id, (result, raw) in executor.raw_by_execution.items():
        assert raw.succeeded
        assert raw.values[VMID_METRIC] == result.values[
            VMID_METRIC
        ].magnitude_in("volt"), execution_id
        assert raw.residuals["linear_system"] <= 1e-9


_CAMPAIGN = None


def _fresh_campaign():
    """One executed campaign (default truth), shared across tests."""
    global _CAMPAIGN
    if _CAMPAIGN is None:
        runner, harness, gateway, arbiter = build_e1_campaign(
            run_id="e1-test-run"
        )
        runner.run_campaign()
        _CAMPAIGN = (runner, harness, gateway, arbiter)
    return _CAMPAIGN


# =====================================================================
# 4-6. Posterior properties
# =====================================================================

def test_4_posterior_is_deterministic():
    observations = _synthetic_observations()
    first = posterior_weights(observations)
    second = posterior_weights(observations)
    assert np.array_equal(first, second)
    assert abs(float(first.sum()) - 1.0) < 1e-12


def test_5_posterior_is_order_invariant():
    observations = _synthetic_observations()
    forward = posterior_weights(observations)
    backward = posterior_weights(list(reversed(observations)))
    assert np.allclose(forward, backward, atol=1e-14, rtol=0.0)


def test_6_batch_equals_sequential_update():
    observations = _synthetic_observations()
    batch = posterior_weights(observations)
    running = prior_weights()
    for observation in observations:
        running = posterior_weights([observation], prior=running)
    assert np.allclose(batch, running, atol=1e-12, rtol=0.0)


# =====================================================================
# 7. Contraction
# =====================================================================

def test_7_posterior_contracts_after_informative_evidence():
    grid = theta_grid()
    prior = prior_weights()
    prior_sd = float(
        np.sqrt(np.dot(prior, (grid - np.dot(prior, grid)) ** 2))
    )

    result = e1_result()
    after = result["posterior_after"]
    assert prior_sd > 500.0
    assert after["sd_r2_ohm"] < prior_sd / 10.0
    # ...and the decision risk collapsed with it.
    assert result["prior_stage"]["posterior"]["evpi"] > 0.5
    assert after["evpi"] < 1e-3


# =====================================================================
# 8. Prediction precedes observation
# =====================================================================

def test_8_predictive_is_generated_from_the_pre_observation_state():
    result = e1_result()
    sequences = result["campaign"]["event_sequences"]
    assert sequences["prediction_preceded_observation"] is True
    assert sequences["decision_recommended"][0] < sequences["execution_started"][0]

    # The recorded decision quantities for iteration 1 were computed from the
    # empty observation set — the state before anything was measured.
    first_iteration = [
        entry
        for entry in result["campaign"]["decision_log"]
        if entry["snapshot_id"].endswith("snap-1")
    ]
    assert first_iteration
    assert all(entry["n_observations"] == 0 for entry in first_iteration)
    # And the event log is hash-chained, so the ordering is tamper-evident.
    runner, _h, _g, _a = _fresh_campaign()
    assert runner.events.verify_chain() is True


# =====================================================================
# 9-13. EVPI / EVSI mathematics
# =====================================================================

def test_9_evpi_matches_an_independent_computation():
    """Independent arithmetic, no shared code with the implementation."""
    grid = theta_grid()
    p = sum(1 for r2 in grid if r2 > THRESHOLD_OHM) / len(grid)
    eu_a = -4.0 * (1.0 - p)          # loss(A|below) = 4
    eu_b = -1.0 * p                  # loss(B|above) = 1
    independent = 0.0 - max(eu_a, eu_b)
    assert abs(evpi(prior_weights()) - independent) < 1e-12
    assert abs(e1_result()["prior_stage"]["posterior"]["evpi"] - independent) < 1e-12


def test_10_evsi_is_non_negative_within_tolerance():
    prior = prior_weights()
    for action in ACTIONS:
        assert evsi(prior, action) >= -TOL, action.action_id


def test_11_evsi_is_bounded_by_evpi():
    prior = prior_weights()
    ceiling = evpi(prior)
    for action in ACTIONS:
        assert evsi(prior, action) <= ceiling + TOL, action.action_id


def test_12_evsi_evppi_evpi_ordering():
    """EVPPI(R2) = EVPI: R2 is the complete latent decision-relevant state.

    Stated, not manufactured — with one parameter the partial-perfect and
    full-perfect information quantities coincide by definition.
    """
    prior = prior_weights()
    evppi = evpi(prior)              # the identity, made explicit
    for action in ACTIONS:
        value = evsi(prior, action)
        assert value <= evppi + TOL <= evpi(prior) + 2 * TOL
    assert "complete latent decision-relevant state" in (
        e1_result()["evppi_statement"]
    )


def test_13_informative_action_is_worth_more_than_the_weak_one():
    prior = prior_weights()
    strong = evsi(prior, ACTION_BY_ID["measure_vmid_10V"])
    weak = evsi(prior, ACTION_BY_ID["measure_vmid_0V01"])
    premium = evsi(prior, ACTION_BY_ID["measure_vmid_10V_premium"])

    assert strong > 0.5
    assert abs(weak) < 1e-3          # the 4 mV signal is under a 50 mV floor
    assert strong > weak + 0.5
    # The premium instrument is MORE informative than the standard one —
    # its uninformativeness is not why it loses; its price is.
    assert premium >= strong - TOL
    table = e1_result()["prior_stage"]["evsi_table"]
    assert table["measure_vmid_10V_premium"]["net"] < 0.0
    assert table["measure_vmid_10V"]["net"] > 0.0
    # INFORMATIONALLY_USEFUL_BUT_TOO_EXPENSIVE != INFORMATIONALLY_UNHELPFUL:
    assert table["measure_vmid_10V_premium"]["evsi"] > 100 * abs(
        table["measure_vmid_0V01"]["evsi"]
    )


# =====================================================================
# 14. No oracle leakage through the campaign
# =====================================================================

def test_14_changing_grader_truth_changes_nothing_before_observation():
    """Two campaigns with different hidden truths agree on every
    pre-observation quantity, and diverge only through executed observations."""
    runner_a, harness_a, gateway_a, _ = build_e1_campaign(
        true_r2_ohm=1378.0, run_id="e1-leak-a"
    )
    runner_b, harness_b, gateway_b, _ = build_e1_campaign(
        true_r2_ohm=900.0, run_id="e1-leak-b"
    )

    # Pre-observation: identical priors, identical EVSI, identical decision.
    prior_a = harness_a.posterior_for(harness_a.current_observations())
    prior_b = harness_b.posterior_for(harness_b.current_observations())
    assert np.array_equal(prior_a, prior_b)
    for action in ACTIONS:
        assert evsi(prior_a, action) == evsi(prior_b, action)
    assert best_decision(prior_a) == best_decision(prior_b)

    # Execute both. Now — and only now — the worlds may diverge.
    runner_a.run_campaign()
    runner_b.run_campaign()
    obs_a = harness_a.current_observations()
    obs_b = harness_b.current_observations()
    assert obs_a and obs_b
    assert obs_a[0].y_volt != obs_b[0].y_volt
    decision_a, _ = best_decision(harness_a.posterior_for(obs_a))
    decision_b, _ = best_decision(harness_b.posterior_for(obs_b))
    assert decision_a == "A"         # truth 1378 > 1200
    assert decision_b == "B"         # truth 900 <= 1200


# =====================================================================
# 15-17. The evidence/admission boundary
# =====================================================================

def test_15_solver_output_cannot_directly_write_belief():
    runner, harness, gateway, _arbiter = _fresh_campaign()
    executor = harness.executor_impl
    execution = next(iter(executor.completed.values()))

    _raises(BeliefWriteViolation, gateway.submit, execution)
    _raises(BeliefWriteViolation, gateway.submit, execution.result)
    for subject in (execution, execution.result, type(execution)):
        for forbidden in ("submit", "admit", "update_standing", "_apply"):
            assert not hasattr(subject, forbidden), (subject, forbidden)


def test_16_admitted_observation_changes_the_posterior_through_inference():
    _runner, harness, gateway, _arbiter = _fresh_campaign()
    observations = harness.current_observations()
    assert observations                       # something was admitted
    assert len(gateway.belief) == 1
    posterior = harness.posterior_for(observations)
    assert not np.array_equal(posterior, prior_weights())
    # ...and the posterior is reconstructible from the admitted set alone.
    assert np.array_equal(posterior, posterior_weights(observations))


def test_17_unadmitted_observation_changes_the_posterior_by_exactly_zero():
    runner, harness, gateway, _arbiter = _fresh_campaign()
    before = harness.current_observations()
    posterior_before = harness.posterior_for(before)

    # A fresh execution produces candidate evidence that is NEVER admitted.
    executor = harness.executor_impl
    candidates = harness.generators(runner.run)[0].generate(None)
    action = next(
        c for c in candidates if c.action_id == "measure_vmid_0V01"
    )
    execution = executor.execute(action, execution_id="e1-unadmitted-probe")
    evidence = harness.build_evidence(
        execution, None, evidence_id="e1-ev-unadmitted"
    )
    assert evidence is not None

    # CANDIDATE evidence cannot even enter the gateway...
    _raises(BeliefWriteViolation, gateway.submit, evidence)
    # ...and the posterior is bit-identical: zero update, not merely small.
    after = harness.current_observations()
    assert after == before
    assert np.array_equal(harness.posterior_for(after), posterior_before)


# =====================================================================
# 18. Terminal decision vs the oracle
# =====================================================================

def test_18_terminal_decision_agrees_with_the_analytic_grader():
    terminal = e1_result()["terminal_decision"]
    assert terminal["sria_decision"] == "A"
    assert terminal["oracle_decision"] == "A"
    assert terminal["correct"] is True


# =====================================================================
# Integration details worth locking
# =====================================================================

def test_action_selection_is_explainable_from_the_decision_basis():
    runner, _h, _g, _a = _fresh_campaign()
    record = runner.run.record(1)
    assert record.selected_action_id == "measure_vmid_10V"
    recommendation = runner.recommendation(record.recommendation_id)
    assert recommendation.coherence is not None
    assert recommendation.is_state_coherent is True
    assert recommendation.dependency_manifest.manifest_digest == (
        record.decision_basis_digest
    )
    # total = EVSI * (1 - p_cf) + failure_voi - cost, with p_cf = 0 declared:
    score = next(
        s for s in recommendation.scores if s.action_id == "measure_vmid_10V"
    )
    gain = score.component("conditional_success_utility_gain").value
    cost = score.component("expected_cost").value
    assert abs(score.total - (gain - cost)) < 1e-12
    assert cost == ACTION_BY_ID["measure_vmid_10V"].cost
    # The information term IS the quadrature EVSI — nothing hand-authored.
    assert abs(gain - evsi(prior_weights(), ACTION_BY_ID["measure_vmid_10V"])) < 1e-12


def test_campaign_pauses_economically_without_self_certifying():
    runner, _h, _g, _a = _fresh_campaign()
    assert runner.run.state.value == "paused"
    assert runner.run.pause_reason.value == "no_action_worth_buying"
    assert runner.run.stop_review_outcome == "stop_not_assessed"
    assert runner.run.is_certification is False


def test_calibration_telemetry_is_recorded_and_separate_from_belief():
    _runner, harness, gateway, _a = _fresh_campaign()
    assert len(harness.memory) == 1
    entry = harness.memory.entries[0]
    assert entry.kind.value == "calibration_diagnostic"
    assert entry.payload["wall_seconds"] > 0.0
    assert len(gateway.belief) == 1           # telemetry did not touch belief


def test_forward_map_is_the_real_solver_not_a_formula():
    """The decision path's predictions come from solve_circuit, verified by
    cross-checking one grid point against a fresh independent solver run."""
    from experiments.electrical_e1.e1_model import solver_vmid

    grid = theta_grid()
    predictions = forward_predictions(10.0)
    index = 37
    fresh = solver_vmid(10.0, float(grid[index]), run_id="e1-crosscheck")
    assert predictions[index] == fresh


def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("SRIA E1 — electrical quantitative verification")
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
        print(f"E1: FAIL ({failures}/{len(tests)})")
        return 1
    print(f"E1: PASS ({len(tests)}/{len(tests)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
