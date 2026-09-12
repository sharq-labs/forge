"""Spatial laws: what they evaluate to, and everything they refuse.

Sprint 5, Phases 2, 3, 4, 12, 13, 14, 17 and 18. A profile is a record of a
law, so it owes what every record here owes — a round trip, a digest over its
own facts, an explicit dimension, and a refusal for every state it cannot
honestly represent.

The refusals are the larger half of this file on purpose. A law that evaluates
is easy; a law that cannot be talked into evaluating something it was never
checked for is the point.
"""

from __future__ import annotations

import functools
import math

import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.fields import (
    BoundaryEdge,
    ConstantProfile,
    HarmonicProfile1D,
    Interpolation,
    LinearProfile1D,
    ProfileAxis,
    SeparableProfile2D,
    SpatialProfile,
    TabulatedProfile1D,
    as_profile,
    edge_axis,
    load_profile,
)
from engcore.scientific.units.quantity import Quantity

K = "kelvin"
FLUX = "watt/meter**2"


def linear(axis=ProfileAxis.Y, intercept=300.0, slope=20.0, unit=K, origin=0.0):
    return LinearProfile1D(
        axis,
        Quantity(intercept, unit),
        Quantity(slope, f"{unit}/meter"),
        Quantity(origin, "meter"),
    )


def harmonic(axis=ProfileAxis.Y, amplitude=1.0, unit="dimensionless", wavenumber=math.pi):
    return HarmonicProfile1D(
        axis, Quantity(amplitude, unit), Quantity(wavenumber, "1/meter")
    )


def table(axis=ProfileAxis.X, coordinates=(0.0, 0.5, 1.0), values=(0.0, 10.0, 0.0), **kw):
    return TabulatedProfile1D(axis, coordinates, values, **kw)


ALL_PROFILES = {
    "constant": ConstantProfile(Quantity(300.0, K)),
    "linear": linear(),
    "harmonic": harmonic(),
    "tabulated": table(unit=FLUX),
    "separable": SeparableProfile2D(
        Quantity(2.0, "watt/meter**3"),
        harmonic(ProfileAxis.X),
        harmonic(ProfileAxis.Y),
    ),
}


# ---- evaluation ---------------------------------------------------------------------
def test_a_constant_is_the_same_everywhere():
    profile = ALL_PROFILES["constant"]
    assert profile.evaluate(x=0.0, y=0.0) == 300.0
    assert profile.evaluate(x=0.9, y=0.1) == 300.0
    assert profile.axes == (), "a constant reads no coordinate"


def test_a_linear_law_rises_along_the_axis_it_declared():
    profile = linear(ProfileAxis.Y, 300.0, 20.0)
    assert profile.evaluate(x=0.0, y=0.0) == pytest.approx(300.0)
    assert profile.evaluate(x=0.0, y=0.5) == pytest.approx(310.0)
    assert profile.evaluate(x=0.0, y=1.0) == pytest.approx(320.0)
    # and not along the other one
    assert profile.evaluate(x=1.0, y=0.0) == pytest.approx(300.0)


def test_a_linear_law_measures_from_its_declared_origin():
    shifted = linear(ProfileAxis.X, 300.0, 20.0, origin=0.5)
    assert shifted.evaluate(x=0.5, y=0.0) == pytest.approx(300.0)
    assert shifted.evaluate(x=0.0, y=0.0) == pytest.approx(290.0)


def test_a_harmonic_law_is_a_sine_of_the_physical_coordinate():
    profile = harmonic(ProfileAxis.Y, 4.0, K, math.pi)
    assert profile.evaluate(x=0.0, y=0.0) == pytest.approx(0.0, abs=1e-12)
    assert profile.evaluate(x=0.0, y=0.5) == pytest.approx(4.0)
    assert profile.evaluate(x=0.0, y=1.0) == pytest.approx(0.0, abs=1e-12)


def test_a_harmonic_law_adds_its_offset():
    profile = HarmonicProfile1D(
        ProfileAxis.X, Quantity(4.0, K), Quantity(math.pi, "1/meter"),
        offset=Quantity(300.0, K),
    )
    assert profile.evaluate(x=0.5, y=0.0) == pytest.approx(304.0)


def test_a_tabulated_law_interpolates_linearly_between_its_samples():
    profile = table()
    assert profile.evaluate(x=0.0, y=0.0) == pytest.approx(0.0)
    assert profile.evaluate(x=0.25, y=0.0) == pytest.approx(5.0)
    assert profile.evaluate(x=0.5, y=0.0) == pytest.approx(10.0)
    assert profile.evaluate(x=0.75, y=0.0) == pytest.approx(5.0)
    assert profile.evaluate(x=1.0, y=0.0) == pytest.approx(0.0)


