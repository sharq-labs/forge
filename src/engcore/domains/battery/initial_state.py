"""Where a trajectory's charge state starts, and on what evidence.

Why this module exists
----------------------
Sprint 3 gave every admitted trajectory the same initial condition: fully
charged. The evidence behind it was one screen -- the first measured voltage
had to sit within 50 mV of the open-circuit voltage authority's full-charge
anchor. That screen is real and it caught a cell that was not full. It is
still only one line of evidence, and terminal voltage near the top of the
charge axis is a weak discriminator: the curve is steep in charge but the
measured rest voltage of a *relaxing* cell and of a *full* cell differ by
millivolts while their charge states differ by percent.

What this module is
-------------------
:class:`InitialBatteryState` records what was concluded and what it was
concluded from. Two lines of evidence are read, and they are independent:

* the **preceding charge cycle** -- did it run the declared constant-current /
  constant-voltage protocol to its declared termination? That is a statement
  about the charger, not about the cell's voltage;
* the **first rest sample** of the trajectory itself -- is the cell at rest,
  and is its voltage consistent with the full-charge anchor?

:data:`InitialStateBasis` names which of them carried the conclusion. When the
two disagree, or when neither is available, the authority answers
:data:`InitialStateBasis.UNKNOWN` and carries no charge state. There is no
fallback that assumes full charge, because that assumption is precisely the one
the Sprint 3 record says was never independently tested.

The charge state this module reports is a fraction of
``initial_available_charge`` -- the capacity
:mod:`engcore.domains.battery.capacity` established from prior cycles -- not of
the manufacturer's rating. A state of charge of 1.0 here means "this cell holds
the charge a like-for-like prior cycle delivered", which is a measured
statement about this cell.

What this module is not
-----------------------
Not a model and not a validation check. It reads measurements a caller
supplies and produces one record with a digest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Any, Sequence

from ...scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from ...scientific.units.quantity import Quantity
from . import context as ctx
from .capacity import CellCapacityState

#: Schema of the serialized initial-state record.
INITIAL_STATE_SCHEMA = "battery.initial_state/1"


class BatteryInitialStateError(ValueError):
    """An initial-state record was asked to hold something it cannot mean."""


class InitialStateBasis(str, Enum):
    """What established the starting charge state."""

    #: The preceding charge ran the declared CC-CV protocol to termination AND
    #: the trajectory's first rest sample agrees with the full-charge anchor.
    #: Two independent lines, agreeing.
    CHARGE_TERMINATION_AND_REST_VOLTAGE = "charge_termination_and_rest_voltage"

    #: The preceding charge terminated as declared, but no usable rest sample
    #: opens the trajectory, so the charger is the only witness.
    CHARGE_TERMINATION_ONLY = "charge_termination_only"

    #: Nothing admissible, or two lines of evidence that disagree.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ChargeTerminationEvidence:
    """What the charge cycle before this trajectory did."""

    cycle_id: str
    final_current: Quantity  # ampere, magnitude at the last sample
    final_voltage: Quantity  # volt
    declared_termination_current: Quantity
    declared_termination_voltage: Quantity
    provenance: str = ""

    def __post_init__(self) -> None:
        cycle_id = str(self.cycle_id).strip()
        if not cycle_id:
            raise BatteryInitialStateError("charge termination evidence needs a cycle_id")
        object.__setattr__(self, "cycle_id", cycle_id)
        for label, unit in (
            ("final_current", ctx.CURRENT_UNIT),
            ("declared_termination_current", ctx.CURRENT_UNIT),
            ("final_voltage", ctx.VOLTAGE_UNIT),
            ("declared_termination_voltage", ctx.VOLTAGE_UNIT),
        ):
            object.__setattr__(
                self, label, _quantity(getattr(self, label), unit, label)
            )

    @property
    def terminated_as_declared(self) -> bool:
        """Did the charger reach the declared constant-voltage termination?"""
        return (
            self.final_current.magnitude_in(ctx.CURRENT_UNIT)
            <= self.declared_termination_current.magnitude_in(ctx.CURRENT_UNIT)
            and self.final_voltage.magnitude_in(ctx.VOLTAGE_UNIT)
            >= self.declared_termination_voltage.magnitude_in(ctx.VOLTAGE_UNIT)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "final_current_a": self.final_current.magnitude_in(ctx.CURRENT_UNIT),
            "final_voltage_v": self.final_voltage.magnitude_in(ctx.VOLTAGE_UNIT),
            "declared_termination_current_a": (
                self.declared_termination_current.magnitude_in(ctx.CURRENT_UNIT)
            ),
            "declared_termination_voltage_v": (
                self.declared_termination_voltage.magnitude_in(ctx.VOLTAGE_UNIT)
            ),
            "terminated_as_declared": self.terminated_as_declared,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class RestVoltageEvidence:
    """The trajectory's own first sample, if the cell is at rest there."""

    voltage: Quantity
    current: Quantity
    rest_current_floor: Quantity
    full_charge_anchor: Quantity
    anchor_tolerance: Quantity
    provenance: str = ""

    def __post_init__(self) -> None:
        for label, unit in (
            ("voltage", ctx.VOLTAGE_UNIT),
            ("full_charge_anchor", ctx.VOLTAGE_UNIT),
            ("anchor_tolerance", ctx.VOLTAGE_UNIT),
            ("current", ctx.CURRENT_UNIT),
            ("rest_current_floor", ctx.CURRENT_UNIT),
        ):
            object.__setattr__(
                self, label, _quantity(getattr(self, label), unit, label)
            )

    @property
    def at_rest(self) -> bool:
        return abs(self.current.magnitude_in(ctx.CURRENT_UNIT)) < (
            self.rest_current_floor.magnitude_in(ctx.CURRENT_UNIT)
        )

    @property
    def offset_from_anchor(self) -> float:
        return self.voltage.magnitude_in(ctx.VOLTAGE_UNIT) - (
            self.full_charge_anchor.magnitude_in(ctx.VOLTAGE_UNIT)
        )

    @property
    def agrees_with_full_charge(self) -> bool:
        return self.at_rest and abs(self.offset_from_anchor) <= (
            self.anchor_tolerance.magnitude_in(ctx.VOLTAGE_UNIT)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "voltage_v": self.voltage.magnitude_in(ctx.VOLTAGE_UNIT),
            "current_a": self.current.magnitude_in(ctx.CURRENT_UNIT),
            "rest_current_floor_a": self.rest_current_floor.magnitude_in(
                ctx.CURRENT_UNIT
            ),
            "full_charge_anchor_v": self.full_charge_anchor.magnitude_in(
                ctx.VOLTAGE_UNIT
            ),
            "anchor_tolerance_v": self.anchor_tolerance.magnitude_in(
                ctx.VOLTAGE_UNIT
            ),
            "at_rest": self.at_rest,
            "offset_from_anchor_v": self.offset_from_anchor,
            "agrees_with_full_charge": self.agrees_with_full_charge,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class InitialBatteryState:
    """The starting charge state of one trajectory, and what says so."""

    cell_id: str
    experiment_id: str
    trajectory_id: str
    basis: InitialStateBasis
    initial_state_of_charge: Quantity | None = None
    initial_available_charge: Quantity | None = None
    capacity_digest: str = ""
    uncertainty: Uncertainty = field(default_factory=Uncertainty)
    charge_termination: ChargeTerminationEvidence | None = None
    rest_voltage: RestVoltageEvidence | None = None
    assumptions: tuple[str, ...] = ()
    why_unknown: str = ""

    def __post_init__(self) -> None:
        for label in ("cell_id", "experiment_id", "trajectory_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise BatteryInitialStateError(
                    f"an initial-state record requires {label}"
                )
            object.__setattr__(self, label, value)
        object.__setattr__(self, "basis", InitialStateBasis(self.basis))
        if self.initial_state_of_charge is not None:
            state = _quantity(
                self.initial_state_of_charge,
                ctx.DIMENSIONLESS,
                "initial_state_of_charge",
            )
            magnitude = state.magnitude_in(ctx.DIMENSIONLESS)
            if not 0.0 <= magnitude <= 1.0:
                raise BatteryInitialStateError(
                    f"initial state of charge must lie in [0, 1], got {magnitude!r}"
                )
            object.__setattr__(self, "initial_state_of_charge", state)
        if self.initial_available_charge is not None:
            object.__setattr__(
                self,
                "initial_available_charge",
                _quantity(
                    self.initial_available_charge,
                    ctx.CAPACITY_UNIT,
                    "initial_available_charge",
                ),
            )
        if not isinstance(self.uncertainty, Uncertainty):
            raise BatteryInitialStateError("uncertainty must be an Uncertainty record")
        object.__setattr__(
            self, "assumptions", tuple(str(x) for x in self.assumptions)
        )

        if self.basis is InitialStateBasis.UNKNOWN:
            if self.initial_state_of_charge is not None:
                raise BatteryInitialStateError(
                    "an UNKNOWN initial state cannot carry a state of charge; "
                    "an invented exact value is what this record refuses"
                )
            if not str(self.why_unknown).strip():
                raise BatteryInitialStateError(
                    "an UNKNOWN initial state must say why it is unknown"
                )
        else:
            if self.initial_state_of_charge is None:
                raise BatteryInitialStateError(
                    f"basis {self.basis.value} must carry a state of charge"
                )
            if self.charge_termination is None:
                raise BatteryInitialStateError(
                    f"basis {self.basis.value} rests on a charge termination "
                    "and must name the cycle it read"
                )
            if self.initial_available_charge is None:
                raise BatteryInitialStateError(
                    "a known initial state is a fraction of a measured "
                    "available charge and must name it"
                )

    @property
    def is_known(self) -> bool:
        return self.basis is not InitialStateBasis.UNKNOWN

    @property
    def digest(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, allow_nan=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": INITIAL_STATE_SCHEMA,
            "cell_id": self.cell_id,
            "experiment_id": self.experiment_id,
            "trajectory_id": self.trajectory_id,
            "basis": self.basis.value,
            "initial_state_of_charge": (
                self.initial_state_of_charge.magnitude_in(ctx.DIMENSIONLESS)
                if self.initial_state_of_charge is not None
                else None
            ),
            "initial_available_charge_ah": (
                self.initial_available_charge.magnitude_in(ctx.CAPACITY_UNIT)
                if self.initial_available_charge is not None
                else None
            ),
            "capacity_digest": self.capacity_digest,
            "uncertainty": self.uncertainty.to_dict(),
            "charge_termination": (
                self.charge_termination.to_dict()
                if self.charge_termination is not None
                else None
            ),
            "rest_voltage": (
                self.rest_voltage.to_dict() if self.rest_voltage is not None else None
            ),
            "assumptions": list(self.assumptions),
            "why_unknown": self.why_unknown,
        }


def establish_initial_state(
    *,
    cell_id: str,
    experiment_id: str,
    trajectory_id: str,
    capacity: CellCapacityState,
    charge_termination: ChargeTerminationEvidence | None,
    rest_voltage: RestVoltageEvidence | None,
    state_of_charge_standard_uncertainty: float | None = None,
) -> InitialBatteryState:
    """Conclude a starting charge state, or refuse to.

    The capacity state comes first: a state of charge is a fraction of an
    available charge, so a cell whose usable capacity is UNKNOWN has an UNKNOWN
    initial state no matter how convincing its rest voltage is.
    """
    if not isinstance(capacity, CellCapacityState):
        raise BatteryInitialStateError("capacity must be a CellCapacityState")

    def unknown(why: str) -> InitialBatteryState:
        return InitialBatteryState(
            cell_id=cell_id,
            experiment_id=experiment_id,
            trajectory_id=trajectory_id,
            basis=InitialStateBasis.UNKNOWN,
            capacity_digest=capacity.digest,
            charge_termination=charge_termination,
            rest_voltage=rest_voltage,
            why_unknown=why,
        )

    if not capacity.is_known:
        return unknown(
            "the usable capacity of this cell is UNKNOWN, and a state of "
            "charge is a fraction of a capacity: "
            f"{capacity.why_unknown}"
        )
    if charge_termination is None:
        return unknown(
            "no charge cycle precedes this trajectory in the record, so "
            "nothing witnesses how the cell was brought to its starting state"
        )
    if not charge_termination.terminated_as_declared:
        return unknown(
            f"the preceding charge {charge_termination.cycle_id} did not reach "
            "the declared constant-voltage termination; the cell did not "
            "start from the protocol's full-charge state"
        )

    if rest_voltage is not None and rest_voltage.at_rest:
        if not rest_voltage.agrees_with_full_charge:
            return unknown(
                "the preceding charge terminated as declared but the "
                "trajectory's first rest sample sits "
                f"{rest_voltage.offset_from_anchor * 1000.0:.1f} mV from the "
                "full-charge anchor; two independent lines of evidence "
                "disagree and neither is preferred"
            )
        basis = InitialStateBasis.CHARGE_TERMINATION_AND_REST_VOLTAGE
    else:
        basis = InitialStateBasis.CHARGE_TERMINATION_ONLY

    if state_of_charge_standard_uncertainty is None:
        uncertainty = Uncertainty(
            kind=UncertaintyKind.UNKNOWN,
            source=basis.value,
            notes=(
                "no calibration-measured spread of the initial charge state "
                "was supplied; an unquantified spread is not zero"
            ),
        )
    else:
        value = float(state_of_charge_standard_uncertainty)
        if not math.isfinite(value) or value < 0.0:
            raise BatteryInitialStateError(
                "state_of_charge_standard_uncertainty must be finite and >= 0"
            )
        uncertainty = Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(value, ctx.DIMENSIONLESS),
            source=basis.value,
            source_kind=UncertaintySource.MEASUREMENT,
            method=(
                "spread of the like-for-like capacity estimator, which is what "
                "a full-charge state of charge is expressed against"
            ),
        )

    assumptions = [
        "the cell begins holding the charge a like-for-like prior cycle "
        "delivered, so the state of charge is 1.0 against that charge and not "
        "against the manufacturer's rating",
    ]
    if basis is InitialStateBasis.CHARGE_TERMINATION_ONLY:
        assumptions.append(
            "no rest sample opens this trajectory, so the charger's "
            "termination is the only witness to the starting state"
        )

    return InitialBatteryState(
        cell_id=cell_id,
        experiment_id=experiment_id,
        trajectory_id=trajectory_id,
        basis=basis,
        initial_state_of_charge=Quantity(1.0, ctx.DIMENSIONLESS),
        initial_available_charge=capacity.initial_available_charge,
        capacity_digest=capacity.digest,
        uncertainty=uncertainty,
        charge_termination=charge_termination,
        rest_voltage=rest_voltage,
        assumptions=tuple(assumptions),
    )


def _quantity(value: Any, unit: str, label: str) -> Quantity:
    if not isinstance(value, Quantity):
        raise BatteryInitialStateError(f"{label} must be a Quantity with a unit")
    value.require_compatible(Quantity(1.0, unit), context=label)
    return value


__all__ = [
    "INITIAL_STATE_SCHEMA",
    "BatteryInitialStateError",
    "ChargeTerminationEvidence",
    "InitialBatteryState",
    "InitialStateBasis",
    "RestVoltageEvidence",
    "establish_initial_state",
]
