"""Batch-24 guard mutations (I-12 part A, agreement between solvers is verification): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch24_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

VA = "src/engcore/scientific/results/validation.py"
SV = "src/engcore/mcp/server.py"
T = "tests/test_core_scientific_audit_batch24.py"

MUTATIONS = [
    # Each of the three classification mutations edits BOTH sets, or the set AND the check that refuses the
    # state it creates. That is not a way of making them easier to kill -- it is the only way to make them
    # OBSERVABLE. `_require_every_level_is_classified` runs at import, so a mutation that leaves a level in
    # both sets or in neither does not produce a wrong verdict: it produces a tree that will not import, and
    # `isolated_mutations` rightly reports COLLECTION_BROKEN rather than a kill (R-67). What a reader needs
    # to know is whether the classification can be WRONG and still work, so each mutation restores a
    # consistent-but-wrong state, which is what the audited defect was.
    Mutation(
        "B24a", f"{VA}",
        "VALIDATION_LEVELS = frozenset({\n    ValidationLevel.BENCHMARK_VALIDATED,\n"
        "    ValidationLevel.EXPERIMENTALLY_VALIDATED,\n})\n",
        "VALIDATION_LEVELS = frozenset({\n    ValidationLevel.BENCHMARK_VALIDATED,\n"
        "    ValidationLevel.CROSS_SOLVER_VALIDATED,\n    ValidationLevel.EXPERIMENTALLY_VALIDATED,\n})\n",
        f"{T}::test_r39_cross_solver_agreement_is_not_a_validation_level",
        "R-39, the audited case restored exactly and consistently: the level moves back to the validation "
        "set and out of the verification set, so agreement between two solvers of one declared model counts "
        "as a comparison with something outside that model again and a result whose only other levels are "
        "dimensional validity and convergence reads VALIDATED",
        also=((VA,
               "    ValidationLevel.ANALYTICALLY_VERIFIED,\n    ValidationLevel.CROSS_SOLVER_VALIDATED,\n})\n",
               "    ValidationLevel.ANALYTICALLY_VERIFIED,\n})\n"),)),
    Mutation(
        "B24b", f"{VA}",
        "    ValidationLevel.ANALYTICALLY_VERIFIED,\n    ValidationLevel.CROSS_SOLVER_VALIDATED,\n})\n",
        "    ValidationLevel.ANALYTICALLY_VERIFIED,\n})\n",
        f"{T}::test_r39_both_kinds_are_named_and_every_level_is_in_exactly_one",
        "the level is in NEITHER kind, and the completeness check that refuses that is removed with it -- "
        "which is the state that let the level sit in the wrong group unnoticed: one kind a set, the other "
        "the remainder, and nobody deciding",
        also=((f"{VA}::_require_every_level_is_classified", "    if unclassified:\n", "    if False:\n"),)),
    Mutation(
        "B24c", f"{VA}",
        "VALIDATION_LEVELS = frozenset({\n    ValidationLevel.BENCHMARK_VALIDATED,\n"
        "    ValidationLevel.EXPERIMENTALLY_VALIDATED,\n})\n",
        "VALIDATION_LEVELS = frozenset({\n    ValidationLevel.BENCHMARK_VALIDATED,\n"
        "    ValidationLevel.CROSS_SOLVER_VALIDATED,\n    ValidationLevel.EXPERIMENTALLY_VALIDATED,\n})\n",
        f"{T}::test_r39_both_kinds_are_named_and_every_level_is_in_exactly_one",
        "the level is in BOTH kinds, and the check that refuses that is removed with it -- so "
        "`evidence_basis` says VALIDATED for a level the same module also calls verification, which is the "
        "contradiction R-39 is, with both halves written down",
        also=((f"{VA}::_require_every_level_is_classified", "    if overlap:\n", "    if False:\n"),)),
    Mutation(
        "B24d", f"{VA}::ValidationReport.evidence_basis",
        "        if attained & VALIDATION_LEVELS:\n",
        "        if attained & (VALIDATION_LEVELS | VERIFICATION_LEVELS):\n",
        f"{T}::test_r39_a_report_whose_validating_evidence_is_agreement_between_solvers_is_verification_only",
        "the word is derived from BOTH sets, so every attained level reads VALIDATED and the distinction the "
        "two sets exist to make is gone -- the classification moved and the rule that reads it did not"),
    Mutation(
        "B24e", "src/engcore/mcp/evidence.py::evidence_basis_of",
        "    if set(attained) & set(VALIDATION_LEVELS):\n",
        "    if set(attained) & {ValidationLevel.CROSS_SOLVER_VALIDATED} | set(VALIDATION_LEVELS):\n",
        f"{T}::test_r39_the_mcp_side_derives_the_same_word_from_the_same_rule",
        "the MCP side re-adds the level to its own copy of the rule, so the boundary and the core disagree "
        "about what kind of evidence a report holds -- the thing `evidence_basis_of` exists to prevent"),
    # NOT MUTATED, and recorded rather than quietly dropped: `_BASIS_MEANS['VERIFICATION_ONLY']` is a STRING
    # literal, and `mutation_guards._code_digest` ignores COMMENT and STRING tokens, so a wording change
    # reports MUTATION CHANGED NO CODE and cannot be verified this way. The wording is guarded by
    # `test_r39_the_word_says_that_agreement_between_solvers_is_one_of_the_things_it_covers`, and
    # `mcp/server.py::_audit_tables` already refuses to import while any basis word has no description.
]


_CHANGED_FILES = (VA, SV, "src/engcore/mcp/evidence.py")


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
    status = run(MUTATIONS, label="BATCH24", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH24_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 24 changed ---", flush=True)
    status |= run(existing, label="BATCH24_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH24_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