def test_a_separable_law_is_the_product_of_its_factors():
    profile = ALL_PROFILES["separable"]
    assert profile.evaluate(x=0.5, y=0.5) == pytest.approx(2.0)
    assert profile.evaluate(x=0.0, y=0.5) == pytest.approx(0.0, abs=1e-12)
    assert set(profile.axes) == {ProfileAxis.X, ProfileAxis.Y}


# ---- Phase 3: coordinate semantics ----------------------------------------------------
def test_the_varying_coordinate_of_each_edge_is_stated_once():
    assert edge_axis(BoundaryEdge.LEFT) is ProfileAxis.Y
    assert edge_axis(BoundaryEdge.RIGHT) is ProfileAxis.Y
    assert edge_axis(BoundaryEdge.BOTTOM) is ProfileAxis.X
    assert edge_axis(BoundaryEdge.TOP) is ProfileAxis.X


def test_a_law_written_against_one_axis_is_refused_on_the_other():
    with pytest.raises(InvalidScientificProblem, match="does not become a profile of the other"):
        linear(ProfileAxis.X).require_axis(ProfileAxis.Y, context="a left edge")
    linear(ProfileAxis.Y).require_axis(ProfileAxis.Y, context="a left edge")


def test_a_constant_binds_to_any_axis_because_it_reads_none():
    ALL_PROFILES["constant"].require_axis(ProfileAxis.X, context="anywhere")
    ALL_PROFILES["constant"].require_axis(ProfileAxis.Y, context="anywhere")


