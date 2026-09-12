"""A calibrated parameter is identified by what it is, not by what it is called.

The two claims Sprint 8 names explicitly:

    same label, different unit   -> not the same parameter
    same name, different model   -> not automatically identical

and the adversarial matrix that goes with them: a wrong unit, a value outside
physical bounds, a duplicate declaration, a permuted grid, an optimizer
returning outside its box, and a tampered serialized identity.
"""

from __future__ import annotations

import pytest

from engcore.inference.parameters import (
    CalibrationParameterSet,
    ParameterBounds,
    ParameterEstimate,
    ParameterIdentity,
    ParameterIdentityError,
    ParameterTransform,
    bind_parameter_set_to_grid,
    require_parameter_set,
)
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.units.quantity import Quantity

TCR = ModelReference(model_id="electrical.material.linear_tcr", version="0.1.0")
OTHER = ModelReference(model_id="thermal.lumped.capacity", version="0.1.0")


def r_ref(model: ModelReference = TCR, unit: str = "ohm") -> ParameterIdentity:
    return ParameterIdentity(
        name="reference_resistance",
        unit=unit,
        model=model,
        bounds=ParameterBounds(Quantity(0.0, unit), Quantity(10.0, unit)),
    )


def alpha(model: ModelReference = TCR) -> ParameterIdentity:
    return ParameterIdentity(
        name="temperature_coefficient",
        unit="1/kelvin",
        model=model,
        bounds=ParameterBounds(Quantity(-0.01, "1/kelvin"), Quantity(0.01, "1/kelvin")),
    )


# =====================================================================
# The two claims
# =====================================================================

def test_same_label_different_unit_is_not_the_same_parameter():
    """A resistance in ohm and a resistance in milliohm are different records.

    They describe the same physical quantity, and that is exactly why this has
    to be caught: a posterior whose axis is in ohm is not usable by a forward
    model that reads milliohm, and the only thing that ever said which was
    which was a string that is identical in both.
    """
    in_ohm = r_ref(unit="ohm")
    in_milliohm = r_ref(unit="milliohm")

    assert in_ohm.name == in_milliohm.name
    assert not in_ohm.is_same_parameter(in_milliohm)
    assert "unit" in in_ohm.differences(in_milliohm)
    assert in_ohm.digest != in_milliohm.digest


def test_same_name_on_a_different_model_is_not_automatically_identical():
    """Two models both calling something `reference_resistance` is routine."""
    mine, theirs = r_ref(TCR), r_ref(OTHER)

    assert mine.name == theirs.name
    assert mine.unit == theirs.unit
    assert not mine.is_same_parameter(theirs)
    # Exactly `model_id`, and not `model_version`: both models happen to be at
    # 0.1.0, so the difference is located precisely rather than smeared across
    # every field that mentions a model.
    assert mine.differences(theirs) == ("model_id",)


def test_the_same_model_at_a_different_version_is_not_the_same_parameter():
    """A version is part of a model reference, so it is part of the identity."""
    later = ModelReference(model_id=TCR.model_id, version="0.2.0")
    assert r_ref(TCR).differences(r_ref(later)) == ("model_version",)


def test_a_different_admissible_range_is_a_different_parameter():
    wide = r_ref()
    narrow = ParameterIdentity(
        name="reference_resistance",
        unit="ohm",
        model=TCR,
        bounds=ParameterBounds(Quantity(0.0, "ohm"), Quantity(1.0, "ohm")),
    )
    assert wide.differences(narrow) == ("upper",)


def test_a_transform_is_part_of_the_identity():
    """A posterior built in log space is not interchangeable with a linear one."""
    linear = ParameterIdentity(
        "sigma", "ohm", TCR,
        ParameterBounds(Quantity(1e-6, "ohm"), Quantity(1.0, "ohm")),
    )
    logged = ParameterIdentity(
        "sigma", "ohm", TCR,
        ParameterBounds(Quantity(1e-6, "ohm"), Quantity(1.0, "ohm")),
        transform=ParameterTransform.LOG,
    )
    assert linear.differences(logged) == ("transform",)


