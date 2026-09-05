"""T1 — thermal parameter inference at three fixed fidelity rungs.

These tests protect four different things, and it is worth being explicit about
which is which:

    the preregistration is intact and the grader truth never leaked
    the shared harness computes the same posterior E2 froze
    the base solver has not moved under the experiment
    the measured result is what the report claims it is
"""

from __future__ import annotations

import ast
import hashlib
import math
from pathlib import Path

import numpy as np
import pytest

from experiments.shared.grid_inference import (
    ParameterGrid,
    posterior_weights,
    predictive_mean,
    summarize,
)
from experiments.thermal_t1 import BASE_COMMIT, DECISION_PATH_MODULES, T1_VERSION
from experiments.thermal_t1 import t1_config, t1_run, t1_truth
from src.engcore.sria.calibration import FidelityOwnership

REPO_ROOT = Path(__file__).resolve().parents[1]
T1_ROOT = Path(t1_config.__file__).resolve().parent


@pytest.fixture(scope="module")
def study() -> dict:
    return t1_run.run_t1()


# =====================================================================
# Preregistration integrity
# =====================================================================

def test_config_hash_is_stable_across_calls() -> None:
    assert t1_config.config_hash() == t1_config.config_hash()
    assert len(t1_config.config_hash()) == 64


def test_preregistration_hash_covers_both_halves() -> None:
    expected = hashlib.sha256(
        f"{t1_config.config_hash()}|{t1_truth.truth_hash()}".encode("utf-8")
    ).hexdigest()
    assert t1_run.preregistration_hash() == expected


def test_decision_path_never_imports_the_grader_truth() -> None:
    """The module that defines the experiment may not see the answer.

    Parsed from the import graph rather than trusted, because a single stray
    import would silently turn a blind inference into a lookup.
    """
    for module_name in DECISION_PATH_MODULES:
        source = (T1_ROOT / f"{module_name}.py").read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported.add(module)
                imported.update(f"{module}.{a.name}" for a in node.names)
        leaked = {name for name in imported if "t1_truth" in name}
        assert not leaked, f"{module_name} imports the grader truth: {leaked}"


def test_alpha_true_lies_inside_the_declared_grid_but_off_its_nodes() -> None:
    """If the truth sat exactly on a node the bias measurement would flatter."""
    grid = t1_config.alpha_grid()
    assert grid.contains(t1_truth.ALPHA_TRUE)
    distances = np.abs(grid.array - t1_truth.ALPHA_TRUE)
    assert distances.min() > 0.0


def test_predicted_sensitivity_matches_the_closed_form() -> None:
    assert t1_truth.sensitivity() == pytest.approx(
        t1_config.PREDICTED_SENSITIVITY, rel=1e-4
    )


def test_predicted_posterior_sd_matches_sigma_over_root_n() -> None:
    """sigma / |du/dalpha| / sqrt(n) — the width the design was sized for."""
    expected = (
        t1_config.OBSERVATION_SIGMA
        / abs(t1_truth.sensitivity())
        / math.sqrt(t1_config.OBSERVATION_COUNT)
    )
    assert expected == pytest.approx(t1_config.PREDICTED_POSTERIOR_SD, rel=1e-3)


# =====================================================================
# The frozen base has not moved
# =====================================================================

def test_frozen_thermal_solver_digests_match() -> None:
    """T1's numbers are about a specific solver. Pin it."""
    mismatched = []
    for relative, expected in t1_config.THERMAL_FROZEN_FILE_DIGESTS.items():
        path = REPO_ROOT / relative
        assert path.is_file(), f"pinned file missing: {relative}"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            mismatched.append(relative)
    assert not mismatched, (
        f"the thermal solver changed under T1 at {BASE_COMMIT}: {mismatched}. "
        f"T1's measured bias is a property of that solver; re-run before "
        f"re-pinning"
    )


def test_every_thermal_source_file_is_pinned() -> None:
    on_disk = {
        str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        for path in (REPO_ROOT / "src/engcore/domains/thermal").rglob("*.py")
    }
    assert on_disk == set(t1_config.THERMAL_FROZEN_FILE_DIGESTS)


# =====================================================================
# The shared harness computes what E2 froze
# =====================================================================

def test_shared_posterior_agrees_with_frozen_e2_posterior() -> None:
    """The copied arithmetic is checked against the original, not asserted.

    ``grid_inference`` restates E2's posterior over a general grid because
    ``e2_model.posterior_weights`` is welded to the Electrical forward map and
    is frozen. This runs both on the same case and requires them to agree.
    """
    from experiments.electrical_e2 import e2_model

    source_voltage = 5.0
    theta = e2_model.theta_grid()
    grid = ParameterGrid(
        name="r2", unit="ohm", values=tuple(float(v) for v in theta)
    )
    forward = e2_model.forward_predictions(source_voltage)
    sigma = 2.0e-3
    measured = (1.6612, 1.6588, 1.6640)

    frozen = e2_model.posterior_weights(
        [
            e2_model.E2Observation(
                action_id=f"agree-{index}",
                source_voltage_volt=source_voltage,
                y_volt=value,
                sigma_volt=sigma,
            )
            for index, value in enumerate(measured)
        ]
    )
    shared = posterior_weights(grid, forward, measured, sigma)

    assert shared.shape == frozen.shape
    np.testing.assert_allclose(shared, frozen, rtol=1e-12, atol=1e-15)


