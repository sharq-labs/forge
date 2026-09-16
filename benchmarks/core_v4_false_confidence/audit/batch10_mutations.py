"""Batch-10 guard mutations (I-02, an honest multistart): each new guard removed, in an ISOLATED copy.

Not in tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core
Freeze V4 round (I-30). The runner is ``isolated_mutations``, which fixes R-67 for these runners.

Run from the repository root, with SCRATCH pointing at a scratch directory::

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch10_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

LG = "src/engcore/hybrid_uq/local_gaussian.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch10.py"

MUTATIONS = [
    # --- R-08: the budget and the replacement allowance are part of the minimum search ---
    Mutation(
        "B10a", f"{LG}::_search_shortfalls",
        '    if float(record["multistart_max_evaluations"]) < float(int(canonical.max_evaluations)):\n',
        "    if False:\n",
        f"{T}::test_r08_a_refit_budget_below_the_canonical_one_is_a_shortfall",
        "R-08: a refit budget below the canonical one stops being a shortfall, which is the audited defect"),
    Mutation(
        "B10b", f"{LG}::_search_shortfalls",
        '    if float(record["multistart_maximum_retractions"]) < float(int(canonical.maximum_retractions)):\n',
        "    if False:\n",
        f"{T}::test_r08_a_replacement_allowance_below_the_canonical_one_is_a_shortfall",
        "R-08: a search that may not replace a refused start stops being a narrower search"),
    Mutation(
        "B10c", f"{LG}::_multistart_verdict",
        "    incomplete = converged < _minimum_starts(p)\n",
        "    incomplete = converged * 2 < len(entries)\n",
        f"{T}::test_r08_a_search_is_incomplete_unless_the_minimum_number_converged",
        "R-08: the audited rule exactly -- up to half the starts may fail silently"),
    Mutation(
        "B10d", f"{LG}::local_gaussian_posterior",
        "            if refit.status is not CalibrationStatus.CONVERGED and int(multistart.max_evaluations) < canonical_budget:\n",
        "            if False:\n",
        f"{T}::test_r08_a_failed_refit_is_retried_at_the_canonical_budget",
        "R-08: a refit that ran out of the caller's budget is never retried at the canonical one, so the "
        "slow start that reaches the second mode is dropped"),

    # --- R-18: a refused start is replaced, not retracted ---
    Mutation(
        "B10e", f"{LG}::local_gaussian_posterior",
        "                start = multistart._point(parameters, halton_index)\n",
        "                start = tuple(float(v) for v in to_natural(z0 + (to_inference(start, transforms) - z0) / 2.0,\n"
        "                                                           transforms))\n",
        f"{T}::test_r18_starts_that_never_leave_the_basin_do_not_claim_a_single_mode",
        "R-18: the audited retraction exactly -- each refused start halved toward the estimate until the "
        "model admits it, so the search never leaves the estimate's own basin"),
    Mutation(
        # the key is a string literal and `_code_digest` ignores STRING tokens, so the mutation has to change
        # the code that chooses the key rather than the key's spelling
        "B10f", f"{LG}::local_gaussian_posterior",
        '            entry: dict[str, Any] = {"start": tuple(start), "proposed_start": proposed, "replacements": replacements,\n'
        '                                     "status": refit.status.value}\n',
        '            entry: dict[str, Any] = {"start": tuple(start), "proposed_start": proposed,\n'
        '                                     "status": refit.status.value}\n'
        '            entry["retractions" if True else "replacements"] = replacements\n',
        f"{T}::test_r18_a_refused_start_is_replaced_by_the_next_halton_point",
        "R-18: the record says a start was retracted when it was replaced, which is the reading the audit "
        "found nothing consumes"),
    Mutation(
        "B10g", f"{LG}::local_gaussian_posterior",
        "                halton_index += 1\n",
        "                halton_index += 0\n",
        f"{T}::test_r18_starts_that_never_leave_the_basin_do_not_claim_a_single_mode",
        "R-18: every replacement retries the same Halton point, so a shared counter that does not advance "
        "leaves five of the six starts with no admissible point at all and the second island unvisited"),

    # --- R-07: a separated optimum is classified by its mass ---
    Mutation(
        "B10h", f"{LG}::local_gaussian_posterior",
        '                        entry["classification"] = ("WORSE_LOCAL_OPTIMUM"\n'
        "                                                   if ratio is not None and ratio <= MULTISTART_MASS_FLOOR\n"
        '                                                   else "SECOND_MODE")\n',
        '                        entry["classification"] = "WORSE_LOCAL_OPTIMUM"\n',
        f"{T}::test_r07_a_broad_basin_that_holds_the_mass_is_a_second_mode",
        "R-07: a separated optimum that is not a better one is merely worse whatever mass it holds, which "
        "is the audited classification"),
    Mutation(
        "B10i", f"{LG}::local_gaussian_posterior",
        '                            entry["laplace_mass_ratio"] = ratio\n',
        "                            pass\n",
        f"{T}::test_r07_a_separated_optimum_records_the_mass_its_classification_follows_from",
        "R-07: the classification stops recording the number it follows from, so no reader can re-derive it"),
    Mutation(
        "B10j", f"{LG}::_separated_mass_ratio",
        "    exponent = -0.5 * (float(refit.objective_value) - float(chi_minimum)) + 0.5 * (float(log_det_at_minimum) - log_det)\n",
        "    exponent = -0.5 * (float(refit.objective_value) - float(chi_minimum))\n",
        f"{T}::test_a_separated_mode_is_weighed_by_its_volume_and_not_only_its_height",
        "R-07: the mass ratio drops the VOLUME term and becomes the peak height alone. R-07's own basin is "
        "a second mode either way (its height ratio already clears the floor), so the case that measures "
        "this is the narrow one added with the implementation"),
    Mutation(
        "B10k", f"{LG}::_separated_mass_ratio",
        '        return None, 0, "the information at the estimate is not positive definite"\n',
        "        log_det_at_minimum = 0.0\n",
        f"{T}::test_a_mass_that_cannot_be_bounded_is_not_a_negligible_mode",
        "R-07: a missing determinant at the estimate is silently taken as 1, so an unbounded ratio is "
        "reported as a number"),

    # --- the read-back ---
    Mutation(
        "B10l", f"{LG}::_require_reasons_follow_measurements",
        '                elif separation is not None and classification in ("SECOND_MODE", "WORSE_LOCAL_OPTIMUM"):\n',
        "                elif False:\n",
        f"{T}::test_the_read_back_requires_a_mass_ratio_for_a_separated_start",
        "R-07: a record may carry a separated classification with no mass at all"),
    Mutation(
        "B10m", f"{LG}::_require_reasons_follow_measurements",
        "                    elif not isinstance(ratio, float) or not math.isfinite(ratio) or ratio < 0.0:\n",
        "                    elif False:\n",
        f"{T}::test_the_read_back_requires_a_mass_ratio_for_a_separated_start",
        "R-07: the recorded ratio stops having to be a finite non-negative number"),
    Mutation(
        "B10n", f"{LG}::_require_reasons_follow_measurements",
        '                    elif (ratio > MULTISTART_MASS_FLOOR) != (classification == "SECOND_MODE"):\n',
        "                    elif False:\n",
        f"{T}::test_the_read_back_holds_a_separated_classification_to_its_recorded_mass",
        "R-07: the classification stops having to follow from the ratio the record carries"),
    Mutation(
        "B10o", f"{LG}::_require_reasons_follow_measurements",
        '                    if ratio is None and isinstance(unavailable, str) and unavailable and classification == "SECOND_MODE":\n',
        "                    if ratio is None:\n",
        f"{T}::test_the_read_back_accepts_a_separated_start_whose_mass_could_not_be_bounded",
        "R-07: any separated start may skip the ratio by omitting it, with no reason given and whatever "
        "classification it likes"),
]

_CHANGED_FILES = (LG,)


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
    status = run(MUTATIONS, label="BATCH10", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH10_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 10 changed ---", flush=True)
    status |= run(existing, label="BATCH10_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH10_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
