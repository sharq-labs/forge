"""Conduction-1D against exact solutions written here.

This domain was UNVERIFIED. It is the easiest in the repository to verify
properly, because the problem Forge solves has a closed form:

    du/dt = alpha d2u/dx2,   u(0,t) = u(L,t) = 0,   u(x,0) = sin(pi x / L)

is separable, and the initial condition is exactly the fundamental eigenmode,
so the continuous solution is

    u(x,t) = sin(pi x / L) exp(-alpha pi^2 t / L^2)

with no series and no truncation. Two oracles follow, and they check different
things:

* the CONTINUOUS solution, which the discrete answer must approach as the mesh
  and step refine -- this verifies the discretisation;
* the EXACT DISCRETE solution of the backward-Euler scheme, which the answer
  must match to round-off at any mesh -- this verifies the assembly and the
  linear solve, separately from any discretisation error.

The second is the sharper of the two, and it is available because backward
Euler on a single eigenmode has a closed-form amplification factor. Neither
imports Forge's assembly.
"""

from __future__ import annotations

import math

import pytest

from engcore.domains.thermal.conduction1d.problem import (
    ConductionSlab,
    SlabDiscretization,
)
from engcore.domains.thermal.conduction1d.solver import solve_slab
from engcore.scientific.units.quantity import Quantity

from .oracle_ids import oracle

ORACLE_CONTINUOUS = "ORA-CONDUCTION-ANALYTIC"
ORACLE_DISCRETE = "ORA-CONDUCTION-DISCRETE"


def _forge(length, alpha, end_time, n_cells, n_steps):
    slab = ConductionSlab(
        slab_id="oracle",
        length=Quantity(length, "meter"),
        diffusivity=Quantity(alpha, "meter**2/second"),
        end_time=Quantity(end_time, "second"),
        discretization=SlabDiscretization(n_cells, n_steps),
    )
    return solve_slab(slab, run_id="oracle")


def _continuous_midpoint(length, alpha, end_time):
    """u(L/2, t) for the fundamental mode. Separation of variables."""
    return math.sin(math.pi * 0.5) * math.exp(
        -alpha * math.pi ** 2 * end_time / length ** 2
    )


def _discrete_midpoint(length, alpha, end_time, n_cells, n_steps):
    """The EXACT backward-Euler answer for this initial condition.

    The scheme is (I + r A) u^{n+1} = u^n with A the standard second-difference
    and r = alpha dt / dx^2. On a uniform grid with zero Dirichlet ends the
    eigenvectors of A are sin(k pi x / L), so the initial condition is an
    eigenvector and stays one. Its eigenvalue is

        mu_1 = 4 sin^2(pi dx / (2 L))

    (the standard second-difference eigenvalue, written for mode 1), so each
    step multiplies the amplitude by 1 / (1 + r mu_1) and after N steps the
    midpoint is sin(pi/2) times that factor to the N.

    No matrix is assembled here and nothing is inverted -- which is the point.
    """
    dx = length / n_cells
    dt = end_time / n_steps
    r = alpha * dt / dx ** 2
    mu = 4.0 * math.sin(math.pi * dx / (2.0 * length)) ** 2
    return math.sin(math.pi * 0.5) * (1.0 / (1.0 + r * mu)) ** n_steps


CASES = [
    # (length, alpha, end_time, n_cells, n_steps)
    (1.0, 1e-4, 100.0, 40, 100),
    (0.5, 2.5e-5, 500.0, 64, 200),
    (2.0, 1e-3, 50.0, 80, 50),
    (1.0, 1e-5, 10.0, 20, 20),
]


@pytest.mark.parametrize("length,alpha,end_time,n_cells,n_steps", CASES)
def test_forge_matches_the_exact_backward_euler_answer(
    length, alpha, end_time, n_cells, n_steps
):
    """Assembly and linear solve, checked to round-off.

    The tolerance is a FLOATING-POINT bound, not a physical one: both sides
    evaluate the same closed-form amplification, so anything beyond a few
    hundred ulps accumulated over n_steps products is a real disagreement.
    """
    assert oracle(ORACLE_DISCRETE).independent
    result = _forge(length, alpha, end_time, n_cells, n_steps)
    got = result.value("u:midpoint").magnitude_in("dimensionless")
    expected = _discrete_midpoint(length, alpha, end_time, n_cells, n_steps)
    assert got == pytest.approx(expected, rel=1e-10), (
        f"forge {got!r} vs exact backward-Euler {expected!r}"
    )


