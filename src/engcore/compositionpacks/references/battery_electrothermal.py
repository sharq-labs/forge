"""Independent ODE reference and parameter UQ for the battery flagship.

The primary route marches the coupled system by explicit staggered splitting:
the cell advances over a window at the temperature the thermal body left, then
the body advances on the heat the cell reported. This module integrates the
same three states as one monolithic system with an adaptive high-order
Runge-Kutta scheme, so the splitting error the primary route carries is exactly
what the comparison measures.

    dz/dt   = -I(t) / (eta Q_basis)
    dv_p/dt = (I(t) R1(T) - v_p) / (R1(T) C1)
    dT/dt   = (I(t)^2 R0(T) + I(t) v_p - hA (T - T_amb)) / C_th

Independence, and its limit
---------------------------
Different algorithm, different discretization, different coupling treatment. It
is **not** independent of the model: it integrates the same equations with the
same open-circuit voltage authority. It can show that the staggered march
solved the system it claims to solve; it cannot show that the system is the
cell.

The current profile
-------------------
Read back from the run's own scenario input receipts, which record the value the
runtime used at each window boundary, and held piecewise-constant between them
exactly as the declared STEP schedule does. The reference therefore integrates
the profile the run was actually driven with, not a re-read of the source file.
"""

from __future__ import annotations

import hashlib
import json
import math

from scipy.integrate import solve_ivp

from ...domains.battery import context as ctx
from ...domains.battery import electrothermal as et
from ...domains.battery import flagship as fl
from ...scientific.models.definition import ValidityStatus
from ...scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from ...scientific.units.quantity import Quantity

#: External inputs the reference needs, by fact path and the unit it reads them
#: in. A missing one is an error rather than a default.
_INPUTS = {
    "r0": ("battery.ohmic_resistance_reference", ctx.RESISTANCE_UNIT),
    "ea0": ("battery.ohmic_activation_energy", et.ACTIVATION_ENERGY_UNIT),
    "r1": ("battery.polarization_resistance_reference", ctx.RESISTANCE_UNIT),
    "ea1": ("battery.polarization_activation_energy", et.ACTIVATION_ENERGY_UNIT),
    "c1": ("battery.polarization_capacitance", et.CAPACITANCE_UNIT),
    "tref": ("battery.reference_temperature", ctx.TEMPERATURE_UNIT),
    "qbasis": ("battery.charge_state_basis", ctx.CAPACITY_UNIT),
    "eta": ("battery.coulombic_efficiency", ctx.DIMENSIONLESS),
    "z0": ("battery.initial_state_of_charge", ctx.DIMENSIONLESS),
    "vp0": ("battery.initial_polarization_voltage", ctx.VOLTAGE_UNIT),
    "cth": ("thermal.heat_capacity", "joule/kelvin"),
    "ha": ("thermal.ambient_conductance", "watt/kelvin"),
    "tamb": ("thermal.ambient_temperature", ctx.TEMPERATURE_UNIT),
    "t0": ("thermal.initial_temperature", ctx.TEMPERATURE_UNIT),
}

#: The schedule input the load current arrives on.
LOAD_CURRENT_INPUT = "battery.load_current"

_GAS = et.MOLAR_GAS_CONSTANT.magnitude_in("joule/(mole*kelvin)")


def _external(record):
    return {item.port.key: item for item in record.external_inputs}


def _fact_values(record):
    """External inputs keyed by fact path.

    The run record keys external inputs by port, not by fact path, so the
    mapping is recovered from the graph plan's own bindings where available and
    from the port id otherwise. Both are the authority's, not this module's.
    """
    by_port = _external(record)
    values: dict[str, float] = {}
    for name, (path, unit) in _INPUTS.items():
        port_id = path.split(".", 1)[1]
        found = None
        for key, item in by_port.items():
            if key.endswith(f".{port_id}"):
                found = item
                break
        if found is None or not isinstance(found.value, Quantity):
            raise ValueError(
                f"battery electrothermal reference requires external input {path!r}"
            )
        values[name] = found.value.magnitude_in(unit)
    return values


