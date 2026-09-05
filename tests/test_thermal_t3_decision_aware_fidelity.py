"""T3 — decision-aware fidelity escalation.

The preregistered policy LOST. These tests pin that outcome as measured, not
as hoped: they assert the specific failures (A1, A2, A5) and the specific
passes (A3, A4, A6, A7), so that any future change to the rule or the
benchmark has to confront what actually happened rather than quietly move it.

They also protect the things that make the negative result trustworthy:

    T1 and T2 are frozen and reused, not edited
    no strategy can see the truth it is being graded against
    the out-of-sample design really does break the cancellation
    the benchmark really does contain both regimes
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import numpy as np
import pytest

from experiments.thermal_t2 import t2_config
from experiments.thermal_t3 import BASE_COMMIT, DECISION_PATH_MODULES, T3_VERSION
from experiments.thermal_t3 import t3_config, t3_run, t3_truth

REPO_ROOT = Path(__file__).resolve().parents[1]
T3_ROOT = Path(t3_config.__file__).resolve().parent
POLICY = t3_config.POLICY_ID


@pytest.fixture(scope="module")
def study() -> dict:
    return t3_run.run_t3()


# =====================================================================
# T1 and T2 are reused, not edited
# =====================================================================

def test_t2_digests_match() -> None:
    mismatched = [
        relative
        for relative, expected in t3_config.T2_FROZEN_FILE_DIGESTS.items()
        if hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()
        != expected
    ]
    assert not mismatched, f"T2 changed under T3: {mismatched}"


def test_t1_digests_still_match_through_t2s_pins() -> None:
    """T3 inherits T1 through T2's pin rather than repeating it."""
    mismatched = [
        relative
        for relative, expected in t2_config.T1_FROZEN_FILE_DIGESTS.items()
        if hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()
        != expected
    ]
    assert not mismatched, f"T1 changed under T3: {mismatched}"


def test_the_fixed_design_is_imported_not_restated() -> None:
    from experiments.thermal_t1 import t1_config

    assert t3_config.RUNGS is t1_config.RUNGS
    assert t3_config.OBSERVATION_SIGMA is t1_config.OBSERVATION_SIGMA
    assert t3_config.alpha_grid() == t1_config.alpha_grid()
    assert t3_config.FIDELITY_COST == {
        s.rung_id: s.work_proxy for s in t1_config.RUNGS
    }


# =====================================================================
# No strategy may see the truth
# =====================================================================

def test_decision_path_never_imports_a_grader_truth() -> None:
    for module_name in DECISION_PATH_MODULES:
        source = (T3_ROOT / f"{module_name}.py").read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported.add(module)
                imported.update(f"{module}.{a.name}" for a in node.names)
        leaked = {n for n in imported if "truth" in n.lower()}
        assert not leaked, f"{module_name} imports a grader truth: {leaked}"


#: Everything a real decision-maker would be handed: the measurements, and the
#: threshold it has been asked about. Nothing else on the scenario is knowable.
STRATEGY_VISIBLE_SCENARIO_FIELDS = {"observations", "tau"}
STRATEGY_FUNCTIONS = ("run_policy", "run_baseline", "_confident")


def test_no_strategy_reads_anything_it_could_not_know() -> None:
    """Parsed, not trusted.

    ``alpha_true``, ``terminal_truth``, ``margin``, ``sign`` and
    ``correct_decision`` are the answer. ``RungView.numerical_error`` is the
    rung's error measured against that answer -- the exact thing the policy
    exists to estimate. Reading any of them would make the result meaningless,
    so the strategy functions are parsed and checked instead of trusted.
    """
    tree = ast.parse((T3_ROOT / "t3_run.py").read_text(encoding="utf-8"))
    checked = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        if function.name not in STRATEGY_FUNCTIONS:
            continue
        checked.append(function.name)
        for node in ast.walk(function):
            if not isinstance(node, ast.Attribute):
                continue
            # Anything read off the scenario must be strategy-visible.
            if isinstance(node.value, ast.Name) and node.value.id == "scenario":
                assert node.attr in STRATEGY_VISIBLE_SCENARIO_FIELDS, (
                    f"{function.name} reads scenario.{node.attr}"
                )
            # The grading-only field is off limits on any object.
            assert node.attr != "numerical_error", (
                f"{function.name} reads the grading-only numerical_error"
            )
    assert sorted(checked) == sorted(STRATEGY_FUNCTIONS)


