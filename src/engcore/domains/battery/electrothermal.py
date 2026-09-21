"""The Sprint 3 flagship kernel: one-RC Thevenin cell with self-heating.

This is the scientific kernel the flagship CompositionPack executes. It states
exactly one step of an electrothermal cell and nothing else: no file reading,
no dataset constants, no fitting, no verdicts.

The equations
-------------
Positive current is discharge, as everywhere else in this domain. Over one
interval ``dt`` at a cell temperature ``T`` held constant across the interval::

    R0(T)  = R0_ref exp( Ea0 / Rgas * (1/T - 1/T_ref) )
    R1(T)  = R1_ref exp( Ea1 / Rgas * (1/T - 1/T_ref) )
    tau    = R1(T) C1
    alpha  = exp(-dt / tau)

    z1     = z0 - I dt / (eta Q)
    vp1    = vp0 alpha + I R1(T) (1 - alpha)
    V      = OCV(z1) - I R0(T) - vp1

    <vp>   = I R1(T) + (vp0 - I R1(T)) (tau/dt) (1 - alpha)
    Qdot   = I^2 R0(T) + I <vp>

``<vp>`` is the exact time-average of the polarization voltage over the
interval, not its endpoint value, so ``Qdot dt`` is the energy the polarization
branch actually dissipated rather than a rectangle drawn through one end of it.

What this kernel claims, and what it does not
----------------------------------------------
It claims the irreversible loss ``I (OCV - V)``, split into an ohmic and a
polarization part. It does **not** claim reversible entropic heating
``I T dU/dT``: that term needs a measured entropy coefficient, this domain has
none, and a zero in its place would be an unearned statement that the term is
absent rather than unmeasured. Its absence is declared in
:data:`HEAT_MODEL_LIMITATIONS` and repeated by the pack that executes this.

It claims no ageing, no hysteresis, no diffusion tail beyond the single RC
branch, and no temperature dependence of the open-circuit voltage. Each is a
model-form limitation, stated rather than approximated.

Refusals
--------
A step that would leave the declared charge interval is refused, not clipped.
A step whose open-circuit voltage falls outside the OCV authority's declared
interval is refused, not extrapolated -- the curve itself refuses, and this
kernel propagates that refusal instead of reaching past it.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from ...scientific.errors import InvalidScientificProblem
from ...scientific.models.curves import DeclaredCurve
from ...scientific.models.definition import ValidityStatus
from ...scientific.units.quantity import Quantity
from . import context as ctx

#: Molar gas constant, CODATA 2018, exact by the 2019 SI redefinition.
MOLAR_GAS_CONSTANT = Quantity(8.31446261815324, "joule/(mole*kelvin)")

ACTIVATION_ENERGY_UNIT = "joule/mole"
CAPACITANCE_UNIT = "farad"
ENERGY_UNIT = "joule"

OHMIC_RESISTANCE = "ohmic_resistance"
POLARIZATION_RESISTANCE = "polarization_resistance"
POLARIZATION_CAPACITANCE = "polarization_capacitance"
POLARIZATION_VOLTAGE = "polarization_voltage"
TERMINAL_VOLTAGE = "terminal_voltage"
OPEN_CIRCUIT_VOLTAGE = "open_circuit_voltage"
HEAT_GENERATION = "heat_generation"
ELECTRICAL_LOSS = "electrical_loss"
OHMIC_DROP = "ohmic_drop"
LOAD_CURRENT = "load_current"

#: Stated on every record this module produces. Not decoration: a consumer that
#: reads a temperature out of a flagship run is reading a temperature produced
#: without these terms, and the record says so where the number is.
HEAT_MODEL_LIMITATIONS = (
    "reversible entropic heat I*T*dU/dT is not modelled: no entropy "
    "coefficient is measured for this cell, and zero would assert absence "
    "rather than record ignorance",
    "no ageing, hysteresis or second diffusion time constant is modelled",
    "the open-circuit voltage authority carries no temperature axis",
)


def _quantity(value: Any, unit: str, label: str, *, positive: bool = False) -> Quantity:
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
class ArrheniusResistance:
    """A resistance declared at a reference temperature and an activation energy.

    ``activation_energy`` may be zero, and that is a different statement from
    omitting the record: zero says the fit found no temperature dependence in
    the evidence, which is a result. It is never a default -- the caller
    supplies it.
    """

    reference_value: Quantity
    activation_energy: Quantity
    reference_temperature: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reference_value",
            _quantity(self.reference_value, ctx.RESISTANCE_UNIT, "reference_value", positive=True),
        )
        object.__setattr__(
            self,
            "activation_energy",
            _quantity(self.activation_energy, ACTIVATION_ENERGY_UNIT, "activation_energy"),
        )
        object.__setattr__(
            self,
            "reference_temperature",
            _quantity(
                self.reference_temperature,
                ctx.TEMPERATURE_UNIT,
                "reference_temperature",
                positive=True,
            ),
        )

    def at(self, temperature: Quantity) -> Quantity:
        kelvin = _quantity(
            temperature, ctx.TEMPERATURE_UNIT, ctx.CELL_TEMPERATURE, positive=True
        ).magnitude
        reference = self.reference_temperature.magnitude
        exponent = (
            self.activation_energy.magnitude_in(ACTIVATION_ENERGY_UNIT)
            / MOLAR_GAS_CONSTANT.magnitude_in("joule/(mole*kelvin)")
            * (1.0 / kelvin - 1.0 / reference)
        )
        # An Arrhenius factor that overflows is a parameter/operating-point
        # combination this form cannot represent, not a very large resistance.
        if exponent > 700.0 or exponent < -700.0:
            raise InvalidScientificProblem(
                f"Arrhenius exponent {exponent:g} at {kelvin:g} K is outside the "
                f"range this form can evaluate; the declared activation energy and "
                f"operating temperature are not jointly representable"
            )
        value = self.reference_value.magnitude_in(ctx.RESISTANCE_UNIT) * math.exp(exponent)
        if not math.isfinite(value) or value <= 0.0:
            raise InvalidScientificProblem(
                "Arrhenius resistance evaluated to a non-physical value"
            )
        return Quantity(value, ctx.RESISTANCE_UNIT)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_value": self.reference_value.to_dict(),
            "activation_energy": self.activation_energy.to_dict(),
            "reference_temperature": self.reference_temperature.to_dict(),
        }


@dataclass(frozen=True)
class ElectrothermalCell:
    """The flagship cell: charge store, two resistances, one RC, one OCV authority."""

    cell_id: str
    nominal_capacity: Quantity
    coulombic_efficiency: Quantity
    ohmic_resistance: ArrheniusResistance
    polarization_resistance: ArrheniusResistance
    polarization_capacitance: Quantity
    open_circuit_voltage_curve: DeclaredCurve

    def __post_init__(self) -> None:
        cell_id = str(self.cell_id).strip()
        if not cell_id:
            raise InvalidScientificProblem("an electrothermal cell requires a cell_id")
        object.__setattr__(self, "cell_id", cell_id)
        object.__setattr__(
            self,
            "nominal_capacity",
            _quantity(self.nominal_capacity, ctx.CAPACITY_UNIT, ctx.NOMINAL_CAPACITY, positive=True),
        )
        efficiency = _quantity(
            self.coulombic_efficiency, ctx.DIMENSIONLESS, ctx.COULOMBIC_EFFICIENCY, positive=True
        )
        if efficiency.magnitude > 1.0:
            raise InvalidScientificProblem(
                f"{ctx.COULOMBIC_EFFICIENCY} must lie in (0, 1], got {efficiency.magnitude!r}: "
                f"a cell cannot return more charge than crossed its terminals"
            )
        object.__setattr__(self, "coulombic_efficiency", efficiency)
        for label in ("ohmic_resistance", "polarization_resistance"):
            if not isinstance(getattr(self, label), ArrheniusResistance):
                raise InvalidScientificProblem(f"{label} must be an ArrheniusResistance")
        object.__setattr__(
            self,
            "polarization_capacitance",
            _quantity(
                self.polarization_capacitance,
                CAPACITANCE_UNIT,
                POLARIZATION_CAPACITANCE,
                positive=True,
            ),
        )
        curve = self.open_circuit_voltage_curve
        if not isinstance(curve, DeclaredCurve):
            raise InvalidScientificProblem(
                "the flagship cell requires a DeclaredCurve open-circuit voltage "
                "authority; a chord between two endpoints is a different model"
            )
        if curve.against != ctx.STATE_OF_CHARGE:
            raise InvalidScientificProblem(
                f"the open-circuit voltage authority must vary with "
                f"{ctx.STATE_OF_CHARGE!r}, not {curve.against!r}"
            )
        curve_unit = Quantity(1.0, curve.unit)
        curve_unit.require_compatible(
            Quantity(1.0, ctx.VOLTAGE_UNIT), context="open-circuit voltage authority"
        )

    def time_constant(self, temperature: Quantity) -> Quantity:
        return (
            self.polarization_resistance.at(temperature) * self.polarization_capacitance
        ).to(ctx.TIME_UNIT)

    @property
    def ocv_digest(self) -> str:
        return self.open_circuit_voltage_curve.fingerprint

    def to_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            ctx.NOMINAL_CAPACITY: self.nominal_capacity.to_dict(),
            ctx.COULOMBIC_EFFICIENCY: self.coulombic_efficiency.to_dict(),
            OHMIC_RESISTANCE: self.ohmic_resistance.to_dict(),
            POLARIZATION_RESISTANCE: self.polarization_resistance.to_dict(),
            POLARIZATION_CAPACITANCE: self.polarization_capacitance.to_dict(),
            "open_circuit_voltage_authority": {
                "digest": self.ocv_digest,
                "quantity": self.open_circuit_voltage_curve.quantity,
                "against": self.open_circuit_voltage_curve.against,
                "interval": [
                    self.open_circuit_voltage_curve.lower,
                    self.open_circuit_voltage_curve.upper,
                ],
                "unit": self.open_circuit_voltage_curve.unit,
                "source": self.open_circuit_voltage_curve.source,
            },
            "limitations": list(HEAT_MODEL_LIMITATIONS),
        }


@dataclass(frozen=True)
class ElectricalState:
    """The two electrical states the cell carries between steps."""

    state_of_charge: Quantity
    polarization_voltage: Quantity

    def __post_init__(self) -> None:
        soc = _quantity(self.state_of_charge, ctx.DIMENSIONLESS, ctx.STATE_OF_CHARGE)
        if not 0.0 <= soc.magnitude <= 1.0:
            raise InvalidScientificProblem(
                f"{ctx.STATE_OF_CHARGE} must lie in [0, 1], got {soc.magnitude!r}"
            )
        object.__setattr__(self, "state_of_charge", soc)
        object.__setattr__(
            self,
            "polarization_voltage",
            _quantity(self.polarization_voltage, ctx.VOLTAGE_UNIT, POLARIZATION_VOLTAGE),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            ctx.STATE_OF_CHARGE: self.state_of_charge.to_dict(),
            POLARIZATION_VOLTAGE: self.polarization_voltage.to_dict(),
        }


@dataclass(frozen=True)
class ElectrothermalStep:
    """One advanced interval, with every quantity the step derived."""

    initial_state: ElectricalState
    final_state: ElectricalState
    operating_temperature: Quantity
    load_current: Quantity
    duration: Quantity
    ohmic_resistance: Quantity
    polarization_resistance: Quantity
    time_constant: Quantity
    alpha: float
    open_circuit_voltage: Quantity
    ohmic_drop: Quantity
    polarization_drop: Quantity
    terminal_voltage: Quantity
    mean_polarization_voltage: Quantity
    heat_generation: Quantity
    electrical_loss: Quantity

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_state": self.initial_state.to_dict(),
            "final_state": self.final_state.to_dict(),
            ctx.CELL_TEMPERATURE: self.operating_temperature.to_dict(),
            LOAD_CURRENT: self.load_current.to_dict(),
            ctx.DURATION: self.duration.to_dict(),
            OHMIC_RESISTANCE: self.ohmic_resistance.to_dict(),
            POLARIZATION_RESISTANCE: self.polarization_resistance.to_dict(),
            "time_constant": self.time_constant.to_dict(),
            "alpha": self.alpha,
            OPEN_CIRCUIT_VOLTAGE: self.open_circuit_voltage.to_dict(),
            OHMIC_DROP: self.ohmic_drop.to_dict(),
            POLARIZATION_VOLTAGE: self.polarization_drop.to_dict(),
            TERMINAL_VOLTAGE: self.terminal_voltage.to_dict(),
            "mean_polarization_voltage": self.mean_polarization_voltage.to_dict(),
            HEAT_GENERATION: self.heat_generation.to_dict(),
            ELECTRICAL_LOSS: self.electrical_loss.to_dict(),
            "limitations": list(HEAT_MODEL_LIMITATIONS),
        }


class ChargeStateExhausted(InvalidScientificProblem):
    """The step would leave the declared charge interval.

    A distinct type because a caller marching a measured profile has a correct
    response to this one -- stop and say the cell reached the edge of the
    model's charge axis -- and no correct response to a unit error.
    """


class OpenCircuitVoltageUnavailable(InvalidScientificProblem):
    """The OCV authority declines to answer at the reached state of charge."""


def advance_electrothermal_step(
    cell: ElectrothermalCell,
    state: ElectricalState,
    *,
    current: Quantity,
    duration: Quantity,
    temperature: Quantity,
) -> ElectrothermalStep:
    """Advance one interval of constant current at one held cell temperature.

    The temperature is an input, not a state: this kernel is the electrical
    half of a coupled system, and the thermal half owns the temperature. A
    caller running this alone is running it at a temperature it declared.
    """

    if not isinstance(cell, ElectrothermalCell):
        raise InvalidScientificProblem("advance_electrothermal_step expects an ElectrothermalCell")
    if not isinstance(state, ElectricalState):
        raise InvalidScientificProblem("state must be an ElectricalState")

    current = _quantity(current, ctx.CURRENT_UNIT, LOAD_CURRENT)
    duration = _quantity(duration, ctx.TIME_UNIT, ctx.DURATION, positive=True)
    temperature = _quantity(
        temperature, ctx.TEMPERATURE_UNIT, ctx.CELL_TEMPERATURE, positive=True
    )

    current_a = current.magnitude
    duration_s = duration.magnitude
    capacity_ah = cell.nominal_capacity.magnitude
    efficiency = cell.coulombic_efficiency.magnitude

    initial_soc = state.state_of_charge.magnitude
    final_soc = initial_soc - current_a * (duration_s / 3600.0) / (efficiency * capacity_ah)
    if not 0.0 <= final_soc <= 1.0:
        raise ChargeStateExhausted(
            f"the step leaves the declared charge interval: z0={initial_soc:g}, "
            f"z1={final_soc:g}. The state is not clipped: a cell held at z=0 while "
            f"current continues to flow is a different physical situation from one "
            f"this model represents"
        )

    r0 = cell.ohmic_resistance.at(temperature)
    r1 = cell.polarization_resistance.at(temperature)
    tau = (r1 * cell.polarization_capacitance).to(ctx.TIME_UNIT)
    tau_s = tau.magnitude
    alpha = math.exp(-duration_s / tau_s)

    r1_ohm = r1.magnitude
    vp0 = state.polarization_voltage.magnitude
    vp_inf = current_a * r1_ohm
    vp1 = vp0 * alpha + vp_inf * (1.0 - alpha)
    # Exact mean of vp(t) = vp_inf + (vp0 - vp_inf) exp(-t/tau) over [0, dt].
    mean_vp = vp_inf + (vp0 - vp_inf) * (tau_s / duration_s) * (1.0 - alpha)

    final_state = ElectricalState(
        Quantity(final_soc, ctx.DIMENSIONLESS),
        Quantity(vp1, ctx.VOLTAGE_UNIT),
    )
    evaluated = cell.open_circuit_voltage_curve.evaluate(final_state.state_of_charge)
    if evaluated.status is not ValidityStatus.IN_DOMAIN or evaluated.value is None:
        raise OpenCircuitVoltageUnavailable(
            f"the open-circuit voltage authority gives no value at "
            f"{ctx.STATE_OF_CHARGE} = {final_soc:g}: {evaluated.reason}"
        )
    ocv = evaluated.value.to(ctx.VOLTAGE_UNIT)

    r0_ohm = r0.magnitude
    ohmic_drop = Quantity(current_a * r0_ohm, ctx.VOLTAGE_UNIT)
    polarization_drop = Quantity(vp1, ctx.VOLTAGE_UNIT)
    terminal = Quantity(ocv.magnitude - ohmic_drop.magnitude - vp1, ctx.VOLTAGE_UNIT)

    # Irreversible dissipation only, and both terms are losses in the sense
    # that they carry the same sign under charge and discharge: I^2 R0 is even
    # in the current, and vp tracks the sign of I through the RC branch.
    heat_w = current_a * current_a * r0_ohm + current_a * mean_vp
    if heat_w < 0.0:
        # Reachable only in the first instants after a current reversal, while
        # the polarization branch still carries the previous direction. It is a
        # real feature of the RC branch giving stored charge back, not an
        # error, and it is recorded rather than floored at zero.
        pass
    heat = Quantity(heat_w, ctx.POWER_UNIT)

    return ElectrothermalStep(
        initial_state=state,
        final_state=final_state,
        operating_temperature=temperature,
        load_current=current,
        duration=duration,
        ohmic_resistance=r0,
        polarization_resistance=r1,
        time_constant=tau,
        alpha=alpha,
        open_circuit_voltage=ocv,
        ohmic_drop=ohmic_drop,
        polarization_drop=polarization_drop,
        terminal_voltage=terminal,
        mean_polarization_voltage=Quantity(mean_vp, ctx.VOLTAGE_UNIT),
        heat_generation=heat,
        electrical_loss=Quantity(heat_w * duration_s, ENERGY_UNIT),
    )


__all__ = [
    "ACTIVATION_ENERGY_UNIT",
    "CAPACITANCE_UNIT",
    "ELECTRICAL_LOSS",
    "HEAT_GENERATION",
    "HEAT_MODEL_LIMITATIONS",
    "LOAD_CURRENT",
    "MOLAR_GAS_CONSTANT",
    "OHMIC_DROP",
    "OHMIC_RESISTANCE",
    "OPEN_CIRCUIT_VOLTAGE",
    "POLARIZATION_CAPACITANCE",
    "POLARIZATION_RESISTANCE",
    "POLARIZATION_VOLTAGE",
    "TERMINAL_VOLTAGE",
    "ArrheniusResistance",
    "ChargeStateExhausted",
    "ElectricalState",
    "ElectrothermalCell",
    "ElectrothermalStep",
    "OpenCircuitVoltageUnavailable",
    "advance_electrothermal_step",
]
