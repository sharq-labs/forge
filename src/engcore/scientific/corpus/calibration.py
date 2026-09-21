"""Calibrated parameters as an artifact, not as an update.

A fit produces a candidate. It does not produce authority. The distinction is
the whole of this module: a :class:`CalibratedParameterSet` records what was
fitted, to which dataset, under which objective, with what diagnostics -- and
it is inert until something explicitly promotes it. Nothing here writes to a
registry, and no production scientific authority changes because a fit ran.

PHYSICALLY IMPOSSIBLE IS REFUSED, NOT WARNED ABOUT
---------------------------------------------------
A parameter declares its physical bounds, and a fitted value outside them is
refused at construction. A negative internal resistance is not a slightly bad
fit that a downstream consumer can weigh against the rest; it is a value the
physics forbids, and a record carrying it would let an optimizer's failure
travel as a scientific result.

The bounds are the model's, not the optimizer's. A bound is declared because
the quantity cannot take values outside it -- not because the search was
started somewhere convenient.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, normalize_unit
from ..units.validation import require_same_dimension
from .dataset import DatasetSplit
from .source import CorpusError, require_quantity, sha256_hex, text

PARAMETER_SPEC_SCHEMA = schema_string("corpus_calibration_parameter_spec")
FITTED_PARAMETER_SCHEMA = schema_string("corpus_fitted_parameter")
CALIBRATION_OBJECTIVE_SCHEMA = schema_string("corpus_calibration_objective")
PARAMETER_SET_SCHEMA = schema_string("corpus_calibrated_parameter_set")


class CalibrationError(CorpusError):
    """A calibration artifact refuses to record what it was given."""


class PriorSource(str, Enum):
    """Where a parameter's starting knowledge came from. Never guessed."""

    MEASURED = "measured"
    LITERATURE = "literature"
    MANUFACTURER = "manufacturer"
    ASSUMED = "assumed"
    NONE = "none"


class Identifiability(str, Enum):
    """Whether the data actually constrained this parameter.

    ``UNKNOWN`` is the default and the honest answer whenever no diagnostic was
    computed. A parameter reported as identified because nobody checked is the
    failure mode this enum exists to prevent.
    """

    IDENTIFIED = "identified"
    WEAK = "weak"
    UNIDENTIFIED = "unidentified"
    UNKNOWN = "unknown"


@dataclass(frozen=True, order=True)
class CalibrationParameterSpec:
    """One free parameter: its identity, unit, physical bounds and prior."""

    parameter_id: str
    unit: str
    lower_bound: Quantity | None = None
    upper_bound: Quantity | None = None
    prior_source: PriorSource = PriorSource.NONE
    prior_note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "parameter_id", text(self.parameter_id, label="parameter_id")
        )
        object.__setattr__(self, "unit", normalize_unit(self.unit))
        object.__setattr__(self, "prior_source", PriorSource(self.prior_source))
        reference = Quantity(1.0, self.unit)
        for label in ("lower_bound", "upper_bound"):
            bound = getattr(self, label)
            if bound is None:
                continue
            require_quantity(bound, label=f"{self.parameter_id} {label}")
            require_same_dimension(
                bound, reference, context=f"{self.parameter_id} {label}"
            )
        if self.lower_bound is not None and self.upper_bound is not None:
            if self.lower_bound.magnitude_in(self.unit) >= self.upper_bound.magnitude_in(
                self.unit
            ):
                raise CalibrationError(
                    f"parameter {self.parameter_id!r} lower bound is not below its upper bound"
                )
        if self.prior_source is PriorSource.NONE and self.prior_note:
            raise CalibrationError(
                f"parameter {self.parameter_id!r} states a prior note with no prior source"
            )
        object.__setattr__(self, "prior_note", str(self.prior_note).strip())

    def admits(self, value: Quantity) -> bool:
        magnitude = value.magnitude_in(self.unit)
        if self.lower_bound is not None and magnitude < self.lower_bound.magnitude_in(self.unit):
            return False
        if self.upper_bound is not None and magnitude > self.upper_bound.magnitude_in(self.unit):
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARAMETER_SPEC_SCHEMA,
            "parameter_id": self.parameter_id,
            "unit": self.unit,
            "lower_bound": None if self.lower_bound is None else self.lower_bound.to_dict(),
            "upper_bound": None if self.upper_bound is None else self.upper_bound.to_dict(),
            "prior_source": self.prior_source.value,
            "prior_note": self.prior_note,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CalibrationParameterSpec":
        require_schema(payload, PARAMETER_SPEC_SCHEMA)
        lower = payload.get("lower_bound")
        upper = payload.get("upper_bound")
        return cls(
            payload["parameter_id"],
            payload["unit"],
            None if lower is None else Quantity.from_dict(lower),
            None if upper is None else Quantity.from_dict(upper),
            PriorSource(payload.get("prior_source", "none")),
            payload.get("prior_note", ""),
        )


