"""Batch-21 guard mutations (I-08 part B, what the local route's probes measure): each guard removed.

Applied in an ISOLATED copy by ``isolated_mutations``, which fixes R-67 for these runners. Not in
tests/mutation_guards.py: that file is certification-pinned, so the batch guards join it in the Core Freeze V4
round (I-30).

    SCRATCH=/tmp/scratch python -m benchmarks.core_v4_false_confidence.audit.batch21_mutations
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
T = "tests/hybrid_uq/test_core_scientific_audit_batch21.py"
C = "tests/hybrid_uq/test_core_v4_false_confidence_conformance.py"
LR = "tests/hybrid_uq/test_hybrid_uq_local_route.py"

MUTATIONS = [
    # --- R-13: the curvature matrix ---
    Mutation(
        "B21a", f"{LG}::local_gaussian_posterior",
        "        worst = max(worst, curvature_worst)\n",
        "        worst = worst\n",
        f"{C}::test_r13_a_curvature_error_spread_over_every_pair_is_not_supported",
        "R-13, the audited case restored exactly: the matrix index is computed and then not used, so each "
        "direction is bounded alone again and a curvature error spread over every pair sits at 0.0992, under "
        "the 0.10 downgrade, while the true sd along the equal-weight direction is 2.24x the reported one"),
    Mutation(
        "B21b", f"{LG}::_curvature_index",
        "    return max(abs(high - 1.0), abs(1.0 - low)), (low, high)\n",
        "    return abs(high - 1.0), (low, high)\n",
        f"{T}::test_r13_the_index_is_the_supremum_of_the_per_direction_index",
        "only the UPPER extreme is read, so a direction whose curvature is far too SMALL -- the flat one, "
        "where the posterior is wider than the covariance says -- contributes nothing. That is the audited "
        "direction: lambda_min = 0.109 against lambda_max = 1.099"),
    Mutation(
        "B21c", f"{LG}::_curvature_matrix",
        "            pairs[(i, j)] = (plus - minus) / (2.0 * square)\n",
        "            pairs[(i, j)] = 0.0\n",
        f"{T}::test_r13_the_matrix_is_recovered_exactly_from_the_probes_already_paid_for",
        "the off-diagonal entries go to zero, so the matrix is diagonal and its eigenvalues are the axis "
        "probes -- exactly the per-direction gate the matrix exists to replace, wearing a matrix's clothes"),
    Mutation(
        "B21d", f"{LG}::_curvature_matrix",
        "        return sum(values) / len(values) if len(values) == 2 else None\n",
        "        return sum(values) / len(values) if values else None\n",
        f"{T}::test_r13_an_index_whose_other_sign_was_never_probed_is_left_out_of_the_matrix",
        "a single sign is accepted as the sign-averaged rise, so a direction whose other half left the "
        "declared box contributes a one-sided second difference -- which is a first difference, and carries "
        "the linear term the averaging exists to cancel. Repointed: it first named the recovery test, which "
        "feeds EVERY probe, so a rule about a MISSING probe was invisible to it"),
    Mutation(
        "B21e", f"{LG}::_require_reasons_follow_measurements",
        '                    f"a nonlinearity index of {index:.6g} is below the {implied:.6g} its own curvature "\n'
        '                    f"extremes {bounds} imply")\n',
        '                    f"a nonlinearity index of {index:.6g} is below the {implied:.6g} its own curvature "\n'
        '                    f"extremes {bounds} imply") if False else None\n',
        f"{T}::test_r13_the_index_must_dominate_the_matrix_the_record_carries",
        "read-back stops holding the index to the matrix the record carries, so a record can report extremes "
        "of (0.001, 1.0) beside an index of 0.07 and be read as SUPPORTED"),
    Mutation(
        "B21f", f"{LG}::RouteDiagnostics.__post_init__",
        "        if bounds and (len(bounds) != 2 or not all(math.isfinite(v) for v in bounds) or bounds[0] > bounds[1]):\n",
        "        if False:\n",
        f"{T}::test_r13_bounds_that_are_not_two_finite_numbers_in_order_are_refused",
        "the extremes stop being (lambda_min, lambda_max), two finite numbers in order, so a record can carry "
        "them reversed -- which inverts every derived check that reads bounds[0] and bounds[1]"),
    # --- R-14: the tails, in every direction ---
    Mutation(
        "B21g", f"{LG}::_tail_directions",
        "    directions = _probe_directions(lam, vec)\n",
        "    directions = _probe_directions(lam, vec)[:len(lam)]\n",
        f"{T}::test_r14_a_posterior_flat_along_its_diagonals_with_residual_dof_is_refused",
        "R-14, the audited case restored exactly: the tail probes go back to the p axes only, and a posterior "
        "exactly Gaussian on both axes out to 6 sd that saturates along its diagonals is SUPPORTED with no "
        "reason at all"),
    Mutation(
        "B21h", f"{LG}::_tail_directions",
        "    for column in (0, len(values) - 1):\n",
        "    for column in ():\n",
        f"{T}::test_r14_the_tail_directions_are_every_probe_direction_plus_the_two_extremes",
        "the curvature matrix's two extreme eigenvectors stop being probed, so the direction the matrix "
        "itself identifies as flattest is the one direction the tails never look along"),
    Mutation(
        "B21i", f"{LG}::_tail_directions",
        "        directions.append(sum(float(u[a]) * scaled[k] for a, k in enumerate(indices)))\n",
        "        directions.append(scaled[indices[0]])\n",
        f"{T}::test_r14_the_tail_directions_are_every_probe_direction_plus_the_two_extremes",
        "the extreme eigenvector is replaced by an axis already in the set, so the two extra probes are "
        "duplicates and measure nothing new -- a direction set that looks p^2 + 2 long and is p^2. It "
        "SURVIVED the count and the unit-Mahalanobis check, which a duplicate axis passes, so the guard now "
        "asserts that the last two directions ARE the mapped eigenvectors"),
    # --- R-15: the clipped probe ---
    Mutation(
        "B21j", f"{LG}::local_gaussian_posterior",
        "                reached = _clipped_radius(z0, sign * axis, radius, lower, upper)\n",
        "                reached = radius\n",
        f"{T}::test_r15_a_clipped_probe_is_counted_and_compared_at_the_radius_it_reached",
        "the clipping is skipped, so a probe outside the declared box is evaluated where no posterior mass "
        "lies and compared with the radius it never reached"),
    Mutation(
        "B21k", f"{LG}::local_gaussian_posterior",
        "                tail_ratio = min(tail_ratio, (value - chi_min) / reached ** 2)\n",
        "                tail_ratio = min(tail_ratio, (value - chi_min) / radius ** 2)\n",
        f"{T}::test_r15_a_clipped_probe_is_counted_and_compared_at_the_radius_it_reached",
        "a clipped probe's rise is compared with the radius it was ASKED for rather than the one it reached, "
        "so pulling a bound inward makes the same posterior look heavier-tailed. It SURVIVED the audited "
        "6.01/5.99 pair, and rightly: those two radii differ by 0.2%, which no verdict can resolve. At a "
        "bound of 2.5 sd the factor is 5.8 -- 0.985 of the radius reached against 0.171 of the radius asked "
        "for, which is the difference between Gaussian as far out as the box allows and REFUSED"),
    Mutation(
        "B21l", f"{LG}::local_gaussian_posterior",
        "                if reached < PROBE_SD:\n",
        "                if reached < radius:\n",
        f"{T}::test_r15_a_clipped_probe_is_counted_and_compared_at_the_radius_it_reached",
        "every clipped probe is discarded instead of only the ones the box stops inside PROBE_SD, which is "
        "the silent drop R-15 is about wearing a counter. Repointed: it first named the bound-1.5 case, where "
        "every probe is outside anyway, so the two branches are indistinguishable there"),
    Mutation(
        "B21m", f"{LG}::local_gaussian_posterior",
        "    if tail_outside:\n        downgrades.append(RouteReason.TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS)\n",
        "    if False:\n        downgrades.append(RouteReason.TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS)\n",
        f"{T}::test_r15_a_probe_clipped_inside_the_two_sd_probes_is_counted_and_downgrades",
        "the fact R-15 is ABOUT stops being said: a route whose tail was never measured, because the declared "
        "box stopped every probe inside the radius the +/-2 sd probes already cover, says nothing about it. "
        "This mutation and B21m2 both SURVIVED the preregistered form of the rule, which folded this into "
        "NONLINEARITY_PROBE_INCOMPLETE -- and the survival was structural, not a gap in the tests: along any "
        "fixed probe direction the box stops a tail probe inside PROBE_SD only when it also stops that "
        "direction's own +/-2 sd probe, so the same word was already emitted. That is what put "
        "TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS in the vocabulary (amendment 1)"),
    Mutation(
        "B21m2", f"{LG}::local_gaussian_posterior",
        "    if tail_outside:\n        downgrades.append(RouteReason.TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS)\n",
        "    if tail_outside:\n        pass\n",
        f"{T}::test_r15_a_probe_clipped_inside_the_two_sd_probes_is_counted_and_downgrades",
        "the same rule removed a second way, with the count still taken and nobody reading it -- which is "
        "the shape the first form of this rule had, and the reason it needed a word of its own"),
    Mutation(
        "B21n", f"{LG}::_clipped_radius",
        "        elif step < 0.0:\n            limit = min(limit, (float(lower[i]) - float(z0[i])) / step)\n",
        "        elif step < 0.0:\n            pass\n",
        f"{T}::test_r15_a_clipped_probe_is_counted_and_compared_at_the_radius_it_reached",
        "only the upper bounds clip, so a probe running toward a LOWER bound leaves the box unclipped -- "
        "exactly half the audited case's probes, since its box is symmetric. Repointed: it first named the "
        "6.01/5.99 pair, which both still refuse when half the clipping is gone, and then a `> 0` on the "
        "clipped count, which the surviving half satisfies. The count is now asserted exactly: two"),
    Mutation(
        "B21m3", f"{LG}::_require_reasons_follow_measurements",
        "        if outside:\n            downgrades.add(RouteReason.TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS)\n",
        "        if False:\n            downgrades.add(RouteReason.TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS)\n",
        f"{T}::test_r15_a_probe_clipped_inside_the_two_sd_probes_is_counted_and_downgrades",
        "read-back stops re-deriving the new word from the count, so a record can carry a non-zero "
        "out-of-bounds count and no reason for it -- and the route that wrote it would be refused instead, "
        "which is the emission rule and the read-back rule disagreeing"),
    # --- compatibility: the new fields are written only when they carry information ---
    Mutation(
        "B21o", f"{LG}::RouteDiagnostics.to_dict",
        "        if self.curvature_eigenvalue_bounds:\n",
        "        if True:\n",
        f"{T}::test_r15_the_new_counts_default_to_zero_so_an_old_record_derives_nothing_from_them",
        "the extremes are written even when nothing was measured, so a record says the curvature matrix was "
        "built where it was not -- and every record written before the rule changes bytes. It SURVIVED "
        "popping the key from a record that does carry it, which says nothing about a record that should not; "
        "the guard now reads a p = 1 route, which builds no matrix"),
    Mutation(
        "B21p", f"{LG}::_require_reasons_follow_measurements",
        "        tail_probe_budget = 2 * len(TAIL_PROBE_SD) * (p * p + 2)\n",
        "        tail_probe_budget = 2 * len(TAIL_PROBE_SD) * p\n",
        f"{T}::test_r15_a_record_may_carry_more_stopped_probes_than_the_old_direction_count_allowed",
        "the read-back budget stays at the old direction count, so a record whose tails were probed in every "
        "direction is refused as carrying more stopped probes than exist -- the widening this batch's own "
        "records depend on. Repointed: it first named a p = 1 case, where the old budget of 4 already covers "
        "anything one direction can produce; at p = 2 the old budget is 8 and one route clips 22"),
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
    status = run(MUTATIONS, label="BATCH21", scratch=scratch,
                 log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH21_MUTATIONS.log")
    existing = _existing()
    print(f"\n--- re-running {len(existing)} pinned mutation(s) on the files batch 21 changed ---", flush=True)
    status |= run(existing, label="BATCH21_PINNED", scratch=scratch,
                  log=ROOT / "benchmarks" / "core_v4_false_confidence" / "BATCH21_PINNED_MUTATIONS.log")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
