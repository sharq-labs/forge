"""Batch-39 guard mutations (I-20 part A, R-46 and finding 87): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch39_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

V = "src/engcore/scientific/results/validation.py"
C = "src/engcore/sria/assurance/critics.py"
T = "tests/test_core_scientific_audit_batch39.py"

MUTATIONS = [
    Mutation(
        "B39a", f"{V}::comparison_met_its_bound",
        "    return abs(residual) <= tolerance\n",
        "    return residual <= tolerance\n",
        f"{T}::test_r46_a_pass_whose_residual_misses_its_bound_from_below_is_refused",
        "R-46 restored exactly: the comparison reads the signed number, so any negative residual meets any "
        "positive bound and the defect this module's docstring describes comes back with a minus sign -- a "
        "PASS with residual -10.0 against tolerance 1e-6 earning numerically_converged"),
    Mutation(
        "B39b", f"{V}::comparison_met_its_bound",
        "    return abs(residual) <= tolerance\n",
        "    return abs(residual) < tolerance\n",
        f"{T}::test_r46_a_zero_tolerance_is_still_a_bound",
        "the bound becomes strict, which refuses exact agreement against a zero tolerance -- the control for "
        "the rule above, and the off-by-one this fix most easily makes",
        expect="KILLED"),
    Mutation(
        "B39c", f"{V}::ValidationCheck.__post_init__",
        "            if self.tolerance < 0.0:\n",
        "            if False:\n",
        f"{T}::test_r46_a_negative_tolerance_is_refused_for_every_outcome",
        "R-46's second construction restored: a negative tolerance is a bound no magnitude can meet, and it "
        "is accepted for every outcome, so the comparison it belongs to says nothing either way"),
    Mutation(
        "B39d", f"{C}::NumericalCritic.assess",
        "                if not ran\n",
        "                if True\n",
        f"{T}::test_r45_a_report_whose_unrun_check_did_not_apply_is_not_a_report_nobody_ran",
        "finding 87 restored: the fixed sentence 'validation was never run' is reported about a report in "
        "which five checks ran and passed and one did not apply"),
    Mutation(
        "B39e", f"{C}::NumericalCritic.assess",
        "                if not ran\n",
        "                if False\n",
        f"{T}::test_r45_a_report_with_no_checks_at_all_still_says_validation_was_never_run",
        "the opposite error: a report with NO checks is described as '0 check(s) ran; 1 did not', which is "
        "the one report the old sentence was true of. The control for the rule above"),
]

_CHANGED_FILES = (V, C)


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
    status = run(MUTATIONS, label="BATCH39", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH39_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 39 changed ---", flush=True)
    status |= run(existing, label="BATCH39_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH39_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
