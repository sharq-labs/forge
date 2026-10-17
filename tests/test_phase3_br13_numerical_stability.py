"""Phase 3 BR13 -- numerical stability: classified failures, damped Newton, chain acceptance, weighted norms.

* ``numerical.health``: one failure vocabulary and the divergence / stagnation
  rules of the coupling runtime, restated on a residual history.
* ``numerical.nonlinear.DampedNewtonProvider``: Newton and Newton-Armijo with a
  declared, scale-aware acceptance measure; every failure is classified; a
  converged record states that a residual is not a solution-error bound.
* ``numerical.robust``: a fallback chain can no longer loosen acceptance.
* ``ResidualNorm.L2_MEASURE``: a measure-weighted coupling residual, refused
  where no measure is defined.

Expectations are derived by hand in the comments, never read back from the code.
NOT RUN (Phase 3 build phase): docs/work/DEFERRED_VALIDATION.md, DV-65..DV-68.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from engcore.data import BulkDataResolver, InMemoryBulkStore
from engcore.data.field import FieldValue
from engcore.data.mesh import UnstructuredMeshData
from engcore.execution.multiphysics.convergence import ResidualCalculator
from engcore.execution.multiphysics.field_measures import site_measures, weighted_rms
from engcore.numerical import (
    NumericalDiagnostics, NumericalMethod, NumericalProblem, NumericalRefusal, OperatorIdentity, ProblemKind,
    UnitBoundary, VariableSpec,
)
from engcore.numerical.health import (
    RESIDUAL_IS_NOT_AN_ERROR_BOUND, HistoryPolicy, NumericalFailureClass, ResidualScaling, classify_history,
    diverging, stagnating,
)
from engcore.numerical.nonlinear import DampedNewtonProvider, acceptance_measure
from engcore.numerical.robust import ChainAcceptance, solve_with_method_chain
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import CellType, FieldDefinition, FieldLocation, StructuredMesh
from engcore.scientific.multiphysics import ConvergenceCriterion, ResidualNorm
from engcore.scientific.solvers.protocol import ConvergenceState, SolverSettings
from engcore.scientific.units.quantity import Quantity

OPERATOR = OperatorIdentity("phase3.test_operator", "1", "b" * 64, "declared")


def _problem(residual, n=1, x0=(1.0,), jacobian=None, pid="p3"):
    boundary = UnitBoundary(tuple(VariableSpec(f"x{i}", "m") for i in range(n)))
    operands = {"residual": residual}
    if jacobian is not None:
        operands["jacobian"] = jacobian
    return NumericalProblem(pid, ProblemKind.NONLINEAR_ROOT, OPERATOR, boundary, operands,
                            initial={f"x{i}": Quantity(x0[i], "m") for i in range(n)})


def _newton(name="newton", tolerances=None, **options):
    base = {"max_iterations": 50}
    if name == "newton_armijo":
        base.update({"armijo_c1": 1e-4, "backtrack_factor": 0.5, "max_backtracks": 30})
    base.update(options)
    return NumericalMethod(name, SolverSettings(tolerances or {"residual_atol": 1e-12, "step_rtol": 1e-15}, base))


# ---- health vocabulary ----------------------------------------------------------------------------------------


def test_history_detectors_follow_the_runtime_rules():
    # latest / first = 3 > 2: diverging; 1.5 < 2: not
    assert diverging([1.0, 0.5, 3.0], 2.0)
    assert not diverging([1.0, 0.5, 1.5], 2.0)
    assert not diverging([1.0, 9.0], None)
    # best before the last 2 is 0.5; the last two (0.6, 0.5) do not beat it -> stagnating
    assert stagnating([1.0, 0.5, 0.6, 0.5], 2)
    assert not stagnating([1.0, 0.5, 0.6, 0.4], 2)
    assert classify_history([1.0, math.nan], HistoryPolicy())[0] is NumericalFailureClass.NON_FINITE
    assert classify_history([1.0, 0.1], HistoryPolicy(2.0, 2)) == (None, "")


@pytest.mark.parametrize("kwargs", [{"divergence_factor": 1.0}, {"divergence_factor": math.inf},
                                    {"stagnation_window": 1}, {"stagnation_window": True}])
def test_history_policy_refuses_meaningless_rules(kwargs):
    with pytest.raises(NumericalRefusal):
        HistoryPolicy(**kwargs)


def test_residual_scaling_is_declared_never_inferred():
    # components 1e6 and 1e-6 scaled by 1e6 and 1e-6 are both 1: the measure is 1
    assert ResidualScaling((1e6, 1e-6)).measure(np.array([1e6, -1e-6])) == pytest.approx(1.0)
    assert ResidualScaling().measure(np.array([1e6, -1e-6])) == 1e6
    assert ResidualScaling().label == "linf_unscaled"
    with pytest.raises(NumericalRefusal):
        ResidualScaling((1.0, 0.0))
    with pytest.raises(NumericalRefusal):
        ResidualScaling((1.0,)).measure(np.array([1.0, 2.0]))


def test_diagnostics_without_a_failure_class_keep_their_serialized_form():
    keys = set(NumericalDiagnostics().to_dict())
    assert "failure_class" not in keys and "step_lengths" not in keys
    tagged = NumericalDiagnostics(failure_class="diverging", step_lengths=(1.0, 0.5)).to_dict()
    assert tagged["failure_class"] == "diverging" and tagged["step_lengths"] == [1.0, 0.5]


# ---- damped Newton --------------------------------------------------------------------------------------------


def test_newton_converges_on_a_square_root_and_states_what_convergence_is_not():
    problem = _problem(lambda x: np.array([x[0] ** 2 - 2.0]), jacobian=lambda x: np.array([[2.0 * x[0]]]))
    record = DampedNewtonProvider().execute(problem, _newton())
    assert record.convergence is ConvergenceState.CONVERGED
    assert record.outputs["x0"].magnitude == pytest.approx(math.sqrt(2.0), rel=1e-12)
    assert RESIDUAL_IS_NOT_AN_ERROR_BOUND in record.diagnostics.warnings
    assert record.diagnostics.failure_class is None
    assert set(record.diagnostics.step_lengths) == {1.0}  # undamped by construction
    assert record.diagnostics.residual_history[-1] <= 1e-12


@pytest.mark.parametrize("method", [
    NumericalMethod("newton", SolverSettings({"step_rtol": 1e-12}, {"max_iterations": 5})),          # no residual_atol
    NumericalMethod("newton", SolverSettings({"residual_atol": 1e-12}, {"max_iterations": 5})),      # no step_rtol
    NumericalMethod("newton", SolverSettings({"residual_atol": 1e-12, "step_rtol": 1e-12}, {})),     # no max_iterations
    NumericalMethod("newton_armijo", SolverSettings({"residual_atol": 1e-12, "step_rtol": 1e-12},
                                                    {"max_iterations": 5})),                         # no line-search options
])
def test_nothing_the_acceptance_depends_on_is_defaulted(method):
    problem = _problem(lambda x: np.array([x[0] - 1.0]), jacobian=lambda x: np.array([[1.0]]))
    with pytest.raises(NumericalRefusal):
        DampedNewtonProvider().execute(problem, method)


def test_a_missing_jacobian_needs_a_declared_finite_difference_step():
    problem = _problem(lambda x: np.array([x[0] ** 3 - 8.0]), x0=(3.0,))
    with pytest.raises(NumericalRefusal, match="finite_difference_step"):
        DampedNewtonProvider().execute(problem, _newton())
    record = DampedNewtonProvider().execute(problem, _newton(finite_difference_step=1e-7))
    assert record.succeeded and record.outputs["x0"].magnitude == pytest.approx(2.0, rel=1e-9)
    assert any("finite differences" in w for w in record.diagnostics.warnings)


def test_a_non_square_system_is_refused_not_solved_in_least_squares():
    problem = _problem(lambda x: np.array([x[0] - 1.0, x[0] - 2.0]), jacobian=lambda x: np.array([[1.0], [1.0]]))
    with pytest.raises(NumericalRefusal, match="square"):
        DampedNewtonProvider().execute(problem, _newton())


def test_full_newton_on_arctan_diverges_and_armijo_damping_converges():
    # Newton on atan(x) from 1.5 overshoots: x -> -1.69 -> 2.32 -> -5.11 -> 32.2; |atan| grows 0.98 -> 1.54,
    # past 1.5x the first residual at the fourth step.  Backtracking keeps |atan| decreasing and reaches 0.
    residual = lambda x: np.array([math.atan(x[0])])  # noqa: E731
    jacobian = lambda x: np.array([[1.0 / (1.0 + x[0] ** 2)]])  # noqa: E731
    problem = _problem(residual, x0=(1.5,), jacobian=jacobian)
    full = DampedNewtonProvider().execute(problem, _newton(divergence_factor=1.5))
    assert full.convergence is ConvergenceState.DIVERGED
    assert full.diagnostics.failure_class == NumericalFailureClass.DIVERGING.value
    assert not full.outputs  # the last iterate is withheld
    damped = DampedNewtonProvider().execute(problem, _newton("newton_armijo"))
    assert damped.convergence is ConvergenceState.CONVERGED
    assert abs(damped.outputs["x0"].magnitude) <= 1e-12
    assert min(damped.diagnostics.step_lengths) < 1.0  # it actually damped


def test_a_singular_jacobian_is_classified_not_pseudo_inverted():
    # x0 + x1 = 1 and 2 x0 + 2 x1 = 3 is inconsistent; its Jacobian [[1,1],[2,2]] is singular
    problem = _problem(lambda x: np.array([x[0] + x[1] - 1.0, 2 * x[0] + 2 * x[1] - 3.0]), n=2, x0=(0.0, 0.0),
                       jacobian=lambda x: np.array([[1.0, 1.0], [2.0, 2.0]]))
    record = DampedNewtonProvider().execute(problem, _newton())
    assert record.convergence is ConvergenceState.FAILED
    assert record.diagnostics.failure_class == NumericalFailureClass.SINGULAR_JACOBIAN.value


def test_a_declared_condition_limit_refuses_a_nearly_singular_jacobian():
    eps = 1e-10  # cond([[1, 1], [1, 1 + eps]]) ~ 4 / eps = 4e10 > 1e8
    problem = _problem(lambda x: np.array([x[0] + x[1] - 2.0, x[0] + (1 + eps) * x[1] - 2.0]), n=2, x0=(0.0, 0.0),
                       jacobian=lambda x: np.array([[1.0, 1.0], [1.0, 1.0 + eps]]))
    record = DampedNewtonProvider().execute(problem, _newton(condition_limit=1e8))
    assert record.diagnostics.failure_class == NumericalFailureClass.SINGULAR_JACOBIAN.value


def test_a_non_finite_residual_is_a_classified_numerical_failure():
    problem = _problem(lambda x: np.array([np.log(x[0])]), x0=(-1.0,), jacobian=lambda x: np.array([[1.0 / x[0]]]))
    record = DampedNewtonProvider().execute(problem, _newton())
    assert record.convergence is ConvergenceState.DIVERGED
    assert record.diagnostics.failure_class == NumericalFailureClass.NON_FINITE.value


def test_a_vanishing_step_with_a_large_residual_is_never_convergence():
    # (x - 1)^3 has a triple root: Newton steps are (x - 1) / 3.  With step_rtol 1e-3 the step test fires near
    # |x - 1| ~ 6e-3, where the residual (~2e-7) is far above residual_atol 1e-30.
    problem = _problem(lambda x: np.array([(x[0] - 1.0) ** 3]), x0=(2.0,), jacobian=lambda x: np.array([[3 * (x[0] - 1.0) ** 2]]))
    record = DampedNewtonProvider().execute(problem, _newton(tolerances={"residual_atol": 1e-30, "step_rtol": 1e-3}))
    assert record.convergence is ConvergenceState.NOT_CONVERGED
    assert record.diagnostics.failure_class == NumericalFailureClass.STEP_STAGNATION.value


def test_an_exhausted_budget_is_an_iteration_limit():
    problem = _problem(lambda x: np.array([(x[0] - 1.0) ** 3]), x0=(2.0,), jacobian=lambda x: np.array([[3 * (x[0] - 1.0) ** 2]]))
    record = DampedNewtonProvider().execute(problem, _newton(tolerances={"residual_atol": 1e-30, "step_rtol": 0.0},
                                                             max_iterations=3))
    assert record.convergence is ConvergenceState.MAX_ITERATIONS
    assert record.diagnostics.failure_class == NumericalFailureClass.ITERATION_LIMIT.value


def test_scales_change_what_is_accepted_and_the_record_names_the_measure():
    # F = (x - 1) * 1e-6: unscaled, x0 = 2 already has measure 1e-6 <= 1e-5 and is accepted without a step;
    # scaled by 1e-6 the measure is 1 > 1e-5, and one Newton step solves the linear residual exactly.
    problem = _problem(lambda x: np.array([1e-6 * (x[0] - 1.0)]), x0=(2.0,), jacobian=lambda x: np.array([[1e-6]]))
    tol = {"residual_atol": 1e-5, "step_rtol": 1e-15}
    unscaled = DampedNewtonProvider().execute(problem, _newton(tolerances=tol))
    assert unscaled.succeeded and unscaled.outputs["x0"].magnitude == 2.0
    scaled = DampedNewtonProvider().execute(problem, _newton(tolerances=tol, residual_scales=(1e-6,)))
    assert scaled.succeeded and scaled.outputs["x0"].magnitude == pytest.approx(1.0)
    assert any("linf_scaled" in w for w in scaled.diagnostics.warnings)


# ---- method chains cannot loosen acceptance --------------------------------------------------------------------


def test_a_chain_of_methods_with_different_tolerances_is_refused_without_a_chain_acceptance():
    problem = _problem(lambda x: np.array([x[0] - 1.0]), jacobian=lambda x: np.array([[1.0]]))
    strict = _newton(tolerances={"residual_atol": 1e-14, "step_rtol": 1e-15})
    loose = _newton("newton_armijo", tolerances={"residual_atol": 1e-2, "step_rtol": 1e-15})
    with pytest.raises(NumericalRefusal, match="different tolerances"):
        solve_with_method_chain(DampedNewtonProvider(), problem, (strict, loose))


def test_a_chain_cannot_loosen_acceptance_through_residual_scales_either():
    # identical tolerances, but the second method's scales (1e6) make its measure 1e6 times smaller
    problem = _problem(lambda x: np.array([x[0] - 1.0]), jacobian=lambda x: np.array([[1.0]]))
    plain = _newton()
    scaled = _newton("newton_armijo", residual_scales=(1e6,))
    with pytest.raises(NumericalRefusal, match="acceptance options"):
        solve_with_method_chain(DampedNewtonProvider(), problem, (plain, scaled))


def test_a_looser_methods_convergence_is_rejected_by_the_chain_acceptance():
    # x^3 - 8 from 3: one Newton step gives 3 - 19/27 = 2.296, residual 4.11 -- within a 5.0 tolerance, so the
    # loose method converges; the chain's 1e-9 acceptance refuses it and moves on to the strict method.
    residual = lambda x: np.array([x[0] ** 3 - 8.0])  # noqa: E731
    problem = _problem(residual, x0=(3.0,), jacobian=lambda x: np.array([[3 * x[0] ** 2]]))
    loose = _newton(tolerances={"residual_atol": 5.0, "step_rtol": 0.0})
    strict = _newton("newton_armijo", tolerances={"residual_atol": 1e-12, "step_rtol": 0.0})
    chain = solve_with_method_chain(DampedNewtonProvider(), problem, (loose, strict),
                                    acceptance=ChainAcceptance(1e-9))
    assert chain.succeeded and chain.accepted.method.method == "newton_armijo"
    first = chain.attempts[0]
    assert first.record.succeeded and first.rejected_by_acceptance
    assert "rejected_by_acceptance" in first.to_dict()
    assert chain.to_dict()["acceptance"]["residual_atol"] == 1e-9
    assert acceptance_measure(problem, chain.accepted, ResidualScaling()) <= 1e-9


def test_a_chain_without_acceptance_keeps_its_serialized_form():
    problem = _problem(lambda x: np.array([x[0] - 1.0]), jacobian=lambda x: np.array([[1.0]]))
    chain = solve_with_method_chain(DampedNewtonProvider(), problem, (_newton(), _newton("newton_armijo")))
    assert "acceptance" not in chain.to_dict()
    assert "rejected_by_acceptance" not in chain.attempts[0].to_dict()


# ---- measure-weighted coupling residual ------------------------------------------------------------------------


def _two_triangles(store):
    # a large triangle (area 50) and a small one (area 0.5) sharing no vertex
    points = np.array([(0, 0), (10, 0), (0, 10), (20, 0), (21, 0), (20, 1)], float)
    return UnstructuredMeshData("tri", CellType.TRIANGLE, points, np.array([(0, 1, 2), (3, 4, 5)])).store(store)


def _field(store, mesh, values, location=FieldLocation.CELL):
    definition = FieldDefinition("q", "W/m**2", mesh.mesh_id, location)
    record, _ = FieldValue(definition, mesh, np.asarray(values, float)).store(store)
    return record


def test_cell_measures_weight_a_residual_by_area_not_by_site_count():
    store = InMemoryBulkStore()
    mesh = _two_triangles(store)
    weights, rule = site_measures(mesh, FieldLocation.CELL, BulkDataResolver(store))
    assert rule == "triangle_area" and weights.tolist() == pytest.approx([50.0, 0.5])
    # a unit change on the large cell only: RMS over sites is sqrt(1/2); weighted it is sqrt(50 / 50.5)
    calculator = ResidualCalculator(BulkDataResolver(store), {mesh.mesh_id: mesh})
    before, after = _field(store, mesh, [0.0, 0.0]), _field(store, mesh, [1.0, 0.0])
    tol = Quantity(0.0, "W/m**2")
    l2 = calculator.compare(ConvergenceCriterion("e", 0.0, tol, ResidualNorm.L2), before, after, unit="W/m**2")
    lm = calculator.compare(ConvergenceCriterion("e", 0.0, tol, ResidualNorm.L2_MEASURE), before, after, unit="W/m**2")
    assert l2.absolute.magnitude == pytest.approx(math.sqrt(0.5))
    assert lm.absolute.magnitude == pytest.approx(math.sqrt(50.0 / 50.5))
    assert lm.norm == "l2_measure" and l2.norm == "l2"


def test_lumped_node_measures_sum_to_the_support_measure():
    store = InMemoryBulkStore()
    mesh = _two_triangles(store)
    weights, _ = site_measures(mesh, FieldLocation.NODE, BulkDataResolver(store))
    # each triangle gives a third of its area to each vertex
    assert weights.tolist() == pytest.approx([50 / 3] * 3 + [0.5 / 3] * 3)
    structured = StructuredMesh("s", Quantity(2.0, "m"), Quantity(1.0, "m"), 3, 2)
    node, rule = site_measures(structured, FieldLocation.NODE, BulkDataResolver(store))
    # dx = 1, dy = 1: trapezoid weights (0.5, 1, 0.5) x (0.5, 0.5)
    assert rule.startswith("structured_node_trapezoid")
    assert node.tolist() == pytest.approx([0.25, 0.5, 0.25, 0.25, 0.5, 0.25]) and node.sum() == pytest.approx(2.0)


def test_a_vector_field_shares_one_weight_per_site():
    assert weighted_rms(np.array([[3.0, 4.0], [0.0, 0.0]]), np.array([1.0, 1.0]), 2) == pytest.approx(math.sqrt(25 / 2))


def test_supports_without_a_defined_measure_are_refused():
    store = InMemoryBulkStore()
    quad = UnstructuredMeshData("q", CellType.QUADRILATERAL, np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float),
                                np.array([(0, 1, 2, 3)])).store(store)
    with pytest.raises(InvalidScientificProblem, match="no measure-weighted norm"):
        site_measures(quad, FieldLocation.NODE, BulkDataResolver(store))
    cube = np.array([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], float)
    hexa = UnstructuredMeshData("h", CellType.HEXAHEDRON, cube, np.array([tuple(range(8))])).store(store)
    with pytest.raises(InvalidScientificProblem):
        site_measures(hexa, FieldLocation.CELL, BulkDataResolver(store))


def test_a_scalar_edge_cannot_declare_the_measure_weighted_norm():
    calculator = ResidualCalculator(BulkDataResolver(InMemoryBulkStore()), {})
    criterion = ConvergenceCriterion("e", 0.0, Quantity(0.0, "K"), ResidualNorm.L2_MEASURE)
    with pytest.raises(InvalidScientificProblem, match="scalar"):
        calculator.compare(criterion, Quantity(1.0, "K"), Quantity(2.0, "K"), unit="K")
