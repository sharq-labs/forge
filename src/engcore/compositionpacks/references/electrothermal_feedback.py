"""Independent ODE reference and parameter UQ for electrothermal feedback."""

from __future__ import annotations

import hashlib
import json
import math

from scipy.integrate import solve_ivp

from ...scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from ...scientific.units.quantity import Quantity


_INPUTS = {
    "c": ("thermal.heat_capacity", "joule/kelvin"),
    "g": ("thermal.ambient_conductance", "watt/kelvin"),
    "tamb": ("thermal.ambient_temperature", "kelvin"),
    "t0": ("thermal.initial_temperature", "kelvin"),
    "v": ("electrical.source_voltage", "volt"),
    "rref": ("material.reference_resistance", "ohm"),
    "alpha": ("material.temperature_coefficient", "1/kelvin"),
    "tref": ("material.reference_temperature", "kelvin"),
}


def _external(record):
    return {
        item.port.key: item
        for item in record.external_inputs
    }


def _parameters(record):
    records = _external(record)
    values = {}
    for name, (port, unit) in _INPUTS.items():
        item = records.get(port)
        if item is None or not isinstance(item.value, Quantity):
            raise ValueError(
                f"electrothermal reference requires scalar input {port!r}"
            )
        values[name] = item.value.magnitude_in(unit)
    return values


def _state_from_values(values, duration: float):
    c = values["c"]
    g = values["g"]
    tamb = values["tamb"]
    t0 = values["t0"]
    v = values["v"]
    rref = values["rref"]
    alpha = values["alpha"]
    tref = values["tref"]
    if c <= 0.0 or g <= 0.0 or rref <= 0.0:
        raise ValueError(
            "electrothermal reference requires C, G and R_ref > 0"
        )

    def resistance(temp: float) -> float:
        made = rref * (1.0 + alpha * (temp - tref))
        if made <= 0.0:
            raise ValueError(
                "linear-TCR reference crossed non-positive resistance"
            )
        return made

    def rhs(_time, state):
        temp = float(state[0])
        r = resistance(temp)
        power = v * v / r
        return [(power - g * (temp - tamb)) / c]

    if duration <= 0.0:
        temperature = t0
    else:
        solution = solve_ivp(
            rhs,
            (0.0, duration),
            (t0,),
            method="DOP853",
            rtol=1e-11,
            atol=1e-12,
            max_step=max(duration / 200.0, 1e-12),
        )
        if not solution.success or not len(solution.y[0]):
            raise ValueError(
                "independent electrothermal ODE reference did not converge"
            )
        temperature = float(solution.y[0][-1])

    r = resistance(temperature)
    power = v * v / r
    return temperature, r, power


def feedback_reference(record):
    duration = (
        record.ended_at.magnitude_in("second")
        - record.started_at.magnitude_in("second")
    )
    temperature, resistance, power = _state_from_values(
        _parameters(record),
        duration,
    )
    return {
        "final_temperature": Quantity(temperature, "kelvin"),
        "resistance": Quantity(resistance, "ohm"),
        "heat_generation": Quantity(power, "watt"),
    }


def feedback_reference_evidence_digest(record) -> str:
    values = feedback_reference(record)
    payload = {
        "method": "independent_dop853_electrothermal_feedback",
        "run_id": record.run_id,
        "outputs": {
            key: value.to_dict()
            for key, value in sorted(values.items())
        },
        "inputs": [
            item.to_dict()
            for item in sorted(
                record.external_inputs,
                key=lambda item: item.port.key,
            )
        ],
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def propagate_feedback_parameter_uncertainty(record):
    """First-order independent parameter propagation by ODE sensitivities."""

    records = _external(record)
    base = _parameters(record)
    duration = (
        record.ended_at.magnitude_in("second")
        - record.started_at.magnitude_in("second")
    )
    nominal = _state_from_values(base, duration)
    sigma = {}
    any_parameter = False
    for name, (port, unit) in _INPUTS.items():
        item = records[port]
        uncertainty = item.uncertainty
        if (
            uncertainty.is_quantified
            and uncertainty.kind is UncertaintyKind.STANDARD
            and uncertainty.source_kind is UncertaintySource.PARAMETER
        ):
            assert uncertainty.standard_uncertainty is not None
            sigma[name] = uncertainty.standard_uncertainty.magnitude_in(unit)
            any_parameter = any_parameter or sigma[name] > 0.0
        else:
            sigma[name] = 0.0
    if not any_parameter:
        return {}

    variances = [0.0, 0.0, 0.0]
    positive = {"c", "g", "rref"}
    for name, standard in sigma.items():
        if standard <= 0.0:
            continue
        x = base[name]
        step = standard
        plus = dict(base)
        minus = dict(base)
        plus[name] = x + step
        use_central = name not in positive or x - step > 0.0
        if use_central:
            minus[name] = x - step
            y_plus = _state_from_values(plus, duration)
            y_minus = _state_from_values(minus, duration)
            derivative = [
                (a - b) / (2.0 * step)
                for a, b in zip(y_plus, y_minus)
            ]
        else:
            y_plus = _state_from_values(plus, duration)
            derivative = [
                (a - b) / step
                for a, b in zip(y_plus, nominal)
            ]
        for index, value in enumerate(derivative):
            variances[index] += (value * standard) ** 2

    output_units = ("kelvin", "ohm", "watt")
    output_names = (
        "final_temperature",
        "resistance",
        "heat_generation",
    )
    return {
        name: Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(
                math.sqrt(max(0.0, variance)),
                unit,
            ),
            source=(
                "independent external parameter standard uncertainties "
                "propagated through an independent DOP853 electrothermal ODE"
            ),
            method="first_order_independent_ode_sensitivity",
            notes=(
                "Central finite-difference sensitivities at one supplied "
                "standard uncertainty; one-sided only when positivity would "
                "otherwise be violated. Numerical/model-form channels are "
                "not included."
            ),
            source_kind=UncertaintySource.PARAMETER,
        )
        for name, unit, variance
        in zip(output_names, output_units, variances)
    }


__all__ = [
    "feedback_reference",
    "feedback_reference_evidence_digest",
    "propagate_feedback_parameter_uncertainty",
]
