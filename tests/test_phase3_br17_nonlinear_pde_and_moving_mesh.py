"""Phase 3 BR17 -- nonlinear PDE admission contract and moving-mesh kinematics (no ALE formulation).

Part A (contract only): no Forge template is nonlinear, so every template is
refused for nonlinear execution; the convergence a provider would report is
re-derived from its Newton histories and a CONVERGED claim they do not
support is refused as false convergence.

Part B (kinematics only): with vertices moving linearly in time, the signed
measure of a simplex is a polynomial of degree d in the step fraction and
dV/dt = V div w exactly, so the discrete geometric conservation law holds for
a time rule exactly when the rule integrates degree d - 1.  The expectations
are closed-form (derivations in the comments).

NOT RUN (Phase 3 build phase): docs/work/DEFERRED_VALIDATION.md, DV-80..DV-84.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from engcore.numerical import NumericalRefusal
from engcore.numerical.mesh_quality import MeshQualityPolicy, MeshQualityRefusal
from engcore.numerical.moving_mesh import (
    ALE_FORMULATION_IMPLEMENTED, MeshBoundField, MeshConfiguration, MovingMeshHistory, advance_mesh,
    discrete_gcl_residual, minimal_exact_rule, require_ale_formulation, require_interface_continuity,
    require_same_topology, start_moving_mesh,
)
from engcore.pde import TEMPLATES, PDERefusal, SourcedQuantity
from engcore.pde.nonlinear import (
    InitialGuess, NewtonStepRecord, NonlinearSolveSpec, admit_nonlinear_execution, require_nonlinear_template,
)
from engcore.scientific.solvers.protocol import ConvergenceState
from engcore.scientific.units.quantity import Quantity

POLICY = MeshQualityPolicy(0.05)


def _s(value):
    return Quantity(value, "s")


# ---- part A: nonlinear PDE admission -----------------------------------------------------------------------------


@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_no_existing_template_is_admitted_for_nonlinear_execution(template_id):
    with pytest.raises(PDERefusal, match="OD-P3-3"):
        require_nonlinear_template(TEMPLATES[template_id])


@pytest.mark.parametrize("kwargs", [
    dict(method="picard", residual_atol=1e-8, residual_rtol=0.0, max_iterations=10, jacobian="exact_linearization"),
    dict(method="newton", residual_atol=0.0, residual_rtol=0.0, max_iterations=10, jacobian="exact_linearization"),
    dict(method="newton", residual_atol=1e-8, residual_rtol=0.0, max_iterations=0, jacobian="exact_linearization"),
    dict(method="newton", residual_atol=1e-8, residual_rtol=0.0, max_iterations=10, jacobian="guessed"),
    dict(method="newton_backtracking", residual_atol=1e-8, residual_rtol=0.0, max_iterations=10,
         jacobian="exact_linearization"),
    dict(method="newton", residual_atol=1e-8, residual_rtol=0.0, max_iterations=10, jacobian="exact_linearization",
         max_backtracks=3),
])
def test_the_newton_method_is_declared_in_full(kwargs):
    with pytest.raises(PDERefusal):
        NonlinearSolveSpec(**kwargs)


SPEC = NonlinearSolveSpec("newton", residual_atol=1e-10, residual_rtol=1e-8, max_iterations=5,
                          jacobian="exact_linearization")


def test_a_converged_claim_is_admitted_only_when_every_history_meets_the_declared_test():
    good = (NewtonStepRecord(0, (1.0, 1e-3, 1e-9)), NewtonStepRecord(1, (2.0, 1e-11)))
    assert admit_nonlinear_execution(ConvergenceState.CONVERGED, good, SPEC).accepted
    # max(atol 1e-10, rtol 1e-8 x 1.0) = 1e-8: a final 1e-7 does not meet it
    with pytest.raises(PDERefusal, match="false convergence"):
        admit_nonlinear_execution(ConvergenceState.CONVERGED, (NewtonStepRecord(0, (1.0, 1e-7)),), SPEC)


@pytest.mark.parametrize("steps", [
    (),
    (NewtonStepRecord(0, (1.0, math.nan)),),
    (NewtonStepRecord(0, (1.0,) + (0.5,) * 5 + (1e-12,)),),          # 6 iterations > max_iterations 5
    (NewtonStepRecord(0, (1.0, 1e-12), (0.5,)),),                    # a damped step under undamped newton
    (NewtonStepRecord(0, ()),),
])
def test_unsupported_converged_claims_are_refused(steps):
    with pytest.raises(PDERefusal, match="false convergence"):
        admit_nonlinear_execution(ConvergenceState.CONVERGED, steps, SPEC)


def test_a_failed_solve_is_recorded_as_failed_and_not_applicable_is_refused():
    out = admit_nonlinear_execution(ConvergenceState.MAX_ITERATIONS, (NewtonStepRecord(0, (1.0, 0.9)),), SPEC)
    assert not out.accepted and "max_iterations" in out.reason
    with pytest.raises(PDERefusal, match="NOT_APPLICABLE"):
        admit_nonlinear_execution(ConvergenceState.NOT_APPLICABLE, (), SPEC)


def test_an_initial_guess_is_declared_never_assumed():
    with pytest.raises(PDERefusal):
        InitialGuess()
    guess = InitialGuess(constant=SourcedQuantity(Quantity(300.0, "K"), "assumed", {"basis": "test"}))
    assert guess.to_dict()["classification"] == "initial_guess_not_evidence"


# ---- part B: moving-mesh kinematics ------------------------------------------------------------------------------


def test_there_is_no_ale_formulation_and_nothing_pretends_otherwise():
    assert ALE_FORMULATION_IMPLEMENTED is False
    with pytest.raises(NumericalRefusal, match="OD-P3-4"):
        require_ale_formulation()


def test_only_simplices_move():
    with pytest.raises(MeshQualityRefusal):
        MeshConfiguration("quadrilateral", np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float), [(0, 1, 2, 3)])


def test_mesh_velocity_is_the_displacement_increment_over_the_exact_step():
    state = start_moving_mesh("bar", "interval", np.array([0.0, 1.0, 2.0]), [(0, 1), (1, 2)], _s(0.0), POLICY)
    moved, step = advance_mesh(state, np.array([0.0, 0.1, 0.4]), _s(0.5), POLICY)
    assert moved.velocity.reshape(-1).tolist() == pytest.approx([0.0, 0.2, 0.8])
    assert moved.to_dict()["velocity_unit"] == "meter/second" and moved.to_dict()["displacement_unit"] == "meter"
    assert moved.to_dict()["classification"] == "mesh_motion_not_material_motion"
    assert step.dt.numerator == 1 and step.dt.denominator == 2
    with pytest.raises(NumericalRefusal, match="advance time"):
        advance_mesh(moved, np.zeros(3), _s(0.5), POLICY)


@pytest.mark.parametrize("rule", ["forward_euler", "backward_euler", "midpoint", "trapezoid", "gauss2"])
def test_in_1d_every_rule_satisfies_the_discrete_gcl(rule):
    state = start_moving_mesh("bar", "interval", np.array([0.0, 1.0, 3.0]), [(0, 1), (1, 2)], _s(0.0), POLICY)
    moved, _ = advance_mesh(state, np.array([0.0, 0.5, 0.2]), _s(1.0), POLICY)
    residual = discrete_gcl_residual(state, moved, rule)
    assert residual.exact_for_this_dimension and residual.max_relative <= 1e-14


def test_in_2d_the_midpoint_rule_is_exact_and_forward_euler_is_not():
    # p1: (1,0) -> (1,0.3), p2: (0,1) -> (0.5,1.5): 2A(tau) = 1 + 0.5 tau - 0.15 tau^2, so dA/dtau = 0.25 - 0.15 tau;
    # exact change 0.175; midpoint gives 0.25 - 0.075 = 0.175; forward Euler gives 0.25 (residual 0.075)
    state = start_moving_mesh("tri", "triangle", np.array([(0, 0), (1, 0), (0, 1)], float), [(0, 1, 2)], _s(0.0), POLICY)
    moved, _ = advance_mesh(state, np.array([(0, 0), (0, 0.3), (0.5, 0.5)], float), _s(1.0), POLICY)
    assert discrete_gcl_residual(state, moved, "midpoint").max_abs_m <= 1e-15
    euler = discrete_gcl_residual(state, moved, "forward_euler")
    assert not euler.exact_for_this_dimension and euler.max_abs_m == pytest.approx(0.075)
    assert minimal_exact_rule(2) == "midpoint"


def test_in_3d_the_midpoint_rule_violates_the_gcl_and_two_point_gauss_does_not():
    # every edge column moves: 6 V(tau) = det([[1, 0, t/2], [t/2, 1, 0], [0, t/2, 1]]) = 1 + tau^3 / 8
    # exact change 1/48; midpoint: dV/dtau(1/2) = 3 (1/4) / 48 = 1/64; residual 1/48 - 1/64 = 1/192
    points = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], float)
    state = start_moving_mesh("tet", "tetrahedron", points, [(0, 1, 2, 3)], _s(0.0), POLICY)
    moved, _ = advance_mesh(state, np.array([(0, 0, 0), (0, 0.5, 0), (0, 0, 0.5), (0.5, 0, 0)], float), _s(1.0), POLICY)
    midpoint = discrete_gcl_residual(state, moved, "midpoint")
    assert not midpoint.exact_for_this_dimension and midpoint.max_abs_m == pytest.approx(1.0 / 192.0)
    assert discrete_gcl_residual(state, moved, "gauss2").max_abs_m <= 1e-15
    assert minimal_exact_rule(3) == "gauss2"


def test_a_cell_that_collapses_inside_the_step_is_refused_although_both_ends_are_valid():
    # p1: (1,0) -> (-1,0), p2: (0,1) -> (0,-1): 2A(tau) = (1 - 2 tau)^2, zero at tau = 1/2, 1 at both ends
    state = start_moving_mesh("tri", "triangle", np.array([(0, 0), (1, 0), (0, 1)], float), [(0, 1, 2)], _s(0.0), POLICY)
    with pytest.raises(MeshQualityRefusal, match="during the step"):
        advance_mesh(state, np.array([(0, 0), (-2, 0), (0, -2)], float), _s(1.0), POLICY)


def test_an_inverted_or_degraded_end_state_is_refused():
    state = start_moving_mesh("tri", "triangle", np.array([(0, 0), (1, 0), (0, 1)], float), [(0, 1, 2)], _s(0.0), POLICY)
    with pytest.raises(MeshQualityRefusal):
        advance_mesh(state, np.array([(0, 0), (0, 0), (0, -2)], float), _s(1.0), POLICY)  # apex through the base
    with pytest.raises(MeshQualityRefusal, match="quality"):
        advance_mesh(state, np.array([(0, 0), (99, 0), (0, 0)], float), _s(1.0), POLICY)  # a 100:1 sliver


def test_history_rollback_and_stale_fields():
    state = start_moving_mesh("bar", "interval", np.array([0.0, 1.0]), [(0, 1)], _s(0.0), POLICY)
    history = MovingMeshHistory()
    history.append(state)
    mark = history.checkpoint()
    bound = MeshBoundField("f" * 64, state.digest)
    bound.require_on(history.current)
    moved, _ = advance_mesh(state, np.array([0.0, 0.5]), _s(1.0), POLICY)
    history.append(moved)
    with pytest.raises(NumericalRefusal, match="stale"):
        bound.require_on(history.current)
    with pytest.raises(NumericalRefusal):
        history.append(moved)  # not a successor of the current state
    assert history.rollback(mark).digest == state.digest
    with pytest.raises(NumericalRefusal):
        history.rollback(type(mark)(1, moved.digest))  # that state is gone


def test_topology_changes_and_open_interfaces_are_refused():
    a = start_moving_mesh("left", "interval", np.array([0.0, 1.0]), [(0, 1)], _s(0.0), POLICY)
    b = start_moving_mesh("right", "interval", np.array([1.0, 2.0]), [(0, 1)], _s(0.0), POLICY)
    c = start_moving_mesh("other", "interval", np.array([0.0, 1.0, 2.0]), [(0, 1), (1, 2)], _s(0.0), POLICY)
    with pytest.raises(NumericalRefusal, match="topology"):
        require_same_topology(a, c)
    assert require_interface_continuity(a, [1], b, [0], tolerance_m=1e-12) == 0.0
    moved, _ = advance_mesh(a, np.array([0.0, 0.1]), _s(1.0), POLICY)
    with pytest.raises(NumericalRefusal, match="opened"):
        require_interface_continuity(moved, [1], b, [0], tolerance_m=1e-12)
