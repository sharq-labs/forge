"""Batch-49 guard mutations (I-27 part C, R-58's production half): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch49_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

X = "src/engcore/uq/cross_domain.py"
E = "src/engcore/systems/electrothermal/coupled.py"
T = "tests/test_core_scientific_audit_batch49.py"

MUTATIONS = [
    Mutation(
        "B49a", f"{E}::run_fixed_point_coupling",
        "        crossings=recorded_crossings(final, transfers),\n",
        "        crossings=(),\n",
        f"{T}::test_r58_the_production_coupling_records_a_crossing_per_transfer",
        "finding 71's production half restored exactly: the run records what crossed and nothing the "
        "producing side said about it, so a receiving domain sees a number again"),
    Mutation(
        "B49b", f"{E}::CoupledRun.__post_init__",
        "            if recorded != declared:\n",
        "            if False:\n",
        f"{T}::test_r58_a_run_cannot_carry_a_partial_set_of_crossings",
        "a run may record a crossing for some of its transfers and not others, which reads as the whole of "
        "what crossed -- the same defect one level up from the one being fixed"),
    Mutation(
        "B49c", f"{X}::CrossedQuantity.from_result",
        "        if findings:\n",
        "        if False:\n",
        f"{T}::test_r58_a_crossing_cannot_be_built_against_another_record",
        "a crossing may be read off a record the transfer does not name, so that record's validity and "
        "validation travel beside this crossing's value -- the relabelling part B refused for an uncertainty"),
    Mutation(
        "B49d", f"{X}::CrossedQuantity.from_result",
        "            if entry is None:\n",
        "            if False:\n",
        f"{T}::test_r58_a_result_that_says_nothing_about_its_uncertainty_is_refused",
        "an absent uncertainty entry passes again, which is how a bare value comes to look complete: "
        "Uncertainty.unknown exists so that 'nobody evaluated it' is a value and not an absence"),
    Mutation(
        "B49e", f"{X}::CrossedQuantity.from_result",
        "        if configured:\n",
        "        if False:\n",
        f"{T}::test_r58_a_configured_input_crossing_carries_an_undeclared_uncertainty",
        "a configured input is looked up in the record that does not produce it, so the crossing is refused "
        "for an absence that is the correct state -- the production ambient crossing stops recording at all"),
    Mutation(
        "B49f", f"{X}::CrossedQuantity.__post_init__",
        "        if not verdicts:\n",
        "        if False:\n",
        f"{T}::test_r58_a_crossing_names_every_model_the_source_declares",
        "a crossing may carry no applicability verdict at all while looking like a complete answer, which "
        "is the bare number this record replaces with extra fields"),
]

_CHANGED_FILES = (X, E)


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
    status = run(MUTATIONS, label="BATCH49", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH49_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 49 changed ---", flush=True)
    status |= run(existing, label="BATCH49_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH49_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
