"""Batch-22 guard mutations (I-13 part A, a prediction's domain bound to its calibration): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch22_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

PR = "src/engcore/hybrid_uq/predictive.py"
LG = "src/engcore/hybrid_uq/local_gaussian.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch22.py"
B4 = "tests/hybrid_uq/test_core_scientific_audit_batch4.py"

MUTATIONS = [
    # --- R-12: the binding ---
    Mutation(
        "B22a", f"{PR}::linearized_predictive_uq",
        "        if supplied != posterior.calibration_content_digest:\n",
        "        if False:\n",
        f"{T}::test_r12_another_datasets_observations_are_refused_rather_than_weighed",
        "R-12, the audited case restored exactly: `calibration_observations` are bound to nothing again, so "
        "another dataset's observations state this prediction's domain and a far extrapolation reads SUPPORTED"),
    Mutation(
        "B22b", f"{LG}::_observation_content_digest",
        "    return digest_of(observations.to_dict())\n",
        '    return digest_of({"dataset_id": observations.dataset_id})\n',
        f"{T}::test_r12_the_same_observations_with_rescaled_conditions_are_refused",
        "the digest falls back to the dataset id, which is a label the CALLER writes -- two of R-12's three "
        "reproductions keep the id and change the content, the conditions rescaled or the values replaced by "
        "a predictor evaluated elsewhere"),
    Mutation(
        "B22c", f"{LG}::local_gaussian_posterior",
        "        calibration_content_digest=_observation_content_digest(observations),\n",
        '        calibration_content_digest="",\n',
        f"{T}::test_r12_the_posterior_carries_one_digest_of_the_content_it_was_calibrated_on",
        "the posterior stops carrying the digest, so there is nothing for the binding to compare against and "
        "it passes silently -- a guard that is switched off by the absence of its own evidence"),
    Mutation(
        "B22d", f"{PR}::_calibration_design",
        '        pairs = tuple(getattr(posterior, "calibrated_conditions", ()) or ())\n'
        '        rows = tuple(getattr(posterior, "calibrated_condition_points", ()) or ())\n',
        "        pairs = ()\n        rows = ()\n",
        f"{T}::test_r12_an_extrapolation_cannot_be_hidden_by_supplying_no_observations_at_all",
        "the posterior's own stored design stops being used, so supplying NO observations leaves the gate "
        "with nothing to compare and an extrapolation to x = 1e4 is reported with a caveat instead of being "
        "measured -- R-12's simplest form"),
    Mutation(
        "B22e", f"{LG}::_calibrated_conditions",
        "        shared &= set(row.conditions)\n",
        "        shared |= set(row.conditions)\n",
        f"{T}::test_r31_a_condition_only_some_observations_declare_is_not_a_range_the_calibration_covered",
        "the stored design becomes the UNION of the declared conditions instead of the intersection, so a "
        "condition only some observations declare becomes a range the calibration never covered. Repointed: "
        "it first named a case where every observation declares the same conditions, where union and "
        "intersection are the same set. It SURVIVED the added case too, because a broad `except Exception` "
        "around the unit conversion swallowed the KeyError the union then raises; that catch is now by type"),
    # --- R-31: every declared condition, and the joint support ---
    Mutation(
        "B22f", f"{PR}::_prediction_domain_reasons",
        "    if any(name not in spec.conditions for name in names):\n",
        "    if False:\n",
        f"{T}::test_r31_a_prediction_that_omits_a_condition_the_calibration_declares_is_not_declared",
        "R-31, the audited case restored exactly: a prediction that simply omits a condition the calibration "
        "declares is compared on the rest, so a prediction at T = 900 K is DOWNGRADED and the same prediction "
        "with T omitted is SUPPORTED. It SURVIVED first, because a single `try` around the lookup AND the unit "
        "conversion caught the resulting KeyError and answered PREDICTION_DOMAIN_NOT_DECLARED anyway -- the "
        "two are now two statements (amendment 2)"),
    Mutation(
        "B22g", f"{PR}::_prediction_domain_reasons",
        "    if residual > PREDICTION_RANGE_RELATIVE_TOLERANCE:\n",
        "    if False:\n",
        f"{T}::test_r31_the_joint_support_is_the_region_covered_and_not_the_box_around_it",
        "the joint-support verdict is computed and then not used, so every prediction is inside the "
        "calibrated domain however far outside it sits"),
    Mutation(
        "B22h", f"{PR}::_condition_support_residual",
        "    equality[0, :n] = 1.0\n",
        "    equality[0, :n] = 0.0\n",
        f"{T}::test_r31_at_one_condition_the_rule_is_the_interval_it_always_was",
        "the weights stop being required to sum to 1, so the region is the convex CONE from the origin rather "
        "than the convex hull of the observed points -- which for a positive condition admits everything "
        "between 0 and the calibration and nothing says so"),
    Mutation(
        "B22i", f"{PR}::_condition_support_residual",
        '                   bounds=[(0.0, None)] * n + [(0.0, None)], method="highs",\n',
        '                   bounds=[(None, None)] * n + [(0.0, None)], method="highs",\n',
        f"{T}::test_r31_the_joint_support_is_the_region_covered_and_not_the_box_around_it",
        "the weights may go NEGATIVE, so the region is the whole affine span of the observed conditions -- "
        "for observations on a line that is the infinite line, and every point on it reads interpolated. It "
        "SURVIVED the off-line point, which is off the span as well; the case added for it is an "
        "extrapolation ALONG the calibrated line, 20 K past its last observation"),
    Mutation(
        "B22j", f"{PR}::_condition_support_residual",
        "    inequality = np.vstack([upper, lower])\n",
        "    inequality = np.vstack([upper])\n",
        f"{T}::test_r31_at_one_condition_the_rule_is_the_interval_it_always_was",
        "only one side of the residual is bounded, so the LP can drive the objective to zero on a point BELOW "
        "the calibrated range -- at one condition, exactly half of the interval it replaces"),
    Mutation(
        "B22k", f"{PR}::_prediction_domain_reasons",
        "    scales = np.where(spread > 0.0, spread, np.where(reference > 0.0, reference, 1.0))\n",
        "    scales = np.ones(len(pairs))\n",
        f"{T}::test_r31_the_tolerance_is_relative_to_the_condition_the_calibration_spread_over",
        "the tolerance stops being relative to each condition's own spread, so one declared number means a "
        "different slack on every condition. It SURVIVED every reproduction, which were all far outside or "
        "exactly inside; the case added for it sits a tenth of the tolerance inside and ten times it outside "
        "-- and that case is what exposed HiGHS's default feasibility tolerance being a hundred times coarser "
        "than the rule (amendment 1)"),
    Mutation(
        "B22l", f"{PR}::_prediction_domain_reasons",
        "    if any(name not in names for name in spec.conditions):\n",
        "    if False:\n",
        f"{T}::test_r31_a_prediction_that_declares_a_condition_the_calibration_never_did_is_not_declared",
        "a prediction may declare a condition the calibration never did and have it IGNORED, so an operating "
        "point the calibration says nothing about gets a domain statement anyway. Repointed: every "
        "reproduction declared exactly the design's names, so none could see it"),
]

_CHANGED_FILES = (PR, LG)


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
    status = run(MUTATIONS, label="BATCH22", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH22_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 22 changed ---", flush=True)
    status |= run(existing, label="BATCH22_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH22_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