@dataclass(frozen=True, order=True)
class FittedParameter:
    """One fitted value, with whatever the fit could honestly say about it."""

    parameter_id: str
    value: Quantity
    identifiability: Identifiability = Identifiability.UNKNOWN
    standard_error: Quantity | None = None
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "parameter_id", text(self.parameter_id, label="parameter_id")
        )
        object.__setattr__(
            self, "value", require_quantity(self.value, label=f"{self.parameter_id} value")
        )
        object.__setattr__(self, "identifiability", Identifiability(self.identifiability))
        if self.standard_error is not None:
            require_quantity(
                self.standard_error, label=f"{self.parameter_id} standard_error"
            )
            require_same_dimension(
                self.standard_error,
                self.value,
                context=f"{self.parameter_id} standard_error",
            )
            if self.standard_error.magnitude < 0.0:
                raise CalibrationError(
                    f"parameter {self.parameter_id!r} standard error is negative"
                )
        if (
            self.identifiability is not Identifiability.UNKNOWN
            and self.standard_error is None
            and self.identifiability is not Identifiability.UNIDENTIFIED
        ):
            raise CalibrationError(
                f"parameter {self.parameter_id!r} claims identifiability "
                f"{self.identifiability.value!r} with no standard error; the claim "
                f"needs the diagnostic it came from"
            )
        object.__setattr__(self, "note", str(self.note).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FITTED_PARAMETER_SCHEMA,
            "parameter_id": self.parameter_id,
            "value": self.value.to_dict(),
            "identifiability": self.identifiability.value,
            "standard_error": (
                None if self.standard_error is None else self.standard_error.to_dict()
            ),
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FittedParameter":
        require_schema(payload, FITTED_PARAMETER_SCHEMA)
        error = payload.get("standard_error")
        return cls(
            payload["parameter_id"],
            Quantity.from_dict(payload["value"]),
            Identifiability(payload.get("identifiability", "unknown")),
            None if error is None else Quantity.from_dict(error),
            payload.get("note", ""),
        )


@dataclass(frozen=True)
class CalibrationObjective:
    """What the fit minimized, named and versioned so it can be compared."""

    objective_id: str
    version: str
    description: str = ""

    def __post_init__(self) -> None:
        for label in ("objective_id", "version"):
            object.__setattr__(self, label, text(getattr(self, label), label=label))
        object.__setattr__(self, "description", str(self.description).strip())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CALIBRATION_OBJECTIVE_SCHEMA,
            "objective_id": self.objective_id,
            "version": self.version,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CalibrationObjective":
        require_schema(payload, CALIBRATION_OBJECTIVE_SCHEMA)
        return cls(
            payload["objective_id"], payload["version"], payload.get("description", "")
        )


@dataclass(frozen=True)
class CalibratedParameterSet:
    """An inert artifact: what was fitted, to what, and how it went.

    Holding one of these grants nothing. Production authority changes when
    something promotes it explicitly, and the promotion is a separate decision
    with its own record -- which is why this class has no ``apply`` and no
    registry reference.
    """

    parameter_set_id: str
    version: str
    specs: tuple[CalibrationParameterSpec, ...]
    values: tuple[FittedParameter, ...]
    objective: CalibrationObjective
    dataset_id: str
    dataset_digest: str
    calibration_split: DatasetSplit = DatasetSplit.CALIBRATION
    objective_value: float | None = None
    diagnostics: Mapping[str, Any] | None = None
    lineage: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label in ("parameter_set_id", "version", "dataset_id"):
            object.__setattr__(self, label, text(getattr(self, label), label=label))
        object.__setattr__(
            self, "dataset_digest", sha256_hex(self.dataset_digest, label="dataset_digest")
        )
        if not isinstance(self.objective, CalibrationObjective):
            raise CalibrationError("a calibrated parameter set requires an objective")

        split = DatasetSplit(self.calibration_split)
        if not split.may_influence_fitting:
            raise CalibrationError(
                f"a parameter set may not be fitted on the {split.value!r} split; "
                f"only calibration evidence is permitted to influence a fit"
            )
        object.__setattr__(self, "calibration_split", split)

        specs = tuple(sorted(self.specs))
        values = tuple(sorted(self.values))
        if not specs or any(
            not isinstance(item, CalibrationParameterSpec) for item in specs
        ):
            raise CalibrationError("a parameter set requires CalibrationParameterSpec records")
        if any(not isinstance(item, FittedParameter) for item in values):
            raise CalibrationError("a parameter set requires FittedParameter records")
        declared = {item.parameter_id: item for item in specs}
        if len(declared) != len(specs):
            raise CalibrationError("parameter set repeats a parameter_id")
        fitted = {item.parameter_id for item in values}
        if fitted != set(declared):
            raise CalibrationError(
                f"fitted parameters do not cover the declared set exactly; "
                f"missing={sorted(set(declared) - fitted)}, "
                f"undeclared={sorted(fitted - set(declared))}"
            )

        impossible: list[str] = []
        for item in values:
            spec = declared[item.parameter_id]
            require_same_dimension(
                item.value,
                Quantity(1.0, spec.unit),
                context=f"fitted {item.parameter_id}",
            )
            if not spec.admits(item.value):
                impossible.append(
                    f"{item.parameter_id}={item.value} outside declared bounds "
                    f"[{spec.lower_bound}, {spec.upper_bound}]"
                )
        if impossible:
            raise CalibrationError(
                "calibration produced physically impossible parameters and the "
                "record is refused rather than carried forward: " + "; ".join(impossible)
            )

        object.__setattr__(self, "specs", specs)
        object.__setattr__(self, "values", values)
        if self.objective_value is not None:
            value = float(self.objective_value)
            if not math.isfinite(value):
                raise CalibrationError("objective_value must be finite")
            object.__setattr__(self, "objective_value", value)
        object.__setattr__(
            self, "diagnostics", None if self.diagnostics is None else dict(self.diagnostics)
        )
        object.__setattr__(
            self,
            "lineage",
            tuple(str(item).strip() for item in self.lineage if str(item).strip()),
        )

    @property
    def unidentified_parameters(self) -> tuple[str, ...]:
        """Parameters the data did not constrain, or that nobody checked."""
        return tuple(
            item.parameter_id
            for item in self.values
            if item.identifiability
            in (Identifiability.UNIDENTIFIED, Identifiability.WEAK, Identifiability.UNKNOWN)
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PARAMETER_SET_SCHEMA,
            "parameter_set_id": self.parameter_set_id,
            "version": self.version,
            "specs": [item.to_dict() for item in self.specs],
            "values": [item.to_dict() for item in self.values],
            "objective": self.objective.to_dict(),
            "dataset_id": self.dataset_id,
            "dataset_digest": self.dataset_digest,
            "calibration_split": self.calibration_split.value,
            "objective_value": self.objective_value,
            "diagnostics": None if self.diagnostics is None else dict(self.diagnostics),
            "lineage": list(self.lineage),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CalibratedParameterSet":
        require_schema(payload, PARAMETER_SET_SCHEMA)
        return cls(
            payload["parameter_set_id"],
            payload["version"],
            tuple(CalibrationParameterSpec.from_dict(i) for i in payload["specs"]),
            tuple(FittedParameter.from_dict(i) for i in payload["values"]),
            CalibrationObjective.from_dict(payload["objective"]),
            payload["dataset_id"],
            payload["dataset_digest"],
            DatasetSplit(payload.get("calibration_split", "calibration")),
            payload.get("objective_value"),
            payload.get("diagnostics"),
            tuple(payload.get("lineage", ())),
        )


__all__ = [
    "CALIBRATION_OBJECTIVE_SCHEMA",
    "FITTED_PARAMETER_SCHEMA",
    "PARAMETER_SET_SCHEMA",
    "PARAMETER_SPEC_SCHEMA",
    "CalibratedParameterSet",
    "CalibrationError",
    "CalibrationObjective",
    "CalibrationParameterSpec",
    "FittedParameter",
    "Identifiability",
    "PriorSource",
]
