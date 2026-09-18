"""Batch-34 guard mutations (I-14 part B, R-28: the identifiability thresholds): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch34_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

ID = "src/engcore/hybrid_uq/identifiability.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch34.py"

MUTATIONS = [
    Mutation(
        "B34a", f"{ID}::assess_routed_identifiability",
        "    tightened = _require_declared_or_tighter_thresholds(\n",
        "    tightened = dict(\n",
        f"{T}::test_r28_a_looser_rule_is_refused_on_the_local_route",
        "R-28 restored exactly: the guard the grid branch calls is not called on the local branch, so the "
        "weak-identification case -- canonically NOT_IDENTIFIABLE at widths [8.553, 1.842] and correlation "
        "0.9999985 -- reads WEAKLY_IDENTIFIABLE under (0.99999, 1e300, 1e9) and PARAMETERS_IDENTIFIABLE "
        "under a correlation threshold of 0.9999999999999. A verdict bought by argument"),
    Mutation(
        "B34b", f"{ID}::assess_routed_identifiability",
        "        why=(f\"{why}{_tightened_note(tightened)} \"\n",
        "        why=(f\"{why} \"\n",
        f"{T}::test_r28_a_tightened_local_verdict_says_the_rule_was_moved",
        "a STRICTER verdict stops saying the rule was moved. The grid path appends this sentence in these "
        "words, and a reader comparing two reports has no other way to know which rule each was reached "
        "under -- the direction is the harmless one and the silence is not"),
    Mutation(
        "B34c", f"{ID}::_tightened_note",
        "    if not tightened:\n        return \"\"\n",
        "    if True:\n        return \"\"\n",
        f"{T}::test_r28_a_tightened_local_verdict_says_the_rule_was_moved",
        "the note is computed and then never produced, which is the same silence by a different route -- and "
        "the read-back re-derivation agrees with it, so the record is consistent about saying nothing"),
    Mutation(
        "B34d", f"{ID}::RoutedIdentifiability.__post_init__",
        "            if not math.isfinite(value) or value <= 0.0 or value > float(canonical):\n",
        "            if False:\n",
        f"{T}::test_r28_a_record_carrying_a_looser_rule_is_refused_at_construction",
        "the record guard goes, and the record is where a bought verdict SURVIVES: the re-derivation below "
        "makes it self-consistent, which is exactly why the audited forgery read back -- its numbers and its "
        "moved rule agreed with each other and neither was compared with the declared rule"),
    Mutation(
        "B34e", f"{ID}::RoutedIdentifiability.__post_init__",
        "            if key in CANONICAL_IDENTIFIABILITY_THRESHOLDS and float(getattr(r, key)) != float(declared)\n",
        "            if False\n",
        f"{T}::test_r28_a_tightened_local_verdict_says_the_rule_was_moved",
        "the read-back stops re-deriving the tightened note from the report's own thresholds, so a record may "
        "claim a moved rule it does not carry, or carry one it does not claim. The note is only worth having "
        "if it is checked against the numbers it describes"),
    Mutation(
        "B34f", f"{ID}::assess_routed_identifiability",
        "        minimum_effective_points=declared[\"minimum_effective_points\"],\n",
        "        minimum_effective_points=1.0e-300,\n",
        f"{T}::test_r28_a_looser_rule_is_refused_on_the_local_route",
        "the no-op argument is quietly loosened instead. A local Gaussian has no effective-point count, so "
        "the value must be the DECLARED one -- passing anything else makes the call a way of getting the "
        "guard to pass rather than a way of running it",
        expect="SURVIVED"),
]

_CHANGED_FILES = (ID,)


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
    status = run(MUTATIONS, label="BATCH34", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH34_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the file batch 34 changed ---", flush=True)
    status |= run(existing, label="BATCH34_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH34_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