def test_grading_happens_outside_the_strategies() -> None:
    """No strategy marks its own homework: ``correct`` is added by grade()."""
    tree = ast.parse((T3_ROOT / "t3_run.py").read_text(encoding="utf-8"))
    for function in ast.walk(tree):
        if isinstance(function, ast.FunctionDef) and function.name in (
            "run_policy", "run_baseline"
        ):
            keys = {
                node.value
                for node in ast.walk(function)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            }
            assert "correct" not in keys, f"{function.name} grades itself"


def test_the_policy_only_pays_for_rungs_it_visited(study: dict) -> None:
    for row in study["_rows"][POLICY]:
        expected = sum(t3_config.FIDELITY_COST[r] for r in row["rungs_used"])
        assert row["work"] == expected


def test_baselines_pay_exactly_one_rung(study: dict) -> None:
    for rung_id in t3_run.RUNG_ORDER:
        for row in study["_rows"][f"always_{rung_id}"]:
            assert row["work"] == t3_config.FIDELITY_COST[rung_id]
            assert row["rungs_used"] == [rung_id]


# =====================================================================
# Preregistration integrity
# =====================================================================

def test_config_hash_stable_and_preregistration_covers_both_halves() -> None:
    assert t3_config.config_hash() == t3_config.config_hash()
    expected = hashlib.sha256(
        f"{t3_config.config_hash()}|{t3_truth.truth_hash()}".encode("utf-8")
    ).hexdigest()
    assert t3_run.preregistration_hash() == expected


def test_every_required_preregistration_element_is_present() -> None:
    payload = t3_config.config_payload()
    assert payload["terminal_decision"]["terminal_time_s"] == 180.0
    assert payload["terminal_decision"]["asymmetric_loss"] is False
    assert payload["scenarios"]["rule"] and payload["scenarios"]["seed_entropy"]
    assert payload["costs"]["fidelity_cost"]
    assert payload["costs"]["wrong_decision_cost"] > 0
    assert payload["rules"]["escalation"] and payload["rules"]["stopping"]
    assert len(payload["strategies"]) == 4
    assert payload["primary_metric"] == "cost_to_correct_decision"
    assert len(payload["metrics"]) == 10
    assert len(payload["acceptance_criteria"]) == 7
    assert len(payload["falsification_criteria"]) == 5
    assert payload["expected_negative_regime"]


def test_seed_entropy_is_disjoint_from_t1_and_t2() -> None:
    from experiments.thermal_t1 import t1_config

    assert t3_config.SEED_ENTROPY not in (
        t1_config.NOISE_SEED, t2_config.SEED_ENTROPY
    )


def test_terminal_condition_is_not_the_assimilated_one() -> None:
    assert t3_config.TERMINAL_TIME_S != t3_config.END_TIME_S
    assert t3_config.FOURIER_RATIO == 3.0


# =====================================================================
# Scenarios
# =====================================================================

def test_scenarios_are_reproducible_and_complete() -> None:
    first, second = t3_truth.all_scenarios(), t3_truth.all_scenarios()
    assert len(first) == t3_config.SCENARIO_COUNT
    assert [s.tau for s in first] == [s.tau for s in second]


def test_every_scenario_lands_in_its_declared_band() -> None:
    for s in t3_truth.all_scenarios():
        low, high = t3_config.MARGIN_BANDS[s.band]
        assert low <= s.margin <= high, s.index
        assert t3_config.ALPHA_TRUE_MIN <= s.alpha_true <= t3_config.ALPHA_TRUE_MAX
        assert abs(abs(s.tau - s.terminal_truth) - s.margin) < 1e-15


def test_the_correct_decision_is_exactly_the_sign(t3_scenarios=None) -> None:
    for s in t3_truth.all_scenarios():
        assert s.correct_decision == (s.sign > 0)


