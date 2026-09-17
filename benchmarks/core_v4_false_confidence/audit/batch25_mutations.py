"""Batch-25 guard mutations (I-12 part B, how a cross-solver level is earned): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch25_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

CO = "src/engcore/scientific/consensus.py"
VA = "src/engcore/scientific/results/validation.py"
EX = "src/engcore/execution/consensus.py"
PB = "src/engcore/mcp/problem.py"
T = "tests/test_core_scientific_audit_batch25.py"
CS = "tests/test_cross_solver_consensus.py"
GL = "tests/test_guard_reach_ledger.py"

MUTATIONS = [
    # --- R-21 (c): a disagreement is a finding whether or not the routes are independent ---
    Mutation(
        "B25a", f"{CO}::CrossSolverConsensus.to_check",
        "        else:\n            outcome = ValidationOutcome.FAIL\n",
        "        elif self.routes_are_independent:\n            outcome = ValidationOutcome.FAIL\n"
        "        else:\n            outcome = ValidationOutcome.WARNING\n",
        f"{CS}::test_dependent_routes_that_disagree_also_fail",
        "R-21, the audited case restored exactly: two routes sharing their machinery and reporting 1.0 "
        "against 1.5 for the same quantity read WARNING again, and the verdict over such a check stays "
        "SUPPORTED. The old reasoning conflated the authority to AWARD with the authority to report a "
        "MEASUREMENT"),
    Mutation(
        "B25b", f"{CO}::CrossSolverConsensus.to_check",
        "        elif comparison.agreed:\n            outcome = ValidationOutcome.PASS\n",
        "        elif True:\n            outcome = ValidationOutcome.PASS\n",
        f"{T}::test_r21_a_disagreement_between_non_independent_routes_fails_rather_than_warns",
        "the disagreement branch becomes unreachable, so every comparison that ran at all is a PASS -- the "
        "opposite error to the audited one, and the one a stricter FAIL rule could most easily be mutated "
        "into by accident"),
    # --- the independence basis ---
    Mutation(
        "B25c", f"{CO}::CrossSolverConsensus.evidence",
        "        if self.establishes is not None:\n"
        "            lines.append(INDEPENDENCE_BASIS_EVIDENCE_PREFIX + INDEPENDENCE_BASIS_DECLARED)\n",
        "        if False:\n"
        "            lines.append(INDEPENDENCE_BASIS_EVIDENCE_PREFIX + INDEPENDENCE_BASIS_DECLARED)\n",
        f"{T}::test_r21_the_consensus_names_the_declared_basis_it_rests_on",
        "the consensus stops saying which independence its level rests on, so the level is refused outright "
        "-- which is the rule working, and is why the line is written where the level is awarded"),
    Mutation(
        "B25d", f"{VA}::_consensus_issuer_gap",
        "    if len(bases) != 1 or bases[0] not in INDEPENDENCE_BASES:\n",
        "    if False:\n",
        f"{T}::test_r21_a_check_claiming_the_level_without_a_basis_is_refused",
        "the level may be carried with NO statement of which independence it rests on, which is R-21's own "
        "sentence: a level earned from declarations and a level earned from the artifacts' own bytes are not "
        "the same claim and a reader cannot tell them apart from the level alone"),
    Mutation(
        "B25e", f"{VA}::_consensus_issuer_gap",
        "    if len(bases) != 1 or bases[0] not in INDEPENDENCE_BASES:\n",
        "    if len(bases) < 1 or bases[0] not in INDEPENDENCE_BASES:\n",
        f"{T}::test_r21_two_basis_lines_are_not_a_basis_either",
        "a check may claim BOTH bases at once, so a level resting on declarations alone can carry the "
        "artifact-verified line beside it and a reader reading either one is misled"),
    Mutation(
        "B25f", f"{EX}::TrustedConsensusGate.assess",
        "        carried = tuple(\n            line for line in base.evidence\n"
        "            if not line.startswith(INDEPENDENCE_BASIS_EVIDENCE_PREFIX)\n        )\n",
        "        carried = tuple(base.evidence)\n",
        f"{T}::test_r21_the_gate_names_the_artifact_verified_basis_when_the_bytes_agree",
        "the gate APPENDS its basis instead of replacing the consensus's, so a level that rests on the "
        "bytes carries `declared` beside `artifact-verified` -- two bases, which is no single basis, and the "
        "level is refused"),
    Mutation(
        "B25g", f"{EX}::TrustedConsensusGate.assess",
        "        elif base_earned:\n"
        '            carried = (*carried, f"level-withheld:{ValidationLevel.CROSS_SOLVER_VALIDATED.value}")\n',
        "        elif False:\n"
        '            carried = (*carried, f"level-withheld:{ValidationLevel.CROSS_SOLVER_VALIDATED.value}")\n',
        f"{T}::test_r21_the_gate_withholds_the_level_when_no_artifact_evidence_is_offered",
        "the gate stops recording the level it NEARLY awarded, so what a run came within one artifact digest "
        "of establishing reaches a reader only as prose -- R-04's finding, reintroduced one layer up. "
        "Repointed: it first named the idempotence guard, which reaches `_withhold_level` with a check that "
        "still CARRIES the level, so the line it counts is the boundary's and not the gate's"),
    # --- the production path ---
    Mutation(
        "B25h", f"{PB}",
        "    decision = TrustedConsensusGate().assess(\n        consensus, (), name=CROSS_SOLVER_CHECK_NAME,\n    )\n"
        "    return (_withhold_level(decision.check),)\n",
        "    return (_withhold_level(consensus.to_check(name=CROSS_SOLVER_CHECK_NAME)),)\n",
        f"{T}::test_r21_the_production_cross_solver_check_is_built_by_the_gate",
        "R-21's second claim restored exactly: the production path mints the check from the consensus alone "
        "and TrustedConsensusGate has no caller again, so the only rule in the tree that requires the "
        "artifacts' own bytes is one nothing runs"),
    Mutation(
        "B25i", f"{PB}::_withhold_level",
        "    if withheld is None and already:\n        return check\n",
        "    if False:\n        return check\n",
        f"{T}::test_r21_withholding_a_level_nobody_awarded_adds_no_second_line_and_no_second_sentence",
        "the boundary appends a second `level-withheld:` line and a second sentence for a level the gate "
        "already withheld -- two statements of one fact for a reader to reconcile, and the count a consumer "
        "reads becomes two"),
    # --- the ledger moves with the fix ---
    Mutation(
        "B25j", "certification/guard_reach_ledger.json", "", "", f"{T}::x",
        "NOT MUTATED. The ledger is JSON and `mutation_guards._apply` parses every mutation with `ast`, so a "
        "JSON edit reports MUTATION BROKE THE PARSE. What the ledger says is verified instead by "
        "`tools/certification/guard_reach.py` -- a FIXED problem must be REACHED or LATENT and a REACHED row "
        "must name a test that exercises it in production -- and by batch 19's own twelve refusal cases, "
        "whose guard mutations are in BATCH19_MUTATIONS.log. This entry exists so a reader does not have to "
        "wonder why the row's move is unmutated.",
        expect="SURVIVED"),
]

_CHANGED_FILES = (CO, VA, EX, PB)


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
    live = [m for m in MUTATIONS if m.id != "B25j"]
    print(f"NOT MUTATED: B25j -- {MUTATIONS[-1].note}", flush=True)
    status = run(live, label="BATCH25", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH25_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 25 changed ---", flush=True)
    status |= run(existing, label="BATCH25_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH25_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
