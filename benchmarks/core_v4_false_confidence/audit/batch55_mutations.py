"""Batch-55 guard mutations (I-30, R-66/R-67/R-68): each new guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``. This batch is the one that folds the round's
563 guard mutations into `tests/mutation_population_v4.py`, inside the area the certificate pins, and
writes the runner in which a kill is the ONE named test failing -- so these mutations are about the
guards that make that evidence evidence.

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch55_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

C = "tools/certification/core_certificate.py"
P = "tools/certification/mutation_population.py"
R = "tools/certification/mutation_v4_runner.py"
T = "tests/test_core_scientific_audit_batch55.py"
V = "tests/test_mutation_population_v4.py"

MUTATIONS = [
    Mutation(
        "B55a", f"{R}::verdict_from_junit",
        "        if _nodeid_of(case) != wanted:\n            continue\n",
        "        if False:\n            continue\n",
        f"{T}::test_r67_a_kill_requires_the_named_target_test_to_fail",
        "finding 97 restored: the FIRST reported case decides the verdict whatever its nodeid, so a "
        "failure in another test is credited to the guard this mutation names"),
    Mutation(
        "B55b", f"{R}::verdict_from_junit",
        "        if case.find(\"failure\") is not None:\n",
        "        if case.find(\"failure\") is not None or case.find(\"error\") is not None:\n",
        f"{T}::test_r67_a_kill_requires_the_named_target_test_to_fail",
        "the audited rule, in the one place it still could hide: a target test that RAISED outside "
        "its own body -- a fixture, a collection error the mutation caused -- reads as the guard "
        "firing, which is the vacuous kill. A string-literal edit was tried first and the harness "
        "rightly reported MUTATION CHANGED NO CODE"),
    Mutation(
        "B55c", f"{R}::_nodeid_of",
        "    return f\"{path}::{case.get('name') or ''}\"\n",
        "    return case.get(\"name\") or \"\"\n",
        f"{T}::test_r67_a_kill_requires_the_named_target_test_to_fail",
        "the nodeid drops the FILE it came from, so it never equals the entry's nodeid and every "
        "verdict becomes NOT_COLLECTED -- a round that reports nothing while looking careful"),
    Mutation(
        "B55d", f"{R}::require_an_isolated_tree",
        "    if work == root or root in work.parents:\n",
        "    if False:\n",
        f"{T}::test_r67_the_runner_refuses_to_mutate_the_repository_itself",
        "finding 97's other half: the round may mutate the checkout in place again, so an interrupted "
        "run leaves a mutated source tree behind and every later measurement is of the wrong bytes"),
    Mutation(
        "B55e", f"{C}::harness_pinning_problems",
        "    missing = [name for name in harness_import_closure(root) if name not in pinned]\n",
        "    missing = []\n",
        f"{T}::test_r68_a_scope_whose_harness_area_misses_an_imported_helper_is_refused",
        "finding 93 restored: a scope that pins a suite and not the module it imports is accepted, "
        "which is how hybrid_synthetic.py was read by ten certified targets and measured by nothing"),
    Mutation(
        "B55f", f"{C}::build_manifest",
        "    if pinning:\n        raise CertificationError(\"; \".join(pinning))\n",
        "    if False:\n        raise CertificationError(\"; \".join(pinning))\n",
        f"{V}::test_a_manifest_is_refused_over_a_harness_area_that_misses_an_imported_helper",
        "the derived check becomes advisory: a manifest is WRITTEN over an area that does not cover "
        "what its suites read, so the certificate says it measured them"),
    Mutation(
        "B55g", f"{C}::harness_import_closure",
        "        seeds.update(entry[4].split(\"::\")[0] for entry in namespace.get(\"POPULATION_V4\", ()))\n",
        "        pass\n",
        f"{V}::test_the_closure_reaches_every_suite_the_population_names",
        "the closure stops being seeded from the population, so the 68 suites a V4 kill is a statement "
        "about are outside it again and only the older TARGETS are covered"),
    Mutation(
        "B55h", f"{P}::v4_population",
        "    payload = [[entry[0], entry[1], entry[2], entry[3], entry[4], entry[5], entry[6],\n"
        "                [list(edit) for edit in entry[7]], entry[8]] for entry in entries]\n",
        "    payload = [[entry[0]] for entry in entries]\n",
        f"{V}::test_the_definitions_digest_covers_the_bodies_and_not_only_the_ids",
        "finding 91's sharper half: the definitions digest is taken over the ids, so the same ids with "
        "a rewritten mutation, target test or expected verdict are the same population"),
    Mutation(
        "B55i", f"{P}::v4_log_problems",
        "        if mid in wanted and found[:1] != [declared.get(mid)]\n",
        "        if False\n",
        f"{T}::test_r66_a_shard_transcript_is_read_for_the_verdict_it_names",
        "a transcript in which an entry reports NOT_A_TEST_FAILURE is accepted as a completed shard, "
        "which is the tally being trusted over the lines it is supposed to summarize"),
    Mutation(
        "B55j", f"{P}::v4_log_problems",
        "    if not control_green or control_red:\n",
        "    if False:\n",
        f"{T}::test_r66_a_shard_transcript_is_read_for_the_verdict_it_names",
        "a round with no green unmutated control is accepted, and every kill in it could be the tree "
        "being broken rather than the guard firing"),
    Mutation(
        "B55k", f"{P}::v4_entries",
        "        if not isinstance(entry, tuple) or len(entry) != 9:\n",
        "        if False:\n",
        f"{V}::test_a_population_whose_entries_are_the_wrong_shape_is_refused",
        "the population is read without checking its shape, so an entry missing its target test or "
        "its expectation is folded in and the runner decides what to do about it at run time"),
]

_CHANGED_FILES = (C, P, R)


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
    status = run(MUTATIONS, label="BATCH55", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH55_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 55 changed ---", flush=True)
    status |= run(existing, label="BATCH55_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH55_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
