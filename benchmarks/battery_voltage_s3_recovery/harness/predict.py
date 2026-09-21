"""The recovery's prediction march, on the frozen model's own kernel.

What executes here
------------------
The electrical half is :func:`engcore.domains.battery.electrothermal.advance_electrothermal_step`
-- the production kernel that ``battery.cell.electrothermal_1rc@0.2.0``'s
realization names -- called on a cell built by
:func:`engcore.domains.battery.flagship_v2.recovery_cell`. Nothing here
reimplements the cell: the open-circuit voltage lookup, the Arrhenius
resistances, the measured charge-state shape, the charge-state advance and the
refusals all come from that kernel and its declared authorities.

The thermal half is the lumped body's closed form, written inline against
:class:`engcore.domains.thermal_models.lumped.ThermalBody` so the two
parameters mean what that model says they mean. Sprint 3's calibration march
did the same thing and defended it with an equivalence test; the same test
lives here, pinning this march against the kernel called step by step.

What does NOT execute here
--------------------------
The authorized multiphysics composition. The composition pack's blueprint pins
its participant's model version, so the recovery's model version cannot enter it
without a parallel blueprint, composition pack and execution pack. The
consequence is that this round produces no replay of an authorized plan and no
certification record, which the freeze record states rather than leaves to be
discovered. What this march does produce is the frozen model's own arithmetic,
and that is what Gate A is scored on.

The staggered splitting is Sprint 3's: within a window the cell advances at the
temperature the body left in the previous window, then the body advances on the
heat the cell just reported.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from engcore.domains.battery import context as bctx
from engcore.domains.battery import electrothermal as et
from engcore.domains.battery import flagship_v2 as model_v2
from engcore.domains.thermal_models.lumped import ThermalBody
from engcore.scientific.units.quantity import Quantity

#: Below this the composition presents a sample as rest. The pack's own band.
REST_BAND_A = 0.2

REFERENCE_TEMPERATURE_K = 298.15


class MarchRefused:
    """Marker: the march stopped because an authority refused, not because it failed."""

    __slots__ = ("index", "reason")

    def __init__(self, index: int, reason: str) -> None:
        self.index = index
        self.reason = reason


def thermal_time_constant_s(
    heat_capacity_j_per_k: float, conductance_w_per_k: float, ambient_k: float
) -> float:
    """The lumped body's own time constant, from the production record."""
    body = ThermalBody(
        body_id="recovery",
        heat_capacity=Quantity(heat_capacity_j_per_k, "joule/kelvin"),
        ambient_conductance=Quantity(conductance_w_per_k, "watt/kelvin"),
        ambient_temperature=Quantity(ambient_k, "kelvin"),
        initial_temperature=Quantity(ambient_k, "kelvin"),
        duration=Quantity(1.0, "second"),
    )
    return body.time_constant_s


def march(
    *,
    cell_id: str,
    band: str,
    times_s: Sequence[float],
    currents_a: Sequence[float],
    ambient_k: float,
    initial_temperature_k: float,
    parameters: dict[str, float],
    available_charge_ah: float,
    initial_state_of_charge: float,
    refinement: int = 1,
):
    """Advance the frozen model across a measured grid.

    Returns ``(instants, voltage, temperature, charge_state, refusal)``. The
    arrays carry one entry per measured instant after the first, and ``refusal``
    is a :class:`MarchRefused` when a declared authority declined to answer.
    """
    if len(times_s) != len(currents_a) or len(times_s) < 2:
        raise ValueError("the march needs at least two aligned samples")

    cell = model_v2.recovery_cell(
        cell_id=cell_id,
        band=band,
        ohmic_resistance_reference=Quantity(
            parameters["ohmic_resistance_reference"], bctx.RESISTANCE_UNIT
        ),
        ohmic_activation_energy=Quantity(
            parameters["ohmic_activation_energy"], et.ACTIVATION_ENERGY_UNIT
        ),
        polarization_resistance_reference=Quantity(
            parameters["polarization_resistance_reference"], bctx.RESISTANCE_UNIT
        ),
        polarization_activation_energy=Quantity(
            parameters["polarization_activation_energy"], et.ACTIVATION_ENERGY_UNIT
        ),
        polarization_capacitance=Quantity(
            parameters["polarization_capacitance"], et.CAPACITANCE_UNIT
        ),
        reference_temperature=Quantity(REFERENCE_TEMPERATURE_K, bctx.TEMPERATURE_UNIT),
        available_charge=Quantity(available_charge_ah, bctx.CAPACITY_UNIT),
    )
    c_th = float(parameters["thermal_capacitance"])
    ha = float(parameters["thermal_conductance"])
    tau_th = thermal_time_constant_s(c_th, ha, ambient_k)

    state = et.ElectricalState(
        state_of_charge=Quantity(float(initial_state_of_charge), bctx.DIMENSIONLESS),
        polarization_voltage=Quantity(0.0, bctx.VOLTAGE_UNIT),
    )
    temperature = float(initial_temperature_k)

    instants: list[float] = []
    voltages: list[float] = []
    temperatures: list[float] = []
    charge_states: list[float] = []
    refusal: MarchRefused | None = None

    for index in range(1, len(times_s)):
        left = float(times_s[index - 1])
        right = float(times_s[index])
        if right <= left:
            continue
        raw = float(currents_a[index - 1])
        current = 0.0 if abs(raw) < REST_BAND_A else raw
        sub = max(int(refinement), 1)
        try:
            for piece in range(sub):
                a = left + (right - left) * piece / sub
                b = left + (right - left) * (piece + 1) / sub
                dt = b - a
                if dt <= 0.0:
                    continue
                step = et.advance_electrothermal_step(
                    cell,
                    state,
                    current=Quantity(current, bctx.CURRENT_UNIT),
                    duration=Quantity(dt, bctx.TIME_UNIT),
                    temperature=Quantity(temperature, bctx.TEMPERATURE_UNIT),
                )
                heat = step.heat_generation.magnitude_in(bctx.POWER_UNIT)
                steady = ambient_k + heat / ha
                beta = math.exp(-dt / tau_th)
                temperature = steady + (temperature - steady) * beta
                state = step.final_state
                voltage = step.terminal_voltage.magnitude_in(bctx.VOLTAGE_UNIT)
        except (
            et.ChargeStateExhausted,
            et.OpenCircuitVoltageUnavailable,
        ) as exc:
            refusal = MarchRefused(index - 1, str(exc))
            break
        except (ValueError, OverflowError) as exc:
            refusal = MarchRefused(index - 1, f"not representable: {exc}")
            break

        instants.append(right)
        voltages.append(voltage)
        temperatures.append(temperature)
        charge_states.append(
            state.state_of_charge.magnitude_in(bctx.DIMENSIONLESS)
        )

    return instants, voltages, temperatures, charge_states, refusal


__all__ = ["MarchRefused", "REST_BAND_A", "march", "thermal_time_constant_s"]
