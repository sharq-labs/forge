"""Batch-6 guard mutations (I-01): each new guard removed as if it had never been written, in an ISOLATED copy.

Not in tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core
Freeze V4 round (I-30). The R-67 defects of the batch-1..5 runners -- mutating the shared checkout and
counting any non-zero exit as a kill -- are fixed in ``isolated_mutations``, which this uses.

Run from the repository root, with SCRATCH pointing at a scratch directory::

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch6_mutations

The second half re-runs the existing pinned mutations that target the files this batch changed
(``src/engcore/hybrid_uq/router.py`` and ``src/engcore/hybrid_uq/vocabulary.py``), under the same isolated
runner, against the test file their recorded kill attribution names.
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

ROUTER = "src/engcore/hybrid_uq/router.py"
BATCH6 = "tests/hybrid_uq/test_core_scientific_audit_batch6.py"
CONFORMANCE = "tests/hybrid_uq/test_core_v4_false_confidence_conformance.py"

MUTATIONS = [
    Mutation(
        "B6a", f"{ROUTER}::route_uncertainty",
        "        elif str(local.diagnostics.uniqueness) in UNRESOLVED_UNIQUENESS:\n",
        "        elif False:\n",
        f"{BATCH6}::test_r01_a_rebuild_is_passed_over_when_no_uniqueness_search_ran",
        "R-01: step 3 rebuilds past an unresolved uniqueness search again"),
    Mutation(
        "B6b", f"{ROUTER}::route_uncertainty",
        # I-01 gives R-01 two independent rules -- resolve uniqueness, or withhold the grid -- and the
        # conformance invariant holds if EITHER does. The first run of this mutation removed only the
        # pass-over and SURVIVED against the conformance test, which was correct and worth recording: the
        # canonical search had already made the answer honest. So what has to be mutated to test the
        # invariant is both rules at once, which is what this does. B6a and B6d kill each rule separately.
        "    if searching is None and bool(canonical_uniqueness_search) and a_grid_route_is_in_play and local_inputs:\n"
        "        searching = MultistartPolicy()\n",
        "    if False:\n"
        "        searching = MultistartPolicy()\n",
        f"{CONFORMANCE}::test_r01_a_grid_rebuilt_without_a_uniqueness_search_never_claims_one_mode",
        "R-01: with the canonical search gone the pass-over alone keeps the invariant, so this must SURVIVE; "
        "B6b2 removes both rules and must kill it", expect="SURVIVED"),
    Mutation(
        "B6b2", f"{ROUTER}::route_uncertainty",
        "    if searching is None and bool(canonical_uniqueness_search) and a_grid_route_is_in_play and local_inputs:\n"
        "        searching = MultistartPolicy()\n",
        "    if False:\n"
        "        searching = MultistartPolicy()\n",
        f"{CONFORMANCE}::test_r01_a_grid_rebuilt_without_a_uniqueness_search_never_claims_one_mode",
        "R-01: BOTH rules removed at once -- the router neither resolves uniqueness nor withholds the grid, "
        "which is exactly the audited behaviour, and the conformance mass floor is the only thing left",
        also=((f"{ROUTER}::route_uncertainty",
               "        elif str(local.diagnostics.uniqueness) in UNRESOLVED_UNIQUENESS:\n",
               "        elif False:\n"),)),
    Mutation(
        "B6c", f"{ROUTER}::HybridUQResult._require_one_truth",
        "                if word in UNRESOLVED_UNIQUENESS:\n",
        "                if False:\n",
        f"{BATCH6}::test_r01_a_rebuilt_grid_record_with_an_unresolved_search_is_refused_on_read",
        "R-01: a hand-built rebuilt-grid record with an unresolved search reads back again"),
    Mutation(
        "B6d", f"{ROUTER}::route_uncertainty",
        "    if searching is None and bool(canonical_uniqueness_search) and a_grid_route_is_in_play and local_inputs:\n",
        "    if False:\n",
        f"{BATCH6}::test_r01_the_router_runs_the_canonical_search_when_a_grid_route_needs_one",
        "I-01 stage 2: the router stops resolving uniqueness itself for a grid route"),
    Mutation(
        "B6e", f"{ROUTER}::route_uncertainty",
        "                problem = None if isinstance(basis, str) else basis\n",
        "                problem = None\n",
        f"{BATCH6}::test_r06_a_supplied_grid_that_misses_a_found_mode_is_passed_over",
        "R-06: the uniqueness basis is measured and then ignored"),
    Mutation(
        "B6f", f"{ROUTER}::_grid_uniqueness_basis",
        "        if outside:\n",
        "        if False:\n",
        f"{BATCH6}::test_r06_a_supplied_grid_that_misses_a_found_mode_is_passed_over",
        "R-06: a found mode outside the grid's box stops counting"),
    Mutation(
        "B6g", f"{ROUTER}::_grid_uniqueness_basis",
        "    if _grid_spans_the_declared_bounds(grid, calibration):\n",
        "    if True:\n",
        f"{BATCH6}::test_r06_a_supplied_grid_with_no_uniqueness_basis_at_all_is_passed_over",
        "R-06: every grid claims the bounds-spanning basis, whatever its box"),
    Mutation(
        "B6h", f"{ROUTER}::_grid_spans_the_declared_bounds",
        "        if not (float(np.min(axis)) <= lower + tolerance and float(np.max(axis)) >= upper - tolerance):\n",
        "        if False:\n",
        f"{BATCH6}::test_r06_a_supplied_grid_with_no_uniqueness_basis_at_all_is_passed_over",
        "R-06: the bounds-spanning test stops looking at the box"),
    Mutation(
        "B6i", f"{ROUTER}::_grid_uniqueness_basis",
        "    if word in UNRESOLVED_UNIQUENESS:\n",
        "    if False:\n",
        f"{BATCH6}::test_r06_a_supplied_grid_backed_only_by_a_below_minimum_search_is_passed_over",
        "R-06: a below-minimum search counts as a uniqueness basis for a supplied grid again"),
]

#: The pinned mutations that target the files this batch changed, re-run under the isolated runner.
_CHANGED_FILES = ("src/engcore/hybrid_uq/router.py", "src/engcore/hybrid_uq/vocabulary.py")


def _existing():
    out = []
    for identifier, spec, old, new, attribution in M.MUTATIONS:
        if not any(spec.partition("::")[0] == changed for changed in _CHANGED_FILES):
            continue
        files = [word for word in attribution.replace(",", " ").split() if word.startswith("tests/")]
        if not files:
            continue
        out.append(Mutation(identifier, spec, old, new, files[0], f"pinned: {attribution}"))
    return out


def main() -> int:
    scratch = scratch_from_environment()
    status = run(MUTATIONS, label="BATCH6", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH6_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 6 changed ---", flush=True)
    status |= run(existing, label="BATCH6_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH6_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
