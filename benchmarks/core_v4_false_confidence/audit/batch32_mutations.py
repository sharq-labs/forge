"""Batch-32 guard mutations (I-07 part A, R-30 and R-29): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch32_mutations
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from isolated_mutations import Mutation, ROOT, run, scratch_from_environment  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
import mutation_guards as M  # noqa: E402

GE = "src/engcore/hybrid_uq/_grid_evidence.py"
RO = "src/engcore/hybrid_uq/router.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch32.py"
B1 = "tests/hybrid_uq/test_core_scientific_audit_batch1.py"

MUTATIONS = [
    # --- a binding mismatch passes the grid over ---------------------------
    Mutation(
        "B32a", f"{GE}::require_grid_is_this_evidence",
        "    problem = grid_is_this_evidence(grid, calibration, observations, forward)\n"
        "    if problem is not None:\n        raise HybridUQError(problem[1])\n",
        "    return None\n",
        f"{T}::test_r30_the_raising_entry_point_still_raises",
        "the RAISING entry point stops checking anything at all. It is the one `engcore.hybrid_uq.predictive` "
        "calls, and a predictive request built ON a supplied posterior has no other route -- so there a "
        "mismatch really is about the request, and CORE-005 would be gone from the predictive layer while "
        "the router's own path still looked healthy"),
    Mutation(
        "B32b", f"{RO}",
        "        binding = grid_is_this_evidence(grid, calibration, observations, forward) if bound else None\n",
        "        binding = None\n",
        f"{T}::test_r30_a_grid_from_another_model_is_still_refused_as_not_this_evidence",
        "the router stops binding a supplied grid to the request's evidence, which is CORE-005 itself: a grid "
        "computed from other data under the same dataset id is USED. Passing over instead of raising must not "
        "become not checking, and this is the mutation that says so"),
    Mutation(
        "B32c", f"{RO}",
        "                problem = (binding\n",
        "                problem = (None\n",
        f"{B1}::test_core005_a_grid_computed_from_other_data_under_the_same_id_is_refused",
        "the binding is computed and then not consulted -- the shape I-16's whole round is about, and the one "
        "a reader of the call site is least likely to notice, because the call is still there. Seen by "
        "CORE-005's own original case rather than by this batch's, so the older suite is what notices"),
    Mutation(
        "B32d", f"{GE}::grid_is_this_evidence",
        "        if not abs(chi_grid - chi_forward) <= tolerance:\n",
        "        if False:\n",
        f"{T}::test_r30_a_grid_from_another_model_is_still_refused_as_not_this_evidence",
        "only the ADMISSION halves of the binding survive, so a grid whose nodes are all admissible and whose "
        "likelihood is a different model's passes: the numbers stop being compared at all"),
    # --- the message ------------------------------------------------------
    Mutation(
        "B32e", f"{GE}::grid_is_this_evidence",
        "                    f\"{chi_grid!r} and the forward evaluator with the request's own observations gives \"\n"
        "                    f\"{chi_forward!r}, a difference of {difference!r} -- {sigma_form:.6g} sigma per \"\n",
        "                    f\"{chi_grid:.6g} and the forward evaluator with the request's own observations gives \"\n"
        "                    f\"{chi_forward:.6g}, a difference of {difference:.6g} -- {sigma_form:.6g} sigma per \"\n",
        f"{T}::test_r30_the_mismatch_is_reported_in_digits_and_units_a_reader_can_act_on",
        "the audited message comes back: six significant figures for a disagreement at the twelfth digit, so "
        "both chi-squares print as 1064.66 and the refusal reads as a bug in the checker rather than a "
        "statement about the grid"),
    # --- prior uniformity is judged by the moment effect -------------------
    Mutation(
        "B32f", f"{GE}::grid_prior_uniformity",
        "        if max(moved_mean, moved_sd) > PRIOR_REWEIGHT_MOMENT_SD:\n",
        "        if True:\n",
        f"{T}::test_r29_a_grid_that_is_uniform_in_effect_is_not_refused_on_a_step_deviation",
        "R-29 restored exactly: the step deviation is the refusal again and the measured effect is discarded, "
        "so a LOG parameter's natural-linspace grid over plus or minus 2% -- moments matching the accepted "
        "spelling's to six digits -- is passed over for a spelling"),
    Mutation(
        "B32g", f"{GE}::grid_prior_uniformity",
        "        if max(moved_mean, moved_sd) > PRIOR_REWEIGHT_MOMENT_SD:\n",
        "        if False:\n",
        f"{T}::test_r29_a_node_density_that_does_move_the_moments_is_still_refused",
        "the opposite error, and the one this part could most easily have made: no node density is ever an "
        "undeclared prior again, so a grid with 350 of 410 nodes heaped below 1.0 is USED. CORE-010 exists "
        "because equal node mass IS the prior, and a rule that allows something new has to keep refusing "
        "what it was refusing for a reason"),
    Mutation(
        "B32h", f"{GE}::_reweighted_moment_shift",
        "    width[1:-1] = (axis[2:] - axis[:-2]) / 2.0\n",
        "    width[1:-1] = axis[2:] - axis[:-2]\n",
        f"{T}::test_r29_a_node_density_that_does_move_the_moments_is_still_refused",
        "the cell volume is doubled for every interior node and left alone at the ends, which is not the "
        "midpoint rule but a density with two spikes at the edges. It changes the measured shift, and a rule "
        "whose own measurement is wrong is worse than a spelling test, because it looks like an argument",
        expect="SURVIVED"),
    Mutation(
        "B32i", f"{GE}::_reweighted_moment_shift",
        "    reweighted = base * cell\n",
        "    reweighted = base\n",
        f"{T}::test_r29_a_node_density_that_does_move_the_moments_is_still_refused",
        "the reweighting is not applied, so the measured shift is exactly zero for every grid and the bound "
        "is satisfied by construction -- a test that always passes, dressed as a measurement"),
    Mutation(
        "B32j", f"{GE}",
        "PRIOR_REWEIGHT_MOMENT_SD = 0.05\n",
        "PRIOR_REWEIGHT_MOMENT_SD = 5.0\n",
        f"{T}::test_r29_the_moment_effect_bound_exists_and_is_the_repositorys_own_resolution",
        "the bound moves off the resolution at which this core declares a moment unchanged, which is the "
        "whole class-B argument for it. 5 sd is not a bound on anything: it is wider than the posterior"),
]

_CHANGED_FILES = (GE, RO)


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
    status = run(MUTATIONS, label="BATCH32", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH32_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 32 changed ---", flush=True)
    status |= run(existing, label="BATCH32_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH32_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
