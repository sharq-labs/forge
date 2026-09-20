"""Analytical reference and parameter-UQ route for thermal -> TCR composition."""

from __future__ import annotations

import hashlib
import json
import math

from ...scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from ...scientific.units.quantity import Quantity


def _external(record):
    return {
        item.port.key: item
        for item in record.external_inputs
    }


def _q(record, key: str) -> Quantity:
    item = _external(record).get(key)
    if item is None or not isinstance(item.value, Quantity):
        raise ValueError(f"analytical reference requires scalar input {key!r}")
    return item.value


def analytical_terminal_state(record) -> tuple[Quantity, Quantity]:
    """Closed-form terminal temperature and linear-TCR resistance."""

    c = _q(record, "thermal.heat_capacity").magnitude_in(
        "joule/kelvin"
    )
    g = _q(record, "thermal.ambient_conductance").magnitude_in(
        "watt/kelvin"
    )
    tamb = _q(record, "thermal.ambient_temperature").magnitude_in(
        "kelvin"
    )
    t0 = _q(record, "thermal.initial_temperature").magnitude_in(
        "kelvin"
    )
    q = _q(record, "thermal.heat_input").magnitude_in("watt")
    rref = _q(record, "material.reference_resistance").magnitude_in(
        "ohm"
    )
    alpha = _q(
        record, "material.temperature_coefficient"
    ).magnitude_in("1/kelvin")
    tref = _q(
        record, "material.reference_temperature"
    ).magnitude_in("kelvin")
    duration = (
        record.ended_at.magnitude_in("second")
        - record.started_at.magnitude_in("second")
    )
    if c <= 0.0 or g <= 0.0 or rref <= 0.0 or duration < 0.0:
        raise ValueError(
            "analytical reference received non-admissible positive parameter"
        )

    decay = math.exp(-g * duration / c)
    steady = tamb + q / g
    temperature = steady + (t0 - steady) * decay
    resistance = rref * (1.0 + alpha * (temperature - tref))
    return (
        Quantity(temperature, "kelvin"),
        Quantity(resistance, "ohm"),
    )


def reference_evidence_digest(record) -> str:
    temperature, resistance = analytical_terminal_state(record)
    payload = {
        "method": "closed_form_lumped_thermal_plus_linear_tcr",
        "run_id": record.run_id,
        "temperature": temperature.to_dict(),
        "resistance": resistance.to_dict(),
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


def propagate_parameter_uncertainty(record) -> Uncertainty | None:
    """First-order independent standard uncertainty of terminal resistance.

    Only STANDARD/PARAMETER inputs are counted. UNKNOWN inputs contribute
    nothing because nothing was quantified. Any other quantified source is
    outside this producer's declared EPISTEMIC_PARAMETER channel and is left
    for its own producer.
    """

    records = _external(record)
    keys = {
        "c": "thermal.heat_capacity",
        "g": "thermal.ambient_conductance",
        "tamb": "thermal.ambient_temperature",
        "t0": "thermal.initial_temperature",
        "q": "thermal.heat_input",
        "rref": "material.reference_resistance",
        "alpha": "material.temperature_coefficient",
        "tref": "material.reference_temperature",
    }
    units = {
        "c": "joule/kelvin",
        "g": "watt/kelvin",
        "tamb": "kelvin",
        "t0": "kelvin",
        "q": "watt",
        "rref": "ohm",
        "alpha": "1/kelvin",
        "tref": "kelvin",
    }
    values = {}
    sigma = {}
    any_parameter_uq = False
    for name, port_key in keys.items():
        item = records.get(port_key)
        if item is None or not isinstance(item.value, Quantity):
            raise ValueError(
                f"parameter UQ requires scalar input {port_key!r}"
            )
        values[name] = item.value.magnitude_in(units[name])
        uncertainty = item.uncertainty
        if not uncertainty.is_quantified:
            sigma[name] = 0.0
            continue
        if (
            uncertainty.kind is not UncertaintyKind.STANDARD
            or uncertainty.source_kind is not UncertaintySource.PARAMETER
        ):
            sigma[name] = 0.0
            continue
        assert uncertainty.standard_uncertainty is not None
        sigma[name] = uncertainty.standard_uncertainty.magnitude_in(
            units[name]
        )
        any_parameter_uq = True

    if not any_parameter_uq:
        return None

    c = values["c"]
    g = values["g"]
    tamb = values["tamb"]
    t0 = values["t0"]
    q = values["q"]
    rref = values["rref"]
    alpha = values["alpha"]
    tref = values["tref"]
    duration = (
        record.ended_at.magnitude_in("second")
        - record.started_at.magnitude_in("second")
    )

    decay = math.exp(-g * duration / c)
    steady = tamb + q / g
    temperature = steady + (t0 - steady) * decay
    factor = 1.0 + alpha * (temperature - tref)

    dtdq = (1.0 - decay) / g
    dtdtamb = 1.0 - decay
    dtdt0 = decay
    dtdc = (t0 - steady) * decay * g * duration / (c * c)
    dtdg = (
        (-q / (g * g)) * (1.0 - decay)
        - (t0 - steady) * decay * duration / c
    )

    derivatives = {
        "c": rref * alpha * dtdc,
        "g": rref * alpha * dtdg,
        "tamb": rref * alpha * dtdtamb,
        "t0": rref * alpha * dtdt0,
        "q": rref * alpha * dtdq,
        "rref": factor,
        "alpha": rref * (temperature - tref),
        "tref": -rref * alpha,
    }
    variance = sum(
        (derivatives[name] * sigma[name]) ** 2
        for name in derivatives
    )
    standard = math.sqrt(max(0.0, variance))
    return Uncertainty(
        kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(standard, "ohm"),
        source=(
            "independent external parameter uncertainties propagated "
            "through closed-form thermal and linear-TCR equations"
        ),
        method="first_order_independent_closed_form_propagation",
        notes=(
            "Assumes the supplied parameter standard uncertainties are "
            "mutually independent; model-form and numerical uncertainty are "
            "not included."
        ),
        source_kind=UncertaintySource.PARAMETER,
    )


__all__ = [
    "analytical_terminal_state",
    "propagate_parameter_uncertainty",
    "reference_evidence_digest",
]
