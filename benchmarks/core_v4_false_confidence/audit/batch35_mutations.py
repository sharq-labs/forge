"""Batch-35 guard mutations (I-14 part C, R-22 claims (b), (c) and (d)): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch35_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

LG = "src/engcore/hybrid_uq/local_gaussian.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch35.py"

MUTATIONS = [
    Mutation(
        "B35a", f"{LG}::_require_reasons_follow_measurements",
        "        if entries and policy_keys != set(_MULTISTART_POLICY_KEYS):\n",
        "        if False:\n",
        f"{T}::test_r22c_stripping_the_policy_no_longer_buys_a_supported_reading",
        "R-22(c) restored exactly: with no policy key at all the record counts as pre-policy, so the "
        "canonical-span and separation-radius checks stop running, and a genuinely DOWNGRADED narrow search "
        "reads back ACCEPTED, claim SUPPORTED, reasons []. The seven keys the forger removes are the ones "
        "that make two other checks possible"),
    Mutation(
        "B35b", f"{LG}::_require_reasons_follow_measurements",
        "        if entries and policy_keys != set(_MULTISTART_POLICY_KEYS):\n",
        "        if entries and policy_keys and policy_keys != set(_MULTISTART_POLICY_KEYS):\n",
        f"{T}::test_r22c_stripping_the_policy_no_longer_buys_a_supported_reading",
        "the rule keeps only the PARTIAL case, which was already refused thirty lines up, and loses the "
        "EMPTY one, which is the forgery. A stricter-looking condition that excludes exactly the case it was "
        "written for"),
    Mutation(
        "B35c", f"{LG}::_require_reasons_follow_measurements",
        "        if math.isnan(tail_ratio) and not (tail_skipped or d.near_bound or d.at_bound):\n",
        "        if False:\n",
        f"{T}::test_r22d_a_tail_ratio_that_no_probe_produced_is_refused",
        "R-22(d) restored exactly: the sentence 'a tail rise ratio is finite, or NaN when no tail probe was "
        "evaluated' goes back to being half-enforced, and a SUPPORTED record whose tail was never measured "
        "reads back with no reasons at all"),
    Mutation(
        "B35d", f"{LG}::_require_reasons_follow_measurements",
        "        if math.isnan(tail_ratio) and not (tail_skipped or d.near_bound or d.at_bound):\n",
        "        if math.isnan(tail_ratio):\n",
        f"{T}::test_r22d_a_genuine_record_with_no_tail_probe_still_reads",
        "the disjunction goes and every NaN ratio is refused, including the route's OWN records: a bound "
        "reached is WHY a probe is skipped, so a rule that refuses the reason refuses the legitimate case. "
        "The direction a correctness fix most easily overshoots into. The control was repointed while "
        "running: it first used a bound of 2.0, whose genuine ratio is FINITE, so refusing every NaN did not "
        "touch it. A bound of 1.0 evaluates no probe at all and writes NaN with near_bound naming the "
        "parameter"),
    Mutation(
        "B35e", f"{LG}::_require_reasons_follow_measurements",
        "                    elif (ratio > MULTISTART_MASS_FLOOR) != (classification == \"SECOND_MODE\"):\n",
        "                    elif False:\n",
        f"{T}::test_r22b_relabelling_a_genuine_second_mode_is_already_refused",
        "the rule this batch found ALREADY CLOSED, removed: a genuine SECOND_MODE at a mass ratio of 1361.5 "
        "against a floor of 0.05 can be relabelled WORSE_LOCAL_OPTIMUM again. Recorded as a mutation of this "
        "batch even though the code is an earlier batch's, because this batch is where the closure is pinned "
        "-- an earlier round's fix with no guard of its own is a fix nobody is watching. EXPECTED SURVIVED, "
        "and the survival is the finding: with the mass rule gone the relabel is still refused, by the "
        "UNIQUENESS re-derivation, which derives a different verdict from the edited classes than the record "
        "carries. So (b) is closed by two independent rules and the mass one merely fires first -- which is "
        "a better answer than this batch's preregistration claimed, and is recorded in amendment 1",
        expect="SURVIVED"),
]

_CHANGED_FILES = (LG,)


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
    status = run(MUTATIONS, label="BATCH35", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH35_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the file batch 35 changed ---", flush=True)
    status |= run(existing, label="BATCH35_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH35_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