def test_the_same_range_written_in_two_units_is_the_same_parameter():
    """The converse. Identity is physical, so a unit-equal bound must not split it.

    A digest that called these two different would be as wrong as one that
    called ohm and milliohm the same, and in a way that is harder to notice:
    two declarations of the same science failing to compare equal.
    """
    in_ohm = ParameterIdentity(
        "reference_resistance", "ohm", TCR,
        ParameterBounds(Quantity(0.0, "ohm"), Quantity(10.0, "ohm")),
    )
    stated_in_milliohm = ParameterIdentity(
        "reference_resistance", "ohm", TCR,
        ParameterBounds(Quantity(0.0, "milliohm"), Quantity(10_000.0, "milliohm")),
    )
    assert in_ohm.is_same_parameter(stated_in_milliohm)
    assert in_ohm.digest == stated_in_milliohm.digest


# =====================================================================
# Bounds are physical, not a prior
# =====================================================================

def test_a_value_outside_physical_bounds_is_refused_not_downweighted():
    with pytest.raises(ParameterIdentityError, match="outside its admissible range"):
        r_ref().require_in_bounds(Quantity(-1.0, "ohm"))


def test_a_bound_is_inclusive_at_both_ends():
    parameter = r_ref()
    assert parameter.require_in_bounds(Quantity(0.0, "ohm")) == 0.0
    assert parameter.require_in_bounds(Quantity(10.0, "ohm")) == 10.0


def test_a_bound_check_converts_rather_than_comparing_magnitudes():
    """5000 milliohm is inside [0, 10] ohm, and comparing 5000 to 10 is not."""
    assert r_ref().require_in_bounds(Quantity(5_000.0, "milliohm")) == pytest.approx(5.0)


def test_the_wrong_unit_is_refused_rather_than_reinterpreted():
    with pytest.raises(ParameterIdentityError, match="declared in .* and was given"):
        r_ref().require_in_bounds(Quantity(1.0, "kelvin"))


def test_a_bare_float_is_refused():
    with pytest.raises(ParameterIdentityError, match="takes a Quantity"):
        r_ref().require_in_bounds(1.0)


def test_a_non_finite_parameter_value_cannot_be_built_at_all():
    """Phase 24's "non-finite prediction", and it is refused a layer earlier.

    This test was first written to assert that `require_in_bounds` rejects a
    non-finite magnitude. It does not get the chance: `Quantity` itself refuses
    to hold one, so there is no way to present a NaN parameter to a bounds
    check. Asserted where the refusal actually happens, because a test that
    passes at the wrong layer would go green if the real guard were removed.

    `ParameterBounds.contains` keeps its own finiteness check as
    defence-in-depth; it is currently unreachable through `Quantity`.
    """
    from engcore.scientific.errors import UnitCompatibilityError

    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(UnitCompatibilityError, match="must be finite"):
            Quantity(bad, "ohm")


def test_inverted_bounds_are_refused_at_declaration():
    with pytest.raises(ParameterIdentityError, match="inverted"):
        ParameterBounds(Quantity(10.0, "ohm"), Quantity(0.0, "ohm"))


def test_bounds_in_another_dimension_are_refused_at_declaration():
    with pytest.raises(ParameterIdentityError, match="different dimension"):
        ParameterIdentity(
            "reference_resistance", "ohm", TCR,
            ParameterBounds(Quantity(0.0, "kelvin"), Quantity(10.0, "kelvin")),
        )


def test_a_log_transform_contradicting_its_own_range_is_refused():
    with pytest.raises(ParameterIdentityError, match="contradict"):
        ParameterIdentity(
            "reference_resistance", "ohm", TCR,
            ParameterBounds(Quantity(0.0, "ohm"), Quantity(10.0, "ohm")),
            transform=ParameterTransform.LOG,
        )


def test_a_log_transform_refuses_a_non_positive_value():
    with pytest.raises(ParameterIdentityError, match="cannot take the value"):
        ParameterTransform.LOG.forward(0.0)


# =====================================================================
# The declared set
# =====================================================================

def test_a_duplicate_parameter_declaration_is_refused():
    with pytest.raises(ParameterIdentityError, match="more than once"):
        CalibrationParameterSet((r_ref(), alpha(), r_ref()))


def test_an_empty_parameter_set_is_refused():
    with pytest.raises(ParameterIdentityError, match="at least one parameter"):
        CalibrationParameterSet(())


def test_a_sequence_of_names_is_not_a_parameter_set():
    with pytest.raises(ParameterIdentityError, match="CalibrationParameterSet"):
        require_parameter_set(("reference_resistance", "temperature_coefficient"))


def test_a_value_for_an_undeclared_parameter_is_refused():
    """"Fit any free field on the model" is what this makes impossible."""
    parameters = CalibrationParameterSet((r_ref(), alpha()))
    with pytest.raises(ParameterIdentityError, match="undeclared parameter"):
        parameters.require_all_in_bounds({
            "reference_resistance": Quantity(1.0, "ohm"),
            "temperature_coefficient": Quantity(0.001, "1/kelvin"),
            "debye_temperature": Quantity(343.0, "kelvin"),
        })