def _current_profile(record):
    """The piecewise-constant current the run was driven with."""
    points: list[tuple[float, float]] = []
    for receipt in record.scenario_input_receipts:
        if receipt.input_id != LOAD_CURRENT_INPUT:
            continue
        points.append(
            (
                receipt.instant.magnitude_in("second"),
                receipt.value.magnitude_in(ctx.CURRENT_UNIT),
            )
        )
    if not points:
        raise ValueError(
            "battery electrothermal reference found no load-current receipts; "
            "the run was not driven by a measured profile"
        )
    points.sort()
    times = [item[0] for item in points]
    currents = [item[1] for item in points]

    def at(instant: float) -> float:
        if instant <= times[0]:
            return currents[0]
        low, high = 0, len(times) - 1
        while low < high:
            middle = (low + high + 1) // 2
            if times[middle] <= instant:
                low = middle
            else:
                high = middle - 1
        return currents[low]

    return at, times


def _integrate(values, record):
    at_current, boundaries = _current_profile(record)
    start = record.started_at.magnitude_in("second")
    end = record.ended_at.magnitude_in("second")

    r0_ref, ea0 = values["r0"], values["ea0"]
    r1_ref, ea1 = values["r1"], values["ea1"]
    c1, tref = values["c1"], values["tref"]
    qbasis, eta = values["qbasis"], values["eta"]
    cth, ha, tamb = values["cth"], values["ha"], values["tamb"]
    if min(r0_ref, r1_ref, c1, qbasis, eta, cth, ha, tref) <= 0.0:
        raise ValueError(
            "battery electrothermal reference requires positive R0, R1, C1, "
            "Q_basis, eta, C_th, hA and T_ref"
        )

    def arrhenius(reference: float, activation: float, temperature: float) -> float:
        exponent = activation / _GAS * (1.0 / temperature - 1.0 / tref)
        if not -700.0 < exponent < 700.0:
            raise ValueError("reference Arrhenius exponent is not representable")
        return reference * math.exp(exponent)

    def rhs(instant, state):
        z, vp, temperature = float(state[0]), float(state[1]), float(state[2])
        if temperature <= 0.0:
            raise ValueError("reference integration reached a non-positive temperature")
        current = at_current(instant)
        r0 = arrhenius(r0_ref, ea0, temperature)
        r1 = arrhenius(r1_ref, ea1, temperature)
        return [
            -current / (eta * qbasis * 3600.0),
            (current * r1 - vp) / (r1 * c1),
            (current * current * r0 + current * vp - ha * (temperature - tamb)) / cth,
        ]

    duration = end - start
    if duration <= 0.0:
        raise ValueError("battery electrothermal reference needs a positive horizon")
    # Every window boundary is a discontinuity of the piecewise-constant
    # current. Integrating across one with an adaptive controller would let the
    # step size hide the jump, so the integration stops at each of them.
    interior = [t for t in boundaries if start < t < end]
    edges = [start] + interior + [end]
    # Restricting the step to the narrowest window keeps the adaptive
    # controller from stepping over a current change entirely and reporting a
    # confident answer to a problem it never saw.
    max_step = max(min(b - a for a, b in zip(edges, edges[1:])), 1e-9)
    solution = solve_ivp(
        rhs,
        (start, end),
        (values["z0"], values["vp0"], values["t0"]),
        method="DOP853",
        rtol=1e-10,
        atol=1e-12,
        max_step=max_step,
    )
    if not solution.success or not solution.y.size:
        raise ValueError(
            "independent battery electrothermal ODE reference did not converge"
        )
    z = float(solution.y[0][-1])
    vp = float(solution.y[1][-1])
    temperature = float(solution.y[2][-1])

    evaluated = fl.FLAGSHIP_OCV_CURVE.evaluate(Quantity(z, ctx.DIMENSIONLESS))
    if evaluated.status is not ValidityStatus.IN_DOMAIN or evaluated.value is None:
        raise ValueError(
            f"reference reached charge state {z:g}, where the declared "
            f"open-circuit voltage authority gives no value: {evaluated.reason}"
        )
    ocv = evaluated.value.magnitude_in(ctx.VOLTAGE_UNIT)
    current = at_current(end)
    r0 = arrhenius(r0_ref, ea0, temperature)
    terminal = ocv - current * r0 - vp
    heat = current * current * r0 + current * vp
    return terminal, temperature, z, heat


