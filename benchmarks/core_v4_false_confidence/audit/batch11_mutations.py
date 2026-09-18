"""Batch-11 guard mutations (I-04, goodness of fit where the information is): each new guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

Run from the repository root, with SCRATCH pointing at a scratch directory::

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch11_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

LG = "src/engcore/hybrid_uq/local_gaussian.py"
GE = "src/engcore/hybrid_uq/_grid_evidence.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch11.py"
C = "tests/hybrid_uq/test_core_v4_false_confidence_conformance.py"

MUTATIONS = [
    # --- R-03: the statistic that looks where the information is ---
    Mutation(
        "B11a", f"{LG}::_goodness_of_fit",
        "    if len(cumulants) == 3:\n",
        "    if False:\n",
        f"{T}::test_r03_padding_that_carries_no_information_does_not_raise_the_claim",
        "R-03: the leverage test is never consulted, which is the audited gate exactly -- the pooled test "
        "alone, diluted by observations that carry no information"),
    Mutation(
        "B11b", f"{LG}::local_gaussian_posterior",
        "    leverage_statistic = float(np.sum(leverage * np.asarray(sensitivity.standardized_residuals) ** 2))\n",
        "    leverage_statistic = float(np.sum(np.asarray(sensitivity.standardized_residuals) ** 2)) / max(n, 1)\n",
        f"{T}::test_r03_the_leverage_statistic_is_the_one_that_sees_the_diluted_misfit",
        "R-03: the statistic stops weighing each residual by the information it carries and becomes a pooled "
        "average, which is the quantity the dilution moves"),
    Mutation(
        "B11c", f"{LG}::_leverage_weights",
        '    keep = singular > singular[0] * max(A.shape) * np.finfo(float).eps\n',
        "    keep = singular >= 0.0\n",
        f"{T}::test_the_leverage_weights_are_the_hat_diagonal",
        "R-03: a rank-deficient column space is taken at face value, so the weights no longer sum to the "
        "rank and are not a share of anything"),
    Mutation(
        "B11d", f"{LG}::_leverage_null_cumulants",
        "    c2 = float(np.sum(d ** 2) - 2.0 * np.sum(h * d ** 2) + np.trace(G @ G))\n",
        "    c2 = float(np.sum(d ** 2))\n",
        f"{T}::test_the_leverage_test_is_the_pooled_test_when_every_weight_is_equal",
        "R-03: the null's variance drops the projection, so it is the variance of the RAW errors and not of "
        "the fitted residuals -- the reduction to the pooled test fails"),
    Mutation(
        "B11e", f"{LG}::_leverage_null_cumulants",
        "    c3 = float(np.sum(d ** 3) - 3.0 * np.sum(h * d ** 3) + 3.0 * np.trace(G @ G2) - np.trace(G @ G @ G))\n",
        "    c3 = float(np.sum(d ** 3))\n",
        f"{T}::test_the_leverage_test_is_the_pooled_test_when_every_weight_is_equal",
        "R-03: the third moment drops the projection too, so the shape of the null is wrong"),
    Mutation(
        "B11f", f"{LG}::_three_moment_p_value",
        "    a = float(c1) - b * dof\n",
        "    a = 0.0\n",
        f"{T}::test_the_leverage_test_is_the_pooled_test_when_every_weight_is_equal",
        "R-03: the match stops shifting, so it reproduces two of the three moments and the p-value is read "
        "off the wrong point of the distribution"),

    # --- the record and the read-back ---
    Mutation(
        "B11g", f"{LG}::RouteDiagnostics.to_dict",
        "        if math.isfinite(self.leverage_weighted_chi_square) or self.leverage_null_cumulants:\n",
        "        if False:\n",
        f"{T}::test_the_record_carries_the_statistic_and_the_cumulants_it_was_judged_on",
        "R-03: the record stops carrying the statistic and the null, so no reader can re-derive the verdict"),
    Mutation(
        "B11h", f"{LG}::_require_reasons_follow_measurements",
        "            found_refusals, found_downgrades = _goodness_of_fit(chi_minimum, n, p, statistic, cumulants)\n",
        "            found_refusals, found_downgrades = _goodness_of_fit(chi_minimum, n, p)\n",
        f"{T}::test_the_read_back_re_derives_the_leverage_verdict",
        "R-03: the read-back re-derives the pooled half only, so a record may state a verdict its leverage "
        "numbers contradict"),
    Mutation(
        "B11i", f"{LG}::_require_reasons_follow_measurements",
        "            elif cumulants and statistic > chi_minimum * (1.0 + 1.0e-9) + 1.0e-9:\n",
        "            elif False:\n",
        "tests/hybrid_uq/test_core_scientific_audit_batch1.py::test_a_record_that_understates_its_chi_square_is_refused_on_read",
        "R-03: the record's two goodness-of-fit numbers stop having to belong to one fit, so understating "
        "the chi-square minimum alone is accepted again"),

    # --- R-20: the ratio is unconditional, and a tiny sample says so ---
    Mutation(
        "B11j", f"{LG}::_one_fit_test",
        "    if float(statistic) / float(null_mean) > MISFIT_REFUSE_VARIANCE_RATIO:\n        return 2\n"
        "    if math.isnan(float(p_value)) or float(p_value) >= GOODNESS_OF_FIT_ALPHA / 2.0:\n        return 0\n",
        "    if math.isnan(float(p_value)) or float(p_value) >= GOODNESS_OF_FIT_ALPHA / 2.0:\n        return 0\n"
        "    if float(statistic) / float(null_mean) > MISFIT_REFUSE_VARIANCE_RATIO:\n        return 2\n",
        f"{T}::test_r20_a_variance_ratio_above_four_refuses_whatever_the_p_value",
        "R-20: the audited ORDER exactly -- the p-value returns before the ratio is tested, so a scatter "
        "2.6x the declared sigma at one degree of freedom reads SUPPORTED"),
    Mutation(
        "B11k", f"{LG}::_goodness_of_fit",
        "    if 1 <= dof <= UNDERPOWERED_RESIDUAL_DOF:\n",
        "    if False:\n",
        f"{T}::test_r20_one_or_two_residual_degrees_of_freedom_is_underpowered",
        "R-20: nothing records that the declared noise model was essentially untestable"),
    Mutation(
        "B11l", f"{LG}::_goodness_of_fit",
        "    if 1 <= dof <= UNDERPOWERED_RESIDUAL_DOF:\n",
        "    if 1 <= dof <= 2 * UNDERPOWERED_RESIDUAL_DOF:\n",
        f"{T}::test_three_residual_degrees_of_freedom_is_not_flagged_underpowered",
        "R-20: the declared limit of 2 drifts to 4 without the residual that names dof 3 and 4 being "
        "revisited. The guard is the other side of the same threshold"),
    Mutation(
        "B11m", f"{LG}::_one_fit_test",
        "    if math.isnan(float(p_value)) or float(p_value) >= GOODNESS_OF_FIT_ALPHA / 2.0:\n",
        "    if math.isnan(float(p_value)) or float(p_value) >= GOODNESS_OF_FIT_ALPHA:\n",
        f"{T}::test_each_test_runs_at_half_the_declared_alpha",
        "R-03: two tests on the same residuals at the full alpha each, which is a family-wise false-refusal "
        "rate above the level batch 1 declared"),

    # --- the grid route runs the same rule ---
    Mutation(
        "B11n", f"{GE}::grid_goodness_of_fit",
        "    if calibration is not None and forward is not None:\n",
        "    if False:\n",
        f"{T}::test_r03_a_supplied_grid_runs_the_same_rule",
        "R-03: the grid keeps the pooled test alone, which is the blind spot the audit inferred from the call"),
    Mutation(
        "B11o", f"{GE}::grid_goodness_of_fit",
        "        if measured is None:\n",
        "        if False:\n",
        f"{T}::test_a_grid_whose_best_node_has_no_curvature_is_passed_over",
        "R-03: a grid whose fit cannot be tested where the information is is used anyway"),
    Mutation(
        "B11p", f"{GE}::grid_goodness_of_fit",
        "    row = int(np.arange(len(ll))[usable][int(np.argmin(chi_square[usable]))])\n",
        "    row = int(np.arange(len(ll))[usable][0])\n",
        f"{T}::test_a_well_fitting_supplied_grid_is_still_used",
        "R-03: the leverage test runs at the grid's FIRST admissible node rather than at the node its "
        "chi-square minimum comes from, so the statistic and the pooled number are not one fit's"),
    Mutation(
        "B11q", f"{GE}::grid_goodness_of_fit",
        "    for reason in sorted((refusals | downgrades) & MISFIT_REASONS, key=lambda r: r.value):\n",
        "    for reason in sorted(refusals | downgrades, key=lambda r: r.value):\n",
        f"{T}::test_a_supplied_grid_over_one_residual_degree_of_freedom_is_still_used",
        "R-20: the underpowered downgrade passes a grid over, although it says the noise model was "
        "untestable and not that the residuals contradict it -- and a grid has no DOWNGRADED claim to carry "
        "it with. Every small grid route in the suite would be passed over"),
]

_CHANGED_FILES = (LG, GE, "src/engcore/hybrid_uq/vocabulary.py", "src/engcore/hybrid_uq/router.py",
                  "src/engcore/hybrid_uq/predictive.py")


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
    status = run(MUTATIONS, label="BATCH11", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH11_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 11 changed ---", flush=True)
    status |= run(existing, label="BATCH11_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH11_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
