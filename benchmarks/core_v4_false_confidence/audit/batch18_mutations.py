"""Batch-18 guard mutations (I-03 part B, the study's own verdict arithmetic): each new guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch18_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

CS = "src/engcore/studies/calibration_study.py"
TC = "src/engcore/studies/tcr.py"
T = "tests/test_core_scientific_audit_batch18.py"
TH = "tests/inference/test_tcr_heldout_uq.py"

MUTATIONS = [
    # --- R-35: the power floor and the bias test ---
    Mutation(
        "B18a", f"{CS}::held_out_verdict",
        "    if n < HELD_OUT_MINIMUM_N:\n",
        "    if False:\n",
        f"{T}::test_r35_a_single_held_out_point_cannot_validate_a_model",
        "R-35, the audited case: one held-out point with an unremarkable residual reads PASS again, which is "
        "absence of rejection reported as validation"),
    Mutation(
        "B18b", f"{CS}",
        "HELD_OUT_MINIMUM_N = 7",
        "HELD_OUT_MINIMUM_N = 1",
        f"{T}::test_r35_the_minimum_is_where_a_one_sigma_bias_is_found_at_better_than_even_odds",
        "the floor returns to 1, where the mean-residual test finds a one-sigma bias at odds of about 1 in 6",
        also=(),
    ),
    Mutation(
        "B18c", f"{CS}::held_out_verdict",
        "    if chi_square_p < HELD_OUT_PER_TEST_ALPHA or bias_p < HELD_OUT_PER_TEST_ALPHA:\n",
        "    if chi_square_p < HELD_OUT_PER_TEST_ALPHA:\n",
        f"{T}::test_r35_a_common_sign_bias_is_found_where_the_omnibus_test_is_blind",
        "R-35: the bias test is dropped, so the common-sign residual pattern a truncated expansion leaves is "
        "invisible again -- ten residuals of +1.2 give a chi-square p of 0.155"),
    Mutation(
        "B18d", f"{CS}::held_out_verdict",
        "    bias_z = float(math.sqrt(n) * mean_residual)\n",
        "    bias_z = float(mean_residual)\n",
        f"{T}::test_r35_a_common_sign_bias_is_found_where_the_omnibus_test_is_blind",
        "the bias statistic loses its sqrt(n), so the test has no power at any sample size -- the shape of a "
        "statistic that looks like a test and is not one"),
    Mutation(
        "B18e", f"{CS}::held_out_verdict",
        "    if chi_square_p < HELD_OUT_PER_TEST_ALPHA or bias_p < HELD_OUT_PER_TEST_ALPHA:\n",
        "    if n >= HELD_OUT_MINIMUM_N and (chi_square_p < HELD_OUT_PER_TEST_ALPHA or bias_p < HELD_OUT_PER_TEST_ALPHA):\n",
        f"{T}::test_r35_a_rejection_is_still_a_rejection_below_the_floor",
        "the floor swallows a REJECTION below it, which is the opposite error to the one the floor closes: a "
        "rejection is evidence whatever the sample size"),
    Mutation(
        "B18f", f"{CS}",
        "HELD_OUT_PER_TEST_ALPHA = HELD_OUT_CHI_SQUARE_ALPHA / 2.0",
        "HELD_OUT_PER_TEST_ALPHA = HELD_OUT_CHI_SQUARE_ALPHA",
        f"{T}::test_r35_the_family_wise_level_is_the_one_the_module_declares",
        "two tests each at the full declared alpha, so the family-wise false-rejection rate is up to twice "
        "the level this module says it runs at"),
    Mutation(
        "B18g", f"{CS}::validate_held_out",
        "    verdict, why = held_out_verdict(standardized_residuals=residuals)\n",
        "    verdict, why = (HeldOutValidation.PASS, 'chi-square not rejected')\n",
        f"{TH}::test_the_well_specified_model_is_not_rejected_on_held_out_evidence",
        "the study stops reading its own verdict rule and goes back to answering PASS"),
    # --- R-36: the clustering ---
    Mutation(
        "B18h", f"{CS}::coverage_design_effect",
        "    design_effect = 1.0 + (mean_m - 1.0) * max(icc, 0.0)\n",
        "    design_effect = 1.0\n",
        f"{T}::test_r36_perfectly_clustered_indicators_give_a_design_effect_of_the_cluster_size",
        "R-36, the audited case: every interval of every repetition is pooled as an independent trial again, "
        "which overstated precision by about 1.45x at the measured design effect of 2.09"),
    Mutation(
        "B18i", f"{CS}::coverage_design_effect",
        "    design_effect = 1.0 + (mean_m - 1.0) * max(icc, 0.0)\n",
        "    design_effect = 1.0 + (mean_m - 1.0) * icc\n",
        f"{T}::test_r36_perfectly_clustered_indicators_give_a_design_effect_of_the_cluster_size",
        "the negative-ICC clamp goes, so negative clustering makes the interval NARROWER than the independent "
        "one -- claiming more precision than the data has"),
    Mutation(
        "B18j", f"{CS}::classify_coverage",
        "    low, high = wilson_interval(measured * trials, trials)\n",
        "    low, high = wilson_interval(covered, total)\n",
        f"{T}::test_r36_the_audited_verdict_flip_reproduces_at_the_effective_sample_size",
        "R-36: the interval is computed at the pooled count again, so the audited 1104/1200 reads CALIBRATED "
        "where the effective sample size says INCONCLUSIVE"),
    Mutation(
        "B18k", f"{CS}::coverage_verdict_with_refusals",
        "    if fraction > acceptance_half_width:\n",
        "    if False:\n",
        f"{T}::test_r36_a_refused_fraction_above_the_studys_own_tolerance_is_inconclusive",
        "a coverage number computed on the repetitions a gate happened to route is reported as a measurement "
        "about the model, however many were refused"),
    # --- R-38 ---
    Mutation(
        "B18l", f"{CS}::_require_declared_sigma",
        "    if observation_sigma is None:\n        return\n",
        "    if observation_sigma is None:\n        observation_sigma = Quantity(0.0, OHM)\n",
        f"{T}::test_r38_a_heterogeneous_held_out_half_can_be_validated",
        "R-38, the audited case: a held-out half whose readings declare different sigmas cannot be validated "
        "at all, whatever is passed or omitted"),
    # Repointed at the CONSTANT: the two call sites (the refused path and the normal one) carry the
    # same line, and the runner rightly refuses a mutation that matches twice in its scope. The
    # constant is where the claim lives anyway.
    Mutation(
        "B18m", f"{CS}",
        'COVERAGE_CALIBRATION_STATUS = "CALIBRATION_NOT_RUN_GRID_POSTERIOR"',
        "COVERAGE_CALIBRATION_STATUS = CalibrationStatus.CONVERGED.value",
        f"{T}::test_r38_a_repetition_that_ran_no_optimizer_does_not_claim_one_converged",
        "R-38: a repetition that runs no optimizer claims CALIBRATION_CONVERGED again"),
    # --- R-02's residual from part A: the domain check becomes informative ---
    Mutation(
        "B18n", f"{TC}::synthesize_tcr_observations",
        "                conditions={CONDITION_TEMPERATURE: Quantity(float(temperature_k), KELVIN)},\n",
        "",
        f"{T}::test_r02_the_tcr_observations_declare_the_temperature_they_were_measured_at",
        "the observations stop declaring the operating point they were measured at, so CORE-006 has no range "
        "to compare a prediction with and every routed record reads PREDICTION_DOMAIN_NOT_DECLARED"),
    Mutation(
        "B18o", f"{CS}::predict_held_out",
        "            conditions={CONDITION_TEMPERATURE: temperatures_by_condition[observation.condition_id]},\n",
        "",
        f"{T}::test_r02_each_predictive_record_carries_its_own_conditions_domain_verdict",
        "the predictive spec stops carrying the condition it is AT, so an extrapolation to 440 K from a "
        "calibration that stopped at 350 K says nothing about its domain. Repointed: the extrapolation test "
        "reads the HELD-OUT VERDICT's routed record, which comes from the other spec, so this mutation "
        "survived it -- the per-observation records needed a guard of their own"),
    Mutation(
        "B18p", f"{CS}::validate_held_out",
        "            conditions={CONDITION_TEMPERATURE: temperatures_by_condition[first.condition_id]},\n",
        "",
        f"{T}::test_r02_an_extrapolating_study_says_it_is_extrapolating",
        "the same on the held-out verdict's own routed record, which is what a reader of the verdict sees"),
]

_CHANGED_FILES = (CS, TC)


def _existing():
    out = []
    for identifier, spec, old, new, attribution in M.MUTATIONS:
        if spec.partition("::")[0] not in _CHANGED_FILES:
            continue
        files = [word for word in attribution.replace(",", " ").split() if word.startswith("tests/")]
        if not files:
            continue
        out.append(Mutation(identifier, spec, old, new, files[0], f"pinned: {attribution}"))
    return out


def main() -> int:
    scratch = scratch_from_environment()
    status = run(MUTATIONS, label="BATCH18", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH18_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 18 changed ---", flush=True)
    status |= run(existing, label="BATCH18_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH18_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
