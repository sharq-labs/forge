"""Batch-54 guard mutations (I-25 part C, R-43's producer half): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch54_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

B = "src/engcore/sria/assurance/uncertainty_budget.py"
U = "src/engcore/sria/uncertainty.py"
T = "tests/test_core_scientific_audit_batch54.py"

MUTATIONS = [
    Mutation(
        "B54a", f"{B}::UncertaintyBudget.aggregate",
        "        if unattributed:\n",
        "        if False:\n",
        f"{T}::test_r43_an_unattributed_quantified_channel_cannot_be_aggregated",
        "finding 51's budget claim restored: a quantified record nobody attributed is root-sum-squared "
        "into a total presented as the channels' own, which is 'aleatoric and model_form marked known "
        "from a numerical-only record' becoming a number"),
    Mutation(
        "B54b", f"{U}::channels_from_predictive_uncertainty",
        "        if source is UncertaintySource.UNSPECIFIED:\n",
        "        if False:\n",
        f"{T}::test_r43_an_unattributed_quantified_record_carries_no_channel_either",
        "an unattributed quantified record is silently dropped by the carrying function instead of being "
        "refused, which loses a number rather than reporting that nothing said whose it is"),
    Mutation(
        "B54c", f"{U}::channels_from_predictive_uncertainty",
        "        if not record.is_quantified:\n",
        "        if False:\n",
        f"{T}::test_r43_an_unknown_record_carries_no_channel",
        "an UNKNOWN record is carried onto a channel, so 'nobody evaluated this' would be filed as the "
        "channel's uncertainty -- and a production record whose metrics were never quantified could not "
        "be carried at all"),
    Mutation(
        "B54d", f"{U}::channels_from_predictive_uncertainty",
        "        channel = CHANNEL_OF_SOURCE.get(source)\n",
        "        channel = CHANNEL_OF_SOURCE.get(source, UncertaintyChannel.ALEATORIC)\n",
        f"{T}::test_r43_a_combined_record_is_refused_rather_than_filed",
        "a COMBINED record is filed under a channel instead of being refused, and a mixture of channels "
        "counted under one of them counts what it contains twice"),
]

_CHANGED_FILES = (B, U)


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
    status = run(MUTATIONS, label="BATCH54", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH54_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 54 changed ---", flush=True)
    status |= run(existing, label="BATCH54_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH54_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
