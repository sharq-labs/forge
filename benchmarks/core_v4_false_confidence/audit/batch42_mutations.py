"""Batch-42 guard mutations (I-21 part A, R-41 and R-42): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch42_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

C = "src/engcore/scientific/ir/constraints.py"
E = "src/engcore/scientific/experiments/experiment.py"
T = "tests/test_core_scientific_audit_batch42.py"

MUTATIONS = [
    Mutation(
        "B42a", f"{C}::ConstraintCheck.__post_init__",
        "        if self.satisfied and margin < 0.0:\n",
        "        if False:\n",
        f"{T}::test_r41_a_satisfied_verdict_beside_a_negative_margin_is_refused",
        "R-41's forgery restored: satisfied=True beside a margin of -2.5 A is accepted again, survives a "
        "round trip, and wins a ranking -- and the verdict and the margin are one measurement"),
    Mutation(
        "B42b", f"{C}::ConstraintCheck.__post_init__",
        "        if not self.satisfied and margin > 0.0:\n",
        "        if False:\n",
        f"{T}::test_r41_a_violated_verdict_beside_a_positive_margin_is_refused",
        "the same disagreement in the other direction, which a rule written only for the dangerous side "
        "would have left open"),
    Mutation(
        "B42c", f"{C}::ConstraintCheck.__post_init__",
        "        if not isinstance(self.satisfied, bool):\n",
        "        if False:\n",
        f"{T}::test_r41_a_truthy_verdict_is_not_a_verdict",
        "a truthy non-bool is a verdict again, so the sign comparison below can be made vacuous by handing "
        "in something that is not a boolean at all"),
    Mutation(
        "B42d", f"{C}::ConstraintCheck.__post_init__",
        "        if self.satisfied and margin < 0.0:\n",
        "        if self.satisfied and margin <= 0.0:\n",
        f"{T}::test_r41_a_zero_margin_is_accepted_either_way",
        "zero is refused for a satisfied check, which refuses every constraint met exactly at its bound -- "
        "the control, and the off-by-one this rule most easily makes, since the check does not carry the "
        "operator that decides that case"),
    Mutation(
        "B42e", f"{E}::_feasibility_problems",
        "    missing = sorted(set(declared) - set(checked))\n",
        "    missing = []\n",
        f"{T}::test_r41_a_candidate_that_checked_one_of_two_declared_constraints_is_not_best",
        "R-41 as audited: coverage stops being required, so a candidate that checked one of two declared "
        "constraints is feasible again -- `all()` over one of two is True, which is what CORE-015 claimed "
        "to have fixed"),
    Mutation(
        "B42f", f"{E}::_feasibility_problems",
        "    undeclared = sorted(set(checked) - set(declared))\n",
        "    undeclared = []\n",
        f"{T}::test_r41_an_extra_check_on_an_undeclared_constraint_is_refused_on_its_own",
        "a check on a name the study does not declare counts as feasibility again, which is how the audited "
        "candidate with T_hot 900 K against a 400 K ceiling was ranked best. REPOINTED while running these "
        "mutations: the preregistered reproduction's forged check REPLACED the declared one, so the coverage "
        "rule already caught it. What sees this rule is a candidate that checked everything declared and "
        "carries one more verdict besides, on a name nothing is judging candidates against"),
    Mutation(
        "B42g", f"{E}::_feasibility_problems",
        "        if check.constraint in checked:\n",
        "        if False:\n",
        f"{T}::test_r41_a_duplicate_check_of_one_constraint_does_not_cover_the_others",
        "one constraint checked twice looks like two constraints checked, so coverage can be faked by "
        "repetition"),
    Mutation(
        "B42h", f"{E}::_feasibility_problems",
        "        if definition.metric in values:\n",
        "        if False:\n",
        f"{T}::test_r41_the_check_is_re_derived_from_the_result_where_the_metric_is_there",
        "the stored verdict is trusted again even where the result the study holds carries the very value "
        "the constraint is about -- a verdict is integrity-only, and here the inputs are in the record"),
    Mutation(
        "B42i", f"{E}::ScientificExperiment.best",
        "            if problem is not None:\n",
        "            if False:\n",
        f"{T}::test_r42_ranking_on_a_value_the_result_contradicts_is_refused",
        "R-42 as audited: an evaluation reporting objective 0.001 W is ranked best while its own result "
        "carries load = 50 W. The contradiction is measured and then not acted on"),
    Mutation(
        "B42j", f"{E}::_ranked_value_problem",
        "    if objective.metric not in values:\n",
        "    if False:\n",
        f"{T}::test_r42_a_result_that_does_not_carry_the_metric_is_ranked_on_its_objective",
        "the rule reaches past the record: a result that does not carry the metric at all is refused rather "
        "than ranked on its objective value. The control -- a rule nobody can satisfy is not a rule"),
    Mutation(
        "B42k", f"{E}::_declared_or_refuse",
        "    if key not in payload:\n",
        "    if False:\n",
        f"{T}::test_r41_a_payload_with_no_constraints_key_is_refused",
        "a missing declaration becomes an empty one again, which silently drops what the study said it was "
        "judging candidates against -- and changes which candidate `best` returns",
        also=((f"{E}::_declared_or_refuse", "    return payload[key] or ()\n", "    return payload.get(key) or ()\n"),)),
]

_CHANGED_FILES = (C, E)


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
    status = run(MUTATIONS, label="BATCH42", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH42_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 42 changed ---", flush=True)
    status |= run(existing, label="BATCH42_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH42_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
