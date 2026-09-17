"""Batch-38 guard mutations (I-14 part F, R-27's finding 22): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch38_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

RO = "src/engcore/hybrid_uq/router.py"
ID = "src/engcore/hybrid_uq/identifiability.py"
LG = "src/engcore/hybrid_uq/local_gaussian.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch38.py"

MUTATIONS = [
    Mutation(
        "B38a", f"{RO}::HybridUQResult._require_one_truth",
        "                if misfit:\n",
        "                if False:\n",
        f"{T}::test_r27f_a_rebuilt_record_carrying_a_misfit_posterior_is_refused",
        "finding 22's third claim restored: a GRID_REBUILT record reads back SUPPORTED carrying a local "
        "posterior whose only reason is MODEL_MISFIT_BEYOND_DECLARED_NOISE. The router passes that rebuild "
        "over on the write side, so the record was never produced by it, and the misfit statement -- the "
        "declared noise does not explain the residuals -- is dropped in silence"),
    Mutation(
        "B38b", f"{RO}::HybridUQResult._require_one_truth",
        "                if structural:\n",
        "                if False:\n",
        f"{T}::test_r27f_a_rebuilt_record_carrying_a_structurally_refused_posterior_is_refused",
        "the other half of the write rule: a box designed from a posterior that has no usable covariance at "
        "all (NUMERICALLY_SINGULAR_JACOBIAN) reads back as a verified grid"),
    Mutation(
        "B38c", f"{RO}::_considered_problems",
        "    if not rows:\n",
        "    if False:\n",
        f"{T}::test_r27f_a_refused_record_with_an_empty_ledger_is_refused_too",
        "finding 22's fifth claim, the bare case: `considered: []` reads back, so the record's account of how "
        "its decision was reached can simply be deleted. REPOINTED while running these mutations: on a grid "
        "record an empty ledger has no USED row either, so the used-route count already caught it. A REFUSED "
        "record is the case only this branch sees, because a refusal carries no used route at all"),
    Mutation(
        "B38d", f"{RO}::_considered_problems",
        "    if len(used) != 1:\n",
        "    if False:\n",
        f"{T}::test_r27f_a_ledger_that_says_the_used_route_was_passed_over_is_refused",
        "the audited ledger forgery: the one USED row is edited to PASSED_OVER for a misfit and the record "
        "still reports GRID_AS_SUPPLIED SUPPORTED -- the ledger says the route was not used and the "
        "decision says it was"),
    Mutation(
        "B38e", f"{RO}::_considered_problems",
        "    elif used[0].get(\"route\") != expected:\n",
        "    elif False:\n",
        f"{T}::test_r27f_a_ledger_naming_another_used_route_is_refused",
        "the ledger names a used route and nothing ties it to the decision the record reports, so a grid "
        "record can say the local route was the one used"),
    Mutation(
        "B38f", f"{RO}::_considered_problems",
        "        if row[\"route\"] not in _LEDGER_ROUTES:\n",
        "        if False:\n",
        f"{T}::test_r27f_each_half_of_the_ledger_vocabulary_is_checked_on_its_own",
        "a row may name any route at all. Caught by the split reproduction: the preregistered one edits a "
        "row's route AND its outcome together, so either check alone kept it refused"),
    Mutation(
        "B38g", f"{RO}::_considered_problems",
        "        if row[\"outcome\"] not in _LEDGER_OUTCOMES:\n",
        "        if False:\n",
        f"{T}::test_r27f_each_half_of_the_ledger_vocabulary_is_checked_on_its_own",
        "a row may report any outcome at all, so 'USED' is not the only word that can claim a route"),
    Mutation(
        "B38h", f"{RO}::_considered_problems",
        "        if extra or \"route\" not in row or \"outcome\" not in row:\n",
        "        if False:\n",
        f"{T}::test_r27f_each_half_of_the_ledger_vocabulary_is_checked_on_its_own",
        "a row may carry any key, so anything uncommitted rides along in the ledger -- the closed-key-set "
        "rule HUQ-12 already applies to the grid summary"),
    Mutation(
        "B38i", f"{RO}::HybridUQResult._require_one_truth",
        "        problems.extend(_considered_problems(decision, self.claim, self.considered))\n",
        "        pass\n",
        f"{T}::test_r27f_an_empty_considered_ledger_is_refused",
        "the rule exists and read-back stops calling it: the shape this round keeps finding, a check written "
        "and not reached"),
    Mutation(
        "B38j", f"{ID}::_grid_diagnostic_problems",
        "    if not math.isfinite(ess) or ess < 1.0 or (points is not None and ess > float(points)):\n",
        "    if False:\n",
        f"{T}::test_r27f_an_effective_sample_size_above_the_point_count_is_refused",
        "an effective sample size is a count of nodes and may exceed the node count the summary commits to, "
        "or be NaN, which makes every comparison below it vacuous"),
    Mutation(
        "B38k", f"{ID}::_grid_diagnostic_problems",
        "    if not math.isfinite(occupied) or not 0.0 < occupied <= 1.0:\n",
        "    if False:\n",
        f"{T}::test_r27f_an_occupied_support_fraction_outside_its_range_is_refused",
        "an occupied support fraction of 1.5 reads back: a fraction of a non-empty support outside (0, 1] "
        "is not a measurement of anything"),
    Mutation(
        "B38l", f"{ID}::_grid_diagnostic_problems",
        "    if len(spacing) != len(names):\n",
        "    if False:\n",
        f"{T}::test_r27f_a_spacing_vector_of_the_wrong_length_is_refused",
        "one spacing ratio for two axes reads back, so the worst-axis maximum below is taken over an "
        "arbitrary subset of the grid's directions"),
    Mutation(
        "B38m", f"{ID}::_grid_diagnostic_problems",
        "    if math.isfinite(ess) and ess < minimum and worst >= 1.0:\n",
        "    if False:\n",
        f"{T}::test_r27f_diagnostics_v1_would_have_refused_are_refused",
        "finding 22's fourth claim restored exactly: effective sample size 1.5 with a step 50x the "
        "posterior's own standard deviation reads back SUPPORTED, and that is the grid V1 refuses as "
        "GRID_TOO_COARSE_FOR_INFERENCE -- every width it reports is quantisation"),
    Mutation(
        "B38n", f"{ID}::_grid_diagnostic_problems",
        "    if math.isfinite(ess) and ess < minimum and worst >= 1.0:\n",
        "    if math.isfinite(ess) and ess < minimum or worst >= 1.0:\n",
        f"{T}::test_r27f_a_broad_posterior_on_a_fine_grid_is_not_what_the_v1_rule_refuses",
        "the AND becomes an OR, which refuses the sharply informative posterior on a correctly sized grid "
        "that V1 deliberately accepts. The control for the rule above: both halves are the rule"),
    Mutation(
        "B38o", f"{RO}::HybridUQResult._require_one_truth",
        "                    problems.extend(_grid_diagnostic_problems(ident.report, points))\n",
        "                    pass\n",
        f"{T}::test_r27f_diagnostics_v1_would_have_refused_are_refused",
        "the diagnostics rule exists and read-back stops calling it"),
    Mutation(
        "B38p", f"{ID}::grid_record_variance_shrink_window",
        "    return min(factors) if factors else math.inf\n",
        "    return math.inf\n",
        f"{T}::test_r27f_the_undetectable_shrink_window_is_stated_as_a_number",
        "the stated limit becomes 'no limit', which is the overclaim this batch removed from the docstring "
        "written as a number instead of a sentence"),
    Mutation(
        "B38q", f"{LG}::_refused",
        "        # forgery needs a refused posterior that round-trips.\n"
        "        observation_content_digest=observation_set_content_digest(observations),\n",
        "        observation_content_digest=\"\",\n",
        f"{T}::test_r27f_a_posterior_the_route_refused_early_reads_back",
        "the defect found while writing this batch's reproductions: a posterior refused before any "
        "measurement serializes as a `/3` record with an empty observation content digest, and batch 36's "
        "rule requires one -- so the router returns a record `from_dict` refuses"),
]

_CHANGED_FILES = (RO, ID, LG)


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
    status = run(MUTATIONS, label="BATCH38", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH38_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 38 changed ---", flush=True)
    status |= run(existing, label="BATCH38_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH38_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