def test_shared_posterior_rejects_a_mis_sized_forward_map() -> None:
    grid = ParameterGrid(name="x", unit="1", values=(1.0, 2.0, 3.0))
    with pytest.raises(ValueError, match="forward map has"):
        posterior_weights(grid, [1.0, 2.0], [1.5], 0.1)


def test_shared_posterior_rejects_a_non_positive_sigma() -> None:
    grid = ParameterGrid(name="x", unit="1", values=(1.0, 2.0, 3.0))
    with pytest.raises(ValueError, match="sigma must be positive"):
        posterior_weights(grid, [1.0, 2.0, 3.0], [1.5], 0.0)


def test_shared_posterior_normalizes() -> None:
    grid = ParameterGrid(name="x", unit="1", values=tuple(np.linspace(0, 1, 51)))
    weights = posterior_weights(grid, grid.array, [0.5], 0.05)
    assert float(weights.sum()) == pytest.approx(1.0, abs=1e-12)


def test_single_point_grid_is_refused() -> None:
    with pytest.raises(ValueError, match="at least two points"):
        ParameterGrid(name="x", unit="1", values=(1.0,))


def test_summary_recovers_a_known_gaussian() -> None:
    """An identity forward map makes the posterior analytically checkable."""
    grid = ParameterGrid(
        name="x", unit="1", values=tuple(np.linspace(-1.0, 1.0, 2001))
    )
    sigma = 0.1
    weights = posterior_weights(grid, grid.array, [0.25], sigma)
    summary = summarize(grid, weights, credible_mass=0.95)
    assert summary.mean == pytest.approx(0.25, abs=2e-3)
    assert summary.sd == pytest.approx(sigma, rel=2e-2)
    assert summary.covers(0.25)
    assert summary.width == pytest.approx(2 * 1.96 * sigma, rel=5e-2)


def test_predictive_mean_of_an_identity_map_is_the_posterior_mean() -> None:
    grid = ParameterGrid(
        name="x", unit="1", values=tuple(np.linspace(-1.0, 1.0, 401))
    )
    weights = posterior_weights(grid, grid.array, [0.1], 0.2)
    summary = summarize(grid, weights)
    assert predictive_mean(weights, grid.array) == pytest.approx(summary.mean)


# =====================================================================
# The one thing that varies
# =====================================================================

def test_observations_are_deterministic_and_shared_by_every_rung() -> None:
    """If rungs saw different noise, no difference could be attributed."""
    first, second = t1_truth.observations(), t1_truth.observations()
    assert first == second
    assert len(first) == t1_config.OBSERVATION_COUNT


def test_forward_map_is_deterministic() -> None:
    values, _ = t1_run.forward_map("coarse")
    again, _ = t1_run.forward_map("coarse")
    np.testing.assert_array_equal(values, again)


def test_forward_map_is_monotonically_decreasing_in_alpha() -> None:
    """Higher diffusivity decays the mode faster. If this fails, the inversion
    is not well posed and every number downstream is meaningless."""
    for spec in t1_config.RUNGS:
        values, _ = t1_run.forward_map(spec.rung_id)
        assert np.all(np.diff(values) < 0.0), spec.rung_id


def test_every_declared_rung_is_run_and_none_is_selected(study: dict) -> None:
    reported = [row["rung_id"] for row in study["rungs"]]
    assert reported == [spec.rung_id for spec in t1_config.RUNGS]


def test_rungs_differ_only_in_resolution(study: dict) -> None:
    held = {
        (row["alpha_true"], row["true_qoi"]) for row in study["rungs"]
    }
    assert len(held) == 1, "the truth or the QoI moved between rungs"


# =====================================================================
# The measured result
# =====================================================================

def test_discretization_error_falls_with_fidelity(study: dict) -> None:
    errors = [
        abs(row["discretization_error_at_truth"])
        for row in sorted(study["rungs"], key=lambda r: r["rank"])
    ]
    assert all(b < a for a, b in zip(errors, errors[1:]))


