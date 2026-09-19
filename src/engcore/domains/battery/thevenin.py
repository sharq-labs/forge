"""One-RC Thevenin battery kernel.

This module adds a dynamic polarization state without changing the existing
Rint production path. It is intentionally a scientific kernel first: callers
must supply the RC parameters and the initial polarization state explicitly.

For constant discharge current I over one interval dt:

    z_1 = z_0 - I dt / (eta Q)
    tau = R_1 C_1
    v_p,1 = v_p,0 exp(-dt/tau) + I R_1 (1 - exp(-dt/tau))
    V_t,1 = OCV(z_1) - I R_0 - v_p,1

Positive current means discharge. No clipping is performed; a step that leaves
SOC [0, 1] is refused rather than converted into a plausible-looking voltage.

This kernel does not claim empirical adequacy, ageing behaviour, hysteresis,
charge behaviour, or model-form uncertainty. Those require evidence outside
the equations below.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...scientific.errors import InvalidScientificProblem
from ...scientific.units.quantity import Quantity
from . import context as ctx
from .cell import CellSpecification


POLARIZATION_RESISTANCE = "polarization_resistance"
POLARIZATION_CAPACITANCE = "polarization_capacitance"
POLARIZATION_VOLTAGE = "polarization_voltage"


def _required(value: Quantity, unit: str, label: str, *, positive: bool = False) -> Quantity:
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(f"{label} must be a Quantity carrying {unit!r}")
    value.require_compatible(Quantity(1.0, unit), context=label)
    converted = value.to(unit)
    if not math.isfinite(converted.magnitude):
        raise InvalidScientificProblem(f"{label} must be finite")
    if positive and converted.magnitude <= 0.0:
        raise InvalidScientificProblem(f"{label} must be strictly positive")
    return converted


@dataclass(frozen=True)
class Thevenin1RCParameters:
    """The dynamic branch added to the cell's existing R0/OCV declaration."""

    polarization_resistance: Quantity
    polarization_capacitance: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "polarization_resistance",
            _required(
                self.polarization_resistance,
                ctx.RESISTANCE_UNIT,
                POLARIZATION_RESISTANCE,
                positive=True,
            ),
        )
        object.__setattr__(
            self,
            "polarization_capacitance",
            _required(
                self.polarization_capacitance,
                "farad",
                POLARIZATION_CAPACITANCE,
                positive=True,
            ),
        )

    @property
    def time_constant(self) -> Quantity:
        return (self.polarization_resistance * self.polarization_capacitance).to("second")

    def to_dict(self) -> dict:
        return {
            POLARIZATION_RESISTANCE: self.polarization_resistance.to_dict(),
            POLARIZATION_CAPACITANCE: self.polarization_capacitance.to_dict(),
            "time_constant": self.time_constant.to_dict(),
        }


@dataclass(frozen=True)
class TheveninState:
    state_of_charge: Quantity
    polarization_voltage: Quantity

    def __post_init__(self) -> None:
        soc = _required(self.state_of_charge, ctx.DIMENSIONLESS, ctx.STATE_OF_CHARGE)
        z = soc.magnitude_in(ctx.DIMENSIONLESS)
        if not 0.0 <= z <= 1.0:
            raise InvalidScientificProblem(f"{ctx.STATE_OF_CHARGE} must lie in [0, 1], got {z!r}")
        object.__setattr__(self, "state_of_charge", soc)
        object.__setattr__(
            self,
            "polarization_voltage",
            _required(self.polarization_voltage, ctx.VOLTAGE_UNIT, POLARIZATION_VOLTAGE),
        )


@dataclass(frozen=True)
class TheveninStepResult:
    initial_state: TheveninState
    final_state: TheveninState
    open_circuit_voltage: Quantity
    terminal_voltage: Quantity
    ohmic_drop: Quantity
    polarization_drop: Quantity
    alpha: float
    time_constant: Quantity

    def to_dict(self) -> dict:
        return {
            "initial_state": {
                "state_of_charge": self.initial_state.state_of_charge.to_dict(),
                "polarization_voltage": self.initial_state.polarization_voltage.to_dict(),
            },
            "final_state": {
                "state_of_charge": self.final_state.state_of_charge.to_dict(),
                "polarization_voltage": self.final_state.polarization_voltage.to_dict(),
            },
            "open_circuit_voltage": self.open_circuit_voltage.to_dict(),
            "terminal_voltage": self.terminal_voltage.to_dict(),
            "ohmic_drop": self.ohmic_drop.to_dict(),
            "polarization_drop": self.polarization_drop.to_dict(),
            "alpha": self.alpha,
            "time_constant": self.time_constant.to_dict(),
            "notice": (
                "closed-form 1RC state update only; empirical adequacy, ageing, hysteresis, "
                "measurement uncertainty and model-form uncertainty are not established here"
            ),
        }