def battery_electrothermal_reference(record):
    values = _fact_values(record)
    terminal, temperature, z, heat = _integrate(values, record)
    return {
        fl.TERMINAL_VOLTAGE_METRIC: Quantity(terminal, ctx.VOLTAGE_UNIT),
        ctx.CELL_TEMPERATURE: Quantity(temperature, ctx.TEMPERATURE_UNIT),
        fl.STATE_OF_CHARGE_METRIC: Quantity(z, ctx.DIMENSIONLESS),
        fl.HEAT_GENERATION_METRIC: Quantity(heat, ctx.POWER_UNIT),
    }


def battery_electrothermal_reference_evidence_digest(record) -> str:
    values = battery_electrothermal_reference(record)
    payload = {
        "method": "independent_dop853_battery_electrothermal",
        "run_id": record.run_id,
        "ocv_authority_digest": fl.FLAGSHIP_OCV_CURVE.fingerprint,
        "outputs": {key: value.to_dict() for key, value in sorted(values.items())},
        "inputs": [
            item.to_dict()
            for item in sorted(record.external_inputs, key=lambda item: item.port.key)
        ],
        "scenario_digest": record.scenario_digest,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


#: Outputs the parameter propagation reports, in the order the variances are
#: accumulated.
_UQ_OUTPUTS = (
    (fl.TERMINAL_VOLTAGE_METRIC, ctx.VOLTAGE_UNIT),
    (ctx.CELL_TEMPERATURE, ctx.TEMPERATURE_UNIT),
)

#: Parameters that must stay strictly positive under perturbation.
_POSITIVE = {"r0", "r1", "c1", "qbasis", "eta", "cth", "ha", "tref", "t0", "tamb"}


def propagate_battery_parameter_uncertainty(record):
    """First-order independent parameter propagation by ODE sensitivities.

    Only external inputs carrying a quantified STANDARD/PARAMETER uncertainty
    contribute. An input whose uncertainty is UNKNOWN contributes nothing and is
    not silently treated as exact -- the absence shows up as a channel the
    completeness matrix reports as missing, which is where it belongs.
    """
    by_port = _external(record)
    base = _fact_values(record)
    sigma: dict[str, float] = {}
    any_parameter = False
    for name, (path, unit) in _INPUTS.items():
        port_id = path.split(".", 1)[1]
        item = next(
            (value for key, value in by_port.items() if key.endswith(f".{port_id}")),
            None,
        )
        uncertainty = None if item is None else item.uncertainty
        if (
            uncertainty is not None
            and uncertainty.is_quantified
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

    nominal = _integrate(base, record)[:2]
    variances = [0.0 for _ in _UQ_OUTPUTS]
    for name, standard in sorted(sigma.items()):
        if standard <= 0.0:
            continue
        centre = base[name]
        plus = dict(base)
        plus[name] = centre + standard
        if name in _POSITIVE and centre - standard <= 0.0:
            derivative = [
                (a - b) / standard
                for a, b in zip(_integrate(plus, record)[:2], nominal)
            ]
        else:
            minus = dict(base)
            minus[name] = centre - standard
            derivative = [
                (a - b) / (2.0 * standard)
                for a, b in zip(
                    _integrate(plus, record)[:2], _integrate(minus, record)[:2]
                )
            ]
        for index, value in enumerate(derivative):
            variances[index] += (value * standard) ** 2

    return {
        name: Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(math.sqrt(max(0.0, variance)), unit),
            source=(
                "independent external parameter standard uncertainties "
                "propagated through an independent DOP853 integration of the "
                "coupled battery electrothermal system"
            ),
            method="first_order_independent_ode_sensitivity",
            notes=(
                "Central finite-difference sensitivities at one supplied "
                "standard uncertainty; one-sided only where positivity would "
                "otherwise be violated. The numerical, measurement and "
                "model-form channels are not included and are reported "
                "separately."
            ),
            source_kind=UncertaintySource.PARAMETER,
        )
        for (name, unit), variance in zip(_UQ_OUTPUTS, variances)
    }


__all__ = [
    "LOAD_CURRENT_INPUT",
    "battery_electrothermal_reference",
    "battery_electrothermal_reference_evidence_digest",
    "propagate_battery_parameter_uncertainty",
]
