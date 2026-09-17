"""Batch-12 guard mutations (I-05, per-mode grid resolution and admissibility cuts): each new guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch12_mutations
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
RT = "src/engcore/hybrid_uq/router.py"
PR = "src/engcore/hybrid_uq/predictive.py"
T = "tests/hybrid_uq/test_core_scientific_audit_batch12.py"

MUTATIONS = [
    # --- R-05: every mode in the band, on its own nodes ---
    Mutation(
        "B12a", f"{GE}::supplied_grid_problem",
        "            or grid_mode_resolution(grid))\n",
        "            or None)\n",
        f"{T}::test_both_checks_run_in_the_supplied_grid_problem_chain",
        "R-05: the per-mode check leaves the supplied-grid chain",
        also=((f"{GE}::supplied_grid_problem", "            or grid_admissibility_truncation(grid)\n", "            or None\n"),)),
    Mutation(
        "B12b", f"{RT}::route_uncertainty",
        "                           or grid_mode_resolution(grid))\n",
        "                           or None)\n",
        f"{T}::test_r05_a_supplied_grid_that_aliases_a_second_mode_is_passed_over",
        "R-05: the router admits a supplied grid without checking any mode, which is the audited route"),
    Mutation(
        "B12c", f"{GE}::grid_mode_resolution",
        "        if residual > MODE_FIT_RESIDUAL_NATS:\n",
        "        if False:\n",
        f"{T}::test_r05_a_mode_the_aliasing_bound_passes_can_still_fail_its_own_fit",
        "R-05: a quadratic that misses its own nodes certifies the mode anyway. The audited case is caught by "
        "the aliasing bound too, so the case that measures this half is the broad shoulder with a narrow "
        "spike, where the fit follows the shoulder and V1's bound passes"),
    Mutation(
        "B12d", f"{GE}::grid_mode_resolution",
        "        aliasing = _minimum_aliasing_number(covariance, _ALIASING_NUMBER_MINIMUM)\n        if aliasing is not None:\n",
        "        aliasing = _minimum_aliasing_number(covariance, _ALIASING_NUMBER_MINIMUM)\n        if False:\n",
        f"{T}::test_r05_a_mode_its_own_fit_describes_perfectly_can_still_fail_the_aliasing_bound",
        "R-05: the mode's own aliasing bound stops being applied. The audited case is caught by the residual "
        "test too, so the case that measures this half is the thin tilted ridge, whose fit is exact to 1e-10 "
        "nats and whose perpendicular width is below the lattice step"),
    Mutation(
        "B12e", f"{GE}::_mode_lattice_covariance",
        "        cut = tuple(slice(max(0, index[i] - radius), min(shape[i], index[i] + radius + 1)) for i in range(p))\n",
        "        cut = tuple(slice(0, shape[i]) for i in range(p))\n",
        f"{T}::test_r05_the_same_grid_refined_is_still_used",
        "R-05: the fit pools the WHOLE lattice instead of a box about the mode -- the audited defect exactly, "
        "one quadratic over a window that holds both modes"),
    Mutation(
        "B12f", f"{GE}::_grid_modes",
        "    for offset in itertools.product((-1, 0, 1), repeat=p):\n",
        "    for offset in ((0,) * (p - 1) + (d,) for d in (-1, 1)):\n",
        f"{T}::test_r05_a_mode_is_a_maximum_over_the_whole_lattice_stencil_not_the_axes",
        "R-05: maximality over one axis only, so an exactly Gaussian tilted ridge staircases into spurious "
        "maxima. The guard is that the stencil is the whole lattice neighbourhood"),
    Mutation(
        "B12g", f"{GE}::_grid_modes",
        "    candidate = np.isfinite(lattice) & (peak - lattice < EDGE_LOG_LIKELIHOOD_DROP)\n",
        "    candidate = np.isfinite(lattice) & (peak - lattice < 0.5)\n",
        f"{T}::test_r05_a_supplied_grid_that_aliases_a_second_mode_is_passed_over",
        "R-05: the band shrinks to half a nat, so a second mode 9.6 nats below the peak is not looked at -- "
        "which is the audited blindness, by another route"),
    Mutation(
        "B12h", f"{RT}::route_uncertainty",
        "                unresolved = grid_mode_resolution(rebuilt)\n                if unresolved is not None:\n",
        "                unresolved = grid_mode_resolution(rebuilt)\n                if False:\n",
        f"{T}::test_r05_a_rebuilt_grid_that_aliases_a_mode_is_refined_or_passed_over",
        "R-05: a REBUILT grid is used with an aliased mode, which the audit measured as narrow-mode mass "
        "0.209 against a true 0.100 and a mean error of -0.36 sd"),

    # --- R-17: an admissibility cut is a truncation face ---
    Mutation(
        "B12i", f"{RT}::route_uncertainty",
        "                           or grid_admissibility_truncation(grid)\n",
        "                           or None\n",
        f"{T}::test_r17_a_supplied_grid_cut_by_inadmissibility_is_passed_over",
        "R-17: the router admits a supplied grid whose posterior the admissible region cuts, which is the "
        "audited route"),
    Mutation(
        "B12j", f"{GE}::admissibility_cut_axes",
        "    reached = np.isfinite(lattice) & (peak - lattice < EDGE_LOG_LIKELIHOOD_DROP)\n",
        "    reached = np.isfinite(lattice) & (peak - lattice < 0.0)\n",
        f"{T}::test_r17_a_supplied_grid_cut_by_inadmissibility_is_passed_over",
        "R-17: only the peak node itself counts as reaching the cut, so a cut one node away from the peak is "
        "invisible"),
    Mutation(
        "B12k", f"{GE}::admissibility_cut_axes",
        "        if bool(np.any(reached[below] & gone[above])) or bool(np.any(reached[above] & gone[below])):\n",
        "        if bool(np.any(reached[below] & gone[above])):\n",
        f"{T}::test_r17_an_inadmissible_node_far_below_the_peak_is_not_a_cut",
        "R-17: a cut is seen from one side only, so which side of the box the admissible region ends on "
        "decides whether the grid is checked"),
    Mutation(
        "B12l", f"{GE}::grid_admissibility_truncation",
        "    if not found:\n        return None\n",
        "    if True:\n        return None\n",
        f"{T}::test_both_checks_run_in_the_supplied_grid_problem_chain",
        "R-17: the check never reports a cut at all"),
    Mutation(
        "B12m", f"{RT}::_rebuild_grid",
        "    truncated = sorted(set(truncated) | set(cut))\n",
        "    truncated = sorted(set(truncated))\n",
        f"{T}::test_r17_a_rebuild_halves_the_step_across_the_cut_until_the_moments_converge",
        "R-17: the rebuild's truncation halving ignores the admissibility cut, which is the audited '0 "
        "truncation halving(s)' with a mean error of -0.144 sd"),
    Mutation(
        "B12n", f"{RT}::_rebuild_grid",
        "    halvings = 0\n    truncated = sorted(set(truncated) | set(cut))\n",
        "    truncated = sorted(set(truncated) + list(cut)) if False else sorted(set(truncated) | set(cut))\n"
        "    truncated = truncated + list(cut)\n    halvings = 0\n",
        f"{T}::test_r17_the_bound_domination_rule_is_not_fired_by_an_admissibility_cut",
        "R-17: the cut axes join the list the bound-domination rule counts, so an axis cut on both sides by "
        "the model's own domain is reported as the DECLARED range dominating the width. This SURVIVES: the "
        "domination check runs above this line and reads the list before the cuts are added, which is what "
        "keeps the two apart -- the ordering is the guard, and B12o mutates it",
        expect="SURVIVED"),
    Mutation(
        "B12o", f"{RT}::_rebuild_grid",
        "    dominated = sorted({local.parameter_names[i] for i in truncated if truncated.count(i) >= 2})\n",
        "    dominated = sorted({local.parameter_names[i] for i in list(truncated) + list(cut) + list(cut)\n"
        "                        if (list(truncated) + list(cut) + list(cut)).count(i) >= 2})\n",
        f"{T}::test_r17_the_bound_domination_rule_is_not_fired_by_an_admissibility_cut",
        "R-17: the domination rule counts the admissibility cuts, so the model's own domain is reported as "
        "the declared range dominating the width"),

    # --- routed prediction ---
    Mutation(
        "B12p", f"{PR}::_grid_evidence_judgement",
        "               or grid_admissibility_truncation(posterior)\n               or grid_mode_resolution(posterior))\n",
        "               or None)\n",
        f"{T}::test_both_checks_run_in_routed_prediction",
        "R-05/R-17: routed prediction predicts from a grid the router would not route"),
]

_CHANGED_FILES = (GE, RT, PR, "src/engcore/hybrid_uq/vocabulary.py")


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
    status = run(MUTATIONS, label="BATCH12", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH12_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 12 changed ---", flush=True)
    status |= run(existing, label="BATCH12_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH12_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
