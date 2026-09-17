"""Batch-46 guard mutations (I-28 part C, R-71's finding 98): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch46_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

A = "src/engcore/inference/admissibility.py"
T = "tests/test_core_scientific_audit_batch46.py"

MUTATIONS = [
    Mutation(
        "B46a", f"{A}::_require_the_source_has_nothing_to_converge",
        "    if result.validation.claims(ValidationLevel.NUMERICALLY_CONVERGED):\n",
        "    if False:\n",
        f"{T}::test_r71_a_source_whose_own_report_claims_convergence_is_refused_at_not_applicable_too",
        "finding 98's first claim restored on the half the audit measured: the source's OWN report claims "
        "NUMERICALLY_CONVERGED and the analytic route admits it, so a numerical result that never "
        "established convergence is relabelled analytic and admitted on the weaker evidence. Pointed at "
        "the record where the convergence state says NOT_APPLICABLE, because the audited fixture is "
        "refused by the state rule as well"),
    Mutation(
        "B46b", f"{A}::_require_the_source_has_nothing_to_converge",
        "    if result.convergence is not ConvergenceState.NOT_APPLICABLE:\n",
        "    if False:\n",
        f"{T}::test_r71_an_analytic_prediction_over_a_converged_source_is_refused_even_without_the_level",
        "a converged iterative solve crosses the analytic route whenever its report simply does not "
        "mention convergence -- which is the easier case to produce than the audited one, because it "
        "needs no false claim, only a silent report"),
    Mutation(
        "B46c", f"{A}::AdmissibleAnalyticPrediction.__post_init__",
        "        if not self.source_result.validation.claims(ValidationLevel.DIMENSIONALLY_VALID):\n",
        "        if False:\n",
        f"{T}::test_r71_the_dimensional_level_has_to_be_in_the_sources_own_report",
        "the dimensional evidence goes back to living in a document handed over beside the record: the "
        "source's own report says the dimensions were never checked, and the caller's attached report "
        "carries the level instead"),
    Mutation(
        "B46d", f"{A}::AdmissibleNumericalPrediction.__post_init__",
        "        if self.sequence_validation == self.source_result.validation:\n",
        "        if False:\n",
        f"{T}::test_r71_the_sources_own_report_is_refused_even_when_it_names_two_members",
        "finding 98's second claim restored: the single solve certifies its own numerical adequacy, which "
        "is the one thing this boundary exists to refuse. Pointed at a source report that would satisfy "
        "the member count, because the audited fixture is refused by that rule too"),
    Mutation(
        "B46e", A,
        "_SEQUENCE_MEMBERS = 2\n",
        "_SEQUENCE_MEMBERS = 1\n",
        f"{T}::test_r71_a_sequence_report_names_at_least_two_members",
        "one member is a single solve, so a 'sequence' report naming one run is accepted as sequence-level "
        "evidence -- the threshold is definitional and moving it by one removes the rule"),
    Mutation(
        "B46f", f"{A}::_require_the_source_names_a_model",
        "    if not tuple(result.models or ()):\n",
        "    if False:\n",
        f"{T}::test_r71_a_source_that_names_no_model_is_refused",
        "finding 98's third claim restored: a source naming no model crosses either route, because the "
        "applicability loop iterates over result.models and is satisfied by anything"),
    Mutation(
        "B46g", f"{A}::_require_binding_names_the_source",
        "    if not any(candidate in text for candidate in candidates):\n",
        "    if False:\n",
        f"{T}::test_r71_a_binding_reference_that_names_nothing_in_the_source_is_refused",
        "finding 98's fourth claim restored: binding_ref is a free string again, so 'binding:p' binds "
        "nothing and the field has a name and no content"),
]

_CHANGED_FILES = (A,)


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
    status = run(MUTATIONS, label="BATCH46", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH46_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 46 changed ---", flush=True)
    status |= run(existing, label="BATCH46_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH46_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
