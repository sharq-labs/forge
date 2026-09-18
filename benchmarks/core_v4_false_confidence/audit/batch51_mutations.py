"""Batch-51 guard mutations (I-26; R-49, R-53): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch51_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

O = "src/engcore/scientific/oracles.py"
T = "tests/test_core_scientific_audit_batch51.py"

MUTATIONS = [
    Mutation(
        "B51a", f"{O}::OracleEvidenceSet.compare",
        "                not_compared.append(f\"{observation.metric}:not predicted\")\n",
        "                failures.append(f\"{observation.metric}:not predicted\")\n",
        f"{T}::test_r53_an_unpredicted_metric_is_not_run_rather_than_failed",
        "finding 65's first claim restored: a metric the prediction does not carry is a FAILURE again, so "
        "the check is FAIL and derive_verdict reads NOT_SUPPORTED -- evidence against the model built out "
        "of a comparison nobody made"),
    Mutation(
        "B51b", f"{O}::OracleEvidenceSet.compare",
        "        elif incomplete:\n",
        "        elif False:\n",
        f"{T}::test_r53_an_unpredicted_metric_is_not_run_rather_than_failed",
        "an incomplete comparison is reported as a PASS, which is the other way of reading an absence as "
        "evidence -- this time in the model's favour"),
    Mutation(
        "B51c", f"{O}::OracleEvidenceSet.__post_init__",
        "        if len(set(keys)) != len(keys):\n",
        "        if False:\n",
        f"{T}::test_r53_one_metric_at_two_operating_points_is_two_observations",
        "expect=SURVIVED, and recorded as such: relaxing the identity to (metric, conditions) is what lets "
        "a two-point set exist, and REMOVING the uniqueness check altogether leaves that possible. The "
        "rule it replaces is guarded from the other side by the in-tree refusal test, which this mutation "
        "kills -- see B51d",
        expect="SURVIVED"),
    Mutation(
        "B51d", f"{O}::OracleEvidenceSet.__post_init__",
        "        if len(set(keys)) != len(keys):\n",
        "        if False:\n",
        "tests/test_external_oracles.py::test_duplicate_metric_observations_are_refused",
        "the same edit, pointed at the invariant it does threaten: two readings of ONE metric at ONE "
        "operating point stop being refused, so a duplicate or a disagreement enters an evidence set and "
        "nothing says which it was"),
    Mutation(
        "B51e", f"{O}::OracleEvidenceSet.compare",
        "            if observation.conditions:\n",
        "            if False:\n",
        f"{T}::test_r49_a_stated_condition_the_evidence_does_not_describe_stops_the_comparison",
        "finding 59's second gap restored: a stated condition the evidence does not declare is ignored "
        "again, so an observation taken at T only is compared against a prediction stated at P = 50 bar"),
    Mutation(
        "B51f", f"{O}::OracleEvidenceSet.compare",
        "                undeclared_point = True\n",
        "                undeclared_point = False\n",
        f"{T}::test_r49_a_bound_prediction_against_evidence_with_no_point_still_awards_no_level",
        "finding 59's third gap restored: evidence that says nothing about where it was observed earns a "
        "validation level, which is a claim that the model was validated somewhere. REPOINTED while "
        "running these mutations: the preregistered reproduction passes no record either, so the binding "
        "rule withholds the level there too; the case only this rule sees is a BOUND prediction against "
        "condition-less evidence"),
    Mutation(
        "B51g", f"{O}::OracleEvidenceSet._binding_gap",
        "        if predicted_from is None:\n",
        "        if False:\n",
        f"{T}::test_r49_a_level_needs_the_record_the_prediction_came_from",
        "finding 59's first claim restored: a bare mapping of numbers earns a level at whatever operating "
        "point the caller asserts, which is how a prediction computed at 400 K passed at a stated 300 K"),
    Mutation(
        "B51h", f"{O}::OracleEvidenceSet.compare",
        "        if binding_contradiction is not None:\n",
        "        if False:\n",
        f"{T}::test_r49_the_named_record_must_have_been_computed_at_the_stated_point",
        "a named record that was computed somewhere else no longer stops the comparison: it becomes a "
        "PASS with the level withheld, which reports a comparison at a point nothing was computed at"),
]

_CHANGED_FILES = (O,)


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
    status = run(MUTATIONS, label="BATCH51", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH51_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 51 changed ---", flush=True)
    status |= run(existing, label="BATCH51_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH51_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
