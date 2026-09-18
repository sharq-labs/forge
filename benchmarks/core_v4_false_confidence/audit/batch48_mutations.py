"""Batch-48 guard mutations (I-27 part B, R-58's finding 71): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch48_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

U = "src/engcore/uq/cross_domain.py"
C = "src/engcore/scientific/composition/conversion.py"
T = "tests/test_core_scientific_audit_batch48.py"

MUTATIONS = [
    Mutation(
        "B48a", f"{U}::_require_the_interval_contains_the_value",
        "    if not inside:\n",
        "    if False:\n",
        f"{T}::test_r58_an_interval_that_does_not_contain_the_value_is_refused",
        "finding 71 claim (a) restored: an INTERVAL of [10, 11] K propagates for a crossing of 350 K and "
        "round-trips, which is another quantity's interval wearing this crossing's record"),
    Mutation(
        "B48b", f"{U}::_entering_value",
        "    if transfer.source_value is not None:\n",
        "    if False:\n",
        f"{T}::test_r58_a_conversions_interval_is_about_the_input_and_not_the_output",
        "for a conversion the containment question is asked about what ARRIVED instead of what entered, so "
        "an interval about the input is checked against the output. REPOINTED while running these "
        "mutations: the audited interval ([10, 11] W against 100 W in) contains neither value, so the case "
        "only this rule sees is [79, 81] W -- the arrived 80 W inside it and the entering 100 W outside"),
    Mutation(
        "B48c", f"{U}::_require_the_uncertainty_names_the_source",
        "    if not attribution or not any(candidate in attribution for candidate in candidates):\n",
        "    if False:\n",
        f"{T}::test_r58_an_uncertainty_about_another_quantity_is_refused",
        "finding 71 claim (c) restored: a 1e-6 K uncertainty from another run, attributed to "
        "'some-other-quantity', crosses and is then relabelled as this crossing's own"),
    Mutation(
        "B48d", f"{U}::_transfer_reference_candidates",
        "        candidates.add(f\"transfer:{upstream.source_record_id}\")\n",
        "        candidates.add(upstream.instant)\n",
        f"{T}::test_r58_a_chain_across_two_records_still_propagates",
        "a chain link can no longer be justified by the crossing that fed it, so the module's own "
        "propagated attribution is refused one step later. REPOINTED while running these mutations: a "
        "chain whose two crossings name the SAME record is justified by that record either way, so the "
        "case only this rule sees is a chain across two records"),
    Mutation(
        "B48e", f"{U}::_attribution",
        "    return f\"transfer:{transfer.source_record_id}|from:{source_uncertainty.source}\"\n",
        "    return f\"transfer:{transfer.source_record_id}\"\n",
        f"{T}::test_r58_the_propagated_record_keeps_both_references",
        "finding 71 claim (b) restored: the original attribution is overwritten with the transfer id, so an "
        "uncertainty about another quantity reads as coming from this crossing's source run"),
    Mutation(
        "B48f", f"{U}::propagate_uncertainty_chain",
        "            if not _agree_relatively(\n",
        "            if False and _agree_relatively(\n",
        f"{T}::test_r58_a_chain_whose_values_do_not_meet_is_refused",
        "finding 71 claim (d) restored: 350 K leaving one crossing and 400 K entering the next propagate one "
        "width along a path nothing travelled"),
    Mutation(
        "B48g", f"{U}::UncertaintyTransfer.__post_init__",
        "        if str(self.completeness) != derived:\n",
        "        if False:\n",
        f"{T}::test_r58_a_record_cannot_state_a_completeness_its_own_arithmetic_denies",
        "a record may call itself complete while its own propagation left the efficiency uncertainty out, "
        "which is the note-instead-of-structure defect with a field to hide in"),
    Mutation(
        "B48h", f"{U}::_completeness_of",
        "    if conversion.efficiency_uncertainty is None:\n",
        "    if False:\n",
        f"{T}::test_r58_a_conversion_with_no_declared_efficiency_uncertainty_says_so_structurally",
        "the lower bound stops being declared: a width that leaves out a factor's uncertainty is presented "
        "as the whole of it, which is what the audit found in a note"),
    Mutation(
        "B48i", f"{U}::_completeness_of",
        "    if source_uncertainty.kind is UncertaintyKind.INTERVAL:\n",
        "    if False:\n",
        f"{T}::test_r58_an_interval_under_a_conversion_stays_a_lower_bound_even_when_the_efficiency_is_declared",
        "an interval under a conversion with a declared efficiency uncertainty calls itself complete, "
        "although a bound and a standard uncertainty cannot be combined without a distribution nobody declared"),
    Mutation(
        "B48j", f"{U}::propagate_transfer_uncertainty",
        "        if width is not None:\n",
        "        if False:\n",
        f"{T}::test_r58_a_declared_efficiency_uncertainty_is_propagated_in_quadrature",
        "a declared efficiency uncertainty is ignored again, so the field exists and the width does not "
        "change -- the defect the audit found, with a declaration nobody reads"),
    Mutation(
        "B48k", f"{C}::EnergyConversion.__post_init__",
        "            if not 0.0 <= width < efficiency:\n",
        "            if False:\n",
        f"{T}::test_r58_an_efficiency_uncertainty_as_wide_as_the_efficiency_is_refused",
        "an efficiency of 0.8 may declare a standard uncertainty of 0.8, which says the fraction is unknown "
        "while looking like a measurement"),
]

_CHANGED_FILES = (U, C, "src/engcore/scientific/composition/transfer.py")


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
    status = run(MUTATIONS, label="BATCH48", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH48_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 48 changed ---", flush=True)
    status |= run(existing, label="BATCH48_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH48_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