def test_both_decisions_are_well_represented() -> None:
    """A strategy must not be able to profit from guessing one answer."""
    scenarios = t3_truth.all_scenarios()
    positives = sum(1 for s in scenarios if s.correct_decision)
    assert 0.42 < positives / len(scenarios) < 0.58


def test_alpha_stays_well_inside_the_frozen_grid() -> None:
    grid = t3_config.alpha_grid()
    for s in t3_truth.all_scenarios():
        assert grid.values[0] < s.alpha_true < grid.values[-1]
        assert s.alpha_true - grid.values[0] > 20 * grid.spacing
        assert grid.values[-1] - s.alpha_true > 20 * grid.spacing


# =====================================================================
# The design premise — F5
# =====================================================================

def test_the_cancellation_holds_at_the_assimilated_condition(
    study: dict,
) -> None:
    """T2's finding, reconfirmed: at r = 1 every rung predicts the same thing,
    because discretization error is exactly an effective-alpha shift."""
    check = study["cancellation_check"]
    assert check["cancellation_holds_at_r1"]
    assert check["spread_at_r1"] < 1e-6


def test_the_cancellation_is_broken_at_the_terminal_condition(
    study: dict,
) -> None:
    """If this failed, T3 would be measuring nothing."""
    check = study["cancellation_check"]
    assert check["cancellation_broken_at_r3"]
    assert check["amplification"] > 1000
    assert not study["falsification"]["triggers"]["F5_out_of_sample_design_failed"]


def test_terminal_rung_errors_separate_by_about_a_decade(study: dict) -> None:
    at_r3 = study["cancellation_check"]["at_r_equals_3"]
    coarse_gap = abs(at_r3["coarse"] - at_r3["reference"])
    medium_gap = abs(at_r3["medium"] - at_r3["reference"])
    assert coarse_gap > 5 * medium_gap


# =====================================================================
# The benchmark is sound — A6, A7
# =====================================================================

def test_benchmark_contains_both_regimes(study: dict) -> None:
    """A6. Without this no comparison between strategies means anything."""
    assert study["acceptance"]["checks"]["A6_benchmark_contains_both_regimes"]
    errors = study["numerical_error_vs_margin"]
    assert errors["FAR"]["coarse"]["fraction_error_exceeds_margin"] < 0.05
    assert errors["NEAR"]["coarse"]["fraction_error_exceeds_margin"] > 0.50


def test_benchmark_is_not_rigged_toward_the_reference_rung(study: dict) -> None:
    """A7. A cheaper baseline matches the reference rung in at least one band."""
    assert study["acceptance"]["checks"]["A7_reference_not_dominant_in_every_band"]
    matches = study["acceptance"][
        "bands_where_a_cheaper_baseline_matches_reference"
    ]
    assert "always_coarse" in matches["FAR"]
    assert "always_medium" in matches["MODERATE"]


def test_the_undecidable_band_defeats_every_fidelity(study: dict) -> None:
    """The band that makes 'always escalate' a losing strategy."""
    band = study["per_band"]["UNDECIDABLE"]
    assert band["always_reference"]["terminal_decision_accuracy"] < 0.75
    errors = study["numerical_error_vs_margin"]["UNDECIDABLE"]
    assert errors["reference"]["fraction_error_exceeds_margin"] > 0.5


# =====================================================================
# The measured outcome — the policy lost
# =====================================================================

def test_the_preregistered_policy_did_not_meet_its_criteria(study: dict) -> None:
    """Recorded as measured. This is a negative result, not a bug."""
    checks = study["acceptance"]["checks"]
    assert not checks["A1_policy_ccd_beats_every_baseline"]
    assert not checks["A2_policy_accuracy_within_2pp_of_reference"]
    assert not checks["A5_near_band_usually_reaches_reference"]
    assert not study["acceptance"]["all_passed"]


def test_the_criteria_that_did_hold(study: dict) -> None:
    checks = study["acceptance"]["checks"]
    assert checks["A3_policy_work_below_reference_work"]
    assert checks["A4_far_band_rarely_reaches_reference"]


