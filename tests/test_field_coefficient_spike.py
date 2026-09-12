"""Phase 8: can the same profile abstraction carry a coefficient?

The question is deliberately split in two, because the answers differ.

**Representable** — yes, with no change to the architecture at all. A
coefficient that varies in space is the same kind of record as a boundary datum
that varies along its edge: a ``SpatialProfile`` in a coefficient's unit. It
stores, serializes, fingerprints and evaluates exactly as the others do, and
nothing in the profile layer had to learn what a coefficient is.

**Executed** — no, and the refusal says why. The five-point operator this model
assembles takes ``k`` outside the divergence, which holds only where ``k`` is
constant. A heterogeneous coefficient needs the conservative form discretised
with face conductivities between nodes: a different scheme, not a different
number. Running one silently under a declaration that says otherwise is exactly
the failure the applicability envelope exists to prevent.

    VERDICT: REPRESENTABLE_NOT_EXECUTED
"""

from __future__ import annotations

import math

import pytest

from engcore.domains.thermal_models.conduction2d import (
    CONDUCTIVITY_UNIT,
    Conduction2DError,
    plate_problem,
)
from engcore.scientific.fields import (
    BoundaryEdge,
    HarmonicProfile1D,
    LinearProfile1D,
    ProfileAxis,
    SeparableProfile2D,
    load_profile,
)
from engcore.scientific.units.quantity import Quantity
from tests.manufactured_conduction2d import square

#: The verdict this file establishes, as a value so the report cannot drift
#: from what the tests actually show.
COEFFICIENT_STATUS = "REPRESENTABLE_NOT_EXECUTED"


def layered():
    """``k(x) = 10 + 8x`` W/(m K) — a plate whose material grades along x."""
    return LinearProfile1D(
        ProfileAxis.X,
        Quantity(10.0, CONDUCTIVITY_UNIT),
        Quantity(8.0, f"{CONDUCTIVITY_UNIT}/meter"),
    )


def speckled():
    """A genuinely two-dimensional coefficient, to show 1-D is not the limit."""
    unit_sine = lambda axis: HarmonicProfile1D(  # noqa: E731
        axis, Quantity(0.2, "dimensionless"), Quantity(math.pi, "1/meter")
    )
    return SeparableProfile2D(
        Quantity(12.0, CONDUCTIVITY_UNIT), unit_sine(ProfileAxis.X), unit_sine(ProfileAxis.Y)
    )


# ---- representable ------------------------------------------------------------------
@pytest.mark.parametrize("build", [layered, speckled], ids=["layered", "speckled"])
def test_a_spatial_coefficient_is_an_ordinary_profile(build):
    """No new record, no new field on an existing one, no new vocabulary."""
    k = build()
    k.require_output_dimension(CONDUCTIVITY_UNIT, context="a coefficient")
    assert k.unit == "watt / kelvin / meter"
    assert len(k.fingerprint()) == 64
    assert load_profile(k.to_dict()) == k


def test_a_spatial_coefficient_evaluates_where_it_is_asked():
    k = layered()
    assert k.evaluate(x=0.0, y=0.5) == pytest.approx(10.0)
    assert k.evaluate(x=1.0, y=0.5) == pytest.approx(18.0)


def test_a_coefficient_of_the_wrong_dimension_is_still_refused():
    with pytest.raises(Exception, match="the wrong law"):
        layered().require_output_dimension("kelvin", context="a coefficient")


def test_a_two_dimensional_coefficient_covers_the_plate():
    mesh = square(16)
    speckled().require_covers_box((0.0, 1.0), (0.0, 1.0), context="a coefficient")
    assert mesh.dimensionality == 2


# ---- not executed -------------------------------------------------------------------
@pytest.mark.parametrize("build", [layered, speckled], ids=["layered", "speckled"])
def test_the_model_refuses_to_execute_a_spatial_coefficient_and_says_why(build):
    """The refusal names the scheme that is missing, not just the restriction."""
    with pytest.raises(Conduction2DError) as raised:
        plate_problem(
            problem_id="graded",
            mesh=square(16),
            conductivity=build(),
            edge_values={e: Quantity(300.0, "kelvin") for e in BoundaryEdge},
        )
    message = str(raised.value)
    assert "representable and is not executed" in message
    assert "face conductivities" in message
    assert "different scheme rather than a different coefficient" in message


def test_the_refusal_distinguishes_a_law_from_the_other_things_it_refuses():
    """Anisotropy, nonlinearity and heterogeneity are three different answers."""
    mesh = square(16)
    edges = {e: Quantity(300.0, "kelvin") for e in BoundaryEdge}

    def refusal(conductivity):
        with pytest.raises(Conduction2DError) as raised:
            plate_problem(
                problem_id="k", mesh=mesh, conductivity=conductivity, edge_values=edges
            )
        return str(raised.value)

    assert "isotropic" in refusal((1.0, 2.0))
    assert "nonlinear" in refusal(lambda t: t)
    assert "not executed by this model" in refusal(layered())
    assert "strictly positive" in refusal(Quantity(-1.0, CONDUCTIVITY_UNIT))


def test_a_constant_coefficient_is_unaffected():
    """The path that does execute still does."""
    problem = plate_problem(
        problem_id="plain",
        mesh=square(16),
        conductivity=Quantity(12.5, CONDUCTIVITY_UNIT),
        edge_values={e: Quantity(300.0, "kelvin") for e in BoundaryEdge},
    )
    assert problem.conductivity.magnitude_in(CONDUCTIVITY_UNIT) == 12.5


def test_the_verdict_is_the_one_the_tests_support():
    assert COEFFICIENT_STATUS == "REPRESENTABLE_NOT_EXECUTED"
