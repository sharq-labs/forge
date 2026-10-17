"""Steady 1D conduction on a non-uniform grid (adaptive mesh control slice 3, EXC-1 amendment A2; ERT V1 Big Rock 21).

Exact expectations: with constant k and constant q the solution is quadratic,
and the vertex-centred scheme reproduces it at the nodes of ANY grid, flux ends
included.  NOT YET EXECUTED (build phase): see docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from engcore.domains.thermal_models.conduction1d_nonuniform import (
    BoundaryKind, ConductionBoundary, SteadyConductionProblem, adapt_conduction, solve_steady_conduction,
    temperature_evaluator,
)
from engcore.numerical.mesh_adaptation import AdaptationPolicy, AdaptationStatus, Grid1D
from engcore.scientific.errors import InvalidScientificProblem, UnitCompatibilityError
from engcore.scientific.units.quantity import Quantity

IRREGULAR = Grid1D((0.0, 0.1, 0.35, 0.4, 0.8, 1.0), "m")


def _temperature(kelvin):
    return ConductionBoundary(BoundaryKind.TEMPERATURE, Quantity(kelvin, "kelvin"))


def _flux(w_per_m2):
    return ConductionBoundary(BoundaryKind.INWARD_HEAT_FLUX, Quantity(w_per_m2, "watt/meter**2"))


def _problem(left, right, *, k=lambda x: 2.0, q=lambda x: 4.0, length=1.0):
    return SteadyConductionProblem(Quantity(length, "meter"), k, q, left, right, "test slab")


# ---- exactness on non-uniform grids -----------------------------------------------------------


def test_a_quadratic_solution_is_exact_at_the_nodes_of_an_irregular_grid():
    # k = 2, q = 4 -> u'' = -2; u(0) = 300, u(1) = 310 -> u = 300 + 11 x - x**2
    solution = solve_steady_conduction(_problem(_temperature(300.0), _temperature(310.0)), IRREGULAR)
    expected = [300.0 + 11.0 * x - x * x for x in IRREGULAR.nodes]
    assert solution.temperatures_k == pytest.approx(expected, abs=1e-9)


def test_an_inward_flux_end_is_exact_too():
    # -k u'(0) = 10 -> u'(0) = -5; u = 306 - 5 x - x**2 so that u(1) = 300
    left = solve_steady_conduction(_problem(_flux(10.0), _temperature(300.0)), IRREGULAR)
    assert left.temperatures_k == pytest.approx([306.0 - 5.0 * x - x * x for x in IRREGULAR.nodes], abs=1e-9)
    # inward at the right face is +k u'(1): u = 300 + b x - x**2 with 2 (b - 2) = 6 -> b = 5
    right = solve_steady_conduction(_problem(_temperature(300.0), _flux(6.0)), IRREGULAR)
    assert right.temperatures_k == pytest.approx([300.0 + 5.0 * x - x * x for x in IRREGULAR.nodes], abs=1e-9)


def test_units_are_converted_at_the_boundary_only():
    in_mm = Grid1D(tuple(1000.0 * x for x in IRREGULAR.nodes), "millimeter")
    celsius_end = ConductionBoundary(BoundaryKind.TEMPERATURE, Quantity(26.85, "degC"))  # 300 K, absolute
    reference = solve_steady_conduction(_problem(_temperature(300.0), _temperature(310.0)), IRREGULAR)
    converted = solve_steady_conduction(_problem(celsius_end, _temperature(310.0)), in_mm)
    assert converted.temperatures_k == pytest.approx(reference.temperatures_k, abs=1e-9)


def test_variable_conductivity_converges_at_second_order():
    # k = 1 + x, q = 0, u(0) = 300, u(1) = 301 -> u = 300 + ln(1 + x) / ln 2
    problem = _problem(_temperature(300.0), _temperature(301.0), k=lambda x: 1.0 + x, q=lambda x: 0.0)

    def error(n):
        grid = Grid1D(tuple(np.linspace(0.0, 1.0, n)), "m")
        u = solve_steady_conduction(problem, grid).temperatures_k
        return max(abs(t - (300.0 + math.log1p(x) / math.log(2.0))) for x, t in zip(grid.nodes, u))

    assert error(17) / error(33) > 3.0


# ---- driven by adapt_grid ----------------------------------------------------------------------


def _wall_layer_problem():
    # a source concentrated within ~1 cm of the left wall: q = 1e6 exp(-x / 0.01) W/m**3, k = 1, both ends 300 K
    return _problem(_temperature(300.0), _temperature(300.0), k=lambda x: 1.0, q=lambda x: 1e6 * math.exp(-x / 0.01))


def _wall_layer_exact(x):
    a, d = 1e6, 0.01  # u = -a d**2 exp(-x/d) + c1 x + c0
    c0 = 300.0 + a * d * d
    c1 = 300.0 + a * d * d * math.exp(-1.0 / d) - c0
    return -a * d * d * math.exp(-x / d) + c1 * x + c0


def test_adaptation_refines_at_the_wall_and_beats_a_uniform_grid_of_the_same_size():
    policy = AdaptationPolicy(theta=0.5, tolerance=Quantity(1e-2, "kelvin"), minimum_cell=Quantity(1e-6, "m"),
                              max_cycles=50, max_nodes=10_000)
    record = adapt_conduction(_wall_layer_problem(), Grid1D(tuple(np.linspace(0.0, 1.0, 11)), "m"), policy)
    assert record.status is AdaptationStatus.TOLERANCE_MET_ESTIMATED
    widths = record.grid.cell_widths
    assert widths[0] < widths[-1] / 10

    def nodal_error(grid, values):
        return max(abs(t - _wall_layer_exact(x)) for x, t in zip(grid.nodes, values))

    uniform = Grid1D(tuple(np.linspace(0.0, 1.0, len(record.grid.nodes))), "m")
    uniform_values = solve_steady_conduction(_wall_layer_problem(), uniform).temperatures_k
    assert nodal_error(record.grid, record.values) < nodal_error(uniform, uniform_values)


def test_the_evaluator_solves_afresh_on_every_grid():
    evaluate = temperature_evaluator(_problem(_temperature(300.0), _temperature(310.0)))
    coarse = Grid1D((0.0, 0.5, 1.0), "m")
    assert evaluate(coarse) == pytest.approx((300.0, 305.25, 310.0))
    assert len(evaluate(IRREGULAR)) == len(IRREGULAR.nodes)


# ---- refusals ----------------------------------------------------------------------------------


@pytest.mark.parametrize("k", [lambda x: 0.0, lambda x: -1.0, lambda x: math.nan, lambda x: 1.0 if x < 0.5 else 0.0])
def test_conductivity_must_be_positive_and_finite_everywhere(k):
    with pytest.raises(InvalidScientificProblem, match="conductivity"):
        solve_steady_conduction(_problem(_temperature(300.0), _temperature(310.0), k=k), IRREGULAR)


def test_a_non_finite_source_is_refused():
    with pytest.raises(InvalidScientificProblem, match="source"):
        solve_steady_conduction(_problem(_temperature(300.0), _temperature(310.0), q=lambda x: math.inf), IRREGULAR)


@pytest.mark.parametrize("nodes", [(0.0, 0.5, 0.9), (0.1, 0.5, 1.0), (0.0, 0.5, 1.1)])
def test_the_grid_must_span_the_slab_exactly(nodes):
    with pytest.raises(InvalidScientificProblem, match="spans"):
        solve_steady_conduction(_problem(_temperature(300.0), _temperature(310.0)), Grid1D(nodes, "m"))


def test_two_flux_ends_are_refused_rather_than_pinned():
    with pytest.raises(InvalidScientificProblem, match="up to a constant"):
        _problem(_flux(10.0), _flux(-10.0))


@pytest.mark.parametrize("side", ["left", "right"])
def test_a_missing_boundary_is_never_defaulted(side):
    ends = {"left": _temperature(300.0), "right": _temperature(310.0), side: None}
    with pytest.raises(InvalidScientificProblem, match="never defaulted"):
        _problem(ends["left"], ends["right"])


def test_boundary_values_are_checked():
    with pytest.raises(InvalidScientificProblem, match="absolute zero"):
        _temperature(0.0)
    with pytest.raises(InvalidScientificProblem, match="Quantity"):
        ConductionBoundary(BoundaryKind.TEMPERATURE, 300.0)
    with pytest.raises(UnitCompatibilityError):
        ConductionBoundary(BoundaryKind.INWARD_HEAT_FLUX, Quantity(300.0, "kelvin"))


def test_the_solution_record_is_never_evidence():
    record = solve_steady_conduction(_problem(_temperature(300.0), _temperature(310.0)), IRREGULAR).to_dict()
    assert record["classification"] == "numerical_solution_not_scientific_evidence"
    assert "not validation" in record["notice"]
