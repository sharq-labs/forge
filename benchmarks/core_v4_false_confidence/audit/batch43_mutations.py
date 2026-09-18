"""Batch-43 guard mutations (I-21 part B, R-44): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch43_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

Q = "src/engcore/scientific/results/requirements.py"
D = "src/engcore/design/evaluation.py"
A = "src/engcore/design/archives.py"
S = "src/engcore/systems/aerospace/multirotor/reference.py"
T = "tests/test_core_scientific_audit_batch43.py"

MUTATIONS = [
    Mutation(
        "B43a", f"{Q}::result_establishment_problems",
        "    if unrun:\n",
        "    if False:\n",
        f"{T}::test_r44_a_candidate_that_attained_a_level_and_left_a_check_unrun_is_not_ranked",
        "REPOINTED while running these mutations: the audited `unverified_report()` case is caught by the "
        "attained-level rule as well, so this rule is only visible on a report that DID attain a level and "
        "left a comparison unrun. finding 52 restored: a check that did not run stops counting, so a result whose validation is "
        "`unverified_report()` -- status NOT_RUN, nothing attained -- is established again and wins on its "
        "objective against a verified candidate"),
    Mutation(
        "B43b", f"{Q}::result_establishment_problems",
        '        problems.append("the validation established no level at all, so nothing stands behind the number")\n',
        "        pass\n",
        f"{T}::test_r44_a_candidate_with_an_empty_validation_report_is_not_ranked",
        "REPOINTED while running these mutations: an empty report has no NOT_RUN check either, so it is the "
        "case only this rule sees. a result whose validation established NOTHING is established, which is the other half of finding "
        "52: there is nothing standing behind the number being ranked"),
    Mutation(
        "B43c", f"{Q}::result_establishment_problems",
        "        if ValidationOutcome(check.outcome) is ValidationOutcome.NOT_RUN\n",
        "        if ValidationOutcome(check.outcome) is not ValidationOutcome.PASS\n",
        f"{T}::test_r44_an_inapplicable_check_does_not_make_a_candidate_unestablished",
        "the rule stops distinguishing a check that did not RUN from one that did not APPLY, which is the "
        "distinction batch 40 introduced for exactly this reason: there was nothing there to gather, and a "
        "candidate is not unestablished for it. The control"),
    Mutation(
        "B43d", f"{Q}::result_establishment_problems",
        "    if unassessed:\n",
        "    if False:\n",
        f"{T}::test_r44_a_result_whose_models_were_not_assessed_is_not_established",
        "CORE-015's own condition stops being checked: a result whose models nobody assessed for "
        "applicability is established again"),
    Mutation(
        "B43e", f"{D}::DesignEvaluation.__post_init__",
        "        if eligibility is SelectionEligibility.ELIGIBLE:\n",
        "        if False:\n",
        f"{T}::test_r44_eligible_cannot_be_declared_over_an_unassessed_result",
        "finding 84 restored at its source: ELIGIBLE goes back to being a caller's word with a free-text "
        "reason that never consults the result, which is how a production Pareto front came to rank "
        "candidates the library's own rule calls unestablished"),
    Mutation(
        "B43f", f"{A}::_unassessed_refs",
        "        if item.eligibility is SelectionEligibility.RANKED_WITHOUT_ASSESSMENT\n",
        "        if False\n",
        f"{T}::test_r44_an_archive_records_the_members_it_ranked_without_assessment",
        "the archive stops recording which of its members were ranked without assessment, so the ranking is "
        "published with the statement removed -- and a persisted archive does not carry its evaluations' "
        "labels, so nothing else can say it"),
    Mutation(
        "B43g", f"{A}::ParetoArchive.validate_against",
        "        if _unassessed_refs(items, expected) != self.unassessed:\n",
        "        if False:\n",
        f"{T}::test_r44_an_edited_unassessed_list_is_refused_on_read",
        "REPOINTED while running these mutations: a round trip passes either way, because `build` computes "
        "the same list the payload carries. What sees this rule is an EDITED payload. The statement stops "
        "being recomputed on read, so a stored list of references becomes a claim "
        "nobody verifies -- which this module's own docstring says it must not be"),
    Mutation(
        "B43h", f"{A}",
        "_RANKABLE = (SelectionEligibility.ELIGIBLE, SelectionEligibility.RANKED_WITHOUT_ASSESSMENT)\n",
        "_RANKABLE = (SelectionEligibility.ELIGIBLE,)\n",
        f"{T}::test_r44_an_archive_records_the_members_it_ranked_without_assessment",
        "the other error this fix could make: refusing to rank an unassessed candidate at all, which would "
        "delete the studies that have no validity domain to assess against rather than correct them"),
    Mutation(
        "B43i", f"{S}::evaluate_reference_candidate",
        "        eligibility=SelectionEligibility.RANKED_WITHOUT_ASSESSMENT,\n",
        "        eligibility=SelectionEligibility.ELIGIBLE,\n",
        f"{T}::test_r44_the_reference_study_declares_what_it_did_not_assess",
        "the production study goes back to claiming ELIGIBLE over results that record "
        "validity_not_assessed for every model they name -- the contradiction finding 84 is about, on the "
        "path production actually runs"),
]

_CHANGED_FILES = (Q, D, A, S)


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
    status = run(MUTATIONS, label="BATCH43", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH43_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 43 changed ---", flush=True)
    status |= run(existing, label="BATCH43_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH43_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
