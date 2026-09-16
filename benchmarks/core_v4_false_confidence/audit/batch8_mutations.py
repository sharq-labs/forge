"""Batch-8 guard mutations (I-09 part A): each new guard removed, in an ISOLATED copy.

Not in tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core
Freeze V4 round (I-30). The runner is ``isolated_mutations``, which fixes R-67 for these runners.

Run from the repository root, with SCRATCH pointing at a scratch directory::

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch8_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

EVIDENCE = "src/engcore/mcp/evidence.py"
SERVER = "src/engcore/mcp/server.py"
PROBLEM = "src/engcore/mcp/problem.py"
T = "tests/mcp/test_core_scientific_audit_batch8.py"

MUTATIONS = [
    Mutation(
        "B8a", f"{EVIDENCE}::attained_levels_of",
        "        if not level_is_earned(level, outcome, residual, tolerance, evidence):\n",
        "        if False:\n",
        f"{T}::test_r47_a_pass_with_a_level_and_nothing_compared_establishes_nothing",
        "R-47: the exported verdict stops re-applying GUARD 2 and reads a claimed level again"),
    Mutation(
        "B8b", f"{EVIDENCE}::attained_levels_of",
        "        gap = _issuer_gap(level, outcome, residual, tolerance, evidence)\n",
        "        gap = None\n",
        f"{T}::test_r47_derive_verdict_refuses_a_duck_typed_check",
        "R-47: the exported verdict stops re-applying VAL-01's issuer rule"),
    Mutation(
        "B8c", f"{EVIDENCE}::attained_levels_of",
        "        except (AttributeError, TypeError, ValueError) as exc:\n",
        "        except (TypeError, ValueError) as exc:\n",
        f"{T}::test_r47_derive_verdict_refuses_an_object_missing_the_fields_the_rule_reads",
        "R-47: an object missing the fields the rule reads is read past instead of refused"),
    Mutation(
        "B8d", f"{EVIDENCE}::attained_levels_of",
        "        if outcome is ValidationOutcome.PASS:\n            attained.add(level)\n",
        "        if True:\n            attained.add(level)\n",
        "tests/mcp/test_evidence.py::test_a_level_established_by_a_check_that_did_not_pass_does_not_count",
        "R-47: a WARNING check's level counts, which the core's own attained_levels does not do"),
    Mutation(
        "B8e", f"{EVIDENCE}::derive_verdict",
        "        if EVIDENCE_BASIS_ORDER[evidence_basis_of(attained)] < EVIDENCE_BASIS_ORDER[demanded]:\n",
        "        if False:\n",
        f"{T}::test_r04_derive_verdict_reads_a_required_basis_on_its_own",
        "R-04: a caller's demand for a kind of evidence stops deciding anything"),
    Mutation(
        "B8f", f"{EVIDENCE}::CredibilityEvidenceReport.missing_evidence_basis",
        "        if EVIDENCE_BASIS_ORDER[self.evidence_basis] < EVIDENCE_BASIS_ORDER[demanded]:\n",
        "        if False:\n",
        f"{T}::test_r04_a_caller_can_demand_a_basis_it_did_not_get",
        "R-04: the report stops naming the basis it was required to have"),
    Mutation(
        "B8g", f"{EVIDENCE}::CredibilityEvidenceReport.from_dict",
        '        if "verdict_qualifiers" not in payload:\n',
        "        if False:\n",
        f"{T}::test_r04_a_payload_with_the_evidence_basis_removed_is_refused",
        "R-04: deleting the whole qualifiers block is a way past the comparison again"),
    Mutation(
        "B8h", f"{EVIDENCE}::_require_qualifiers_as_derived",
        "    missing = sorted(set(derived) - set(stated))\n",
        "    missing = []\n",
        f"{T}::test_r04_a_payload_with_the_evidence_basis_removed_is_refused",
        "R-04: deleting one qualifier -- evidence_basis -- is a way past it again"),
    Mutation(
        "B8i", f"{SERVER}::_verdict_block",
        "        **_BASIS_GUIDANCE[(verdict, basis)],\n",
        "        **_VERDICT_GUIDANCE[verdict],\n",
        f"{T}::test_r04_a_verification_only_support_does_not_read_as_validation",
        "R-04: the sentence an agent reads goes back to the one that does not mention verification"),
    # A mutation that only renames a STRING is refused by the harness -- `_code_digest` ignores string
    # tokens on purpose, because a mutation that changes no executable code is a verifier that cannot
    # fail. The first draft of B8j..B8l renamed the rule keys and was correctly refused; each mutates
    # the code behind the key instead.
    Mutation(
        "B8j", f"{SERVER}::_verdict_block",
        '        "evidence_basis": basis,\n',
        '        "evidence_basis": None,\n',
        f"{T}::test_r04_the_verdict_block_names_its_evidence_basis",
        "R-04: the block carries the key and not the basis"),
    Mutation(
        "B8k", f"{SERVER}::_fired_rules",
        '         () if report.evidence_basis == "VALIDATED" else (report.evidence_basis,),\n',
        "         () if True else (report.evidence_basis,),\n",
        f"{T}::test_r04_a_non_deciding_verification_only_rule_fires",
        "R-04: the non-deciding rule never fires, so a VERIFICATION_ONLY support reads bare again"),
    Mutation(
        "B8l", f"{SERVER}::_fired_rules",
        "         () if _finished(report) else (report.convergence,),\n",
        "         () if True else (report.convergence,),\n",
        f"{T}::test_the_rule_table_names_a_solver_that_did_not_finish",
        "I-10's named rule: the rule never fires, so the convergence gap is nameless again"),
    Mutation(
        "B8m", SERVER,
        '                     **_BASIS_GUIDANCE[(verdict, basis)]}\n',
        '                     **_VERDICT_GUIDANCE[verdict]}\n',
        f"{T}::test_r04_describe_capabilities_explains_the_evidence_basis",
        "R-04: describe_capabilities says the same thing for every basis"),
    Mutation(
        "B8n", f"{PROBLEM}::_withhold_level",
        '            else (*check.evidence, f"{WITHHELD_LEVEL_EVIDENCE_PREFIX}{withheld.value}")\n',
        "            else check.evidence\n",
        f"{T}::test_r04_a_withheld_level_is_recorded_where_a_reader_finds_it",
        "R-04: a withheld level goes back to reaching a reader only inside a detail sentence"),
]

_CHANGED_FILES = (EVIDENCE, SERVER, PROBLEM)


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
    status = run(MUTATIONS, label="BATCH8", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH8_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 8 changed ---", flush=True)
    status |= run(existing, label="BATCH8_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH8_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
