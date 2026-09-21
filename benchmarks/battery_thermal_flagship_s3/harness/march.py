"""The same staggered march, without the evidence record.

Calibration needs thousands of trajectory evaluations and the authorized path
builds a full provenance record for every one of them. This module marches the
identical scheme -- same kernel, same lumped closed form, same participant
order, same window boundaries -- with none of the recording, so a fit is
minutes rather than hours.

It is **not** a second model. Every electrical step is
:func:`~engcore.domains.battery.electrothermal.advance_electrothermal_step` and
every thermal step is the lumped body's own closed form. The accompanying test
pins this march against an authorized run of the same trajectory, so a
divergence is a test failure rather than a quiet second opinion.

Nothing here produces evidence. The flagship's predictions come from the
authorized path; this one exists to find the parameters that path is then run
with.
"""

from __future__ import annotations

import math
from typing import Sequence

from engcore.domains.battery import electrothermal as et
from engcore.domains.battery.flagship_ocv import (
    CHARGE_STATE_BASIS_AH,
    FLAGSHIP_OCV_CURVE,
    OCV_LOWER,
    OCV_UPPER,
)

_KNOT_Z = [z for z, _ in FLAGSHIP_OCV_CURVE.form.samples]
_KNOT_V = [v for _, v in FLAGSHIP_OCV_CURVE.form.samples]
_GAS = et.MOLAR_GAS_CONSTANT.magnitude_in("joule/(mole*kelvin)")


def ocv(z: float) -> float:
    """The declared curve, evaluated the way the DeclaredCurve evaluates it.

    Raises outside the declared interval for the same reason the record returns
    no value there: a number produced past the evidence is the failure this
    whole authority exists to prevent, and a fitter that got one would be
    fitting to it.
    """
    if z < OCV_LOWER or z > OCV_UPPER:
        raise ValueError(
            f"charge state {z:g} is outside the declared open-circuit voltage "
            f"interval [{OCV_LOWER}, {OCV_UPPER}]"
        )
    if z <= _KNOT_Z[0]:
        return _KNOT_V[0]
    for index in range(1, len(_KNOT_Z)):
        left, right = _KNOT_Z[index - 1], _KNOT_Z[index]
        if z <= right:
            span = right - left
            return _KNOT_V[index - 1] + (_KNOT_V[index] - _KNOT_V[index - 1]) * (
                (z - left) / span
            )
    return _KNOT_V[-1]


class ChargeStateOutOfRange(ValueError):
    """The march reached a charge state the declared authority does not cover."""


def march(
    *,
    times_s: Sequence[float],
    currents_a: Sequence[float],
    ambient_k: float,
    initial_temperature_k: float,
    r0_ref: float,
    ea0: float,
    r1_ref: float,
    ea1: float,
    c1: float,
    c_th: float,
    ha: float,
    reference_temperature_k: float = 298.15,
    charge_state_basis_ah: float = CHARGE_STATE_BASIS_AH,
    coulombic_efficiency: float = 1.0,
    initial_state_of_charge: float = 1.0,
    refinement: int = 1,
):
    """Advance the coupled system across the measured grid.

    Returns ``(instants, voltage, temperature, charge_state, stopped_at)``,
    where the arrays carry one entry per measured instant after the first and
    ``stopped_at`` is the index the march stopped before, or ``None``.

    The scheme is the composition's: within a window the cell advances at the
    temperature the body left in the previous window, then the body advances on
    the heat the cell just reported. That lag is the explicit staggered
    splitting, and it is the thing the refinement study and the monolithic
    reference measure.
    """
    if len(times_s) != len(currents_a) or len(times_s) < 2:
        raise ValueError("march needs at least two aligned samples")
    if min(r0_ref, r1_ref, c1, c_th, ha, charge_state_basis_ah) <= 0.0:
        raise ValueError("march requires positive R0, R1, C1, C_th, hA and basis")

    tau_th = c_th / ha
    z = float(initial_state_of_charge)
    vp = 0.0
    temperature = float(initial_temperature_k)

    instants: list[float] = []
    voltages: list[float] = []
    temperatures: list[float] = []
    charge_states: list[float] = []
    stopped_at: int | None = None

    for index in range(1, len(times_s)):
        left = float(times_s[index - 1])
        right = float(times_s[index])
        current = float(currents_a[index - 1])
        sub = max(int(refinement), 1)
        try:
            for piece in range(sub):
                a = left + (right - left) * piece / sub
                b = left + (right - left) * (piece + 1) / sub
                dt = b - a
                if dt <= 0.0:
                    continue
                held = temperature
                r0 = r0_ref * math.exp(ea0 / _GAS * (1.0 / held - 1.0 / reference_temperature_k))
                r1 = r1_ref * math.exp(ea1 / _GAS * (1.0 / held - 1.0 / reference_temperature_k))
                if not (math.isfinite(r0) and math.isfinite(r1)) or min(r0, r1) <= 0.0:
                    raise ChargeStateOutOfRange("Arrhenius evaluation is not representable")
                z_next = z - current * (dt / 3600.0) / (
                    coulombic_efficiency * charge_state_basis_ah
                )
                if not 0.0 <= z_next <= 1.0 or z_next < OCV_LOWER:
                    raise ChargeStateOutOfRange(
                        f"charge state {z_next:g} leaves the declared interval"
                    )
                tau = r1 * c1
                alpha = math.exp(-dt / tau)
                vp_inf = current * r1
                vp_next = vp * alpha + vp_inf * (1.0 - alpha)
                mean_vp = vp_inf + (vp - vp_inf) * (tau / dt) * (1.0 - alpha)
                heat = current * current * r0 + current * mean_vp

                # The lumped body's own closed form, on the heat just reported.
                steady = ambient_k + heat / ha
                beta = math.exp(-dt / tau_th)
                temperature = steady + (temperature - steady) * beta

                z = z_next
                vp = vp_next
        except ChargeStateOutOfRange:
            stopped_at = index - 1
            break

        instants.append(right)
        voltages.append(ocv(z) - current * r0 - vp)
        temperatures.append(temperature)
        charge_states.append(z)

    return instants, voltages, temperatures, charge_states, stopped_at


__all__ = ["ChargeStateOutOfRange", "march", "ocv"]