@pytest.mark.parametrize("length,alpha,end_time,n_cells,n_steps", CASES)
def test_the_ends_stay_at_the_dirichlet_value(
    length, alpha, end_time, n_cells, n_steps
):
    """Zero at both ends is imposed, so it must be reported as exactly zero."""
    result = _forge(length, alpha, end_time, n_cells, n_steps)
    assert result.value("u:boundary_left").magnitude_in("dimensionless") == 0.0
    assert result.value("u:boundary_right").magnitude_in("dimensionless") == 0.0


def test_the_discrete_answer_converges_to_the_continuous_one():
    """Refining the mesh and the step must approach the analytic solution.

    Backward Euler is first order in time and the second difference is second
    order in space, so halving both should roughly halve the error. Asserting
    the RATIO rather than a fixed tolerance is what makes this a convergence
    test rather than a threshold guess.
    """
    assert oracle(ORACLE_CONTINUOUS).independent
    length, alpha, end_time = 1.0, 1e-4, 100.0
    exact = _continuous_midpoint(length, alpha, end_time)

    errors = []
    for factor in (1, 2, 4, 8):
        got = _forge(length, alpha, end_time, 20 * factor, 25 * factor)
        errors.append(abs(
            got.value("u:midpoint").magnitude_in("dimensionless") - exact
        ))

    for coarse, fine in zip(errors, errors[1:]):
        assert fine < coarse, errors
    # First-order-dominated: each halving should cut the error by at least 1.7.
    assert errors[0] / errors[-1] > 5.0, errors


def test_the_field_decays_and_never_grows():
    """Backward Euler is unconditionally stable, and diffusion only decays.

    A scheme that grew here would be an explicit method mislabelled, or a sign
    error in the assembled operator.
    """
    previous = None
    for end_time in (1.0, 10.0, 100.0, 1000.0):
        got = _forge(1.0, 1e-4, end_time, 40, 100).value(
            "u:max_abs"
        ).magnitude_in("dimensionless")
        assert 0.0 < got <= 1.0 + 1e-12, (end_time, got)
        if previous is not None:
            assert got < previous, (end_time, got, previous)
        previous = got


def test_zero_diffusivity_is_refused_rather_than_silently_frozen():
    """alpha > 0 is a declared bound; the limit itself is not solvable here.

    With alpha = 0 nothing diffuses and the answer is the initial condition
    forever. Forge declares alpha > 0 rather than returning that, and this
    pins the refusal so a future change cannot quietly start answering.
    """
    with pytest.raises(Exception):
        _forge(1.0, 0.0, 100.0, 40, 100)


@pytest.mark.parametrize("scale", [1e-3, 1.0, 1e3])
def test_the_solution_depends_only_on_the_fourier_number(scale):
    """A similarity property with a derivation, not an invented invariant.

    Substituting x = L xi and t = (L^2/alpha) tau into the heat equation
    removes both L and alpha: the dimensionless field depends on position only
    through xi and on time only through Fo = alpha t / L^2. So two slabs with
    the same Fo and the same mesh must report the same midpoint, however
    differently L and alpha are chosen.
    """
    base_length, base_alpha, base_time = 1.0, 1e-4, 100.0
    fourier = base_alpha * base_time / base_length ** 2

    length = base_length * scale
    alpha = base_alpha * scale          # keep alpha/L^2 * t fixed below
    end_time = fourier * length ** 2 / alpha

    a = _forge(base_length, base_alpha, base_time, 40, 100)
    b = _forge(length, alpha, end_time, 40, 100)
    assert a.value("u:midpoint").magnitude_in("dimensionless") == pytest.approx(
        b.value("u:midpoint").magnitude_in("dimensionless"), rel=1e-9
    )