def test_evaluation_is_by_physical_coordinate_and_never_by_index():
    """The same physical point gives the same value however it is sampled.

    A law read by array index would give the midpoint different values on a
    5-sample and a 9-sample traverse of the same edge. This one cannot: it is
    never told which sample it is on.
    """
    profile = table(ProfileAxis.X, (0.0, 1.0), (0.0, 100.0))
    for count in (5, 9, 17, 33):
        positions = [index / (count - 1) for index in range(count)]
        midpoint = positions[count // 2]
        assert profile.evaluate(x=midpoint, y=0.0) == pytest.approx(100.0 * midpoint)


def test_a_law_in_millimetres_evaluates_against_metres():
    profile = TabulatedProfile1D(
        ProfileAxis.X, (0.0, 1000.0), (0.0, 100.0),
        unit=FLUX, coordinate_unit="millimeter",
    )
    assert profile.span == pytest.approx((0.0, 1.0))
    assert profile.evaluate(x=0.5, y=0.0) == pytest.approx(50.0)


# ---- Phase 4: units --------------------------------------------------------------------
def test_a_law_of_the_wrong_dimension_is_refused_however_plausible_its_numbers():
    with pytest.raises(InvalidScientificProblem, match="the wrong law"):
        ConstantProfile(Quantity(300.0, "volt")).require_output_dimension(
            K, context="a dirichlet edge"
        )


def test_a_linear_slope_is_per_unit_length():
    with pytest.raises(InvalidScientificProblem, match="slope per unit length"):
        LinearProfile1D(ProfileAxis.Y, Quantity(300.0, K), Quantity(20.0, K))


def test_a_wavenumber_is_an_inverse_length():
    with pytest.raises(InvalidScientificProblem, match="wavenumber multiplies a position"):
        HarmonicProfile1D(ProfileAxis.Y, Quantity(1.0, K), Quantity(math.pi, "meter"))


def test_a_harmonic_offset_is_added_to_its_amplitude():
    with pytest.raises(InvalidScientificProblem, match="offset and amplitude are added"):
        HarmonicProfile1D(
            ProfileAxis.Y, Quantity(1.0, K), Quantity(1.0, "1/meter"),
            offset=Quantity(1.0, "volt"),
        )


def test_separable_factors_must_be_dimensionless():
    with pytest.raises(InvalidScientificProblem, match="the wrong law"):
        SeparableProfile2D(
            Quantity(2.0, "watt/meter**3"), harmonic(ProfileAxis.X, unit=K),
            harmonic(ProfileAxis.Y),
        )


def test_separable_factors_must_read_their_own_axis():
    with pytest.raises(InvalidScientificProblem, match="does not become a profile of the other"):
        SeparableProfile2D(
            Quantity(2.0, "watt/meter**3"), harmonic(ProfileAxis.Y),
            harmonic(ProfileAxis.Y),
        )


def test_a_separable_law_does_not_nest():
    with pytest.raises(InvalidScientificProblem, match="nesting two-dimensional"):
        SeparableProfile2D(
            Quantity(1.0, "watt/meter**3"), ALL_PROFILES["separable"],
            harmonic(ProfileAxis.Y),
        )


# ---- Phase 12: tabulated integrity -----------------------------------------------------
@pytest.mark.parametrize(
    "coordinates, values, expected",
    [
        ((0.0, 1.0, 0.5), (0.0, 1.0, 2.0), "run backwards"),
        ((0.0, 0.5, 0.5), (0.0, 1.0, 2.0), "repeats the coordinate"),
        ((0.0, float("nan")), (0.0, 1.0), "non-finite"),
        ((0.0, 1.0), (0.0, float("inf")), "non-finite"),
        ((0.0, 1.0, 2.0), (0.0, 1.0), "coordinates and 2 values"),
        ((0.0,), (1.0,), "at least two samples"),
    ],
)
def test_a_malformed_table_is_refused(coordinates, values, expected):
    with pytest.raises(InvalidScientificProblem, match=expected):
        table(coordinates=coordinates, values=values)


def test_a_tabulated_coordinate_must_be_a_length():
    with pytest.raises(InvalidScientificProblem, match="is not a length"):
        table(coordinate_unit="kelvin")


def test_a_table_refuses_to_extrapolate():
    profile = table(ProfileAxis.X, (0.2, 0.8), (0.0, 10.0))
    assert profile.evaluate(x=0.5, y=0.0) == pytest.approx(5.0)
    for outside in (0.1, 0.9, -1.0, 5.0):
        with pytest.raises(InvalidScientificProblem, match="Extrapolation is not declared"):
            profile.evaluate(x=outside, y=0.0)


def test_a_table_that_stops_short_of_its_span_is_refused():
    profile = table(ProfileAxis.X, (0.0, 0.6), (0.0, 10.0))
    with pytest.raises(InvalidScientificProblem, match="must cover"):
        profile.require_covers(0.0, 1.0, context="the bottom edge")
    profile.require_covers(0.0, 0.6, context="the bottom edge")


def test_the_closed_forms_are_defined_everywhere_and_say_so():
    for name in ("constant", "linear", "harmonic"):
        ALL_PROFILES[name].require_covers(-1e6, 1e6, context="anywhere")


# ---- Phase 13: interpolation is declared -----------------------------------------------
def test_the_interpolation_method_is_declared_and_survives_serialization():
    profile = table()
    assert profile.interpolation is Interpolation.LINEAR
    assert profile.to_dict()["interpolation"] == "linear"
    assert load_profile(profile.to_dict()).interpolation is Interpolation.LINEAR


@pytest.mark.parametrize("method", ["cubic", "spline", "nearest", "pchip", ""])
def test_an_undeclared_interpolation_method_is_refused(method):
    with pytest.raises(ValueError):
        table(interpolation=method)


# ---- Phase 14: serialization and fingerprint -------------------------------------------
@pytest.mark.parametrize("name", sorted(ALL_PROFILES))
def test_every_profile_round_trips(name):
    profile = ALL_PROFILES[name]
    restored = load_profile(profile.to_dict())
    assert restored == profile
    assert restored.fingerprint() == profile.fingerprint()
    assert restored.evaluate(x=0.3, y=0.7) == pytest.approx(
        profile.evaluate(x=0.3, y=0.7)
    )


def test_the_fingerprint_moves_when_any_material_fact_moves():
    base = table(ProfileAxis.X, (0.0, 0.5, 1.0), (0.0, 10.0, 0.0), unit=FLUX)
    variants = {
        "values": table(ProfileAxis.X, (0.0, 0.5, 1.0), (0.0, 11.0, 0.0), unit=FLUX),
        "coordinates": table(ProfileAxis.X, (0.0, 0.6, 1.0), (0.0, 10.0, 0.0), unit=FLUX),
        "span": table(ProfileAxis.X, (0.0, 0.5, 2.0), (0.0, 10.0, 0.0), unit=FLUX),
        "axis": table(ProfileAxis.Y, (0.0, 0.5, 1.0), (0.0, 10.0, 0.0), unit=FLUX),
        "unit": table(ProfileAxis.X, (0.0, 0.5, 1.0), (0.0, 10.0, 0.0), unit="watt/meter**3"),
        "coordinate_unit": table(
            ProfileAxis.X, (0.0, 0.5, 1.0), (0.0, 10.0, 0.0),
            unit=FLUX, coordinate_unit="millimeter",
        ),
    }
    for label, variant in variants.items():
        assert variant.fingerprint() != base.fingerprint(), f"{label} did not move it"
    assert len({v.fingerprint() for v in variants.values()}) == len(variants)


def test_the_profile_type_is_part_of_the_identity():
    fingerprints = {name: p.fingerprint() for name, p in ALL_PROFILES.items()}
    assert len(set(fingerprints.values())) == len(ALL_PROFILES)


def test_a_renamed_profile_is_the_same_law():
    """The description is display, not identity — the mesh rule, reused."""
    plain = ConstantProfile(Quantity(300.0, K))
    described = ConstantProfile(Quantity(300.0, K), description="as measured on site")
    assert described.fingerprint() == plain.fingerprint()


def test_two_laws_with_one_description_are_not_one_law():
    left = ConstantProfile(Quantity(300.0, K), description="edge")
    right = ConstantProfile(Quantity(301.0, K), description="edge")
    assert left.fingerprint() != right.fingerprint()


def test_a_payload_without_the_schema_is_refused():
    payload = dict(ALL_PROFILES["linear"].to_dict())
    del payload["schema"]
    with pytest.raises(Exception):
        load_profile(payload)


def test_a_payload_naming_an_unknown_law_is_refused():
    payload = dict(ALL_PROFILES["linear"].to_dict())
    payload["kind"] = "polynomial_7d"
    with pytest.raises(InvalidScientificProblem, match="no spatial law of kind"):
        load_profile(payload)


def test_a_tampered_value_deserializes_to_a_different_identity():
    """Tampering is detectable because identity is over the values, not a name."""
    profile = table(unit=FLUX)
    payload = profile.to_dict()
    payload["values"] = [0.0, 99.0, 0.0]
    restored = load_profile(payload)
    assert restored.fingerprint() != profile.fingerprint()
    assert restored != profile


# ---- Phase 18: no callable escape hatch -------------------------------------------------
def a_function(y):  # pragma: no cover - never called
    return y


class Callable:  # pragma: no cover - never called
    def __call__(self, y):
        return y


@pytest.mark.parametrize(
    "law",
    [
        lambda y: y,
        a_function,
        functools.partial(a_function),
        Callable(),
        eval,
        compile,
        "300 + 20*y",
        {"expression": "300 + 20*y"},
        object(),
    ],
)
def test_no_executable_or_stringly_law_is_accepted(law):
    with pytest.raises(InvalidScientificProblem, match="Executable objects are refused"):
        as_profile(law, context="a boundary value")


def test_a_quantity_is_promoted_to_a_constant_law():
    promoted = as_profile(Quantity(300.0, K), context="a boundary value")
    assert isinstance(promoted, ConstantProfile)
    assert promoted.evaluate(x=0.4, y=0.6) == 300.0


def test_a_profile_passes_through_unchanged():
    profile = linear()
    assert as_profile(profile, context="a boundary value") is profile


def test_the_deserializer_has_no_route_to_executing_anything():
    """`load_profile` dispatches on a closed table and nothing else.

    No eval, no exec, no import by name — so a payload cannot name code and be
    obeyed, whatever it claims to be.
    """
    import inspect

    from engcore.scientific.fields import profiles

    source = inspect.getsource(profiles)
    for forbidden in ("eval(", "exec(", "__import__", "importlib", "getattr(builtins"):
        assert forbidden not in source, f"the profile module mentions {forbidden}"


@pytest.mark.parametrize("name", sorted(ALL_PROFILES))
def test_every_profile_is_frozen(name):
    """A law that could be edited after it was checked was never checked."""
    profile = ALL_PROFILES[name]
    assert isinstance(profile, SpatialProfile)
    field = next(iter(profile.payload()))
    with pytest.raises(Exception):
        setattr(profile, field, None)
    with pytest.raises(Exception):
        setattr(profile, "description", "edited")


def test_equal_laws_compare_equal_and_different_ones_do_not():
    assert ConstantProfile(Quantity(300.0, K)) == ConstantProfile(Quantity(300.0, K))
    assert ConstantProfile(Quantity(300.0, K)) != ConstantProfile(Quantity(301.0, K))
    assert linear(ProfileAxis.X) != linear(ProfileAxis.Y)
