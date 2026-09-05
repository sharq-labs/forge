"""T2 — repeated-draw numerical calibration of the thermal fidelity ladder.

What these protect:

    T1 is frozen and reused, not edited
    the preregistration is intact and the grader truth never leaked
    the draws are independent, reproducible, and shared across arms
    the control arm really is zero-discretization
    the measured result is what the report claims, and no more
"""

from __future__ import annotations

import ast
import hashlib
import math
from pathlib import Path

import numpy as np
import pytest

from experiments.thermal_t1 import t1_config, t1_run, t1_truth
from experiments.thermal_t2 import BASE_COMMIT, DECISION_PATH_MODULES, T2_VERSION
from experiments.thermal_t2 import t2_config, t2_run, t2_truth

REPO_ROOT = Path(__file__).resolve().parents[1]
T2_ROOT = Path(t2_config.__file__).resolve().parent


@pytest.fixture(scope="module")
def study() -> dict:
    return t2_run.run_t2()


# =====================================================================
# T1 is reused, not edited
# =====================================================================

def test_t1_and_shared_harness_digests_match() -> None:
    """T2's numbers are about the ladder T1 froze. If T1 moved, they aren't."""
    mismatched = []
    for relative, expected in t2_config.T1_FROZEN_FILE_DIGESTS.items():
        path = REPO_ROOT / relative
        assert path.is_file(), f"pinned file missing: {relative}"
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            mismatched.append(relative)
    assert not mismatched, (
        f"T1 or the shared harness changed under T2: {mismatched}"
    )


def test_t2_never_writes_into_the_t1_package() -> None:
    """No T2 module may open a path inside experiments/thermal_t1."""
    for path in T2_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "thermal_t1" not in source or "import" in source, path.name
        for forbidden in ("write_text(", "open(", "unlink(", "mkdir("):
            if forbidden in source:
                assert "thermal_t1" not in source.split(forbidden)[1][:200], (
                    f"{path.name} writes near a thermal_t1 reference"
                )


def test_the_fixed_design_is_imported_from_t1_not_restated() -> None:
    """Anything restated could drift. These must be the same objects."""
    assert t2_config.OBSERVATION_SIGMA is t1_config.OBSERVATION_SIGMA
    assert t2_config.OBSERVATION_COUNT is t1_config.OBSERVATION_COUNT
    assert t2_config.RUNGS is t1_config.RUNGS
    assert t2_config.NOMINAL_LEVEL == t1_config.CREDIBLE_MASS
    assert t2_truth.ALPHA_TRUE is t1_truth.ALPHA_TRUE
    assert t2_config.alpha_grid() == t1_config.alpha_grid()


def test_t2_uses_t1s_forward_maps_unchanged() -> None:
    for spec in t1_config.RUNGS:
        from_t2, _ = t2_run.arm_forward_map(spec.rung_id)
        from_t1, _ = t1_run.forward_map(spec.rung_id)
        assert from_t2 is from_t1


# =====================================================================
# Preregistration integrity
# =====================================================================

def test_decision_path_never_imports_a_grader_truth() -> None:
    for module_name in DECISION_PATH_MODULES:
        source = (T2_ROOT / f"{module_name}.py").read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported.add(module)
                imported.update(f"{module}.{a.name}" for a in node.names)
        leaked = {n for n in imported if "truth" in n.lower()}
        assert not leaked, f"{module_name} imports a grader truth: {leaked}"


def test_config_hash_is_stable_and_preregistration_covers_both_halves() -> None:
    assert t2_config.config_hash() == t2_config.config_hash()
    expected = hashlib.sha256(
        f"{t2_config.config_hash()}|{t2_truth.truth_hash()}".encode("utf-8")
    ).hexdigest()
    assert t2_run.preregistration_hash() == expected


def test_every_required_preregistration_element_is_present() -> None:
    """Replication count, seed rule, level, metrics, criteria — all four."""
    payload = t2_config.config_payload()
    assert payload["replications"] == t2_config.REPLICATIONS > 0
    assert payload["seed_rule"] and payload["seed_entropy"]
    assert payload["nominal_level"] == 0.95
    assert len(payload["metrics"]) == len(t2_config.METRICS) >= 10
    assert payload["acceptance_criteria"]
    assert payload["falsification_criteria"]
    assert payload["coverage_acceptance_bands"]


def test_acceptance_bands_bracket_the_point_predictions() -> None:
    """A band that excluded its own prediction would be incoherent."""
    for arm_id, predicted in t2_config.PREDICTED_COVERAGE.items():
        low, high = t2_config.COVERAGE_ACCEPTANCE_BANDS[arm_id]
        assert low <= predicted <= high, arm_id


