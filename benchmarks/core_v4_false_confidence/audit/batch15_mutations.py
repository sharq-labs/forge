"""Batch-15 guard mutations (I-19, the declarations a problem makes are read): each new guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch15_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

IR = "src/engcore/scientific/ir/problem.py"
RQ = "src/engcore/scientific/results/requirements.py"
TR = "src/engcore/execution/trusted.py"
EV = "src/engcore/mcp/evidence.py"
DOM = "src/engcore/domains/__init__.py"
DCV = "src/engcore/domains/electrical/dc/validation.py"
CSV = "src/engcore/domains/kinetics/cstr/validation.py"
DCS = "src/engcore/domains/electrical/dc/solver.py"
CSS = "src/engcore/domains/kinetics/cstr/solver.py"
T = "tests/test_core_scientific_audit_batch15.py"

MUTATIONS = [
    # --- strict parsing ---
    Mutation(
        "B15a", f"{IR}::_require_only_known_keys",
        "    if unknown:\n",
        "    if False:\n",
        f"{T}::test_r72_a_misspelled_requirements_key_is_refused",
        "R-72, the audited case: a misspelled `validation_requirements` key is dropped again, so the record "
        "round-trips to a problem with no requirements and still reads as though it stated them"),
    Mutation(
        "B15b", f"{IR}::ScientificProblem.from_dict",
        '        _require_only_known_keys(payload, cls.READ_KEYS, record="scientific problem")\n',
        "",
        f"{T}::test_r72_a_misspelled_uncertainty_key_is_refused",
        "R-72: the problem reader stops checking its own key set, which is where the drop happened"),
    Mutation(
        "B15c", f"{IR}::UncertaintySpecification.from_dict",
        '        _require_only_known_keys(payload, cls.READ_KEYS, record="uncertainty specification")\n',
        "",
        f"{T}::test_r72_an_unknown_key_inside_the_uncertainty_specification_is_refused",
        "R-72: a misspelling INSIDE the specification -- `confidence_levl` -- is dropped again, so the "
        "demand arrives without the level it was made at"),
    Mutation(
        "B15d", f"{IR}::ScientificProblem.from_dict",
        '                if "uncertainty" in payload\n',
        '                if payload.get("uncertainty")\n',
        f"{T}::test_r72_a_present_but_empty_uncertainty_key_is_refused",
        "R-72: a present-but-empty `uncertainty` value is read as `no uncertainty demanded` again, which is "
        "a declaration the reader invents"),
    # --- the registry ---
    Mutation(
        "B15e", f"{RQ}::unsatisfiable_validation_requirements",
        "            if name not in registered\n",
        "            if False\n",
        f"{T}::test_r72_a_requirement_naming_no_check_kind_is_unsatisfiable",
        "R-72: `numerically_convergd` stops being reported as a requirement no result can ever satisfy"),
    Mutation(
        "B15f", DOM,
        'register_validation_check_kinds(\n    "dimensional_consistency",\n    "linear_system_residual",\n'
        '    "boundary_conditions_held",\n    "field_finite",\n    "amplitude_decay",\n)\n',
        "",
        f"{T}::test_r72_the_kinds_the_three_declaring_problems_name_are_all_registered",
        "the SHA-pinned conduction1d tree's kinds stop being declared on its behalf, so the frozen slab "
        "problem's own five requirements read as naming nothing"),
    Mutation(
        "B15g", DCV,
        'register_validation_check_kinds(\n    "dimensional_consistency",\n    "linear_system_residual",\n'
        '    "kirchhoff_current_law",\n',
        "register_validation_check_kinds(\n",
        f"{T}::test_r72_the_kinds_the_three_declaring_problems_name_are_all_registered",
        "three of the DC domain's six emitted kinds stop being registered, so its problem's requirements "
        "read as naming nothing"),
    Mutation(
        "B15h", CSV,
        'register_validation_check_kinds(\n    "dimensional_consistency",\n    "integration_reported_success",\n',
        "register_validation_check_kinds(\n",
        f"{T}::test_r72_the_kinds_the_three_declaring_problems_name_are_all_registered",
        "two of the CSTR domain's emitted kinds stop being registered"),
    # --- the requirement rules ---
    Mutation(
        "B15i", f"{RQ}::unmet_validation_requirements",
        '        if getattr(check, "outcome", None) is ValidationOutcome.PASS\n',
        "        if True\n",
        f"{T}::test_r72_a_declared_check_that_did_not_pass_is_unmet",
        "R-72: a check of the right name that did NOT pass satisfies the requirement again -- a NOT_RUN "
        "check says the opposite of what the declaration promises"),
    Mutation(
        "B15j", f"{RQ}::unmet_uncertainty_requirements",
        "            and UncertaintyKind(record.kind) is UncertaintyKind.UNKNOWN\n",
        "            and False\n",
        f"{T}::test_r72_a_quantified_demand_is_unmet_by_an_unknown_record",
        "R-72: a demand for QUANTIFIED uncertainty is satisfied by the record's own word for `not "
        "evaluated`"),
    Mutation(
        "B15k", f"{RQ}::unmet_uncertainty_requirements",
        "        if spec.confidence_level is not None and not _same_confidence_level(\n",
        "        if False and not _same_confidence_level(\n",
        f"{T}::test_r72_a_demanded_confidence_level_is_the_one_the_record_must_declare",
        "R-72: an interval at 68 % satisfies a demand for 95 % again"),
    Mutation(
        "B15l", f"{RQ}::_same_confidence_level",
        "    if declared is None:\n        return False\n",
        "    if declared is None:\n        return True\n",
        f"{T}::test_r72_a_record_that_declares_no_confidence_level_does_not_satisfy_a_demand_for_one",
        "a record that declares no coverage at all satisfies a demand for a named one"),
    Mutation(
        "B15m", f"{RQ}::unmet_uncertainty_requirements",
        "        if produced and name not in produced:\n",
        "        if False:\n",
        f"{T}::test_r72_a_metric_the_problem_does_not_carry_can_never_be_satisfied",
        "a demand about a name the problem does not carry stops being reported"),
    # --- the checks that carry the verdict ---
    Mutation(
        "B15n", f"{RQ}::requirement_checks",
        "    if unmet:\n",
        "    if False:\n",
        f"{T}::test_r72_what_is_unmet_becomes_a_not_run_check_and_nothing_else_does",
        "R-72: an unmet validation requirement stops becoming a record, so it reaches no reader and no "
        "verdict"),
    Mutation(
        "B15o", f"{RQ}::requirement_checks",
        "    if missing:\n",
        "    if False:\n",
        f"{T}::test_r72_what_is_unmet_becomes_a_not_run_check_and_nothing_else_does",
        "R-72: the same for the uncertainty half"),
    Mutation(
        "B15p", f"{RQ}::merged_requirement_checks",
        '            detail=" | ".join(details),\n',
        "            detail=details[0],\n",
        f"{T}::test_r72_a_report_over_several_problems_carries_one_check_naming_each",
        "a report answering two problems names only the first one's unmet requirement, so the second's "
        "disappears behind a check that looks answered"),
    Mutation(
        "B15q", f"{RQ}::report_with_requirement_checks",
        "    if not checks:\n        return report\n",
        "    return report\n",
        f"{T}::test_r72_a_dc_result_says_so_when_a_declared_check_is_missing",
        "R-72: a producer's result stops carrying its own unmet declaration, so the verdict travels only "
        "with a report somebody remembered to assemble"),
    # --- the two boundaries and the two producers ---
    Mutation(
        "B15r", f"{TR}::TrustedExecutionRecord.trusted",
        "            and not self.unmet_declared_requirements\n",
        "",
        f"{T}::test_r72_the_trusted_runtime_does_not_call_such_a_record_trusted",
        "R-72's audited trusted-runtime case exactly: `validation checks ['dimensional_consistency'] status "
        "pass trusted True` against a problem requiring two other checks"),
    Mutation(
        "B15s", f"{TR}::TrustedExecutionRecord.unmet_declared_requirements",
        "        return unmet_validation_requirements(self.prepared.problem, self.validation)\n",
        "        return ()\n",
        f"{T}::test_r72_the_trusted_runtime_does_not_call_such_a_record_trusted",
        "the trusted record re-derives nothing and answers that every declaration is met"),
    Mutation(
        "B15t", f"{EV}::CredibilityEvidenceReport.from_result",
        "            + requirement_checks(\n"
        "                problem,\n"
        "                validation=result.validation,\n"
        "                uncertainty=dict(result.uncertainty),\n"
        "            )\n",
        "",
        f"{T}::test_r72_the_credibility_boundary_carries_the_unmet_declaration_when_it_is_given_the_problem",
        "R-72: the credibility boundary accepts the problem and reads nothing from it, which is the state "
        "the re-audit found -- `from_result` never saw a problem at all"),
    Mutation(
        "B15u", f"{CSS}::solve_reactor_bundle",
        "        validation=report_with_requirement_checks(\n",
        "        validation=(lambda p, r, **k: r)(\n",
        f"{T}::test_r72_both_editable_domain_result_builders_read_their_problems_declaration",
        "the CSTR runner stops reading its problem's declaration while still looking as though it does"),
]

_CHANGED_FILES = (IR, RQ, TR, EV, DOM, DCV, CSV, DCS, CSS)


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
    status = run(MUTATIONS, label="BATCH15", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH15_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 15 changed ---", flush=True)
    status |= run(existing, label="BATCH15_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH15_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
