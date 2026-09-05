"""K1 — preregistration integrity, artifact consistency, and frozen-history safety.

These tests guard the *experiment*, not the domain: that the preregistration is
complete and pinned, that the recorded results are the ones the frozen
configuration describes, that every acceptance criterion the report claims is
actually backed by the recorded data, and that no historical frozen experiment
was touched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from experiments.kinetics_k1 import BASE_COMMIT, K1_VERSION
from experiments.kinetics_k1 import k1_config
from src.engcore.domains.kinetics.cstr import (
    INVARIANT_REL_TOL,
    STEADY_STATE_REL_TOL,
    TOLERANCE_REL_TOL,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
K1_DIR = REPO_ROOT / "experiments" / "kinetics_k1"


@pytest.fixture(scope="module")
def results() -> dict:
    return json.loads((K1_DIR / "k1_results.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def frozen() -> dict:
    return json.loads((K1_DIR / "k1_config_frozen.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def by_regime(results) -> dict:
    return {row["regime_id"]: row for row in results["regimes"]}


# =====================================================================
# The preregistration is pinned
# =====================================================================

def test_config_hash_is_stable_and_matches_the_frozen_artifact(frozen) -> None:
    recomputed = hashlib.sha256(
        json.dumps(
            k1_config.config_payload(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    assert recomputed == k1_config.config_hash()
    assert recomputed == frozen["config_hash"], (
        "the preregistration changed after it was frozen; if this was "
        "intentional the experiment version must be incremented and the study "
        "rerun from scratch"
    )


def test_the_results_were_produced_by_the_frozen_configuration(
    results, frozen
) -> None:
    assert results["config_hash"] == frozen["config_hash"]
    assert results["experiment_version"] == K1_VERSION
    assert results["base_commit"] == BASE_COMMIT


def test_every_required_preregistration_element_is_present(frozen) -> None:
    config = frozen["config"]
    required = {
        "scientific_question",
        "preregistration_kind",
        "chemistry",
        "base_operation",
        "integration",
        "regimes",
        "invalid_declarations",
        "failure_semantics_matrix",
        "metrics",
        "gate_thresholds",
        "acceptance_criteria",
        "falsification_criteria",
        "no_tuning_after_results",
        "non_goals",
        "randomness",
        "parameter_provenance",
    }
    assert required <= set(config)
    for key in required:
        assert config[key], key


def test_the_preregistration_declares_its_own_limitations(frozen) -> None:
    """It must not present itself as a blind preregistration."""
    kind = frozen["config"]["preregistration_kind"].lower()
    assert "feasibility-informed" in kind
    assert "not blindness" in kind
    provenance = frozen["config"]["gate_thresholds"]["provenance"].lower()
    assert "exploratory" in provenance


def test_the_parameterization_does_not_claim_verification_it_lacks(
    frozen,
) -> None:
    provenance = frozen["config"]["parameter_provenance"].lower()
    assert "not been checked against the printed source" in provenance


def test_the_gate_thresholds_recorded_are_the_ones_in_force(frozen) -> None:
    thresholds = frozen["config"]["gate_thresholds"]
    assert thresholds["tolerance_rel_tol"] == TOLERANCE_REL_TOL
    assert thresholds["invariant_rel_tol"] == INVARIANT_REL_TOL
    assert thresholds["steady_state_rel_tol"] == STEADY_STATE_REL_TOL


def test_the_experiment_declares_it_has_no_randomness(frozen) -> None:
    assert "no seed" in frozen["config"]["randomness"].lower() or (
        "none" in frozen["config"]["randomness"].lower()
    )


def test_no_tuning_rule_is_recorded_verbatim(frozen) -> None:
    assert "not adjusted" in frozen["config"]["no_tuning_after_results"]
    assert "rerun from scratch" in frozen["config"]["no_tuning_after_results"]


def test_the_invalidated_first_run_is_documented_not_erased() -> None:
    """The declared correction procedure leaves a trail."""
    import experiments.kinetics_k1 as package

    text = package.__doc__ or ""
    assert "1.0.0 — INVALIDATED" in text
    assert "MAX_ITERATIONS" in text
    assert K1_VERSION == "1.0.1"


# =====================================================================
# Every acceptance claim is backed by the recorded data
# =====================================================================

def test_all_acceptance_criteria_are_recorded_and_met(results) -> None:
    assert len(results["acceptance"]) == len(k1_config.ACCEPTANCE_CRITERIA)
    failed = [key for key, ok in results["acceptance"].items() if not ok]
    assert failed == [], failed
    assert results["acceptance_all_met"] is True


def test_every_preregistered_prediction_was_met(results) -> None:
    missed = [k for k, ok in results["predictions_met"].items() if not ok]
    assert missed == [], missed


def test_a1_the_benign_regime_carries_real_units(by_regime) -> None:
    units = {v["units"] for v in by_regime["R1"]["values"].values()}
    assert {"mole / meter ** 3", "kelvin", "second", "dimensionless"} <= units


def test_a2_stiffness_was_measured_not_asserted(by_regime) -> None:
    assert by_regime["R1"]["stiffness_work_ratio"] < 5.0
    assert by_regime["R2"]["stiffness_work_ratio"] > 20.0
    assert by_regime["R3"]["stiffness_work_ratio"] > 200.0
    # The strongly stiff arm defeats the explicit probe outright.
    assert by_regime["R3"]["stiffness"]["explicit_completed"] is False
    assert by_regime["R3"]["stiffness"]["work_ratio_is_lower_bound"] is True


def test_the_frozen_artifact_uses_the_superseded_budget_accounting(
    by_regime,
) -> None:
    """P3.2 compatibility, pinned rather than left implicit.

    v1.0.1 counted the REFUSED call as work: a 500-evaluation budget was
    reported as 501 evaluations. The artifact is frozen and is not rewritten,
    so a reader comparing it against a fresh run will see 501 here and 500
    there. The corrected semantics — ``rhs_evaluations_completed`` = 500,
    ``rhs_evaluations_attempted`` = 501 — apply prospectively and are enforced
    by the P3.2 tests in ``tests/domains/kinetics``.
    """
    r5 = by_regime["R5"]
    assert r5["rhs_evaluations"] == 501, (
        "the frozen artifact records the superseded attempted-count semantics"
    )
    assert r5["rhs_budget"] == 500


def test_a3_the_computational_limit_produced_a_genuine_non_success(
    by_regime,
) -> None:
    r5 = by_regime["R5"]
    assert r5["convergence_state"] == "max_iterations"
    assert r5["values"] == {}
    assert r5["is_usable"] is False
    assert r5["outcome_detail"] == "rhs_budget_exhausted"
    assert 0.0 < r5["fraction_of_horizon_completed"] < 1.0


def test_a4_execution_success_and_usability_are_recorded_separately(
    by_regime,
) -> None:
    r7, r8 = by_regime["R7"], by_regime["R8"]
    assert r8["convergence_state"] == "converged" and r8["is_usable"] is False
    assert r7["convergence_state"] == "converged" and r7["is_usable"] is True
    # ...and the gate is what catches R7.
    assert r7["attained_levels_gate"] == []
    assert by_regime["R1"]["attained_levels_gate"]


def test_a5_every_invalid_declaration_was_refused_by_the_domain(
    results,
) -> None:
    assert len(results["invalid_declarations"]) == len(
        k1_config.INVALID_DECLARATIONS
    )
    for declaration in results["invalid_declarations"]:
        assert declaration["refused"] is True, declaration["label"]
        assert declaration["refused_by_domain"] is True, declaration["label"]
        assert declaration["error_type"] == "ReactorConfigurationError"


def test_a6_both_independent_reference_mechanisms_awarded_a_level(
    by_regime,
) -> None:
    analytic = [
        rid for rid, row in by_regime.items()
        if "analytically_verified" in row["attained_levels_gate"]
    ]
    cross = [
        rid for rid, row in by_regime.items()
        if "cross_solver_validated" in row["attained_levels_gate"]
    ]
    assert analytic, "no regime earned the exact-invariant claim"
    assert cross, "no regime earned the independent steady-state claim"
    # The analytic claim is only available where the invariant is exact.
    for rid in analytic:
        assert by_regime[rid]["adiabatic"] is True


def test_a7_all_five_failure_cases_are_represented(results) -> None:
    for case, seen in results["failure_cases_represented"].items():
        assert seen is True, case


def test_case_b_is_labelled_as_an_adapter_probe_not_a_regime(results) -> None:
    probe = results["step_size_collapse_probe"]
    assert probe["convergence_state"] == "not_converged"
    assert probe["partial_trajectory_preserved"] is True
    assert probe["metrics_extracted"] is False
    assert "NOT a scientific regime" in probe["purpose"]
    assert "globally bounded" in probe["why_not_a_regime"]


def test_a8_no_single_solve_claimed_numerical_convergence(by_regime) -> None:
    for rid, row in by_regime.items():
        assert "numerically_converged" not in row["attained_levels_per_solve"], rid
        if row["values"]:
            assert row["attained_levels_per_solve"] == ["dimensionally_valid"], rid


def test_a9_three_steady_states_but_one_attractor(by_regime) -> None:
    r6a, r6b = by_regime["R6a"], by_regime["R6b"]
    assert r6a["steady_states_found"] == 3
    assert abs(
        r6a["values"]["T:final"]["magnitude"]
        - r6b["values"]["T:final"]["magnitude"]
    ) < 1e-6
    # The hot start really did take a different route to the same place.
    assert r6b["max_temperature_k"] > r6a["max_temperature_k"] + 100.0


def test_a10_provenance_is_complete_for_every_regime(by_regime) -> None:
    """Completeness of the FROZEN 1.0.1 artifact, historical semantics included.

    ``git_commit == BASE_COMMIT`` here is the *defect this branch corrected*,
    not the behaviour it endorses: v1.0.1 passed the frozen Core baseline into
    the executing-revision field. The artifact is frozen and is deliberately
    not rewritten, so this test pins what it actually records. The corrected
    semantics — ``git_commit`` = the revision that ran,
    ``core_baseline_commit`` = the frozen Core revision — are enforced on the
    live code path by the P1.1 tests in ``tests/domains/kinetics``.
    """
    for rid, row in by_regime.items():
        provenance = row["provenance"]
        assert provenance["models"], rid
        assert provenance["solvers"], rid
        assert provenance["git_commit"] == BASE_COMMIT, rid
        assert set(provenance["tolerances"]) >= {"rtol", "max_rhs_evaluations"}, rid
        assert provenance["environment"], rid
        assert row["physics_fingerprint"], rid
        assert row["solver_backend"].startswith("scipy.integrate.solve_ivp"), rid


def test_every_regime_in_the_preregistration_was_actually_run(
    results, by_regime
) -> None:
    declared = {spec.regime_id for spec in k1_config.REGIMES}
    assert set(by_regime) == declared


# =====================================================================
# Falsification triggers
# =====================================================================

def test_f4_no_invalid_state_entered_an_admitted_result(by_regime) -> None:
    """A result outside the envelope must never be reported usable."""
    for rid, row in by_regime.items():
        if row["is_usable"] and row["values"]:
            assert row["max_temperature_k"] <= 1000.0, rid
            assert row["min_concentration_mol_per_m3"] >= -1e-9, rid


def test_f7_no_converged_stationary_result_disagrees_with_the_reference(
    by_regime,
) -> None:
    for rid, row in by_regime.items():
        error = row["steady_state_relative_error"]
        if error is not None:
            assert error <= STEADY_STATE_REL_TOL, rid


def test_the_report_states_its_non_goals_and_claims_no_physical_validation(
) -> None:
    """The overclaims must appear only where they are being disclaimed.

    Checked as negated context rather than as absence: the non-goals section
    legitimately contains "no digital twin", and a bare substring ban would
    forbid the disclaimer along with the claim.
    """
    import re

    report = (K1_DIR / "k1_report.md").read_text(encoding="utf-8").lower()
    assert "no physical validation" in report
    assert "no inference of any kind" in report

    affirmative = []
    for banned in (
        "domain neutral",
        "domain-neutral",
        "chemistry generality",
        "inference ready",
        "inference-ready",
        "digital twin",
        "production ready",
        "production-ready",
        "experimentally validated",
    ):
        for match in re.finditer(re.escape(banned), report):
            preceding = report[max(0, match.start() - 10):match.start()]
            if not re.search(r"\b(no|not|never|without)\b[\s\w-]*$", preceding):
                affirmative.append(f"{banned!r} at {match.start()}: …{preceding}")
    assert affirmative == [], affirmative


# =====================================================================
# F5 — historical frozen experiments are untouched
# =====================================================================

def test_k1_does_not_import_or_write_any_frozen_experiment() -> None:
    """F5: no historical artifact may be read, written or re-run by K1."""
    import ast

    frozen_packages = {
        "thermal_t1", "thermal_t2", "thermal_t3",
        "electrical_e1", "electrical_e2", "electrical_e3",
        "electrical_v01_demo", "falsification",
    }
    for module in ("k1_config.py", "k1_run.py", "__init__.py"):
        tree = ast.parse((K1_DIR / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for name in names:
                for package in frozen_packages:
                    assert package not in name, f"{module} imports {name}"


def test_k1_writes_only_inside_its_own_directory() -> None:
    source = (K1_DIR / "k1_run.py").read_text(encoding="utf-8")
    assert "write_text" in source
    # Every write target is built from `root`, which is this file's own parent.
    assert 'root = Path(__file__).resolve().parent' in source
    assert source.count("write_text") == source.count("root /")


def test_the_frozen_thermal_and_electrical_digests_still_match() -> None:
    """The pins T2 and T3 already carry must still hold after K1's work."""
    from experiments.thermal_t2 import t2_config
    from experiments.thermal_t3 import t3_config

    mismatched = [
        relative
        for relative, expected in {
            **t2_config.T1_FROZEN_FILE_DIGESTS,
            **t3_config.T2_FROZEN_FILE_DIGESTS,
        }.items()
        if hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()
        != expected
    ]
    assert mismatched == [], mismatched
