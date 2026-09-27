"""BIG 11 second re-review (BIG 14 14.1), A2: an output selection cannot shrink or erase the compared difference.

A zero, scaled or non-affine weight map made any two records agree ("within tolerance", ladder level 5) and converted an offset unit
wrongly; a selection is now an affine combination of distinct indices.  (A1, the held UNKNOWN ambient, is tested in the PyBaMM suite.)
"""

from __future__ import annotations

import pytest

from engcore.providers import ComparisonDeclaration, OutputSelection, compare_providers
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity
from tests.test_provider_boundary import _record


@pytest.mark.parametrize("weights", [
    ((( 0, 0.0),),),                      # a zero map: every record reads 0.0
    (((0, 1e-12),),),                     # a scaled map: any difference shrinks below the tolerance
    (((0, 1.0), (1, 1.0)),),              # sums to 2: a degC point would gain 273.15 once instead of twice
    (((0, 1.5), (1, -0.5)),),             # a negative weight
    (((0, 0.5), (0, 0.5)),),              # a repeated index
    (((True, 1.0),),),                    # a truth value as an index
    (((0, float("nan")),),),
    ((),),                                # a point with no term
    (),                                   # no point
])
def test_a2_a_weight_map_that_is_not_an_affine_combination_is_refused(weights):
    with pytest.raises(InvalidScientificProblem):
        OutputSelection(weights=weights)


@pytest.mark.parametrize("kw", [dict(rows=()), dict(rows=(1, 1)), dict(rows=(-1,)), dict(component=-1), dict(component=True)])
def test_a2_rows_and_component_are_distinct_non_negative_indices(kw):
    with pytest.raises(InvalidScientificProblem):
        OutputSelection(**kw)


def test_a2_a_corner_mean_and_a_row_pick_are_still_accepted_and_a_zero_map_cannot_make_two_records_agree():
    OutputSelection(weights=(((0, 0.25), (1, 0.25), (2, 0.25), (3, 0.25)),), rows=(0,))
    decl = ComparisonDeclaration("cell voltage", "V", "identity", Quantity(1e-3, "V"), 0.0, "demo")
    a = _record("alpha", {"v": Quantity(3.7, "V")})
    b = _record("beta", {"v": Quantity(4.2, "V")})
    assert not compare_providers(decl, a, "v", b, "v").within_tolerance              # 0.5 V apart: not within 1 mV
    with pytest.raises(InvalidScientificProblem):
        compare_providers(decl, a, "v", b, "v", a_select=OutputSelection(weights=(((0, 0.0),),)), b_select=OutputSelection(weights=(((0, 0.0),),)))
