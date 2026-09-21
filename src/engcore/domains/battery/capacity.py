"""Cell capacity and state of health, stated explicitly instead of assumed.

Why this module exists
----------------------
A charge-state basis is the denominator of every open-circuit voltage lookup a
cell model makes. Sprint 3 used one declared constant -- the manufacturer's
2 Ah rating -- for every cell in every experiment, and named it
``nominal_capacity``. Two different things were hiding behind that one number:

* what the manufacturer rates the cell at, and
* how much charge *this* cell can actually deliver *now*.

They are not the same quantity and they do not even have the same order of
error. On the NASA archive the rating sits about 30 % above the charge the
cells actually deliver, and the gap between two cells of the same batch
reaches 8 % at room temperature. A model whose charge state is a fraction of
the rating therefore evaluates two cells at different true depths of discharge
while believing they are at the same one.

What this module is
-------------------
:class:`CellCapacityState` is the explicit identity. It separates

``nominal_capacity``
    the manufacturer's rating. A declared constant, never a measurement of a
    particular cell.
``reference_capacity``
    the earliest admissible measured capacity of *this* cell under *this*
    protocol -- the denominator state of health is measured against.
``measured_usable_capacity``
    the most recent admissible measurement of what this cell delivers under
    this protocol.
``initial_available_charge``
    the charge available at the first instant of the trajectory about to be
    predicted. This is the charge-state basis a march should use.
``soh_capacity``
    ``measured_usable_capacity / reference_capacity``, dimensionless.

What this module refuses to do
------------------------------
**It never reads the trajectory it is asked about.** The capacity of the run
being predicted is the answer to the prediction, and a basis taken from it
would make every charge state exactly right by construction. Every estimator
below takes its evidence from cycles that completed *before* the trajectory
starts, and :func:`establish_capacity` is given those cycles only.

When no admissible prior evidence exists the authority answers
:data:`CapacityBasis.UNKNOWN` with no capacity at all, and a caller that wants
a number has to refuse. An invented basis is the failure this module exists to
prevent, so there is no fallback to the rating.

What this module is not
-----------------------
Not a model, not a fitter and not a validation check. It produces one record
from measurements a caller supplies. Nothing here is promoted by running it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from ...scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from ...scientific.units.quantity import Quantity
from . import context as ctx

#: Schema of the serialized capacity state.
CAPACITY_STATE_SCHEMA = "battery.capacity_state/1"


class BatteryCapacityError(ValueError):
    """A capacity record was asked to hold something it cannot mean."""


class CapacityBasis(str, Enum):
    """Where an available-charge number came from.

    The order is the order of preference in :func:`establish_capacity`, and
    every member except :data:`UNKNOWN` names evidence that completed before
    the trajectory it is used for.
    """

    #: The most recent prior discharge of this cell at the same load level and
    #: the same ambient. Like for like: same protocol, same cutoff, so what it
    #: measures is the same quantity the next discharge will deliver.
    PRIOR_LIKE_FOR_LIKE_DISCHARGE = "prior_like_for_like_discharge"

    #: The charge the immediately preceding charge cycle put into the cell.
    #: Admissible only when that charge followed a like-for-like discharge:
    #: otherwise it measures the charge *replaced*, which is the previous
    #: discharge's depth and not this cell's usable capacity.
    PRECEDING_CHARGE_THROUGHPUT = "preceding_charge_throughput"

    #: No admissible prior evidence. Carries no capacity.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PriorCycle:
    """One completed cycle of this cell, offered as evidence.

    ``sequence`` orders cycles within the cell; only cycles with a strictly
    smaller ``sequence`` than the trajectory's own are admissible, and
    :func:`establish_capacity` enforces that rather than trusting the caller.
    """

    cycle_id: str
    sequence: int
    kind: str  # "discharge" or "charge"
    throughput: Quantity  # magnitude of charge moved, ampere_hour
    load_current: Quantity | None = None  # ampere, discharges only
    ambient_temperature: Quantity | None = None  # kelvin
    provenance: str = ""

    def __post_init__(self) -> None:
        cycle_id = str(self.cycle_id).strip()
        if not cycle_id:
            raise BatteryCapacityError("a prior cycle requires a cycle_id")
        object.__setattr__(self, "cycle_id", cycle_id)
        kind = str(self.kind).strip().lower()
        if kind not in ("discharge", "charge"):
            raise BatteryCapacityError(
                f"prior cycle kind must be 'discharge' or 'charge', got {kind!r}"
            )
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "sequence", int(self.sequence))
        throughput = _capacity(self.throughput, "throughput")
        object.__setattr__(self, "throughput", throughput)
        if self.load_current is not None:
            object.__setattr__(
                self,
                "load_current",
                _quantity(self.load_current, ctx.CURRENT_UNIT, "load_current"),
            )
        if self.ambient_temperature is not None:
            object.__setattr__(
                self,
                "ambient_temperature",
                _quantity(
                    self.ambient_temperature,
                    ctx.TEMPERATURE_UNIT,
                    "ambient_temperature",
                ),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "sequence": self.sequence,
            "kind": self.kind,
            "throughput_ah": self.throughput.magnitude_in(ctx.CAPACITY_UNIT),
            "load_current_a": (
                self.load_current.magnitude_in(ctx.CURRENT_UNIT)
                if self.load_current is not None
                else None
            ),
            "ambient_temperature_k": (
                self.ambient_temperature.magnitude_in(ctx.TEMPERATURE_UNIT)
                if self.ambient_temperature is not None
                else None
            ),
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class CellCapacityState:
    """What is known about one cell's capacity before one trajectory runs."""

    cell_id: str
    experiment_id: str
    basis: CapacityBasis
    nominal_capacity: Quantity | None = None
    reference_capacity: Quantity | None = None
    measured_usable_capacity: Quantity | None = None
    initial_available_charge: Quantity | None = None
    soh_capacity: Quantity | None = None
    uncertainty: Uncertainty = field(default_factory=Uncertainty)
    source_evidence: tuple[PriorCycle, ...] = ()
    assumptions: tuple[str, ...] = ()
    why_unknown: str = ""

    def __post_init__(self) -> None:
        for label in ("cell_id", "experiment_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise BatteryCapacityError(f"a capacity state requires {label}")
            object.__setattr__(self, label, value)
        object.__setattr__(self, "basis", CapacityBasis(self.basis))
        for label in (
            "nominal_capacity",
            "reference_capacity",
            "measured_usable_capacity",
            "initial_available_charge",
        ):
            value = getattr(self, label)
            if value is not None:
                object.__setattr__(self, label, _capacity(value, label))
        if self.soh_capacity is not None:
            object.__setattr__(
                self,
                "soh_capacity",
                _quantity(self.soh_capacity, ctx.DIMENSIONLESS, "soh_capacity"),
            )
        if not isinstance(self.uncertainty, Uncertainty):
            raise BatteryCapacityError("uncertainty must be an Uncertainty record")
        object.__setattr__(self, "source_evidence", tuple(self.source_evidence))
        object.__setattr__(
            self, "assumptions", tuple(str(x) for x in self.assumptions)
        )

        if self.basis is CapacityBasis.UNKNOWN:
            if self.initial_available_charge is not None:
                raise BatteryCapacityError(
                    "an UNKNOWN capacity basis cannot carry an available "
                    "charge: that is the invented number this record exists "
                    "to refuse"
                )
            if not str(self.why_unknown).strip():
                raise BatteryCapacityError(
                    "an UNKNOWN capacity basis must say why it is unknown"
                )
            if (
                UncertaintyKind(self.uncertainty.kind)
                is not UncertaintyKind.UNKNOWN
            ):
                raise BatteryCapacityError(
                    "an UNKNOWN capacity basis cannot carry a quantified "
                    "uncertainty about a capacity it does not have"
                )
        else:
            if self.initial_available_charge is None:
                raise BatteryCapacityError(
                    f"basis {self.basis.value} must carry an "
                    "initial_available_charge"
                )
            if not self.source_evidence:
                raise BatteryCapacityError(
                    f"basis {self.basis.value} must name the prior cycles it "
                    "was read from; a capacity with no evidence behind it is "
                    "a declaration, not a measurement"
                )

    @property
    def is_known(self) -> bool:
        return self.basis is not CapacityBasis.UNKNOWN

    @property
    def digest(self) -> str:
        """SHA-256 over the serialized record. Identity, not a checksum."""
        payload = json.dumps(self.to_dict(), sort_keys=True, allow_nan=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        def ah(value: Quantity | None) -> float | None:
            return (
                value.magnitude_in(ctx.CAPACITY_UNIT) if value is not None else None
            )

        return {
            "schema": CAPACITY_STATE_SCHEMA,
            "cell_id": self.cell_id,
            "experiment_id": self.experiment_id,
            "basis": self.basis.value,
            "nominal_capacity_ah": ah(self.nominal_capacity),
            "reference_capacity_ah": ah(self.reference_capacity),
            "measured_usable_capacity_ah": ah(self.measured_usable_capacity),
            "initial_available_charge_ah": ah(self.initial_available_charge),
            "soh_capacity": (
                self.soh_capacity.magnitude_in(ctx.DIMENSIONLESS)
                if self.soh_capacity is not None
                else None
            ),
            "uncertainty": self.uncertainty.to_dict(),
            "source_evidence": [item.to_dict() for item in self.source_evidence],
            "assumptions": list(self.assumptions),
            "why_unknown": self.why_unknown,
        }

    @classmethod
    def unknown(
        cls,
        *,
        cell_id: str,
        experiment_id: str,
        why: str,
        nominal_capacity: Quantity | None = None,
        assumptions: Sequence[str] = (),
    ) -> "CellCapacityState":
        return cls(
            cell_id=cell_id,
            experiment_id=experiment_id,
            basis=CapacityBasis.UNKNOWN,
            nominal_capacity=nominal_capacity,
            why_unknown=why,
            assumptions=tuple(assumptions),
        )


def establish_capacity(
    *,
    cell_id: str,
    experiment_id: str,
    sequence: int,
    load_current: Quantity,
    ambient_temperature: Quantity,
    prior_cycles: Iterable[PriorCycle],
    nominal_capacity: Quantity | None = None,
    relative_standard_uncertainty: float | None = None,
    current_tolerance: Quantity | None = None,
    ambient_tolerance: Quantity | None = None,
    plausible_range: tuple[Quantity, Quantity] | None = None,
) -> CellCapacityState:
    """Read a capacity state off evidence that completed before ``sequence``.

    ``sequence`` is the trajectory's own position in the cell's cycle order.
    Every cycle in ``prior_cycles`` whose sequence is not strictly smaller is
    discarded here rather than trusted, because a caller that passed the
    trajectory's own cycle would otherwise leak the answer into its basis.

    ``relative_standard_uncertainty`` is the spread of this estimator measured
    on calibration evidence, as a fraction of the capacity. It is supplied, not
    invented: with nothing supplied the record carries
    :data:`UncertaintyKind.UNKNOWN`, because an unquantified spread is not zero.
    """
    current_tolerance = current_tolerance or Quantity(0.3, ctx.CURRENT_UNIT)
    ambient_tolerance = ambient_tolerance or Quantity(5.0, ctx.TEMPERATURE_UNIT)
    low, high = plausible_range or (
        Quantity(0.5, ctx.CAPACITY_UNIT),
        Quantity(2.4, ctx.CAPACITY_UNIT),
    )
    low_ah = low.magnitude_in(ctx.CAPACITY_UNIT)
    high_ah = high.magnitude_in(ctx.CAPACITY_UNIT)
    load_a = _quantity(load_current, ctx.CURRENT_UNIT, "load_current").magnitude_in(
        ctx.CURRENT_UNIT
    )
    ambient_k = _quantity(
        ambient_temperature, ctx.TEMPERATURE_UNIT, "ambient_temperature"
    ).magnitude_in(ctx.TEMPERATURE_UNIT)
    current_tol = current_tolerance.magnitude_in(ctx.CURRENT_UNIT)
    ambient_tol = ambient_tolerance.magnitude_in(ctx.TEMPERATURE_UNIT)
    sequence = int(sequence)

    admissible: list[PriorCycle] = []
    for cycle in prior_cycles:
        if not isinstance(cycle, PriorCycle):
            raise BatteryCapacityError(
                "prior evidence must be PriorCycle records, so the sequence "
                "that makes it prior is part of the record"
            )
        if cycle.sequence >= sequence:
            continue
        admissible.append(cycle)

    like: list[PriorCycle] = []
    for cycle in admissible:
        if cycle.kind != "discharge":
            continue
        if cycle.load_current is None or cycle.ambient_temperature is None:
            continue
        if abs(cycle.load_current.magnitude_in(ctx.CURRENT_UNIT) - load_a) > current_tol:
            continue
        if (
            abs(
                cycle.ambient_temperature.magnitude_in(ctx.TEMPERATURE_UNIT)
                - ambient_k
            )
            > ambient_tol
        ):
            continue
        throughput = cycle.throughput.magnitude_in(ctx.CAPACITY_UNIT)
        if not low_ah <= throughput <= high_ah:
            continue
        like.append(cycle)

    if not like:
        return CellCapacityState.unknown(
            cell_id=cell_id,
            experiment_id=experiment_id,
            nominal_capacity=nominal_capacity,
            why=(
                f"no prior discharge of {cell_id} before cycle {sequence} ran at "
                f"{load_a:g} A within {current_tol:g} A and at "
                f"{ambient_k:g} K within {ambient_tol:g} K with a delivered "
                f"capacity inside [{low_ah:g}, {high_ah:g}] Ah; the usable "
                "capacity under this protocol has not been measured on this "
                "cell yet"
            ),
            assumptions=(
                "a capacity measured at a different load level or ambient is "
                "not the capacity this protocol will deliver, so it is not "
                "substituted",
            ),
        )

    like.sort(key=lambda item: item.sequence)
    latest = like[-1]
    earliest = like[0]
    usable = latest.throughput
    reference = earliest.throughput
    usable_ah = usable.magnitude_in(ctx.CAPACITY_UNIT)
    reference_ah = reference.magnitude_in(ctx.CAPACITY_UNIT)

    evidence = [latest]
    if earliest is not latest:
        evidence.append(earliest)

    # The immediately preceding charge, admissible as a cross-check only when
    # it followed the like-for-like discharge we just used: otherwise it is the
    # charge replaced after some other discharge, which is a different quantity.
    preceding_charge = None
    for cycle in sorted(admissible, key=lambda item: item.sequence, reverse=True):
        if cycle.kind == "charge":
            preceding_charge = cycle
            break
    cross_check = None
    if (
        preceding_charge is not None
        and preceding_charge.sequence > latest.sequence
        and not any(
            c.kind == "discharge" and latest.sequence < c.sequence < preceding_charge.sequence
            for c in admissible
        )
    ):
        cross_check = preceding_charge.throughput.magnitude_in(ctx.CAPACITY_UNIT)
        evidence.append(preceding_charge)

    if relative_standard_uncertainty is None:
        uncertainty = Uncertainty(
            kind=UncertaintyKind.UNKNOWN,
            source=CapacityBasis.PRIOR_LIKE_FOR_LIKE_DISCHARGE.value,
            notes=(
                "no calibration-measured spread for this estimator was "
                "supplied; an unquantified spread is not zero"
            ),
        )
    else:
        relative = float(relative_standard_uncertainty)
        if not math.isfinite(relative) or relative < 0.0:
            raise BatteryCapacityError(
                "relative_standard_uncertainty must be a finite fraction >= 0"
            )
        uncertainty = Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(relative * usable_ah, ctx.CAPACITY_UNIT),
            source=CapacityBasis.PRIOR_LIKE_FOR_LIKE_DISCHARGE.value,
            source_kind=UncertaintySource.MEASUREMENT,
            method=(
                "spread of this estimator against the delivered capacity it "
                "predicts, measured on calibration cells only"
            ),
        )

    assumptions = [
        "the charge protocol between the evidence cycle and this trajectory is "
        "the one the evidence cycle was charged with",
        "capacity fade between two consecutive like-for-like cycles is inside "
        "the declared estimator spread",
    ]
    if cross_check is not None:
        assumptions.append(
            f"the preceding charge replaced {cross_check:.4f} Ah, which is a "
            f"cross-check on the {usable_ah:.4f} Ah basis and not the basis"
        )

    return CellCapacityState(
        cell_id=cell_id,
        experiment_id=experiment_id,
        basis=CapacityBasis.PRIOR_LIKE_FOR_LIKE_DISCHARGE,
        nominal_capacity=nominal_capacity,
        reference_capacity=reference,
        measured_usable_capacity=usable,
        initial_available_charge=usable,
        soh_capacity=Quantity(usable_ah / reference_ah, ctx.DIMENSIONLESS)
        if reference_ah > 0.0
        else None,
        uncertainty=uncertainty,
        source_evidence=tuple(evidence),
        assumptions=tuple(assumptions),
    )


def _quantity(value: Any, unit: str, label: str) -> Quantity:
    if not isinstance(value, Quantity):
        raise BatteryCapacityError(f"{label} must be a Quantity with a unit")
    value.require_compatible(Quantity(1.0, unit), context=label)
    return value


def _capacity(value: Any, label: str) -> Quantity:
    quantity = _quantity(value, ctx.CAPACITY_UNIT, label)
    if quantity.magnitude_in(ctx.CAPACITY_UNIT) <= 0.0:
        raise BatteryCapacityError(f"{label} must be a positive charge")
    return quantity


__all__ = [
    "CAPACITY_STATE_SCHEMA",
    "BatteryCapacityError",
    "CapacityBasis",
    "CellCapacityState",
    "PriorCycle",
    "establish_capacity",
]
