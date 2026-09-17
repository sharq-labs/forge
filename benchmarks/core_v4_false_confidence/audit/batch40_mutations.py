"""Batch-40 guard mutations (I-20 part B, R-45): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch40_mutations
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
D = "src/engcore/domains/electrical/dc/validation.py"
P = "src/engcore/domains/electrical/dc/problem.py"
T = "tests/test_core_scientific_audit_batch40.py"

MUTATIONS = [
    Mutation(
        "B40a", f"{V}",
        'REPORT_SCHEMA = schema_string("validation_report", 2)\n',
        'REPORT_SCHEMA = schema_string("validation_report")\n',
        f"{T}::test_r45_the_status_precedence_change_is_named_by_a_version",
        "finding 53 restored: the record whose meaning CORE-013 changed goes back to claiming the version it "
        "had before, which is the whole reason a reader cannot tell an honest older report from an edited one"),
    Mutation(
        "B40b", f"{V}::ValidationReport.from_dict",
        "        if version == LEGACY_REPORT_SCHEMA:\n",
        "        if False:\n",
        f"{T}::test_r45_the_pre_core013_record_reads_back_with_its_status_re_derived",
        "the version is read and then not used: every `/1` record written with a PASS and a NOT_RUN check is "
        "refused again, which is the audited loss -- the whole record, not just its label"),
    Mutation(
        "B40c", f"{V}::_legacy_status",
        "    if ValidationOutcome.WARNING in outcomes:\n        return ValidationOutcome.WARNING\n",
        "    if False:\n        return ValidationOutcome.WARNING\n",
        f"{T}::test_r45_a_legacy_warning_record_reads_back_too",
        "the legacy precedence stops being the legacy precedence, so a stored status it explains is reported "
        "as one no rule ever produced. REPOINTED while running these mutations: the preregistered refusal "
        "reproduction cannot see this rung, because its payload's legacy status is PASS with or without the "
        "WARNING branch. What sees it is a record whose stored status IS 'warning' -- what the older tree "
        "wrote for any report holding a warning beside an unrun check"),
    Mutation(
        "B40d", f"{V}::_legacy_status_read",
        "    if stored == legacy:\n",
        "    if True:\n",
        f"{T}::test_r45_a_legacy_status_that_matches_neither_precedence_is_refused_and_says_so",
        "the opposite error, and the one this fix most easily makes: EVERY `/1` status is dropped, so a "
        "record whose status matches no precedence at all is read as if it were honest"),
    Mutation(
        "B40e", f"{V}::ValidationReport.status",
        "        outcomes = {c.outcome for c in self.checks} - {ValidationOutcome.NOT_APPLICABLE}\n",
        "        outcomes = {c.outcome for c in self.checks}\n",
        f"{T}::test_r45_a_report_of_nothing_but_inapplicable_checks_established_nothing",
        "REPOINTED while running these mutations: for a MIXED report the exclusion is invisible, because the "
        "precedence chain ends in `return PASS` and an unrecognized member falls through it. The case that "
        "sees the rule is a report of nothing but inapplicable checks, which without the exclusion reads "
        "PASS -- a report that established nothing reporting a pass, which is worse than the NOT_RUN "
        "finding 87 named"),
    Mutation(
        "B40f", f"{V}::ValidationCheck.__post_init__",
        "            if ValidationOutcome(self.outcome) is ValidationOutcome.NOT_APPLICABLE and establishes is not None:\n",
        "            if False:\n",
        f"{T}::test_r45_an_inapplicable_check_still_establishes_nothing",
        "a check that did not apply may declare a level, which would rest on the absence of anything to "
        "check -- the same category error as establishing UNVERIFIED, one field over"),
    Mutation(
        "B40g", f"{D}::check_voltage_sources",
        "            outcome=ValidationOutcome.NOT_APPLICABLE,\n"
        '            detail="circuit contains no voltage sources",\n',
        "            outcome=ValidationOutcome.NOT_RUN,\n"
        '            detail="circuit contains no voltage sources",\n',
        f"{T}::test_r45_a_clean_circuit_with_no_voltage_source_reports_pass",
        "the audit's own example restored: the production gate goes back to recording 'this circuit has no "
        "voltage source' as evidence that was not gathered. The distinction is only worth having if the "
        "producers make it"),
    Mutation(
        "B40h", f"{P}::build_dc_problem",
        '            | ({"voltage_source_relation"} if circuit.voltage_sources else set())\n',
        '            | {"voltage_source_relation"}\n',
        f"{T}::test_r45_the_problem_stops_demanding_a_check_its_circuit_cannot_produce",
        "the problem demands a PASSING check its own circuit cannot produce, so the report carries a NOT_RUN "
        "`declared_validation_requirements` and the gate fix above becomes invisible on the production path",
        also=((f"{P}::build_dc_problem",
               '            | ({"resistor_metric_consistency"} if circuit.resistors else set())\n',
               '            | {"resistor_metric_consistency"}\n'),)),
]

_CHANGED_FILES = (V, D, P)


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
    status = run(MUTATIONS, label="BATCH40", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH40_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 40 changed ---", flush=True)
    status |= run(existing, label="BATCH40_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH40_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
