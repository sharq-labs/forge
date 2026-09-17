"""Batch 21 of the 2026-09-16 core re-audit: what the local route's probes MEASURE (I-08 part B).

Part A made the probe basis and the scaling downgrade independent of declared units. Part B is the three
problems about what the probes measure, all on the invariant basis part A built.

* **R-13.** Each probed direction is bounded ALONE. A residual curvature of -0.099 on every pair of 10
  parameters passes every probe at index 0.0992 -- under the 0.10 downgrade -- while along the equal-weight
  direction the true chi-square rise at 2, 3 and 6 reported sd is 0.5, 1.303 and 9.068 against a Gaussian's
  4, 9 and 36. The true sd there is 2.24x the reported one.
* **R-14.** The 3 and 6 sd tail probes run along the p axes only, so a posterior that is exactly Gaussian on
  both axes out to 6 sd and saturates along its diagonals is SUPPORTED with no reason at all.
* **R-15.** A tail probe beyond a declared bound is dropped without being counted, so pulling a bound from
  6.01 to 5.99 posterior sd RAISES the claim.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH21_THRESHOLD_PROTOCOL.json`. No new threshold: the
curvature gate reuses NONLINEARITY_DOWNGRADE and NONLINEARITY_REFUSE, because the matrix index IS the
supremum over all unit directions of the per-direction index those two already threshold; the clipped-probe
floor IS PROBE_SD, the radius the nonlinearity probes already cover.

All twelve reproductions were committed as strict xfails in `1b1bafae`, before any of part B was written,
and each was confirmed there to fail on its own assertion. The markers came off in the implementing commit.
"""

from __future__ import annotations

import math

import false_confidence_cases as F
import hybrid_synthetic as S
import numpy as np
import pytest

from engcore.hybrid_uq import MultistartPolicy, RouteClaim, RouteReason
from engcore.hybrid_uq.vocabulary import HybridUQError


def _module():
    import engcore.hybrid_uq.local_gaussian as module

    return module


def _local(problem, multistart=None):
    """``multistart=False`` runs the route with no uniqueness search, the way the audit's own cases do."""
    from engcore.hybrid_uq import local_gaussian_posterior

    policy = None if multistart is False else (multistart if multistart is not None else MultistartPolicy())
    return local_gaussian_posterior(problem.calibrate(), problem.observations, problem.forward,
                                    multistart=policy)


def _symbol(module, name):
    """A named helper, asserted rather than assumed, so a reproduction fails on its assertion."""
    value = getattr(module, name, None)
    assert value is not None, f"engcore.hybrid_uq.local_gaussian.{name} is what part B adds"
    return value


def _bounds(diagnostics):
    """``curvature_eigenvalue_bounds``, asserted rather than assumed, for the same reason."""
    assert hasattr(diagnostics, "curvature_eigenvalue_bounds"), (
        "RouteDiagnostics records the extreme eigenvalues of the curvature matrix it was judged on")
    return tuple(diagnostics.curvature_eigenvalue_bounds)


def _count(diagnostics, name):
    assert hasattr(diagnostics, name), f"RouteDiagnostics records {name}"
    return int(getattr(diagnostics, name))


def _rises_for(module, matrix):
    """The probe rises a posterior with whitened curvature ``matrix`` would produce, in the route's own keys."""
    p = len(matrix)
    out = {}
    probe = module.PROBE_SD
    for label, direction in _symbol(module, "_labelled_probe_directions")(np.ones(p), np.eye(p)):
        # `_labelled_probe_directions` is handed the identity basis, so `direction` IS the whitened direction
        for sign in (1.0, -1.0):
            u = sign * probe * np.asarray(direction, dtype=float)
            out[(label, sign)] = float(u @ np.asarray(matrix, dtype=float) @ u)
    return out


# =====================================================================
# R-13: the curvature matrix
# =====================================================================
def test_r13_the_matrix_is_recovered_exactly_from_the_probes_already_paid_for():
    """No new forward evaluation: a local quadratic is fully determined by the axes and the diagonals."""
    module = _module()
    matrix = np.array([[1.0, -0.4, 0.2], [-0.4, 0.8, 0.05], [0.2, 0.05, 1.3]])
    built, indices = _symbol(module, "_curvature_matrix")(3, _rises_for(module, matrix))
    assert indices == (0, 1, 2), indices
    assert np.allclose(built, matrix, atol=1e-12), built


