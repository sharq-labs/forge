"""Batch-47 guard mutations (I-27 part A; R-60, R-61, R-64): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch47_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

X = "src/engcore/scientific/composition/transfer.py"
D = "src/engcore/scientific/composition/dependency.py"
T = "tests/test_core_scientific_audit_batch47.py"

MUTATIONS = [
    Mutation(
        "B47a", f"{X}::QuantityTransfer._check_against_the_declared_budget",
        "        scale = max(abs(budgeted), abs(arrived))\n",
        "        scale = max(abs(budgeted), abs(arrived), 1.0)\n",
        f"{T}::test_r60_a_small_crossing_carrying_everything_is_refused",
        "finding 73 restored exactly: the floor is back, so below one unit of the conversion's own exemplar "
        "the criterion is absolute and a crossing carries the whole input against a declared half"),
    Mutation(
        "B47b", f"{X}::_agree_relatively",
        "    return abs(left - right) <= BUDGET_TOLERANCE * scale\n",
        "    return True\n",
        f"{T}::test_r61_two_genuinely_different_values_are_still_refused",
        "REPOINTED while running these mutations: the shared relative comparison stops comparing, so 300 K "
        "and 400 K crossing one declaration at one instant agree -- which is the contradiction the "
        "agreement rule exists to refuse, and the thing a value-based comparison must not lose while it "
        "stops refusing two spellings of one number"),
    Mutation(
        "B47c", f"{X}::_transfers_state_one_value",
        "    if not _agree_relatively(left.value.magnitude_in(unit), right.value.magnitude_in(unit)):\n",
        "    if left.value != right.value:\n",
        f"{T}::test_r61_one_value_spelled_in_two_units_agrees",
        "finding 74 restored: agreement is comparison of a magnitude and a unit STRING again, so one value "
        "spelled in two units is 'two different values' and a justified ProvenanceRecord is unconstructible"),
    Mutation(
        "B47d", f"{X}::_transfers_state_one_value",
        "    return left.value_origin == right.value_origin\n",
        "    return left.value_origin == right.value_origin and left.source_record_id == right.source_record_id\n",
        f"{T}::test_r61_one_value_from_two_records_agrees",
        "finding 74's second claim restored: one value read from two records at one instant is refused as a "
        "contradiction, where it is a redundancy"),
    Mutation(
        "B47e", f"{X}::require_agreeing_transfers",
        "            f\"{existing.source_record_id!r} and \"\n",
        "            f\"{existing.instant!r} and \"\n",
        f"{T}::test_r61_the_refusal_names_the_records_that_disagree",
        "the accurate message loses the records again: a reader is told two values disagree and not which "
        "records said them, which is what made the audited message print one number twice"),
    Mutation(
        "B47f", f"{X}::require_agreeing_transfers",
        "        if earlier is not None and earlier.instant != transfer.instant:\n",
        "        if False:\n",
        f"{T}::test_r61_a_stale_instant_cannot_sit_beside_the_final_one",
        "finding 75 restored: a stale iteration and the final one coexist in one record, and the canonical "
        "order puts 'coupled_iteration:9' after ':10', so a consumer keeping the last one takes the stale value"),
    Mutation(
        "B47g", f"{X}::QuantityTransfer.__post_init__",
        "        if origin not in TRANSFER_VALUE_ORIGINS:\n",
        "        if False:\n",
        f"{T}::test_r61_a_value_origin_nobody_declared_is_refused",
        "the origin becomes free text, which is the unchecked spelling the field exists to replace: "
        "check_against_result would then silently ask neither question"),
    Mutation(
        "B47h", f"{X}::QuantityTransfer.check_against_result",
        "        if result_id != self.source_record_id:\n",
        "        if False:\n",
        f"{T}::test_r61_another_record_carrying_the_same_number_is_still_not_the_record_named",
        "finding 75's 'checks neither against anything' restored for the id: a transfer naming one record is "
        "checked against whatever result a caller happens to hand over. REPOINTED while running these "
        "mutations -- the preregistered reproduction's result carries no such quantity, so the missing-value "
        "rule answers it too; the case only the id rule sees is another record that DOES carry this "
        "quantity at this value"),
    Mutation(
        "B47i", f"{X}::QuantityTransfer.check_against_result",
        "            if name in values:\n",
        "            if False:\n",
        f"{T}::test_r61_a_configured_input_that_the_record_does_produce_is_a_finding",
        "a crossing may declare a configured input for a quantity the named record produces, which is the "
        "declaration contradicting the record and the one thing this branch is for"),
    Mutation(
        "B47j", f"{X}::QuantityTransfer.check_against_result",
        "        if not _agree_relatively(crossed.magnitude_in(unit), stated.magnitude_in(unit)):\n",
        "        if False:\n",
        f"{T}::test_r61_a_value_that_is_not_in_the_record_it_names_is_a_finding",
        "the value is no longer compared with the record it is claimed to come from: 'any-string-at-all "
        "carrying 999 K' becomes checkable in name only"),
    Mutation(
        "B47k", f"{D}::QuantityDependency.__post_init__",
        "        if carries_an_energy_density and self.conversion is None and not self.transport_declaration:\n",
        "        if False:\n",
        f"{T}::test_r64_an_energy_derived_crossing_with_no_declaration_is_refused",
        "finding 78 restored: a heat flux, a line power, a volumetric source and a specific energy cross "
        "with nothing declared, and silence reads as 'all of it arrives'"),
    Mutation(
        "B47l", f"{D}::QuantityDependency.__post_init__",
        "        if carries_energy and self.transport_declaration:\n",
        "        if False:\n",
        f"{T}::test_r64_prose_about_an_exact_energy_crossing_is_refused",
        "an exact energy or power may satisfy the fail-closed edge with a sentence instead of an "
        "EnergyConversion, which is a second and weaker way to say the thing the conversion record states "
        "in checkable fractions"),
    Mutation(
        "B47m", f"{D}::QuantityDependency.__post_init__",
        "            if not (carries_energy or carries_an_energy_density):\n",
        "            if not carries_energy:\n",
        f"{T}::test_r64_an_energy_derived_crossing_can_declare_a_conversion",
        "a density may no longer declare a conversion, so the rule above becomes a wall: the only way past "
        "it is prose, for crossings where the fractions are exactly what a reader needs"),
]

_CHANGED_FILES = (X, D, "src/engcore/scientific/composition/conversion.py",
                  "src/engcore/systems/electrothermal/coupled.py")


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
    status = run(MUTATIONS, label="BATCH47", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH47_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 47 changed ---", flush=True)
    status |= run(existing, label="BATCH47_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH47_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
