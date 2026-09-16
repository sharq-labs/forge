"""Batch-9 guard mutations (I-09 part B): each new guard removed, in an ISOLATED copy.

Not in tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core
Freeze V4 round (I-30). The runner is ``isolated_mutations``, which fixes R-67 for these runners.

Run from the repository root, with SCRATCH pointing at a scratch directory::

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch9_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

VALIDATION = "src/engcore/scientific/results/validation.py"
DOMAINS = "src/engcore/domains/__init__.py"
LUMPED = "src/engcore/domains/thermal_models/lumped.py"
T = "tests/test_core_scientific_audit_batch9.py"

MUTATIONS = [
    Mutation(
        "B9a", f"{VALIDATION}::_issuer_gap",
        "    if level is ValidationLevel.ANALYTICALLY_VERIFIED:\n",
        "    if False:\n",
        f"{T}::test_r04_a_hand_written_analytically_verified_check_is_refused",
        "R-04: the level needs no issuer again, which is the audited defect exactly"),
    Mutation(
        "B9b", f"{VALIDATION}::_analytic_issuer_gap",
        "    if len(named) != 1:\n", "    if False:\n",
        f"{T}::test_r04_an_unregistered_reference_is_refused",
        "R-04: an unregistered reference id, or two of them, passes"),
    Mutation(
        "B9c", f"{VALIDATION}::_analytic_issuer_gap",
        '    if expression != declaration.get("expression"):\n', "    if False:\n",
        f"{T}::test_r04_a_closed_form_that_is_not_the_registered_one_is_refused",
        "R-04: the closed form the check names stops having to be the registered one"),
    # The first draft of this file had B9d, B9e and B9f as three mutations of three checks -- the
    # gate name, the version, the values fingerprint. Two SURVIVED, and were right to: all three
    # compared against the gate the REGISTRY names rather than the one the record names, so each was
    # subsumed by the fingerprint comparison. The implementation now makes one comparison, and this
    # is one mutation. What the run bought was the removal of dead code from the guard, which is
    # what a survivor is supposed to buy.
    Mutation(
        "B9d", f"{VALIDATION}::_analytic_issuer_gap",
        "    if records[0] != expected:\n", "    if False:\n",
        f"{T}::test_r04_a_caller_built_threshold_set_is_refused",
        "R-04: any threshold record passes as the awarding gate's declared set -- another gate, "
        "another version of it, or other numbers"),
    Mutation(
        "B9e", f"{VALIDATION}::_analytic_issuer_gap",
        "    if records[0] != expected:\n", "    if False:\n",
        f"{T}::test_r04_a_reference_whose_gate_is_another_domains_is_refused",
        "R-04: the same mutation against the other case the one comparison covers"),
    Mutation(
        "B9f", f"{VALIDATION}::_analytic_issuer_gap",
        "    if len(records) != 1:\n", "    if False:\n",
        f"{T}::test_r04_a_check_with_no_threshold_record_is_refused",
        "R-04: a check that never says which numbers judged it passes"),
    Mutation(
        "B9g", f"{VALIDATION}::_analytic_issuer_gap",
        "    if len(records) != 1:\n", "    if False:\n",
        f"{T}::test_r04_two_threshold_records_are_refused",
        "R-04: two threshold records pass, leaving a reader unable to say which judged the check"),
    Mutation(
        "B9h", f"{LUMPED}::LumpedThermalSolver._reference_check",
        "            establishes=LUMPED_ANALYTIC_REFERENCE_THRESHOLDS.award(\n"
        "                ValidationLevel.ANALYTICALLY_VERIFIED, earned=agrees\n"
        "            ),\n",
        "            establishes=(\n"
        "                ValidationLevel.ANALYTICALLY_VERIFIED if agrees else None\n"
        "            ),\n",
        f"{T}::test_r04_the_production_lumped_check_carries_its_issuer_record",
        "R-04: the production check awards the level beside its gate rather than through it. This "
        "SURVIVES, and the survival is the finding: LUMPED_ANALYTIC_REFERENCE_THRESHOLDS is a module "
        "constant with no caller-facing `thresholds=` argument on LumpedThermalSolver, so there is no "
        "override for `award` to withhold from and the issuer gap (B9i) is what actually enforces the "
        "record. `award` is kept because it is the one place a future thresholds= argument would be "
        "judged, and because every other gate in the repository reads this way -- but it is not "
        "load-bearing here today, and the audit document says so rather than counting it",
        expect="SURVIVED"),
    Mutation(
        "B9i", f"{LUMPED}::LumpedThermalSolver._reference_check",
        "        ) + LUMPED_ANALYTIC_REFERENCE_THRESHOLDS.evidence()\n",
        "        )\n",
        f"{T}::test_r04_the_production_lumped_check_carries_its_issuer_record",
        "R-04: the production check stops recording which numbers it was judged against"),
    Mutation(
        "B9j", f"{VALIDATION}::_issuer_gap",
        '        if any(isinstance(line, str) and line.startswith("oracle:") for line in evidence):\n',
        "        if False:\n",
        "tests/test_external_oracles.py::test_benchmark_and_analytic_oracles_map_to_their_own_levels_only_when_pinned",
        "R-04: a pinned ANALYTIC_REFERENCE oracle is the level's OTHER legitimate issuer, and stops "
        "being one -- the guard that this batch did not narrow the level to one issuer"),
]

_CHANGED_FILES = (VALIDATION, DOMAINS, LUMPED)


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
    status = run(MUTATIONS, label="BATCH9", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH9_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 9 changed ---", flush=True)
    status |= run(existing, label="BATCH9_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH9_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