# ADDED while running batch 21's guard mutations, not preregistered. B21d -- accepting ONE sign as the
# sign-averaged rise -- SURVIVED, because the recovery test above feeds every probe, so a rule about a
# MISSING probe is invisible to it. A one-sided second difference is a first difference and carries the
# linear term the averaging exists to cancel, so the index it feeds is not a curvature at all.
def test_r13_an_index_whose_other_sign_was_never_probed_is_left_out_of_the_matrix():
    module = _module()
    matrix = np.array([[1.0, -0.4, 0.2], [-0.4, 0.8, 0.05], [0.2, 0.05, 1.3]])
    rises = _rises_for(module, matrix)
    del rises[(("axis", 1), -1.0)]
    built, indices = _symbol(module, "_curvature_matrix")(3, rises)
    assert indices == (0, 2), indices
    assert np.allclose(built, matrix[np.ix_([0, 2], [0, 2])], atol=1e-12), built
    # and with only one index left there is no matrix at all, rather than a 1x1 one that repeats an axis probe
    for label in (("axis", 0), ("axis", 2)):
        del rises[(label, -1.0)]
    assert _symbol(module, "_curvature_matrix")(3, rises) is None


def test_r13_the_index_is_the_supremum_of_the_per_direction_index():
    """The identity the gate stands on, which is why it needs no new threshold."""
    module = _module()
    rng = np.random.default_rng(20260917)
    for _ in range(20):
        a = rng.normal(size=(4, 4))
        matrix = np.eye(4) + 0.3 * (a + a.T) / 2.0
        index, (low, high) = _symbol(module, "_curvature_index")(matrix)
        assert index == pytest.approx(max(abs(high - 1.0), abs(1.0 - low)), rel=1e-12)
        for _ in range(50):
            d = rng.normal(size=4)
            d /= np.linalg.norm(d)
            assert abs(float(d @ matrix @ d) - 1.0) <= index + 1e-12
        # and it is attained, so the index is the supremum and not merely an upper bound
        values = np.linalg.eigvalsh(matrix)
        assert max(abs(values.max() - 1.0), abs(1.0 - values.min())) == pytest.approx(index, rel=1e-12)


def test_r13_an_exactly_gaussian_posterior_has_a_curvature_matrix_of_one():
    """The no-regression half: a linear model must not gain a curvature finding it does not have."""
    post = _local(F.rescaled_slope(1.0, "B21_linear"))
    bounds = _bounds(post.diagnostics)
    assert len(bounds) == 2, bounds
    assert bounds[0] == pytest.approx(1.0, abs=1e-6) and bounds[1] == pytest.approx(1.0, abs=1e-6)
    assert float(post.diagnostics.nonlinearity_index) < 1.0e-6
    assert post.claim is RouteClaim.SUPPORTED, [r.value for r in post.reasons]


def test_r13_a_curvature_error_spread_over_every_pair_is_refused():
    """The audited case, with the arithmetic the protocol preregistered.

    At p = 10 with M = I + c(J - I) and c = -0.099 the eigenvalues are 1.099 (multiplicity 9) and
    1 + 9c = 0.109, so the curvature index is 0.891 -- above NONLINEARITY_REFUSE = 0.50 -- where every
    per-direction probe sat at 0.0992, under the 0.10 downgrade.
    """
    module = _module()
    post = _local(F.collective_curvature_error(), multistart=False)
    low, high = _bounds(post.diagnostics)
    assert low == pytest.approx(0.109, abs=0.01), low
    assert float(post.diagnostics.nonlinearity_index) == pytest.approx(0.891, abs=0.02)
    assert float(post.diagnostics.nonlinearity_index) > module.NONLINEARITY_REFUSE
    assert RouteReason.NONLINEAR_BEYOND_LOCAL_GAUSSIAN in post.diagnostics.refusals
    assert post.claim is RouteClaim.REFUSED and post.covariance is None


def test_r13_the_index_must_dominate_the_matrix_the_record_carries():
    """Read-back: a record may not carry extremes its own index does not account for."""
    import dataclasses

    post = _local(F.collective_curvature_error(), multistart=False)
    good = post.diagnostics
    _bounds(good)
    with pytest.raises(HybridUQError):
        dataclasses.replace(good, curvature_eigenvalue_bounds=(0.001, 1.0))


def test_r13_bounds_that_are_not_two_finite_numbers_in_order_are_refused():
    import dataclasses

    good = _local(F.rescaled_slope(1.0, "B21_linear_readback")).diagnostics
    _bounds(good)
    for bad in ((1.2, 0.8), (1.0,), (math.nan, 1.0), (0.9, math.inf)):
        with pytest.raises(HybridUQError):
            dataclasses.replace(good, curvature_eigenvalue_bounds=bad)