def test_a_missing_declared_parameter_is_refused():
    parameters = CalibrationParameterSet((r_ref(), alpha()))
    with pytest.raises(ParameterIdentityError, match="no value supplied"):
        parameters.require_all_in_bounds({"reference_resistance": Quantity(1.0, "ohm")})


def test_values_come_back_in_declared_column_order():
    parameters = CalibrationParameterSet((r_ref(), alpha()))
    got = parameters.require_all_in_bounds({
        "temperature_coefficient": Quantity(0.004, "1/kelvin"),
        "reference_resistance": Quantity(2.0, "ohm"),
    })
    assert got == (2.0, 0.004)


def test_two_sets_differing_in_a_parameter_are_refused():
    mine = CalibrationParameterSet((r_ref(), alpha()))
    theirs = CalibrationParameterSet((r_ref(unit="milliohm"), alpha()))
    with pytest.raises(ParameterIdentityError, match="not the same parameter"):
        mine.require_same_parameters(theirs)


# =====================================================================
# Binding to the grid the existing engine already uses
# =====================================================================

def test_a_grid_whose_axes_are_permuted_is_refused():
    """The failure nothing downstream could detect on its own.

    `AdmittedForwardTable` and `PosteriorGrid` carry `parameter_names` and
    nothing holds them to a declaration. Swap two columns and every array still
    has the right shape, every number is still finite, and the posterior is
    about two different parameters.
    """
    parameters = CalibrationParameterSet((r_ref(), alpha()))
    with pytest.raises(ParameterIdentityError, match="different order"):
        bind_parameter_set_to_grid(
            parameters, ("temperature_coefficient", "reference_resistance")
        )


def test_a_grid_with_the_wrong_axes_is_refused():
    parameters = CalibrationParameterSet((r_ref(), alpha()))
    with pytest.raises(ParameterIdentityError, match="are not the declared"):
        bind_parameter_set_to_grid(parameters, ("reference_resistance", "debye"))


def test_the_matching_grid_binds():
    parameters = CalibrationParameterSet((r_ref(), alpha()))
    bind_parameter_set_to_grid(
        parameters, ("reference_resistance", "temperature_coefficient")
    )


# =====================================================================
# Estimates
# =====================================================================

def test_an_optimizer_returning_outside_its_box_cannot_be_recorded():
    """Phase 24's "optimizer returns outside bounds", caught at the record.

    Checked when the estimate is built rather than trusted from whatever
    produced it: a record that stored an out-of-range value would make the
    violation invisible from that point on.
    """
    with pytest.raises(ParameterIdentityError, match="outside its admissible range"):
        ParameterEstimate(r_ref(), -0.5)


def test_a_non_finite_estimate_is_a_failed_calibration():
    with pytest.raises(ParameterIdentityError, match="non-finite estimate"):
        ParameterEstimate(r_ref(), float("nan"))


def test_an_estimate_carries_its_unit():
    estimate = ParameterEstimate(r_ref(), 2.5)
    assert estimate.value == Quantity(2.5, "ohm")
    assert estimate.identity.key == "electrical.material.linear_tcr@0.1.0:reference_resistance"


# =====================================================================
# Serialization refuses a tampered identity
# =====================================================================

def test_an_identity_round_trips():
    parameter = r_ref()
    assert ParameterIdentity.from_dict(parameter.to_dict()).is_same_parameter(parameter)


def test_an_edited_identity_is_refused_on_read():
    payload = dict(r_ref().to_dict())
    payload["unit"] = "milliohm"
    with pytest.raises(ParameterIdentityError, match="was\n?\\s*edited|edited"):
        ParameterIdentity.from_dict(payload)


def test_a_parameter_set_round_trips_and_refuses_an_edited_member():
    parameters = CalibrationParameterSet((r_ref(), alpha()))
    assert CalibrationParameterSet.from_dict(parameters.to_dict()).digest == parameters.digest

    payload = parameters.to_dict()
    payload["parameters"][0]["name"] = "renamed"
    with pytest.raises(ParameterIdentityError):
        CalibrationParameterSet.from_dict(payload)


def test_an_estimate_round_trips():
    estimate = ParameterEstimate(r_ref(), 2.5)
    assert ParameterEstimate.from_dict(estimate.to_dict()).magnitude == 2.5