def evaluate_thevenin_step(
    cell: CellSpecification,
    parameters: Thevenin1RCParameters,
    state: TheveninState,
    *,
    current: Quantity,
    duration: Quantity,
) -> TheveninStepResult:
    """Advance one constant-current discharge interval exactly for the 1RC ODE."""

    if not isinstance(cell, CellSpecification):
        raise InvalidScientificProblem("evaluate_thevenin_step expects a CellSpecification")
    if not isinstance(parameters, Thevenin1RCParameters):
        raise InvalidScientificProblem("parameters must be Thevenin1RCParameters")
    if not isinstance(state, TheveninState):
        raise InvalidScientificProblem("state must be TheveninState")

    current = _required(current, ctx.CURRENT_UNIT, ctx.DISCHARGE_CURRENT)
    duration = _required(duration, ctx.TIME_UNIT, ctx.DURATION, positive=True)

    current_a = current.magnitude_in(ctx.CURRENT_UNIT)
    if current_a < 0.0:
        raise InvalidScientificProblem(
            "the current 1RC kernel is discharge/rest only: negative current would be charge "
            "and needs separate charge/hysteresis validity evidence"
        )
    duration_h = duration.magnitude_in("hour")
    duration_s = duration.magnitude_in("second")
    capacity_ah = cell.nominal_capacity.magnitude_in(ctx.CAPACITY_UNIT)
    efficiency = cell.coulombic_efficiency.magnitude_in(ctx.DIMENSIONLESS)

    initial_soc = state.state_of_charge.magnitude_in(ctx.DIMENSIONLESS)
    final_soc = initial_soc - current_a * duration_h / (efficiency * capacity_ah)
    if not 0.0 <= final_soc <= 1.0:
        raise InvalidScientificProblem(
            f"the 1RC step leaves the declared charge state: z0={initial_soc:g}, z1={final_soc:g}; "
            "split the interval or supply a stopping rule instead of clipping the state"
        )

    tau_s = parameters.time_constant.magnitude_in("second")
    alpha = math.exp(-duration_s / tau_s)

    r1 = parameters.polarization_resistance.magnitude_in(ctx.RESISTANCE_UNIT)
    vp0 = state.polarization_voltage.magnitude_in(ctx.VOLTAGE_UNIT)
    vp_inf = current_a * r1
    vp1 = vp0 * alpha + vp_inf * (1.0 - alpha)

    final_state = TheveninState(
        Quantity(final_soc, ctx.DIMENSIONLESS),
        Quantity(vp1, ctx.VOLTAGE_UNIT),
    )
    ocv = cell.open_circuit_voltage(final_state.state_of_charge)
    if ocv is None:
        raise InvalidScientificProblem(
            "the cell's declared OCV curve gives no value at the final state of charge"
        )

    r0 = cell.internal_resistance.magnitude_in(ctx.RESISTANCE_UNIT)
    ohmic_drop = Quantity(current_a * r0, ctx.VOLTAGE_UNIT)
    polarization_drop = Quantity(vp1, ctx.VOLTAGE_UNIT)
    terminal = (ocv - ohmic_drop - polarization_drop).to(ctx.VOLTAGE_UNIT)

    return TheveninStepResult(
        initial_state=state,
        final_state=final_state,
        open_circuit_voltage=ocv.to(ctx.VOLTAGE_UNIT),
        terminal_voltage=terminal,
        ohmic_drop=ohmic_drop,
        polarization_drop=polarization_drop,
        alpha=alpha,
        time_constant=parameters.time_constant,
    )


__all__ = [
    "POLARIZATION_CAPACITANCE",
    "POLARIZATION_RESISTANCE",
    "POLARIZATION_VOLTAGE",
    "Thevenin1RCParameters",
    "TheveninState",
    "TheveninStepResult",
    "evaluate_thevenin_step",
]
