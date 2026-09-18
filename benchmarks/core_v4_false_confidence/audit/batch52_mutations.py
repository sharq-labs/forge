"""Batch-52 guard mutations (I-25 part A, R-55): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch52_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

R = "src/engcore/scientific/fields/result.py"
V = "src/engcore/scientific/models/structured_validity.py"
F = "src/engcore/data/field.py"
T = "tests/test_core_scientific_audit_batch52.py"

MUTATIONS = [
    Mutation(
        "B52a", f"{R}::FieldSummary.__post_init__",
        "        if not (self.minimum.magnitude <= mean <= self.maximum.magnitude_in(unit)):\n",
        "        if False:\n",
        f"{T}::test_r55_a_mean_outside_its_own_range_is_refused",
        "finding 70 restored in part: a summary may state a mean outside its own range, which is a "
        "statement about a set of values that cannot be true of any set"),
    Mutation(
        "B52b", f"{R}::FieldSummary.__post_init__",
        "        if self.l2_norm.magnitude < 0.0:\n",
        "        if False:\n",
        f"{T}::test_r55_a_negative_norm_is_refused",
        "a negative l2_norm is accepted again: a norm is a length, and a length below zero is not a "
        "rounding of anything"),
    Mutation(
        "B52c", f"{R}::FieldRecord.__post_init__",
        "            if not entry.is_compatible_with(declared.units):\n",
        "            if False:\n",
        f"{T}::test_r55_a_summary_in_another_dimension_is_refused",
        "finding 70's unit claim restored: a kelvin field may be summarized in pascal, volt or second, "
        "and every reader that acts on the summary compares those numbers with a temperature bound"),
    Mutation(
        "B52d", f"{R}::FieldRecord.__post_init__",
        "        if self.summary.non_finite > self.reference.count:\n",
        "        if False:\n",
        f"{T}::test_r55_more_non_finite_values_than_values_is_refused",
        "a summary may count more non-finite values than the field has values, so the count a finiteness "
        "predicate reads is not a count of anything"),
    Mutation(
        "B52e", f"{F}::FieldValue._require_the_summary_describes_these_values",
        "            if abs(left - right) > SUMMARY_AGREEMENT_RTOL * scale:\n",
        "            if False:\n",
        f"{T}::test_r55_a_summary_that_does_not_match_the_bytes_is_refused_on_read",
        "finding 70's central claim restored: the read path resolves the content-addressed bytes and does "
        "not compare them with the summary, so a record whose values hold a 900 K hot spot keeps a summary "
        "saying 310 K with its digest unchanged"),
    Mutation(
        "B52f", f"{F}::FieldValue.store",
        "            summary_verified_against=reference.digest,\n",
        "            summary_verified_against=\"\",\n",
        f"{T}::test_r55_a_record_bound_to_its_bytes_is_decided_as_before",
        "a field that stores its own values stops saying that its summary came from them, so every "
        "predicate over a legitimately produced record answers UNKNOWN -- the rule turned into a wall, "
        "which is what the binding exists to avoid"),
    Mutation(
        "B52g", f"{V}::FieldRangeCondition.evaluate",
        "        if not value.summary_is_bound_to_its_values:\n",
        "        if False:\n",
        f"{T}::test_r55_a_range_predicate_will_not_decide_from_an_unbound_summary",
        "the range predicate decides from an unbound summary again, which is the record's own word about "
        "an array nobody resolved"),
    Mutation(
        "B52h", f"{V}::FieldFiniteCondition.evaluate",
        "        if not value.summary_is_bound_to_its_values:\n",
        "        if False:\n",
        f"{T}::test_r55_a_finiteness_predicate_will_not_decide_from_an_unbound_summary",
        "and so does the finiteness predicate, from an unbound count"),
    Mutation(
        "B52i", f"{V}::FieldRangeCondition.evaluate",
        "        if int(value.definition.components) > 1:\n",
        "        if False:\n",
        f"{T}::test_r55_a_vector_field_is_judged_on_its_magnitude",
        "finding 67 restored: a vector field is judged per component again, so (1, 1, 1) m/s with a speed "
        "of 1.732 passes a 1.2 m/s maximum"),
    Mutation(
        "B52j", f"{V}::FieldRangeCondition._evaluate_magnitude",
        "        if magnitude is None or self.maximum is None:\n",
        "        if False:\n",
        f"{T}::test_r55_a_bound_vector_record_without_a_magnitude_is_still_unknown",
        "a multi-component record written before the magnitude existed is judged anyway, on a None, "
        "which is the absence this rule reports rather than infers. REPOINTED while running these "
        "mutations: the preregistered reproduction's record is also unbound, so the binding rule answers "
        "it first; the case only this rule sees is a record BOUND to its own bytes that still carries no "
        "magnitude"),
]

_CHANGED_FILES = (R, V, F)


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
    status = run(MUTATIONS, label="BATCH52", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH52_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 52 changed ---", flush=True)
    status |= run(existing, label="BATCH52_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH52_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
