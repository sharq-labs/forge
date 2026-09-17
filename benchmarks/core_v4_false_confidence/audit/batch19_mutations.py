"""Batch-19 guard mutations (I-16, the guard reach ledger): each refusal the verifier makes, removed.

The guards this batch adds are not scientific rules -- they are the rules that keep a REACH CLAIM
checkable. So the mutations remove them one at a time and ask whether anything notices: a verifier whose
refusals nobody exercises is the same defect one level up, which is the whole finding I-16 answers.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Batch 19 is why
that runner copies ``tools`` and ``certification``. Not in tests/mutation_guards.py: that file is
certification-pinned, so the batch guards join it in the Core Freeze V4 round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch19_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

G = "tools/certification/guard_reach.py"
T = "tests/test_guard_reach_ledger.py"

MUTATIONS = [
    # --- the rule that makes the ledger worth having ---
    Mutation(
        "B19a", f"{G}::verify",
        '        if row.get("audit_status") == "FIXED" and status not in ("REACHED", "LATENT"):\n',
        "        if False:\n",
        f"{T}::test_i16_a_fixed_row_that_is_only_a_library_guard_is_refused",
        "the central rule goes: a problem may be recorded FIXED while the rule that fixes it is one no "
        "production path reaches, which is the shape of every one of this round's five findings"),
    # --- a row must be checkable ---
    Mutation(
        "B19b", f"{G}::_test_exists",
        '    path, _, name = reference.partition("::")\n'
        "    file = ROOT / path\n"
        "    if not file.exists():\n"
        "        return False\n"
        '    return not name or f"def {name}(" in file.read_text(encoding="utf-8")\n',
        "    return True\n",
        f"{T}::test_i16_a_row_whose_test_does_not_exist_is_refused",
        "`exercised_by` stops being checked, so a REACHED row can cite a test that was renamed away and "
        "keep claiming production exercises it"),
    Mutation(
        "B19c", f"{G}::verify",
        "        if expected is not None and declared != expected:\n",
        "        if False:\n",
        f"{T}::test_i16_a_row_that_disagrees_with_the_audit_is_refused",
        "the ledger may drift from the audit it is about -- a row could call R-09 library-only and the "
        "audit's own `yes` would never contradict it"),
    Mutation(
        "B19j", f"{G}::verify",
        "        if status not in STATUSES:\n",
        "        if False:\n",
        f"{T}::test_i16_each_refusal_is_exercised[bad-status]",
        "an invented status passes, and every rule keyed on the three words then silently does nothing"),
    Mutation(
        "B19k", f"{G}::verify",
        '        if not str(row.get("why", "")).strip():\n',
        "        if False:\n",
        f"{T}::test_i16_each_refusal_is_exercised[no-why]",
        "a status with no reason is accepted, which is the bare assertion the ledger exists to replace"),
    Mutation(
        "B19l", f"{G}::verify",
        "        if not rule or not (ROOT / rule).exists():\n",
        "        if False:\n",
        f"{T}::test_i16_each_refusal_is_exercised[missing-rule]",
        "a row may name a rule file that does not exist, so a deleted guard keeps its REACHED row"),
    Mutation(
        "B19m", f"{G}::verify",
        '        if status in ("REACHED", "LIBRARY_ONLY") and not (row.get("entry_points") or ()):\n',
        "        if False:\n",
        f"{T}::test_i16_each_refusal_is_exercised[no-entry-point]",
        "REACHED without naming the production entry point that reaches it -- reach by assertion"),
    Mutation(
        "B19n", f"{G}::verify",
        '        if status == "REACHED" and not (row.get("exercised_by") or ()):\n',
        "        if False:\n",
        f"{T}::test_i16_each_refusal_is_exercised[reached-with-no-test]",
        "REACHED without a test that exercises it there, which is what distinguishes this ledger from a "
        "comment"),
    Mutation(
        "B19o", f"{G}::verify",
        '        if status == "LIBRARY_ONLY" and not str(row.get("closed_by", "")).startswith("I-"):\n',
        "        if False:\n",
        f"{T}::test_i16_each_refusal_is_exercised[library-only-with-no-improvement]",
        "a LIBRARY_ONLY finding may name no improvement, so R-21, R-43 and R-58 could sit in the ledger "
        "as observations nobody owns"),
    Mutation(
        "B19p", f"{G}::verify",
        '        if status == "LATENT" and not str(row.get("what_would_create_it", "")).strip():\n',
        "        if False:\n",
        f"{T}::test_i16_each_refusal_is_exercised[latent-with-no-shape]",
        "LATENT becomes the status anything unreached can claim, instead of a statement about a shape that "
        "does not occur yet"),
    Mutation(
        "B19q", f"{G}::verify",
        "            if name not in BYPASS_CHECKS:\n"
        '                findings.append(f"{problem}: names bypass {name!r}, which this checker does not implement")\n',
        "            if False:\n"
        '                findings.append(f"{problem}: names bypass {name!r}, which this checker does not implement")\n',
        f"{T}::test_i16_each_refusal_is_exercised[unknown-bypass]",
        "a row may claim a bypass check that was never written, which is a declared guard that does not "
        "exist -- the inverse of an undeclared guard and just as bad"),
    Mutation(
        "B19r", f"{G}::verify",
        "    if missing:\n",
        "    if False:\n",
        f"{T}::test_i16_each_refusal_is_exercised[undeclared-bypass]",
        "a check this module implements may go undeclared by every row, which is a guard nobody declared -- "
        "the defect this ledger is about"),
    Mutation(
        "B19s", f"{G}::verify",
        '                if not str(reasons.get(entry, "")).strip():\n',
        "                if False:\n",
        f"{T}::test_i16_each_refusal_is_exercised[allow-list-without-a-reason]",
        "an allow-list entry needs no reason, so a path can be exempted from a bypass check with nothing "
        "said about why -- and an allow-list entry IS a hole in a guard"),
    Mutation(
        "B19t", f"{G}::verify",
        "                if not (ROOT / entry).exists():\n",
        "                if False:\n",
        f"{T}::test_i16_each_refusal_is_exercised[allow-list-path-that-does-not-exist]",
        "a stale allow-list entry survives a rename, quietly widening the check's blind spot to a path "
        "nothing occupies -- until something does"),
    Mutation(
        "B19u", f"{G}::verify",
        "    if not rows:\n",
        "    if False:\n",
        f"{T}::test_i16_each_refusal_is_exercised[no-guards]",
        "an empty ledger verifies clean, which is the most comfortable false negative available"),
    # --- the four static bypass checks ---
    Mutation(
        "B19d", f"{G}::raw_posterior_grid_consumers",
        "    return sorted(hits)\n",
        "    return []\n",
        f"{T}::test_i16_an_undeclared_raw_posterior_grid_consumer_fails_the_build",
        "R-02's check reports nothing, so a new production consumer of the frozen posterior_predictive_uq "
        "-- an interval with no goodness of fit, containment, prior uniformity or prediction domain -- "
        "arrives silently"),
    Mutation(
        "B19e", f"{G}::raw_posterior_grid_consumers",
        "        if path in set(allowed):\n",
        "        if path in set():\n",
        f"{T}::test_i16_an_undeclared_raw_posterior_grid_consumer_fails_the_build",
        "the declared allow-list stops being read, so the three legitimate callers read as findings and the "
        "check becomes noise a reader would switch off -- a guard that cries wolf is a guard that goes"),
    Mutation(
        "B19f", f"{G}::assessments_without_record_values",
        '            if "record_values" not in call:\n',
        "            if False:\n",
        f"{T}::test_i16_an_assessment_without_record_values_fails_the_build",
        "R-09's check reports nothing, so a new domain assessment that never considered the operating point "
        "it was made at goes back to producing an empty `evaluated` and the CORE-014 binding compares "
        "nothing"),
    Mutation(
        "B19g", f"{G}::to_check_outside_the_gate",
        '            if "_withhold_level(" in prefix:\n                continue\n',
        "            if True:\n                continue\n",
        f"{T}::test_i16_an_unwrapped_to_check_outside_the_gate_fails_the_build",
        "R-21's check stops distinguishing the wrapped mcp call from an unwrapped one, so the one mitigation "
        "standing between production and an unverified CROSS_SOLVER_VALIDATED can be deleted without a "
        "single test noticing"),
    Mutation(
        "B19h", f"{G}::rebuild_without_multistart",
        '            if "multistart=None" in call.replace(" ", "") or "multistart" not in call:\n',
        "            if False:\n",
        f"{T}::test_i16_a_rebuild_without_a_multistart_fails_the_build",
        "the LATENT check reports nothing, so the day a production path routes a grid it may ask for the "
        "rebuild while declining the uniqueness search -- R-01's shape, arriving unguarded"),
    Mutation(
        "B19i", f"{G}",
        '    "ROUTE_UNCERTAINTY_REBUILD_WITHOUT_MULTISTART",\n)',
        ")",
        f"{T}::test_i16_the_four_bypass_checks_are_implemented_and_all_declared",
        "one of the four checks leaves the declared set, so the ledger's row for it becomes an unknown-bypass "
        "finding instead and the check stops running at all"),
]

#: The files batch 19 changed. `tools/` and `certification/` are new to the mutation population, so the
#: pinned re-run is expected to report NONE -- recorded rather than assumed.
_CHANGED_FILES = (G, "certification/guard_reach_ledger.json")


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
    status = run(MUTATIONS, label="BATCH19", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH19_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 19 changed ---", flush=True)
    status |= run(existing, label="BATCH19_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH19_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