# =====================================================================
# R-14: the tails, in every direction the probes cover
# =====================================================================
def test_r14_a_posterior_flat_along_its_diagonals_with_residual_dof_is_refused():
    """The case the audit's own note says I-08 must add: four residual degrees of freedom, so no cap.

    The premise is checked here rather than pinned: exactly Gaussian along both invariant axes out to 6 sd,
    and a rise of 15.92 against the Gaussian's 36 along either diagonal -- a ratio of 0.442, below
    TAIL_REFUSE_RATIO = 0.50.
    """
    module = _module()
    problem = F.off_axis_flat_tail_with_residual_dof()
    post = _local(problem)
    assert int(post.diagnostics.observations) - int(post.diagnostics.parameters) > module.UNDERPOWERED_RESIDUAL_DOF
    assert RouteReason.GOODNESS_OF_FIT_UNDERPOWERED not in post.diagnostics.downgrades
    assert float(post.diagnostics.minimum_tail_rise_ratio) == pytest.approx(0.442, abs=0.02)
    assert RouteReason.TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN in post.diagnostics.refusals
    assert post.claim is RouteClaim.REFUSED and post.covariance is None


def test_r14_the_tail_directions_are_every_probe_direction_plus_the_two_extremes():
    """p^2 + 2 directions: the p invariant axes, the p(p-1) diagonals, and the matrix's two extremes."""
    module = _module()
    cov = np.array([[4.0, 1.8], [1.8, 1.0]])
    lam, vec = _symbol(module, "_invariant_basis")(cov)
    matrix = np.array([[1.0, 0.2], [0.2, 0.7]])
    directions = _symbol(module, "_tail_directions")(lam, vec, matrix, (0, 1))
    assert len(directions) == 2 * 2 + 2, len(directions)
    inverse = np.linalg.inv(cov)
    for delta in directions:
        assert float(delta @ inverse @ delta) == pytest.approx(1.0, rel=1e-9)
    # ADDED while running batch 21's guard mutations, not preregistered. B21i replaced each extreme
    # eigenvector with an axis ALREADY in the set and survived a count and a length check: two duplicate
    # probes measure nothing new, and a direction set that is p^2 + 2 long and p^2 wide is the defect with a
    # larger number on it. The last two directions must BE the mapped eigenvectors.
    scaled = [math.sqrt(max(float(lam[k]), 0.0)) * np.asarray(vec)[:, k] for k in range(len(lam))]
    _values, vectors = np.linalg.eigh(matrix)
    for offset, column in enumerate((0, len(matrix) - 1)):
        want = sum(float(vectors[a, column]) * scaled[a] for a in range(len(matrix)))
        got = directions[len(directions) - 2 + offset]
        assert np.allclose(want, got, rtol=1e-9, atol=1e-12), (column, want, got)
    # without a matrix the two extremes are simply absent, and nothing else changes
    assert len(_symbol(module, "_tail_directions")(lam, vec, None, ())) == 2 * 2


# =====================================================================
# R-15: a clipped probe, compared at its own radius and counted
# =====================================================================
def test_r15_moving_a_bound_across_a_probe_radius_does_not_raise_the_claim():
    """The audited case: REFUSED at bounds of 6.01 posterior sd and SUPPORTED at 5.99."""
    outside = _local(F.tail_beyond_a_bound(6.01))
    inside = _local(F.tail_beyond_a_bound(5.99))
    assert inside.claim is outside.claim, (outside.claim.value, inside.claim.value)
    assert RouteReason.TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN in inside.diagnostics.refusals


def test_r15_a_clipped_probe_is_counted_and_compared_at_the_radius_it_reached():
    inside = _local(F.tail_beyond_a_bound(5.99))
    # p = 1, so one direction, two radii, two signs: the 3 sd probes are inside the box and BOTH 6 sd probes
    # are clipped. Two, not merely more than none -- the count is what says the box stops the probe in both
    # directions, and the exact number was ADDED while running batch 21's mutations: B21n removed the
    # LOWER-bound half of the clipping and survived a `> 0`, because a symmetric box's upper half alone
    # still clips something.
    assert _count(inside.diagnostics, "tail_probes_clipped") == 2
    assert _count(inside.diagnostics, "tail_probes_outside_bounds") == 0
    # ADDED for B21k, which compared a clipped probe's rise with the radius it was ASKED for rather than the
    # one it reached, and survived the 6.01/5.99 pair -- at 5.99 the two radii are within 0.2% of each other,
    # so the audited flip cannot see the difference. At a bound of 2.5 sd it is a factor of 5.8: the rise
    # there is 6.16, which is 0.985 of the 2.5^2 the probe reached and 0.171 of the 6^2 it asked for. The
    # first says the posterior is Gaussian as far out as the box allows; the second refuses it outright.
    clipped_hard = _local(F.tail_beyond_a_bound(2.5))
    assert float(clipped_hard.diagnostics.minimum_tail_rise_ratio) == pytest.approx(0.9854, abs=0.002)
    assert RouteReason.TAIL_HEAVIER_THAN_LOCAL_GAUSSIAN not in clipped_hard.diagnostics.refusals
    assert RouteReason.TAIL_HEAVIER_WITHIN_6_SD not in clipped_hard.diagnostics.downgrades