def test_falsification_triggers_fired_as_written(study: dict) -> None:
    fired = set(study["falsification"]["fired"])
    assert fired == {
        "F1_policy_failed_to_beat_baselines",
        "F4_saving_bought_with_reliability",
    }
    assert study["falsification"]["comparison_is_informative"]


def test_the_policy_is_never_the_sweep_winner(study: dict) -> None:
    assert study["policy_wins_from_wrong_decision_cost"] is None
    assert POLICY not in {e["winner"] for e in study["cost_sweep"]}


def test_the_report_does_not_claim_success(study: dict) -> None:
    """The rendered answer must follow the criteria, not the author's hopes."""
    report = t3_run.render_markdown(study)
    assert "**No — not as specified.**" in report
    assert "Why it came out this way" in report


# =====================================================================
# Why it lost — the diagnosis, pinned
# =====================================================================

def test_escalation_costs_more_than_going_straight_to_the_reference(
    study: dict,
) -> None:
    diagnosis = study["failure_diagnosis"]
    assert diagnosis["policy_paid_more_than_always_reference_on"] > 500
    full = sum(t3_config.FIDELITY_COST[r] for r in t3_run.RUNG_ORDER)
    assert full > t3_config.FIDELITY_COST[t3_config.REFERENCE_RUNG_ID]


def test_the_give_up_rule_misfires_on_a_biased_rung(study: dict) -> None:
    """The stopping rule reads a biased mean, so a decidable scenario can look
    like a coin flip. This is the mechanism behind A5's failure."""
    cause = study["failure_diagnosis"][
        "cause_2_the_undecidable_stop_is_corrupted_by_the_bias_it_hunts"
    ]
    assert cause["early_stops_below_the_reference_rung"] > 0
    assert cause["of_which_decided_wrongly"] > 0
    assert cause["by_band"]["NEAR"] > 0


def test_the_error_indicator_is_conservative_as_declared(study: dict) -> None:
    """Declared in the preregistration, measured here."""
    cause = study["failure_diagnosis"]["cause_3_indicator_conservatism"]
    assert cause["median_indicator_over_actual_error"] > 1.0
    assert cause["unnecessary_escalations"] > 0


def test_the_policy_never_made_an_incorrect_confident_decision(
    study: dict,
) -> None:
    """Measured, and explicitly not allowed to offset the failure."""
    achieved = study["failure_diagnosis"]["what_the_policy_did_achieve"]
    assert achieved["incorrect_confident_decisions"] == 0
    assert achieved["always_reference_incorrect_confident"] > 0
    assert achieved["always_coarse_incorrect_confident"] > 0


def test_the_achievement_is_marked_as_not_offsetting_the_failure(
    study: dict,
) -> None:
    note = study["failure_diagnosis"]["what_the_policy_did_achieve"]["note"]
    assert "does NOT offset" in note
    report = t3_run.render_markdown(study)
    assert "does not rescue A1, A2 or A5" in report


# =====================================================================
# Determinism and claim discipline
# =====================================================================

def test_the_policy_is_deterministic() -> None:
    scenario = t3_truth.all_scenarios()[7]
    table = t3_run.scenario_table(scenario)
    first = t3_run.run_policy(scenario, table)
    second = t3_run.run_policy(scenario, table)
    assert first == second


def test_report_makes_no_physical_validation_or_marketing_claim(
    study: dict,
) -> None:
    report = " ".join(t3_run.render_markdown(study).split()).lower()
    for banned in (
        "experimentally validated",
        "physically validated",
        "autonomous scientist",
        "scientific intelligence",
        "proves that",
        "production-ready",
    ):
        assert banned not in report, banned


def test_report_states_the_scope_and_non_goals(study: dict) -> None:
    report = t3_run.render_markdown(study).lower()
    assert "synthetic" in report
    assert "no physical validation" in report
    assert "no generic fidelitypolicy" in report


def test_version_and_base_commit_are_recorded(study: dict) -> None:
    assert study["experiment_version"] == T3_VERSION
    assert study["base_commit"] == BASE_COMMIT
    assert len(BASE_COMMIT) == 40
