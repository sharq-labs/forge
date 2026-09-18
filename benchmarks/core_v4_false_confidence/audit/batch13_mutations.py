"""Batch-13 guard mutations (I-18, a sound adequacy comparison): each new guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch13_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

AD = "src/engcore/adequacy/predictive.py"
SP = "src/engcore/inference/split.py"
T = "tests/test_core_scientific_audit_batch13.py"
B3 = "benchmarks/battery_flagship_b3/tests/test_battery_flagship_b3.py"

MUTATIONS = [
    # --- R-24: content binding binds the content ---
    Mutation(
        "B13a", f"{AD}::assess_predictive_observation",
        "        if not same_sigma:\n",
        "        if False:\n",
        f"{T}::test_r24_a_spec_sigma_that_is_not_the_declared_one_is_refused",
        "R-24: a caller-chosen likelihood sigma is content-bound again -- 0.05 K against a declared 0.5 K "
        "created a decisive preference and 5 K erased a genuine one"),
    Mutation(
        "B13b", f"{AD}::assess_predictive_observation",
        "        if twin != split.twin:\n",
        "        if False:\n",
        f"{T}::test_r24_a_twin_that_is_not_the_splits_twin_is_refused",
        "R-24: an assessment bound to one twin's split is recorded for another twin"),
    Mutation(
        "B13c", f"{AD}::assess_predictive_observation",
        "        split_content_digest = _split_content_digest(split)\n",
        "        split_content_digest = \"\"\n" if False else "        pass\n",
        f"{T}::test_r24_the_identity_carries_the_splits_content",
        "R-24: the identity stops carrying the split's content, so two campaigns labelled alike pair as one "
        "evidence"),
    Mutation(
        "B13d", f"{AD}::_split_content_digest",
        '        "calibration_content": sorted(observation_content_digest(o) for o in split.calibration.observations),\n',
        '        "calibration_content": len(split.calibration.observations),\n',
        f"{T}::test_r24_the_identity_carries_the_splits_content",
        "R-24: the digest counts the calibration half instead of digesting it, which is the audited case "
        "exactly -- an older 4-point campaign and a newer one of the same size would pair"),
    Mutation(
        # The first draft of this file had a gate of its own here for "bound to the SAME split". It SURVIVED,
        # and was right to: `split_content_digest` is an EVIDENCE_IDENTITY_FIELD, so the pairing loop already
        # refuses two assessments bound to different split content and names the field. The gate was dead code
        # and is gone; this mutation removes the field from the list the pairing loop reads, which is the real
        # guard.
        "B13e", f"{AD}",
        '    "split_content_digest",\n',
        "\n",
        f"{T}::test_r24_two_campaigns_under_the_same_labels_do_not_pair_as_one_evidence",
        "R-24: the split content leaves the evidence identity, so two campaigns labelled alike pair as one "
        "evidence -- the audited case, a decisive preference driven only by the training data"),
    Mutation(
        "B13f", f"{AD}::PredictiveEvidenceIdentity._canonical",
        '                if not (name == "split_content_digest" and not self.split_content_digest)}\n',
        "                }\n",
        f"{T}::test_r24_a_record_written_before_this_rule_keeps_the_digest_it_had",
        "R-24: the empty digest enters the canonical form, so every record written before this rule stops "
        "hashing to what it hashed to. The guard is the compatibility the rule promises"),

    # --- R-34: the binding is verified, not declared ---
    Mutation(
        "B13g", f"{AD}::assess_predictive_observation",
        "        _CONTENT_BOUND_RECORDS.add(assessment.record_digest)\n",
        "        pass\n",
        f"{T}::test_r34_a_bound_assessment_is_verified_and_an_unbound_one_is_not",
        "R-34: nothing is ever registered, so no binding is verifiable"),
    Mutation(
        "B13h", f"{AD}::compare_log_predictive_scores",
        "    if not all(item.content_binding_verified for item in (*a, *b)):\n",
        "    if not all(item.content_bound for item in (*a, *b)):\n",
        f"{T}::test_r34_a_flipped_flag_on_unbound_assessments_names_no_preferred_model",
        "R-34: the comparison reads the caller-settable FLAG again, which is the audited defect -- a flipped "
        "flag on unbound assessments named a model with a 15.9-nat preference"),
    Mutation(
        "B13i", f"{AD}::PredictiveObservationAssessment.record_digest",
        '        payload = {k: v for k, v in self.to_dict().items() if k != "content_bound"}\n',
        '        payload = {"observation_key": self.observation_key}\n',
        f"{T}::test_r34_a_fabricated_log_density_names_no_preferred_model",
        "R-34: the registry key stops covering what the record says, so a fabricated log density under the "
        "same key is verified"),

    # --- R-32: a copy is a copy inside a half too ---
    Mutation(
        "B13j", f"{SP}::ObservationSplit.__post_init__",
        '                if len({entry.split(":", 1)[0] for entry in where}) > 1 or len(where) > 1\n',
        '                if len({entry.split(":", 1)[0] for entry in where}) > 1\n',
        f"{T}::test_r32_a_copy_the_digest_sees_and_the_tolerance_cannot_is_still_refused",
        "R-32: the exact-content detector looks only ACROSS the halves again. The audited four-copy case is "
        "caught by the near-duplicate route too, so the case that measures THIS detector is the one only it "
        "sees: at a value of 1e20 the digest's twelve significant digits make two rows one content while "
        "their difference is 1e5 declared sigmas"),
    Mutation(
        "B13k", f"{SP}::ObservationSplit.__post_init__",
        "                inside = _near_duplicates(observations, observations)\n",
        "                inside = []\n",
        f"{T}::test_r32_a_near_copy_inside_one_half_is_refused_too",
        "R-32: the near-duplicate detector looks only across the halves, so a copy nudged below any "
        "measurement resolution inside one half is two measurements again"),
    Mutation(
        "B13l", f"{SP}::_near_duplicates",
        '            candidates += [(NEAR_DUPLICATE_LINEAGE_RELATIVE_TO_SIGMA, False, other)\n'
        '                           for other in by_lineage.get((str(item.source_ref).strip(), unit), ())]\n',
        "            pass\n",
        f"{T}::test_r32_a_copy_the_old_rule_admitted_is_a_copy",
        "R-32: the LINEAGE route goes, so a re-imported reading whose sigma was re-declared, or which was "
        "renamed, crosses into held-out -- the audited residual"),
    Mutation(
        "B13m", f"{SP}::_near_duplicates",
        "            if needs_same_sigma and abs(sigma - other_sigma) > tolerance * scale:\n",
        "            if False:\n",
        f"{T}::test_r32_two_quantized_readings_with_different_uncertainties_are_two_measurements",
        "R-32: the numeric route stops requiring the declared sigmas to agree, which is what the audit "
        "suggested -- and it refuses REAL evidence. B3 holds two cross-half pairs whose voltages are "
        "bit-identical (the instrument quantizes) and whose uncertainties differ by 4.8e-6 of a sigma, at "
        "distinct rows with distinct provenance. Those are two measurements, and this guard is why lineage "
        "and not the sigma is what the rule dropped. The named test is that pattern synthetically; the B3 "
        "suite itself is the evidence that found it"),

    # --- the comparison's own arithmetic ---
    Mutation(
        "B13n", f"{AD}::compare_log_predictive_scores",
        "    elif repeated_content:\n",
        "    elif False:\n",
        f"{T}::test_r32_two_paired_positions_of_one_reading_name_no_preferred_model",
        "R-32: declared replicates are counted as independent paired positions again, so the standard error "
        "of the difference goes to zero"),
    Mutation(
        "B13o", f"{AD}::_decisive_preference",
        "    if abs(float(delta)) <= critical * float(standard_error):\n",
        "    if abs(float(delta)) <= COMPARISON_MINIMUM_SE_MULTIPLE * float(standard_error):\n",
        f"{T}::test_r33_the_gate_itself_uses_the_t_quantile_at_its_own_boundary",
        "R-33: the gate compares a t statistic with the NORMAL quantile again. Reached by reading the gate at "
        "its own boundary, because the window between 2 SE and the t quantile is a fixture search through "
        "data and a measurement through the function"),
    Mutation(
        "B13p", f"{AD}::_critical_se_multiple",
        "    return float(_student_t.ppf(1.0 - COMPARISON_ALPHA / 2.0, int(n) - 1))\n",
        "    return float(_student_t.ppf(1.0 - COMPARISON_ALPHA / 2.0, int(n)))\n",
        f"{T}::test_r33_the_se_multiple_is_a_t_quantile_on_n_minus_one_degrees_of_freedom",
        "R-33: the degrees of freedom are n rather than n - 1, which is the sample sd's own dof"),
    Mutation(
        "B13q", f"{AD}",
        "COMPARISON_MINIMUM_N = 10\n",
        "COMPARISON_MINIMUM_N = 2\n",
        f"{T}::test_r33_the_minimum_paired_count_is_where_the_standard_error_is_worth_a_quarter",
        "R-33: the minimum returns to 2, where the sample sd's own relative standard error is 0.707"),
    Mutation(
        "B13r", f"{AD}::ModelScoreComparison.to_dict",
        '            "measurement_errors_assumed_independent": bool(self.measurement_errors_assumed_independent),\n',
        "        }\n" if False else "            **{},\n",
        f"{T}::test_r32_the_comparison_records_the_independence_it_assumes",
        "R-32: the record stops stating the independence its standard error assumes"),
]

_CHANGED_FILES = (AD, SP)


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
    status = run(MUTATIONS, label="BATCH13", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH13_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 13 changed ---", flush=True)
    status |= run(existing, label="BATCH13_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH13_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