def test_r15_a_probe_clipped_inside_the_two_sd_probes_is_counted_and_downgrades():
    """Below PROBE_SD there is no tail to measure, so the probe is not used -- and it is not silent either.

    AMENDED against its preregistered form, and recorded as amendment 1 in BATCH21's protocol. The
    preregistration said such a probe "adds the existing NONLINEARITY_PROBE_INCOMPLETE downgrade". It has a
    member of its own instead, because folding the two together made the fact UNOBSERVABLE: along any of the
    fixed probe directions a tail probe is stopped inside PROBE_SD only when that direction's own +/-2 sd
    probe was stopped too, which already emits NONLINEARITY_PROBE_INCOMPLETE. Both guard mutations that
    removed the rule survived -- including the one that removed the whole condition -- and that is what put
    TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS in the vocabulary.
    """
    post = _local(F.tail_beyond_a_bound(1.5))
    assert _count(post.diagnostics, "tail_probes_outside_bounds") > 0
    assert RouteReason.TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS in post.diagnostics.downgrades
    # the OTHER downgrade is still the +/-2 sd probes', which this box also stops, and they are separate facts
    assert RouteReason.NONLINEARITY_PROBE_INCOMPLETE in post.diagnostics.downgrades


def test_r15_the_new_counts_default_to_zero_so_an_old_record_derives_nothing_from_them():
    """Every record written under hybrid_uq.route_diagnostics/2 must still read back."""
    module = _module()
    payload = _local(F.rescaled_slope(1.0, "B21_old_record")).diagnostics.to_dict()
    for key in ("curvature_eigenvalue_bounds", "tail_probes_clipped", "tail_probes_outside_bounds"):
        payload.pop(key, None)
    rebuilt = module.RouteDiagnostics.from_dict(payload)
    assert _bounds(rebuilt) == ()
    assert _count(rebuilt, "tail_probes_clipped") == 0 and _count(rebuilt, "tail_probes_outside_bounds") == 0
    # ADDED while running batch 21's guard mutations, not preregistered. B21o wrote the extremes key
    # unconditionally and survived: popping a key the record does carry says nothing about a record that
    # should not carry it. A p = 1 route builds no curvature matrix -- a 1x1 matrix would just repeat its
    # own axis probe -- so its record must not carry the key at all, or it says a rule was applied where
    # nothing was measured and changes the bytes of every record written before the rule.
    one_parameter = _local(F.tail_beyond_a_bound(6.01)).diagnostics
    assert _bounds(one_parameter) == ()
    assert "curvature_eigenvalue_bounds" not in one_parameter.to_dict()
    assert "tail_probes_clipped" not in one_parameter.to_dict()


def _tight_box(factor: float):
    """A p = 2 posterior whose declared box stops its probes, at ``factor`` times each marginal sd."""
    model = lambda t, x: t[1] * np.exp(-t[0] * x)  # noqa: E731
    x = np.linspace(0.0, 1.0, 8)
    truth = np.array([3.0, 2.0])
    wide = S.Problem("B21_wide", model, x, truth, 0.35, (0.01, 0.01), (20.0, 10.0), truth,
                     observed=model(truth, x))
    from engcore.hybrid_uq import local_gaussian_posterior

    design = local_gaussian_posterior(wide.calibrate(), wide.observations, wide.forward, multistart=None)
    sd = np.sqrt(np.diag(np.asarray(design._design_covariance)))
    return S.Problem(f"B21_tight_{factor:g}", model, x, truth, 0.35, truth - factor * sd,
                     truth + factor * sd, truth, observed=model(truth, x))


# ADDED while running batch 21's guard mutations, not preregistered. B21p narrowed the read-back budget on
# the tail counts back to the p-direction era and SURVIVED every p = 1 case, where the old budget of 4 is
# larger than anything one direction can produce. At p = 2 the old budget is 8 and the new direction set can
# stop 22 probes in one route, so a record this batch itself writes would be refused as carrying more
# stopped probes than exist.
@pytest.mark.parametrize("factor,expected", [(2.6, "clipped"), (0.9, "outside_bounds")])
def test_r15_a_record_may_carry_more_stopped_probes_than_the_old_direction_count_allowed(factor, expected):
    post = _local(_tight_box(factor))
    counts = {name: _count(post.diagnostics, name)
              for name in ("tail_probes_clipped", "tail_probes_outside_bounds")}
    assert counts[f"tail_probes_{expected}"] > 2 * 2 * 2, counts
    if expected == "outside_bounds":
        assert RouteReason.TAIL_NOT_MEASURED_BEYOND_THE_PROBE_RADIUS in post.diagnostics.downgrades
