"""The audited false-confidence reproductions, as reusable synthetic problems (re-audit 2026-09-16, I-15).

Every case here is one of the reproductions in `benchmarks/core_v4_false_confidence/REAUDIT_2026-09-16.json`,
rebuilt from that record's `reproduction` and `evidence` fields. They live beside `hybrid_synthetic.py` rather
than in it because that module is imported by the certified suites and is pinned in the harness area (R-68).

Each builder returns a `hybrid_synthetic.Problem`. The models take ``(theta, x)`` and most ignore ``x``: their
observations are a fixed short vector with a declared sigma, exactly as the reproductions set them up.
"""

from __future__ import annotations

import numpy as np

from hybrid_synthetic import Problem

THREE = np.arange(3.0)


def _orthogonal_shape(x):
    """A unit residual shape the affine model cannot absorb, so chi-square at the estimate is what it is set to."""
    design = np.column_stack([np.ones_like(x), x])
    q, _ = np.linalg.qr(design)
    for probe in (np.cos(np.pi * np.arange(len(x))), np.sin(np.pi * np.arange(len(x)) / len(x) + 0.7)):
        residual = probe - q @ (q.T @ probe)
        if np.linalg.norm(residual) > 1e-8:
            return residual / np.linalg.norm(residual)
    raise AssertionError("no residual direction outside the affine model's span")