def test_seed_entropy_is_disjoint_from_t1() -> None:
    assert t2_config.SEED_ENTROPY != t1_config.NOISE_SEED


# =====================================================================
# The draws
# =====================================================================

def test_draws_are_reproducible() -> None:
    assert t2_truth.all_observations() == t2_truth.all_observations()


def test_draws_are_distinct_across_replications() -> None:
    draws = t2_truth.all_observations()
    assert len(draws) == t2_config.REPLICATIONS
    assert len({tuple(d) for d in draws}) == t2_config.REPLICATIONS


def test_draws_match_the_declared_observation_model() -> None:
    """If the drawn sigma were not the declared sigma the likelihood would be
    wrong and every coverage number would be meaningless."""
    flat = np.asarray(t2_truth.all_observations(), dtype=np.float64).ravel()
    residuals = flat - t2_truth.true_qoi()
    n = residuals.size
    assert abs(residuals.mean()) < 4.0 * t2_config.OBSERVATION_SIGMA / math.sqrt(n)
    assert residuals.std(ddof=1) == pytest.approx(
        t2_config.OBSERVATION_SIGMA, rel=0.06
    )


def test_replication_index_is_bounds_checked() -> None:
    with pytest.raises(IndexError):
        t2_truth.replication_observations(t2_config.REPLICATIONS)


def test_every_arm_sees_the_same_draws(study: dict) -> None:
    counts = {arm["replications"] for arm in study["arms"]}
    assert counts == {t2_config.REPLICATIONS}


# =====================================================================
# The control arm
# =====================================================================

def test_control_arm_has_negligible_discretization_contribution(
    study: dict,
) -> None:
    """In the units that matter: alpha, relative to the posterior sd.

    The control's forward map is the closed form and has no discretization
    error at all. Its small non-zero residual comes from evaluating that map
    AT alpha_true by linear interpolation on the alpha grid -- alpha_true sits
    deliberately between nodes -- and is pinned by the next test.
    """
    control = next(a for a in study["arms"] if a["is_control"])
    assert (
        abs(control["discretization_contribution"])
        < 1e-4 * control["posterior_sd_mean"]
    )


def test_the_control_arms_residual_is_exactly_grid_interpolation(
    study: dict,
) -> None:
    """Explained, not tolerated.

    Linear interpolation of a convex f over spacing h overshoots by
    f'' h^2 s(1-s)/2 at fractional position s between nodes. If the residual
    matches that to a few parts in 1e4 it is interpolation and nothing else --
    in particular it is not a defect in ``exact_midpoint``.
    """
    grid = t2_config.alpha_grid()
    alpha = t2_truth.ALPHA_TRUE
    h = grid.spacing
    k = math.pi**2 * t2_config.END_TIME_S / t2_config.LENGTH_M**2
    second_derivative = t2_truth.true_qoi() * k**2

    index = int(np.searchsorted(grid.array, alpha)) - 1
    fraction = (alpha - grid.array[index]) / h
    predicted = second_derivative * h**2 * fraction * (1.0 - fraction) / 2.0

    control = next(a for a in study["arms"] if a["is_control"])
    assert control["discretization_error_at_truth"] == pytest.approx(
        predicted, rel=1e-3
    )


def test_the_interpolation_artifact_is_common_to_every_arm(study: dict) -> None:
    """It therefore cancels in comparisons between arms, which is why it does
    not disturb the fidelity conclusion."""
    grid = t2_config.alpha_grid()
    alpha = t2_truth.ALPHA_TRUE
    for arm in study["arms"]:
        forward, _ = t2_run.arm_forward_map(arm["arm_id"])
        assert float(np.interp(alpha, grid.array, forward)) == pytest.approx(
            arm["discretization_error_at_truth"] + t2_truth.true_qoi(),
            rel=1e-12,
        )


def test_control_arm_is_not_costed(study: dict) -> None:
    control = next(a for a in study["arms"] if a["is_control"])
    assert control["work_proxy"] is None


def test_control_arm_calibrates_at_the_nominal_level(study: dict) -> None:
    """Everything else in T2 is conditional on this.

    With no discretization error the posterior is correctly specified, so its
    credible interval must cover at about the nominal rate. If this fails the
    inference is broken and no statement about fidelity follows.
    """
    control = next(a for a in study["arms"] if a["is_control"])
    low, high = t2_config.COVERAGE_ACCEPTANCE_BANDS[t2_config.CONTROL_ARM_ID]
    assert low <= control["empirical_coverage"] <= high
    assert abs(control["standardized_error_mean"]) < 0.15
    assert control["standardized_error_sd"] == pytest.approx(1.0, abs=0.15)