def test_coarse_posterior_is_confident_and_biased(study: dict) -> None:
    """The finding, stated as a test.

    Confident: its width is within a small factor of the reference rung's.
    Biased: its centre is many posterior standard deviations from the truth,
    and the interval excludes the truth entirely.
    """
    rows = {row["rung_id"]: row for row in study["rungs"]}
    coarse, reference = rows["coarse"], rows["reference"]

    assert not coarse["covers_truth"]
    assert abs(coarse["mean_error_in_sd"]) > 10.0
    assert coarse["posterior"]["sd"] < 2.0 * reference["posterior"]["sd"]
    assert study["finding"]["coarse_posterior_is_confident_and_biased"]


def test_bias_falls_monotonically_with_fidelity(study: dict) -> None:
    assert study["fidelity_effect"]["bias_decreases_monotonically_with_fidelity"]


def test_error_decomposes_into_discretization_plus_the_shared_noise_draw(
    study: dict,
) -> None:
    """The residual is explained, not just reported.

    At the reference rung the linearization is tight, so the sum of the
    discretization term and the shared noise term must reproduce the observed
    error closely. This is what licenses the claim that the reference rung's
    missed coverage is the noise draw rather than its numerics.
    """
    decomposition = study["error_decomposition"]["per_rung"]
    reference = decomposition["reference"]
    assert reference["linear_prediction"] == pytest.approx(
        reference["observed_mean_error"], rel=0.01
    )
    assert not reference["discretization_dominates"]
    assert decomposition["coarse"]["discretization_dominates"]


def test_the_noise_term_is_identical_at_every_rung(study: dict) -> None:
    terms = {
        part["noise_component_alpha"]
        for part in study["error_decomposition"]["per_rung"].values()
    }
    assert len(terms) == 1


def test_discretization_prediction_held_at_every_rung(study: dict) -> None:
    """The preregistered per-rung bias was a discretization prediction; check
    it against the discretization component, which is what it predicted."""
    decomposition = study["error_decomposition"]["per_rung"]
    for rung_id, predicted in t1_config.PREDICTED_BIAS.items():
        assert decomposition[rung_id][
            "discretization_component_alpha"
        ] == pytest.approx(predicted["alpha_bias"], rel=0.02), rung_id


# =====================================================================
# Fidelity corpus — cost only
# =====================================================================

def test_fidelity_corpus_records_cost_and_never_accuracy(study: dict) -> None:
    """The module refuses domain-owned claims; T1 respects that rather than
    routing around it. The measured bias stays in T1's own results."""
    corpus = study["fidelity_corpus"]
    assert corpus["relationships"]
    for relationship in corpus["relationships"]:
        assert relationship["ownership"] == FidelityOwnership.STRUCTURE_TRANSFERABLE.value
        assert "work" in relationship["metric"] or "cost" in relationship["metric"]


def test_fidelity_corpus_registers_every_declared_rung(study: dict) -> None:
    assert len(study["fidelity_corpus"]["rungs"]) == len(t1_config.RUNGS)


def test_t1_supplies_the_first_real_fidelity_ladder(study: dict) -> None:
    """The M2 note said no genuine low/high-fidelity pairs exist. With T1's
    rungs registered the corpus reports a real ladder — with no src change."""
    corpus = study["fidelity_corpus"]
    assert corpus["corpus_status_without_t1"]["models_with_a_real_ladder"] == 0
    assert corpus["corpus_status_without_t1"]["status"] == "insufficient_real_data"
    assert corpus["corpus_status"]["models_with_a_real_ladder"] == 1
    assert corpus["corpus_status"]["status"] == "observed"


def test_fidelity_relationship_ratios_match_the_declared_work_proxies(
    study: dict,
) -> None:
    reference = t1_config.rung(t1_config.REFERENCE_RUNG_ID)
    by_low = {
        r["low_rung"]["rung_id"].rsplit(".", 1)[-1]: r
        for r in study["fidelity_corpus"]["relationships"]
    }
    for spec in t1_config.RUNGS:
        if spec.rung_id == t1_config.REFERENCE_RUNG_ID:
            continue
        expected = reference.work_proxy / spec.work_proxy
        assert by_low[spec.rung_id]["median_ratio"] == pytest.approx(expected)


# =====================================================================
# Claim discipline
# =====================================================================

def test_report_makes_no_physical_validation_claim(study: dict) -> None:
    report = " ".join(t1_run.render_markdown(study).split()).lower()
    for banned in (
        "experimentally validated",
        "physically validated",
        "validated against experiment",
        "autonomous scientist",
        "scientific intelligence",
        "proves that",
    ):
        assert banned not in report, banned


def test_report_states_the_synthetic_scope(study: dict) -> None:
    report = t1_run.render_markdown(study).lower()
    assert "synthetic" in report
    assert "no physical validation" in report


def test_version_and_base_commit_are_recorded(study: dict) -> None:
    assert study["experiment_version"] == T1_VERSION
    assert study["base_commit"] == BASE_COMMIT
    assert len(BASE_COMMIT) == 40