# ---------------------------------------------------------------------------
# R-07 (finding 1): a broad basin dismissed as WORSE_LOCAL_OPTIMUM on peak height alone
# ---------------------------------------------------------------------------
def worse_local_optimum_holds_the_mass():
    """p=1: a narrow optimum at 0 and a broad basin near 5 that holds 79% of the posterior.

    s = exp(-(th/0.5)^2); predictions [th/0.01*s, sqrt(10)*(1-s), (th-5)/10*(1-s)]. The broad basin's
    chi-square is 10 above the narrow optimum's, which is above chi2.ppf(0.99, 1) = 6.63, so every refit
    that reaches it is classified WORSE_LOCAL_OPTIMUM and the verdict reads MULTISTART_NO_SECOND_MODE.
    """
    def model(t, _x):
        th = float(t[0])
        s = np.exp(-((th / 0.5) ** 2))
        return np.asarray([th / 0.01 * s, np.sqrt(10.0) * (1.0 - s), (th - 5.0) / 10.0 * (1.0 - s)])

    return Problem("R07_worse_local_optimum", model, THREE, (0.0,), 1.0, (-1.0,), (30.0,), (0.05,),
                   observed=(0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# R-08 (finding 7): a refit budget removes exactly the start that would reach the second mode
# R-01 (finding 5): the same model, with the rebuild dropping the uniqueness caveat
# ---------------------------------------------------------------------------
def second_mode_behind_a_refit_budget():
    """p=1: modes at 0 and 20, switched by s = 1/(1+exp(2(th-10))); predictions [th*s, (th-20)^2(1-s)/4, 0]."""
    def model(t, _x):
        th = float(t[0])
        s = 1.0 / (1.0 + np.exp(np.clip(2.0 * (th - 10.0), -700.0, 700.0)))
        return np.asarray([th * s, (th - 20.0) ** 2 * (1.0 - s) / 4.0, 0.0])

    return Problem("R08_refit_budget", model, THREE, (0.0,), 1.0, (-30.0,), (30.0,), (0.5,),
                   observed=(0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# R-18 (finding 8): retracted starts counted as full-span starts
# ---------------------------------------------------------------------------
def retracted_starts_never_leave_the_basin():
    """p=1: two admissible islands of equal mass (sd 0.1) at 0 and 20; everything between is refused.

    Every Halton start that misses both islands is retracted toward the estimate, so the search never
    leaves the estimate's basin and still reads MULTISTART_NO_SECOND_MODE.
    """
    def model(t, _x):
        th = float(t[0])
        if abs(th) < 1.0:
            return np.asarray([th / 0.1, 0.0, 0.0])
        if abs(th - 20.0) < 1.0:
            return np.asarray([(th - 20.0) / 0.1, 0.0, 0.0])
        # Not admissible. NaN rather than None so the same model builds a grid, where
        # `Problem.grid` marks a non-finite row inadmissible and `Problem.forward` returns None.
        return np.full(3, np.nan)

    return Problem("R18_retracted_starts", model, THREE, (0.0,), 1.0, (-30.0,), (30.0,), (0.0,),
                   observed=(0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# R-05 (finding 15): a narrow second mode inside the box that one quadratic fit at the argmax cannot see
# ---------------------------------------------------------------------------
def narrow_second_mode_inside_the_box():
    """p=1: a(th) = th^2 for th >= 0 and (8 th)^2 below, predictions a(th)*x.

    The broad mode sits near +0.99 with local sd 0.0052; the narrow one near -0.124 with local sd 0.00065,
    which a step of 0.005 aliases away.
    """
    def model(t, x):
        th = float(t[0])
        a = th ** 2 if th >= 0.0 else (8.0 * th) ** 2
        return a * np.asarray(x, dtype=float)

    x = np.linspace(1.0, 2.0, 6)
    return Problem("R05_narrow_second_mode", model, x, (1.0,), 0.05, (-1.0,), (2.0,), (0.9,))


# ---------------------------------------------------------------------------
# R-06 (finding 17): the one-mode box a rebuild with no uniqueness search designs, pinned
# ---------------------------------------------------------------------------
#: The box `route_uncertainty` designed for `hybrid_synthetic.bimodal_two_parameter` at f9bab88 when it was
#: given a GridRebuildPolicy and no multistart: +/- 6 local sd around the estimate of the mode at theta1 = +1,
#: at 60 nodes per axis. It is pinned rather than re-derived so that R-06's case keeps supplying the SAME grid
#: once the router stops designing that box (it is the one-mode grid that is the case, not the router's choice
#: of it). The numbers are recorded in BATCH6_THRESHOLD_PROTOCOL.json's `what_was_already_seen`.
BIMODAL_ONE_MODE_BOX = ((0.8772477442945313, 1.16794008323988, 60),
                        (-0.051501794106415255, 0.8602397960788308, 60))


def bimodal_one_mode_axes():
    return [np.linspace(lo, hi, nodes) for lo, hi, nodes in BIMODAL_ONE_MODE_BOX]


# ---------------------------------------------------------------------------
# R-13 (finding 3): a curvature error of -0.099 on every pair, invisible to per-direction probes
# ---------------------------------------------------------------------------
def collective_curvature_error(p: int = 10, level: float = 0.099):
    """p=10: u = theta / S with S = 1 + 0.1 i; predictions [u_1..u_10, 50 copies of u' (M/50) u / 2].

    M = level*I - level*1 1'. Every pairwise and axial probe stays at index 0.099, while the equal-weight
    direction's true curvature is 0.109 of the reported curvature (true sd 2.24x the reported sd).
    """
    scale = 1.0 + 0.1 * np.arange(p)
    M = level * np.eye(p) - level * np.ones((p, p))
    copies = 50

    def model(t, _x):
        u = np.asarray(t, dtype=float) / scale
        quad = float(u @ (M / copies) @ u) / 2.0
        return np.concatenate([u, np.full(copies, quad)])

    x = np.arange(float(p + copies))
    observed = tuple([0.0] * p + [-1.0] * copies)
    return Problem("R13_collective_curvature", model, x, (0.0,) * p, 1.0, (-20.0,) * p, (20.0,) * p, (0.0,) * p,
                   observed=observed)


# ---------------------------------------------------------------------------
# R-14 (finding 4): Gaussian on both axes out to 6 sd, flat along the diagonals beyond about 3 sd
# ---------------------------------------------------------------------------
def off_axis_flat_tail(scale: float = 1.0, label: str = "R14_off_axis_flat_tail"):
    """p=2: u = theta1, v = theta2 / (2 scale), h = (1 + (|u v| / 6)^4)^(-1/8); predictions [u h, v h, 0, 0].

    ``scale`` is a pure restatement of theta2's unit: the posterior of the scaled parameter is the exact
    pushforward of the unscaled one. It is a separate case (R-16) because the local route's probe directions
    come from ``eigh`` of the covariance in DECLARED units, which ``scale`` rotates.
    """
    def model(t, _x):
        u, v = float(t[0]), float(t[1]) / (2.0 * scale)
        h = (1.0 + (abs(u * v) / 6.0) ** 4) ** (-0.125)
        return np.asarray([u * h, v * h, 0.0, 0.0])

    x = np.arange(4.0)
    return Problem(label, model, x, (0.0, 0.0), 1.0, (-20.0, -40.0 * scale), (20.0, 40.0 * scale), (0.1, 0.1 * scale),
                   observed=(0.0, 0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# R-16 (finding 10): the probe directions come from eigh(cov) in DECLARED units, so a unit change moves them
# ---------------------------------------------------------------------------
def coupled_off_axis_flat_tail(scale: float, label: str):
    """R-14's flat-diagonal posterior, with theta1 and theta2 correlated so ``eigh`` rotates with the unit.

    predictions [u h, v h, 0.5 (u + v) h, 0] with u = theta1, v = theta2 / scale and h as in R-14. ``scale``
    is a pure restatement of theta2's unit, so the posterior is the exact pushforward and every dimensionless
    diagnostic -- the nonlinearity index, the tail rise ratio, the claim -- must be identical. They are not:
    the covariance in declared units is correlated, its eigenvectors depend on ``scale``, and the tail probes
    run along them.
    """
    def model(t, _x):
        u, v = float(t[0]), float(t[1]) / scale
        h = (1.0 + (abs(u * v) / 6.0) ** 4) ** (-0.125)
        return np.asarray([u * h, v * h, 0.5 * (u + v) * h, 0.0])

    return Problem(label, model, np.arange(4.0), (0.0, 0.0), 1.0,
                   (-20.0, -20.0 * scale), (20.0, 20.0 * scale), (0.1, 0.1 * scale),
                   observed=(0.0, 0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# R-15 (finding 9): a tail probe beyond a declared bound is dropped without being counted
# ---------------------------------------------------------------------------
def tail_beyond_a_bound(bound: float):
    """p=1: r = th / (1 + (|th| / 3.05)^12)^(1/12); predictions [r, 0.02 th, 0]. Bounds at +/- ``bound`` sd."""
    def model(t, _x):
        th = float(t[0])
        r = th / (1.0 + (abs(th) / 3.05) ** 12) ** (1.0 / 12.0)
        return np.asarray([r, 0.02 * th, 0.0])

    return Problem(f"R15_tail_bound_{bound:g}", model, THREE, (0.0,), 1.0, (-bound,), (bound,), (0.1,),
                   observed=(0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# R-16 / R-26 (findings 10, 13): the same model and data, one parameter restated in a smaller unit
# ---------------------------------------------------------------------------
def rescaled_slope(factor: float, label: str):
    """p=2: y = t0 + (t1 / factor) x, so ``factor`` is a pure restatement of the slope's unit.

    factor = 1 is volts; 1e3 is millivolts; 1e9 is nanovolts. The posterior of the rescaled parameter is the
    exact pushforward of the original, so every claim must be identical and every number must rescale.
    """
    x = np.linspace(0.0, 1.0, 12)

    def model(t, x):
        return float(t[0]) + (float(t[1]) / factor) * np.asarray(x, dtype=float)

    # The start is stated in each parameter's own declared unit: an initial point of 0 for a parameter whose
    # value is 2e9 is not a restatement of the same request, it is a different one.
    return Problem(label, model, x, (1.0, 2.0 * factor), 0.05, (-10.0, -10.0 * factor), (10.0, 10.0 * factor),
                   (0.5, 1.0 * factor), observed=None, seed=20260913)


# ---------------------------------------------------------------------------
# R-03 (finding 2) and R-20 (finding 6): the pooled goodness-of-fit gate
# ---------------------------------------------------------------------------
def gross_misfit_with_ten_precise_points():
    """p=2, n=10, sigma 0.01, residuals scaled so chi-square at the estimate is 72 on 8 dof (chi2/dof = 9)."""
    x = np.linspace(0.0, 1.0, 10)
    sigma = 0.01
    observed = 1.0 + 2.0 * x + _orthogonal_shape(x) * np.sqrt(72.0) * sigma
    return Problem("R03_gross_misfit", lambda t, x: t[0] + t[1] * np.asarray(x, dtype=float), x, (1.0, 2.0), sigma,
                   (-10.0, -10.0), (10.0, 10.0), (0.0, 0.0), observed=tuple(observed))


def dilute(problem, *, count: int, sigma_factor: float):
    """``problem`` with ``count`` observations appended that carry no information about the parameters.

    Each added reading is the model's own prediction at the calibrated estimate, with a sigma ``sigma_factor``
    times the largest declared one, so it adds a degree of freedom and about ``sigma_factor ** -2`` of one
    reading's Fisher information. This is R-03's padding: it buys degrees of freedom and leaves the
    covariance where it was.
    """
    from engcore.inference import GaussianObservation, ObservationSet
    from engcore.scientific.units.quantity import Quantity

    estimate = np.asarray(problem.calibrate().estimate_vector, dtype=float)
    unit = problem.observations.observations[0].value.units
    sigma = float(np.max(problem.sigma)) * float(sigma_factor)
    predicted = float(np.asarray(problem.model(estimate, problem.x), dtype=float)[0])
    added = tuple(
        GaussianObservation(condition_id=f"uninformative{i}", observable_name="y", value=Quantity(predicted, unit),
                            sigma=Quantity(sigma, unit), source_ref=f"synthetic:uninformative:{i}")
        for i in range(int(count)))
    diluted = Problem.__new__(Problem)
    diluted.__dict__.update(problem.__dict__)
    diluted.observations = ObservationSet(problem.observations.observations + added,
                                          dataset_id=problem.observations.dataset_id + ".diluted")
    # The model is evaluated at problem.x, so the added rows need an x each; they carry the same x as the
    # first reading, which is what makes them exact copies of an informative condition with a huge sigma.
    diluted.x = np.concatenate([problem.x, np.full(int(count), problem.x[0])])
    diluted.sigma = np.concatenate([problem.sigma, np.full(int(count), sigma)])
    diluted.observed = np.concatenate([problem.observed, np.full(int(count), predicted)])
    return diluted


def small_dof_variance_ratio(target_chi_square: float, points: int):
    """p=2 with ``points`` observations, so 1 or 2 residual degrees of freedom, at a chosen chi-square."""
    x = np.linspace(0.0, 1.0, points)
    sigma = 0.05
    observed = 1.0 + 2.0 * x + _orthogonal_shape(x) * np.sqrt(float(target_chi_square)) * sigma
    return Problem(f"misfit_dof_{points - 2}", lambda t, x: t[0] + t[1] * np.asarray(x, dtype=float), x, (1.0, 2.0), sigma,
                   (-10.0, -10.0), (10.0, 10.0), (0.0, 0.0), observed=tuple(observed))


# ---------------------------------------------------------------------------
# R-11 (finding 16): the declared upper bound sets the reported width
# ---------------------------------------------------------------------------
def decay_with_upper_bound(bound: float):
    """A decay whose signal is gone within the observation window, so only its rate's UPPER bound is reached.

    y = t1 exp(-t0 x) at x in [0, 1] with a true rate of 30: the curve has decayed to 2e-13 by x = 1, so the
    data rule out every SMALL rate and say nothing about a large one. The posterior's low side is bounded by
    the data and its high side runs to the declared upper bound, which is the one-sided case the both-sides
    domination rule lets through -- and the width reported there is the bound's.
    """
    return Problem(f"R11_decay_bound_{bound:g}", lambda t, x: t[1] * np.exp(-t[0] * np.asarray(x, dtype=float)),
                   np.linspace(0.0, 1.0, 8), (30.0, 2.0), 0.05, (0.01, 0.01), (bound, 10.0), (5.0, 1.0))


# ---------------------------------------------------------------------------
# R-17 (finding 19): a posterior cut by forward-model inadmissibility counts as contained
# ---------------------------------------------------------------------------
#: The local standard deviation of R-17's one-parameter problem, in closed form: sigma / ||x||.
ADMISSIBILITY_CUT_SD = 0.05 / float(np.sqrt(np.sum(np.linspace(1.0, 2.0, 6) ** 2)))


def admissibility_cut(offset_sd: float = 0.5, cut: float = 1.0):
    """p=1: y = t0 x, with the forward model refusing every t0 below ``cut``.

    The optimum sits ``offset_sd`` local standard deviations above the cut, so the posterior is cut off hard
    INSIDE a grid box rather than at a declared bound. Every node past the cut is inadmissible, so no face of
    such a grid ever carries density and ``grid_containment`` reads the grid as containing its posterior.
    """
    def model(t, x):
        th = float(t[0])
        if th < cut:
            return np.full(len(x), np.nan)
        return th * np.asarray(x, dtype=float)

    x = np.linspace(1.0, 2.0, 6)
    truth = cut + float(offset_sd) * ADMISSIBILITY_CUT_SD
    return Problem(f"R17_admissibility_cut_{offset_sd:g}", model, x, (truth,), 0.05, (cut - 1.0,), (cut + 1.0,),
                   (truth,), observed=tuple(truth * x))


def admissibility_cut_grid_axis(problem, cut: float = 1.0, steps_below: float = 2.0, span_sd: float = 8.0):
    """The supplied grid of R-17: a step of 0.6 local sd, starting two steps below the cut.

    Two whole steps below the cut, so the grid's own low face carries no admissible node at all and the cut
    falls strictly between nodes -- which is the case ``grid_containment`` cannot see.
    """
    step = 0.6 * ADMISSIBILITY_CUT_SD
    top = float(problem.spec.initial_vector[0]) + float(span_sd) * ADMISSIBILITY_CUT_SD
    return np.arange(cut - float(steps_below) * step, top, step)