def test_conclusions_are_licensed_by_the_control(study: dict) -> None:
    assert study["falsification"]["conclusions_about_fidelity_are_licensed"]


# =====================================================================
# The preregistered result
# =====================================================================

def test_all_acceptance_criteria_passed(study: dict) -> None:
    assert study["acceptance"]["all_passed"], study["acceptance"]["failed"]


def test_no_falsification_trigger_fired(study: dict) -> None:
    assert not study["falsification"]["fired"]


def test_coverage_predictions_held(study: dict) -> None:
    for arm_id, check in study["prediction_check"].items():
        assert check["in_band"], (
            f"{arm_id}: predicted {check['predicted_coverage']}, observed "
            f"{check['observed_coverage']}, band {check['band']}"
        )


def test_coarse_rung_never_covers(study: dict) -> None:
    coarse = next(a for a in study["arms"] if a["arm_id"] == "coarse")
    assert coarse["empirical_coverage"] == 0.0
    assert coarse["confidently_wrong_rate"] == 1.0


def test_coverage_increases_with_fidelity(study: dict) -> None:
    ordered = [
        a for a in study["arms"] if not a["is_control"]
    ]
    coverages = [a["empirical_coverage"] for a in ordered]
    assert all(b > a for a, b in zip(coverages, coverages[1:]))


def test_noise_dominates_only_at_the_reference_rung(study: dict) -> None:
    budget = {
        e["arm_id"]: e["noise_dominates"]
        for e in study["error_budget"]["per_arm"]
    }
    assert budget["coarse"] is False
    assert budget["medium"] is False
    assert budget["reference"] is True
    assert study["error_budget"]["noise_dominates_from_rung"] == "reference"


def test_posterior_sd_is_effectively_draw_independent(study: dict) -> None:
    """F4's premise, checked: the claimed uncertainty does not react to the
    data. That is what makes 'confident' a property of the rung."""
    for arm in study["arms"]:
        assert arm["posterior_sd_relative_spread"] < 0.01, arm["arm_id"]


def test_standardized_error_sd_is_about_one_everywhere(study: dict) -> None:
    """Discretization shifts the posterior; it does not widen or narrow it.
    So z has unit spread at every arm and only its centre moves."""
    for arm in study["arms"]:
        assert arm["standardized_error_sd"] == pytest.approx(1.0, abs=0.15), (
            arm["arm_id"]
        )


# =====================================================================
# The post-hoc observations, and their limits
# =====================================================================

def test_qoi_prediction_error_is_blind_to_the_bias(study: dict) -> None:
    """Every arm predicts the assimilated observable equally well, including
    the one that is 32 sd wrong about alpha."""
    blind = study["post_hoc_observations"][
        "qoi_prediction_error_is_blind_to_the_bias"
    ]
    assert blind["qoi_rms_relative_spread_across_arms"] < 0.01
    assert blind["qoi_rms_is_at_the_noise_floor"]


def test_post_hoc_observations_are_labelled_as_not_preregistered(
    study: dict,
) -> None:
    assert study["post_hoc_observations"]["preregistered"] is False
    report = t2_run.render_markdown(study)
    assert "Observed, not preregistered" in report


def test_post_hoc_observations_are_not_acceptance_criteria(study: dict) -> None:
    """They were noticed after the fact and must not be counted as if they
    had been predicted."""
    names = " ".join(study["acceptance"]["checks"]).lower()
    assert "qoi" not in names
    assert "blind" not in names


# =====================================================================
# Claim discipline
# =====================================================================

def test_report_makes_no_physical_validation_claim(study: dict) -> None:
    report = " ".join(t2_run.render_markdown(study).split()).lower()
    for banned in (
        "experimentally validated",
        "physically validated",
        "validated against experiment",
        "autonomous scientist",
        "scientific intelligence",
        "proves that",
        "adaptive fidelity selection is",
    ):
        assert banned not in report, banned


def test_report_states_the_synthetic_scope_and_the_non_goals(
    study: dict,
) -> None:
    report = t2_run.render_markdown(study).lower()
    assert "synthetic" in report
    assert "no physical validation" in report
    assert "no adaptive fidelity selection" in report


def test_version_and_base_commit_are_recorded(study: dict) -> None:
    assert study["experiment_version"] == T2_VERSION
    assert study["base_commit"] == BASE_COMMIT
    assert len(BASE_COMMIT) == 40
