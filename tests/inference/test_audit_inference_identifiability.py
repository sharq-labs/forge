"""INF-10 and NUM-04: the identifiability verdict cannot be bought with arguments or units.

INF-10  ``assess_identifiability`` took its thresholds from the caller, silently:
        ``width_threshold=1e9, correlation_threshold=1.0, condition_threshold=1e300``
        turned a posterior whose alpha interval is 136 % of alpha into
        PARAMETERS_IDENTIFIABLE, and the report did not say the rule had moved.
NUM-04  the relative width is the 95 % interval divided by |estimate|, which is
        meaningless on an offset scale: the same temperature parameter declared in
        kelvin and in degC gets different widths and possibly different verdicts.
        A PosteriorGrid carries no units, so the refusal is made where a
        parameter's unit is declared.
"""

from __future__ import annotations

import numpy as np
import pytest

from engcore.inference.calibration import (
    CalibrationError,
    IdentifiabilityStatus,
    assess_identifiability,
)
from engcore.inference.grid import gaussian_grid_posterior
from engcore.inference.parameters import ParameterBounds, ParameterIdentity, ParameterIdentityError
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.units.quantity import Quantity
from engcore.studies import tcr

T_REF = Quantity(300.0, "kelvin")


@pytest.fixture(scope="module")
def weak_posterior():
    truth = tcr.TcrTruth(Quantity(1.0, "ohm"), Quantity(0.004, "1/kelvin"), T_REF)
    temps = [299.0, 301.0]
    by = {f"T{i}": Quantity(t, "kelvin") for i, t in enumerate(temps)}
    src = tcr.synthesize_tcr_observations(truth, temps, sigma=Quantity(0.02, "ohm"), dataset_id="cal", seed=3)
    pts = [(float(x), float(y)) for x in np.linspace(0.9, 1.1, 21) for y in np.linspace(-0.02, 0.02, 21)]
    table = tcr.tcr_forward_table(src, pts, reference_temperature=T_REF, temperatures_by_condition=by)
    return gaussian_grid_posterior(table, src)


def test_the_declared_thresholds_call_it_not_identifiable(weak_posterior):
    assert assess_identifiability(weak_posterior).status is IdentifiabilityStatus.NOT_IDENTIFIABLE


@pytest.mark.parametrize("relaxed", [
    {"width_threshold": 1.0e9, "correlation_threshold": 1.0, "condition_threshold": 1.0e300},
    {"width_threshold": 1.0e9},
    {"correlation_threshold": 1.0},
    {"condition_threshold": 1.0e300},
    {"minimum_effective_points": 1.0},
])
def test_relaxed_thresholds_cannot_buy_an_identifiable_verdict(weak_posterior, relaxed):
    with pytest.raises(CalibrationError, match="threshold"):
        assess_identifiability(weak_posterior, **relaxed)


@pytest.mark.parametrize("insane", [
    {"width_threshold": float("nan")},
    {"width_threshold": 0.0},
    {"correlation_threshold": -0.1},
    {"condition_threshold": float("inf")},
])
def test_meaningless_thresholds_are_refused(weak_posterior, insane):
    with pytest.raises(CalibrationError, match="threshold"):
        assess_identifiability(weak_posterior, **insane)


def test_tightened_thresholds_are_applied_and_said(weak_posterior):
    report = assess_identifiability(weak_posterior, width_threshold=0.5, correlation_threshold=0.9)
    assert report.status is IdentifiabilityStatus.NOT_IDENTIFIABLE
    assert report.width_threshold == 0.5 and report.correlation_threshold == 0.9
    assert "tightened" in report.why


def _identity(unit, low, high):
    return ParameterIdentity(name="reference_temperature", unit=unit, model=ModelReference("m", "1"),
                             bounds=ParameterBounds(Quantity(low, unit), Quantity(high, unit)))


@pytest.mark.parametrize("unit", ["degC", "degF"])
def test_a_parameter_on_an_offset_scale_is_refused(unit):
    with pytest.raises(ParameterIdentityError, match="offset"):
        _identity(unit, 0.0, 100.0)


@pytest.mark.parametrize("unit", ["kelvin", "delta_degC", "1/degC"])
def test_a_parameter_on_a_ratio_scale_is_accepted(unit):
    assert _identity(unit, 0.0, 100.0).unit
