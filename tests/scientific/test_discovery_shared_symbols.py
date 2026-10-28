"""One physical sample cannot give a shared symbol two different meanings."""
from dataclasses import replace

import pytest

from engcore.scientific.discovery import DiscoveryDataset, DiscoveryFeature
from engcore.scientific.equations import Constant, Symbol
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity


def feature(name, bindings):
    # A constant feature still carries declared sample bindings; consistency is
    # a dataset property, independent of whether this expression uses a symbol.
    return DiscoveryFeature(name, Constant(Quantity(1, "1")), (1., 1.), bindings)


def dataset(features):
    return DiscoveryDataset("synthetic", features, (1., 2.), (0,), (1,), "a" * 64, ("b" * 64,))


@pytest.mark.parametrize("other", [Quantity(2, "A"), Quantity(1, "kg"), Quantity(1001, "mA")])
def test_conflicting_shared_symbol_refuses(other):
    left = feature("left", ({"x": Quantity(1, "A")}, {"x": Quantity(2, "A")}))
    right = feature("right", ({"x": other}, {"x": Quantity(2, "A")}))
    with pytest.raises(InvalidScientificProblem, match="shared symbol"):
        dataset((left, right))


def test_equivalent_units_and_distinct_row_values_are_allowed():
    a = feature("a", ({"x": Quantity(1, "A")}, {"x": Quantity(2, "A")}))
    b = feature("b", ({"x": Quantity(1000, "mA")}, {"x": Quantity(2000, "mA")}))
    assert dataset((a, b)).features == (a, b)


def test_actual_contradictory_symbol_columns_are_rejected():
    a = DiscoveryFeature("linear", Symbol("x"), (2., 3.),
                         ({"x": Quantity(2, "1")}, {"x": Quantity(3, "1")}))
    b = DiscoveryFeature("square", Symbol("x"), (4., 9.),
                         ({"x": Quantity(4, "1")}, {"x": Quantity(9, "1")}))
    with pytest.raises(InvalidScientificProblem, match="shared symbol"):
        dataset((a, b))


def test_dataset_reconstruction_cannot_bypass_consistency():
    a = feature("a", ({"x": Quantity(1, "A")}, {"x": Quantity(2, "A")}))
    d = dataset((a,))
    bad = feature("bad", ({"x": Quantity(1, "A")}, {"x": Quantity(3, "A")}))
    with pytest.raises(InvalidScientificProblem, match="shared symbol"):
        replace(d, features=(a, bad))
