"""1D local mesh adaptation (adaptive mesh control slice 2, EXC-1 amendment A1; ERT V1 Big Rock 20).

Exact expectations: for u = x**2 (u'' = 2) the indicator of a cell of width h
is h**2 / 4, which is the exact maximum P1 interpolation error.  NOT YET
EXECUTED (build phase): see docs/work/DEFERRED_VALIDATION.md.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from engcore.numerical import NumericalRefusal
from engcore.numerical.mesh_adaptation import (
    AdaptationPolicy, AdaptationStatus, Grid1D, adapt_grid, cell_indicators, doerfler_mark, refine,
)
from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.units.quantity import Quantity


def _uniform(n, a=0.0, b=1.0):
    return Grid1D(tuple(np.linspace(a, b, n)), "m")


def _policy(**kw):
    base = dict(theta=1.0, tolerance=Quantity(1e-3, "K"), minimum_cell=Quantity(1e-6, "m"), max_cycles=10,
                max_nodes=10_000)
    return AdaptationPolicy(**{**base, **kw})


def _square(grid):
    return [x * x for x in grid.nodes]


# ---- indicators ----------------------------------------------------------------------------


def test_indicator_is_the_exact_p1_error_for_a_quadratic_on_any_grid():
    grid = Grid1D((0.0, 0.1, 0.5, 1.0), "m")
    assert cell_indicators(grid, _square(grid)) == pytest.approx([0.01 / 4, 0.16 / 4, 0.25 / 4])
    uniform = _uniform(5)
    assert cell_indicators(uniform, _square(uniform)) == pytest.approx([0.0625 / 4] * 4)


def test_a_linear_solution_has_no_estimated_error():
    grid = _uniform(6)
    assert cell_indicators(grid, [3.0 * x + 1.0 for x in grid.nodes]) == pytest.approx([0.0] * 5)


def test_values_must_be_finite_and_one_per_node():
    grid = _uniform(4)
    with pytest.raises(NumericalRefusal):
        cell_indicators(grid, [0.0, 1.0, 2.0])
    with pytest.raises(NumericalRefusal):
        cell_indicators(grid, [0.0, math.nan, 1.0, 2.0])


# ---- marking and refinement -----------------------------------------------------------------


def test_doerfler_marks_the_fewest_largest_cells():
    assert doerfler_mark([1.0, 5.0, 3.0, 1.0], 0.5) == [1]
    assert doerfler_mark([1.0, 5.0, 3.0, 1.0], 0.8) == [1, 2]
    assert doerfler_mark([0.0, 0.0], 0.5) == []
    with pytest.raises(NumericalRefusal):
        doerfler_mark([1.0], 0.0)


def test_repeated_corner_refinement_stays_graded():
    grid = Grid1D((0.0, 1.0, 2.0, 3.0, 4.0), "m")
    for _ in range(5):
        grid = refine(grid, [0], minimum_cell=1e-6, max_ratio=2.0)
        widths = grid.cell_widths
        assert np.all(widths[:-1] <= 2.0 * widths[1:] + 1e-12) and np.all(widths[1:] <= 2.0 * widths[:-1] + 1e-12)
    assert grid.cell_widths[0] == pytest.approx(1.0 / 32)


def test_refinement_never_goes_below_the_minimum_cell():
    grid = Grid1D((0.0, 1.0, 2.0), "m")
    assert refine(grid, [0], minimum_cell=0.6, max_ratio=2.0).nodes == grid.nodes


@pytest.mark.parametrize("nodes", [(0.0, 1.0), (0.0, 1.0, 1.0), (0.0, 2.0, 1.0), (0.0, math.nan, 1.0)])
def test_grids_are_validated(nodes):
    with pytest.raises(NumericalRefusal):
        Grid1D(nodes, "m")


# ---- the adaptation loop ---------------------------------------------------------------------


def test_quadratic_meets_the_estimated_tolerance_at_cycle_two_with_seventeen_nodes():
    record = adapt_grid(_square, _uniform(5), _policy(), value_unit="K")
    assert record.status is AdaptationStatus.TOLERANCE_MET_ESTIMATED
    assert [c.node_count for c in record.cycles] == [5, 9, 17]
    assert record.cycles[-1].max_indicator == pytest.approx(0.0625 ** 2 / 4)
    assert record.values == pytest.approx(tuple(_square(record.grid)))  # fresh values on the final grid


def test_a_boundary_layer_is_refined_at_the_wall_not_in_the_far_field():
    def layer(grid):
        return [math.exp(-x / 0.02) for x in grid.nodes]

    record = adapt_grid(layer, _uniform(11), _policy(theta=0.5, tolerance=Quantity(1e-4, "K"), max_cycles=30),
                        value_unit="K")
    widths = record.grid.cell_widths
    assert widths[0] < widths[-1] / 10


def test_budgets_end_the_loop_honestly():
    assert adapt_grid(_square, _uniform(5), _policy(tolerance=Quantity(1e-9, "K"), max_cycles=1),
                      value_unit="K").status is AdaptationStatus.BUDGET_EXHAUSTED
    assert adapt_grid(_square, _uniform(5), _policy(tolerance=Quantity(1e-9, "K"), max_nodes=6),
                      value_unit="K").status is AdaptationStatus.NODE_BUDGET
    assert adapt_grid(_square, _uniform(5), _policy(tolerance=Quantity(1e-9, "K"), minimum_cell=Quantity(0.2, "m")),
                      value_unit="K").status is AdaptationStatus.RESOLUTION_FLOOR


@pytest.mark.parametrize("kw", [dict(theta=0.0), dict(theta=1.5), dict(max_cycles=0), dict(max_nodes=3),
                                dict(minimum_cell=Quantity(0.0, "m")), dict(tolerance=Quantity(0.0, "K")),
                                dict(max_ratio=1.0)])
def test_policy_declarations_are_checked(kw):
    with pytest.raises(NumericalRefusal):
        _policy(**kw)


def test_a_tolerance_stated_as_an_absolute_offset_temperature_is_refused():
    with pytest.raises(ScientificCoreError, match="spread"):
        _policy(tolerance=Quantity(1e-3, "degC"))


def test_the_record_is_never_evidence():
    record = adapt_grid(_square, _uniform(5), _policy(), value_unit="K").to_dict()
    assert record["classification"] == "numerical_mesh_adaptation_not_scientific_evidence"
    assert "not a bound, not validation" in record["notice"]
