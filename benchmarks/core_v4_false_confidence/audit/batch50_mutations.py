"""Batch-50 guard mutations (I-31; R-51, R-54): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch50_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

D = "src/engcore/scientific/models/definition.py"
U = "src/engcore/scientific/models/unknown_diagnostics.py"
T = "tests/test_core_scientific_audit_batch50.py"

MUTATIONS = [
    Mutation(
        "B50a", f"{D}::CategoryCondition.__post_init__",
        "        if isinstance(self.allowed, (str, bytes, bytearray)):\n",
        "        if False:\n",
        f"{T}::test_r54_a_bare_string_allowed_set_is_refused",
        "finding 66 claim (a) restored: allowed='laminar' is the six letters again, so the word is outside "
        "its own allowed set and each letter is inside it -- the condition answering the opposite question"),
    Mutation(
        "B50b", f"{D}::CrossLimitCondition.evaluate_in",
        "        if divisor < 0.0:\n",
        "        if False:\n",
        f"{T}::test_r54_two_negative_operands_are_not_ordered_by_their_ratio",
        "finding 66 claim (b) restored: -0.5 V over -1 V reads IN_DOMAIN with a ABOVE b, because a/b <= 1 "
        "orders a and b only while b is positive"),
    Mutation(
        "B50c", f"{D}::CrossLimitCondition.explain_in",
        "            value is not None and not isinstance(value, Quantity)\n",
        "            value is not None\n",
        f"{T}::test_r51_an_omitted_limit_is_not_supplied_rather_than_unreadable",
        "finding 63 restored exactly: a declared, readable limit counts as unreadable, so one limit "
        "declared and the other omitted reads UNREADABLE_SHAPE -- and the repair layer tells the caller "
        "that declaring the missing one will not help"),
    Mutation(
        "B50d", f"{D}::CrossLimitCondition.explain_in",
        "        if all(isinstance(value, Quantity) for value in operands):\n",
        "        if False:\n",
        f"{T}::test_r54_the_unordered_ratio_has_its_own_reason_and_its_own_guidance",
        "an unordered relation is reported as the caller's omission, which is the channel this batch "
        "un-blurs for R-51 being re-blurred in the other direction"),
    Mutation(
        "B50e", f"{U}::_context_key",
        "            if supplied.get(operand) is None:\n",
        "            if False:\n",
        f"{T}::test_r51_the_diagnostic_names_the_operand_the_context_is_missing",
        "the diagnostic stops naming the operand the context is missing and names the numerator whatever "
        "was supplied, so a caller reading it is pointed at a key that is already there"),
]

_CHANGED_FILES = (D, U, "src/engcore/domains/repair.py")


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
    status = run(MUTATIONS, label="BATCH50", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH50_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 50 changed ---", flush=True)
    status |= run(existing, label="BATCH50_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH50_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
