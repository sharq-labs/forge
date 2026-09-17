"""Batch-31 guard mutations (I-06 and the I-14 part that blocks it): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch31_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

RO = "src/engcore/hybrid_uq/router.py"
LG = "src/engcore/hybrid_uq/local_gaussian.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch31.py"
C = "tests/hybrid_uq/test_core_v4_false_confidence_conformance.py"

MUTATIONS = [
    # --- domination is diagnosed one side at a time ------------------------
    Mutation(
        "B31a", f"{RO}::_rebuild_grid",
        "                            if reach > _GAUSSIAN_BAND_SD:\n"
        "                                one_sided.append((local.parameter_names[i], side, reach))\n",
        "                            if False:\n"
        "                                one_sided.append((local.parameter_names[i], side, reach))\n",
        f"{T}::test_r11_a_posterior_running_to_one_declared_bound_is_passed_over",
        "R-11 restored exactly: one reached declared bound goes to the halving loop, so the same data are "
        "SUPPORTED with a rate sd of 2.372, 2.788 and 3.522 at declared upper bounds of 40, 60 and 80. The "
        "bound sets the answer, which is the pathology CORE-002's both-sides rule was written to stop"),
    Mutation(
        "B31b", f"{RO}",
        "_GAUSSIAN_BAND_SD = math.sqrt(2.0 * EDGE_LOG_LIKELIHOOD_DROP)\n",
        "_GAUSSIAN_BAND_SD = 5.2565\n",
        f"{T}::test_r11_the_band_distance_is_derived_from_the_band_and_not_chosen",
        "the distance becomes a literal instead of the expression it is derived from, so it can drift from "
        "the band it is about the moment EDGE_LOG_LIKELIHOOD_DROP moves -- which is how a derived constant "
        "turns into a tuned one without anyone deciding to tune it"),
    Mutation(
        "B31c", f"{RO}::_rebuild_grid",
        "    if one_sided:\n",
        "    if False:\n",
        f"{C}::test_r11_a_supported_width_does_not_depend_on_where_a_declared_bound_is_put",
        "the per-side finding is measured and then not acted on, which I-16's whole round is about: a rule "
        "that computes its own answer and returns anyway. Seen by I-15's own INV-4 case rather than by this "
        "batch's, so the conformance suite is what notices"),
    # --- a peak that decays toward its bound keeps the refinement path -----
    Mutation(
        "B31d", f"{RO}::_rebuild_grid",
        "                        if math.isfinite(sd[i]) and sd[i] > 0.0:\n"
        "                            reach = abs(bound - peak_at) / float(sd[i])\n",
        "                        if math.isfinite(sd[i]) and sd[i] > 0.0:\n"
        "                            reach = float('inf')\n",
        f"{T}::test_r11_a_truncated_posterior_that_decays_toward_its_bound_still_takes_the_refinement_path",
        "every reached declared bound becomes a domination, so the halving loop is unreachable and a "
        "posterior that DECAYS toward its bound is refused with it. That is the blanket refusal the audit "
        "warned against -- 'keep truncation refinement for posteriors that actually decay toward the "
        "bound' -- and it would satisfy INV-4's first half while measuring nothing"),
    Mutation(
        "B31e", f"{RO}::_rebuild_grid",
        "            peak_at = lo[i] + float(peak_index[i]) * (hi[i] - lo[i]) / steps\n",
        "            peak_at = lo[i]\n",
        f"{T}::test_r11_a_truncated_posterior_that_decays_toward_its_bound_still_takes_the_refinement_path",
        "the distance is measured from the box's low face rather than from the peak, so on a contained "
        "posterior it is the whole box width and the refusal fires on a truncated case the halving loop was written for. Repointed while running: both this and B31d first named the CONTAINED case, where no face reaches its bound at all, so the branch they corrupt is never entered and both survived"),
    # --- the refusal names the side ---------------------------------------
    Mutation(
        "B31f", f"{RO}::_rebuild_grid",
        "                      f\"the posterior runs to the {worst[1]} declared bound of {worst[0]!r} while staying within \"\n",
        "                      f\"the posterior runs to a declared bound while staying within \"\n",
        f"{T}::test_r11_the_refusal_names_the_parameter_and_which_side_it_ran_to",
        "the reader is told a bound was reached and not WHICH, and the two findings have opposite remedies: "
        "both sides dominated means widen nothing because the range says nothing, one side means the data "
        "constrain one direction only and widening makes it worse. That confusion is what produced the "
        "1.743 / 2.037 / 3.473 sequence. The assertion was tightened while running: the detail also ends with a `dominated side(s)` list, so looking for the word `high` anywhere in the line passed"),
    # --- the leverage null cannot be computed negative (I-14, early) -------
    Mutation(
        "B31g", f"{LG}::_leverage_null_cumulants",
        "    return (\n"
        "        _clamp_leverage_cumulant(c1, scale=terms1, terms=count, name=\"c1\"),\n"
        "        _clamp_leverage_cumulant(c2, scale=terms2, terms=count, name=\"c2\"),\n"
        "        _clamp_leverage_cumulant(c3, scale=terms3, terms=count, name=\"c3\"),\n"
        "    )\n",
        "    return c1, c2, c3\n",
        f"{T}::test_r11_the_fixture_is_routable_at_all",
        "the blocker comes back: a problem where one observation holds all the leverage has a structurally "
        "zero null, the closed form reaches it by cancellation and lands on -2.22e-16, and the route's own "
        "self-check refuses the record -- so the problem cannot be ROUTED at all, whatever its verdict "
        "would have been. A numerical detail that costs a whole class of problems every answer"),
    Mutation(
        "B31h", f"{LG}::_clamp_leverage_cumulant",
        "    if value >= -floor:\n        return 0.0\n",
        "    return 0.0\n",
        f"{T}::test_r11_a_cumulant_far_below_the_round_off_floor_is_refused_and_not_clamped",
        "the floor goes and the clamp becomes unconditional, so a genuinely negative cumulant -- which can "
        "only be a coding error, the quantity being a trace of a power of a PSD matrix -- is silently made "
        "zero. A clamp without a floor is not a numerical fix, it is a way of not being told"),
    Mutation(
        "B31i", f"{LG}::_clamp_leverage_cumulant",
        "    floor = float(terms) * float(np.finfo(float).eps) * abs(float(scale))\n",
        "    floor = float(np.finfo(float).eps)\n",
        f"{T}::test_r11_the_fixture_is_routable_at_all",
        "the floor stops scaling with the computation, so it is eps absolute rather than eps relative to "
        "the magnitudes summed. For a null whose terms are of order 1e-7 that happens to still work and for "
        "one of order 1e3 it does not, which is the failure mode of every absolute tolerance on a relative "
        "quantity",
        expect="SURVIVED"),
]

_CHANGED_FILES = (RO, LG)


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
    status = run(MUTATIONS, label="BATCH31", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH31_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 31 changed ---", flush=True)
    status |= run(existing, label="BATCH31_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH31_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
