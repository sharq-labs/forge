"""Domain-independent, unit-bearing transient scenario contracts.

These records describe *what is imposed and observed over time*.  They do not
select models, solvers, or scientific applicability and therefore carry no
authority to turn an executable trajectory into validation evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping

from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.constraints import ConstraintDefinition
from ..scientific.serialization import require_schema, require_schema_any, schema_string
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity, dimensionality, normalize_unit

SCENARIO_VALUE_SCHEMA_V1 = schema_string("scenario_named_quantity")
SCENARIO_VALUE_SCHEMA = schema_string("scenario_named_quantity", 2)
STATE_VARIABLE_SCHEMA = schema_string("scenario_state_variable")
STATE_SNAPSHOT_SCHEMA = schema_string("scenario_state_snapshot")
TIME_SAMPLE_SCHEMA = schema_string("scenario_time_sample")
TIME_SERIES_INPUT_SCHEMA = schema_string("scenario_time_series_input")
OPERATING_CONDITION_SCHEMA = schema_string("scenario_operating_condition")
SCENARIO_EVENT_SCHEMA = schema_string("scenario_event")
TERMINATION_CONDITION_SCHEMA = schema_string("scenario_termination_condition")
SCENARIO_QOI_SCHEMA = schema_string("scenario_quantity_of_interest")
SCENARIO_SEGMENT_SCHEMA = schema_string("scenario_segment")
SCENARIO_SCHEMA = schema_string("scenario_specification")

#: Segment ownership at a shared boundary, stated once and applied everywhere.
#:
#: Every segment owns ``[start, end)``.  The final segment of a scenario also
#: owns its terminal endpoint, because the horizon has to end somewhere.  So
#: for segments ``A=[0,10)``, ``B=[10,20)``, ``C=[20,30]`` the instant ``t=10``
#: belongs to ``B`` and to nothing else -- not to ``A`` because ``A`` was
#: iterated first.
#:
#: This rule is the same one in segment selection, schedule composition, event
#: boundaries, runtime windows, receipts and replay.  Where it is applied, the
#: code says so by calling :meth:`ScenarioSpecification.segment_at`.
SEGMENT_OWNERSHIP = "[start, end), final segment inclusive of its endpoint"

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")
_TIME_DIMENSION = dimensionality("second")


def _identifier(value: object, label: str) -> str:
    text = str(value).strip()
    if not text or not _ID.fullmatch(text):
        raise InvalidScientificProblem(
            f"{label} must be a non-empty typed identifier"
        )
    return text


def _time(value: Quantity, label: str) -> Quantity:
    if not isinstance(value, Quantity) or dimensionality(value.units) != _TIME_DIMENSION:
        raise InvalidScientificProblem(f"{label} must be a time Quantity")
    return value.to("second")


def _strict_keys(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise InvalidScientificProblem(
            f"{label} shape mismatch; missing={sorted(expected - set(payload))}, "
            f"extra={sorted(set(payload) - expected)}"
        )


@dataclass(frozen=True, order=True)
class NamedQuantity:
    quantity_id: str
    value: Quantity
    uncertainty: Uncertainty | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity_id", _identifier(self.quantity_id, "quantity_id"))
        if not isinstance(self.value, Quantity):
            raise InvalidScientificProblem("scenario values must be Quantity records")
        uncertainty = self.uncertainty
        if uncertainty is None:
            uncertainty = Uncertainty.unknown(
                f"no uncertainty was supplied for scenario quantity {self.quantity_id}"
            )
        if not isinstance(uncertainty, Uncertainty):
            raise InvalidScientificProblem("scenario uncertainty must be Uncertainty")
        for label in ("standard_uncertainty", "lower", "upper"):
            bound = getattr(uncertainty, label)
            if bound is not None:
                bound.require_compatible(
                    self.value.units,
                    context=f"scenario quantity {self.quantity_id!r} {label}",
                )
        object.__setattr__(self, "uncertainty", uncertainty)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCENARIO_VALUE_SCHEMA, "quantity_id": self.quantity_id, "value": self.value.to_dict(), "uncertainty": self.uncertainty.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NamedQuantity":
        schema = require_schema_any(payload, (SCENARIO_VALUE_SCHEMA_V1, SCENARIO_VALUE_SCHEMA))
        expected = {"schema", "quantity_id", "value"} if schema == SCENARIO_VALUE_SCHEMA_V1 else {"schema", "quantity_id", "value", "uncertainty"}
        _strict_keys(payload, expected, "scenario value")
        return cls(payload["quantity_id"], Quantity.from_dict(payload["value"]), None if schema == SCENARIO_VALUE_SCHEMA_V1 else Uncertainty.from_dict(payload["uncertainty"]))


@dataclass(frozen=True, order=True)
class StateVariable:
    variable_id: str
    unit: str
    owner_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "variable_id", _identifier(self.variable_id, "state variable_id"))
        object.__setattr__(self, "owner_id", _identifier(self.owner_id, "state owner_id"))
        object.__setattr__(self, "unit", normalize_unit(self.unit))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": STATE_VARIABLE_SCHEMA, "variable_id": self.variable_id, "unit": self.unit, "owner_id": self.owner_id}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StateVariable":
        require_schema(payload, STATE_VARIABLE_SCHEMA)
        _strict_keys(payload, {"schema", "variable_id", "unit", "owner_id"}, "state variable")
        return cls(payload["variable_id"], payload["unit"], payload["owner_id"])


@dataclass(frozen=True)
class StateSnapshot:
    instant: Quantity
    values: tuple[NamedQuantity, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "instant", _time(self.instant, "state snapshot instant"))
        values = tuple(self.values)
        if any(not isinstance(item, NamedQuantity) for item in values):
            raise InvalidScientificProblem("state snapshot values must be NamedQuantity records")
        ids = [item.quantity_id for item in values]
        if len(ids) != len(set(ids)):
            raise InvalidScientificProblem("state snapshot contains duplicate variable ids")
        object.__setattr__(self, "values", tuple(sorted(values)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": STATE_SNAPSHOT_SCHEMA, "instant": self.instant.to_dict(), "values": [item.to_dict() for item in self.values]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StateSnapshot":
        require_schema(payload, STATE_SNAPSHOT_SCHEMA)
        _strict_keys(payload, {"schema", "instant", "values"}, "state snapshot")
        return cls(Quantity.from_dict(payload["instant"]), tuple(NamedQuantity.from_dict(item) for item in payload["values"]))


@dataclass(frozen=True, order=True)
class TimeSample:
    instant: Quantity
    value: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(self, "instant", _time(self.instant, "time sample instant"))
        if not isinstance(self.value, Quantity):
            raise InvalidScientificProblem("time sample value must be a Quantity")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TIME_SAMPLE_SCHEMA, "instant": self.instant.to_dict(), "value": self.value.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TimeSample":
        require_schema(payload, TIME_SAMPLE_SCHEMA)
        _strict_keys(payload, {"schema", "instant", "value"}, "time sample")
        return cls(Quantity.from_dict(payload["instant"]), Quantity.from_dict(payload["value"]))


class InterpolationKind(str, Enum):
    STEP = "step"
    LINEAR = "linear"


@dataclass(frozen=True)
class TimeSeriesInput:
    input_id: str
    samples: tuple[TimeSample, ...]
    interpolation: InterpolationKind

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_id", _identifier(self.input_id, "time-series input_id"))
        object.__setattr__(self, "interpolation", InterpolationKind(self.interpolation))
        samples = tuple(self.samples)
        if not samples or any(not isinstance(item, TimeSample) for item in samples):
            raise InvalidScientificProblem("time-series input requires TimeSample records")
        unit = samples[0].value.units
        previous = None
        for sample in samples:
            sample.value.require_compatible(unit, context=f"time-series input {self.input_id!r}")
            instant = sample.instant.magnitude_in("second")
            if previous is not None and instant <= previous:
                raise InvalidScientificProblem("time-series sample instants must increase strictly")
            previous = instant
        object.__setattr__(self, "samples", samples)

    @property
    def unit(self) -> str:
        return self.samples[0].value.units

    def value_at(self, instant: Quantity) -> Quantity:
        seconds = _time(instant, "time-series query instant").magnitude_in("second")
        points = [item.instant.magnitude_in("second") for item in self.samples]
        if seconds < points[0] or seconds > points[-1]:
            raise InvalidScientificProblem(
                f"time-series input {self.input_id!r} has no value at {seconds} second"
            )
        upper = next((i for i, point in enumerate(points) if point >= seconds), len(points) - 1)
        if points[upper] == seconds or upper == 0 or self.interpolation is InterpolationKind.STEP:
            index = upper if points[upper] == seconds else upper - 1
            return self.samples[index].value
        lower = upper - 1
        fraction = (seconds - points[lower]) / (points[upper] - points[lower])
        low = self.samples[lower].value.magnitude_in(self.unit)
        high = self.samples[upper].value.magnitude_in(self.unit)
        return Quantity(low + fraction * (high - low), self.unit)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TIME_SERIES_INPUT_SCHEMA, "input_id": self.input_id, "samples": [item.to_dict() for item in self.samples], "interpolation": self.interpolation.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TimeSeriesInput":
        require_schema(payload, TIME_SERIES_INPUT_SCHEMA)
        _strict_keys(payload, {"schema", "input_id", "samples", "interpolation"}, "time-series input")
        return cls(payload["input_id"], tuple(TimeSample.from_dict(item) for item in payload["samples"]), InterpolationKind(payload["interpolation"]))


@dataclass(frozen=True, order=True)
class OperatingCondition(NamedQuantity):
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": OPERATING_CONDITION_SCHEMA,
            "quantity_id": self.quantity_id,
            "value": self.value.to_dict(),
            "uncertainty": self.uncertainty.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OperatingCondition":
        require_schema(payload, OPERATING_CONDITION_SCHEMA)
        _strict_keys(
            payload,
            {"schema", "quantity_id", "value", "uncertainty"},
            "operating condition",
        )
        return cls(payload["quantity_id"], Quantity.from_dict(payload["value"]), Uncertainty.from_dict(payload["uncertainty"]))


@dataclass(frozen=True, order=True)
class ScenarioEvent:
    """A deterministic synchronization instant in the scenario horizon.

    It does not claim a physical trigger or prescribe an action. Execution
    must place an exact window boundary at the instant and receipt the
    schedule.
    """

    event_id: str
    instant: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _identifier(self.event_id, "event_id"))
        object.__setattr__(self, "instant", _time(self.instant, "event instant"))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCENARIO_EVENT_SCHEMA, "event_id": self.event_id, "instant": self.instant.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScenarioEvent":
        require_schema(payload, SCENARIO_EVENT_SCHEMA)
        _strict_keys(payload, {"schema", "event_id", "instant"}, "scenario event")
        return cls(payload["event_id"], Quantity.from_dict(payload["instant"]))


@dataclass(frozen=True, order=True)
class TerminationCondition:
    """A declared reason for a scenario to stop before its horizon.

    The constraint's ``metric`` names a :class:`QuantityOfInterest`'s
    ``quantity_id`` -- the scenario's own declared observables and the only
    values execution can read without inventing one.  That binding is enforced
    by :class:`ScenarioSpecification`, so it is a stated contract rather than a
    convention the runtime happens to follow.

    Execution stops at the **first window boundary at which the constraint is
    satisfied**.  A condition already satisfied at the scenario start is
    refused rather than producing an empty trajectory.
    """

    condition_id: str
    constraint: ConstraintDefinition

    def __post_init__(self) -> None:
        object.__setattr__(self, "condition_id", _identifier(self.condition_id, "termination condition_id"))
        if not isinstance(self.constraint, ConstraintDefinition):
            raise InvalidScientificProblem("termination condition requires ConstraintDefinition")
        if self.constraint.name != self.condition_id:
            raise InvalidScientificProblem(
                f"termination condition {self.condition_id!r} must carry a constraint "
                f"of the same name, not {self.constraint.name!r}; the receipt that "
                f"records a stop names one identity"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TERMINATION_CONDITION_SCHEMA, "condition_id": self.condition_id, "constraint": self.constraint.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TerminationCondition":
        require_schema(payload, TERMINATION_CONDITION_SCHEMA)
        _strict_keys(payload, {"schema", "condition_id", "constraint"}, "termination condition")
        return cls(payload["condition_id"], ConstraintDefinition.from_dict(payload["constraint"]))


@dataclass(frozen=True, order=True)
class QuantityOfInterest:
    qoi_id: str
    quantity_id: str
    unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "qoi_id", _identifier(self.qoi_id, "qoi_id"))
        object.__setattr__(self, "quantity_id", _identifier(self.quantity_id, "qoi quantity_id"))
        object.__setattr__(self, "unit", normalize_unit(self.unit))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCENARIO_QOI_SCHEMA, "qoi_id": self.qoi_id, "quantity_id": self.quantity_id, "unit": self.unit}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "QuantityOfInterest":
        require_schema(payload, SCENARIO_QOI_SCHEMA)
        _strict_keys(payload, {"schema", "qoi_id", "quantity_id", "unit"}, "scenario qoi")
        return cls(payload["qoi_id"], payload["quantity_id"], payload["unit"])


@dataclass(frozen=True)
class ScenarioSegment:
    segment_id: str
    start: Quantity
    end: Quantity
    inputs: tuple[TimeSeriesInput, ...] = ()
    operating_conditions: tuple[OperatingCondition, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "segment_id", _identifier(self.segment_id, "segment_id"))
        start = _time(self.start, "segment start")
        end = _time(self.end, "segment end")
        if end.magnitude <= start.magnitude:
            raise InvalidScientificProblem("scenario segment end must be after start")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        inputs = tuple(self.inputs)
        ids = [item.input_id for item in inputs]
        if any(not isinstance(item, TimeSeriesInput) for item in inputs) or len(ids) != len(set(ids)):
            raise InvalidScientificProblem("segment inputs must have unique TimeSeriesInput ids")
        for item in inputs:
            if item.samples[0].instant != start or item.samples[-1].instant != end:
                raise InvalidScientificProblem(
                    f"segment input {item.input_id!r} must cover both segment boundaries"
                )
        conditions = tuple(self.operating_conditions)
        condition_ids = [item.quantity_id for item in conditions]
        if any(not isinstance(item, OperatingCondition) for item in conditions) or len(condition_ids) != len(set(condition_ids)):
            raise InvalidScientificProblem("segment operating conditions must have unique ids")
        object.__setattr__(self, "inputs", tuple(sorted(inputs, key=lambda item: item.input_id)))
        object.__setattr__(self, "operating_conditions", tuple(sorted(conditions)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCENARIO_SEGMENT_SCHEMA, "segment_id": self.segment_id, "start": self.start.to_dict(), "end": self.end.to_dict(), "inputs": [item.to_dict() for item in self.inputs], "operating_conditions": [item.to_dict() for item in self.operating_conditions]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScenarioSegment":
        require_schema(payload, SCENARIO_SEGMENT_SCHEMA)
        _strict_keys(payload, {"schema", "segment_id", "start", "end", "inputs", "operating_conditions"}, "scenario segment")
        return cls(payload["segment_id"], Quantity.from_dict(payload["start"]), Quantity.from_dict(payload["end"]), tuple(TimeSeriesInput.from_dict(item) for item in payload["inputs"]), tuple(OperatingCondition.from_dict(item) for item in payload["operating_conditions"]))


@dataclass(frozen=True, order=True)
class SegmentContribution:
    """Which scenario segment authored one stretch of a composed schedule."""

    segment_id: str
    start: Quantity
    end: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(self, "segment_id", _identifier(self.segment_id, "segment_id"))
        object.__setattr__(self, "start", _time(self.start, "contribution start"))
        object.__setattr__(self, "end", _time(self.end, "contribution end"))

    def owns(self, seconds: float, *, final: bool) -> bool:
        start = self.start.magnitude_in("second")
        end = self.end.magnitude_in("second")
        if seconds < start:
            return False
        return seconds <= end if final else seconds < end


@dataclass(frozen=True)
class ComposedInputSchedule:
    """One control quantity reused across consecutive segments, as one schedule.

    A mission reuses the same input id in every phase it applies to.  The
    composed schedule is the deterministic merge of those per-segment series
    into the single runtime schedule execution consumes, with each sample's
    authoring segment retained so a receipt can name it.

    Nothing is invented by the merge: at a shared boundary the later segment
    owns the instant (:data:`SEGMENT_OWNERSHIP`), which is exactly how a STEP
    change between phases is expressed, and no value is interpolated across a
    boundary that neither segment declared.
    """

    input_id: str
    series: TimeSeriesInput
    contributions: tuple[SegmentContribution, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_id", _identifier(self.input_id, "input_id"))
        if not isinstance(self.series, TimeSeriesInput) or self.series.input_id != self.input_id:
            raise InvalidScientificProblem(
                "composed schedule requires the TimeSeriesInput it composes"
            )
        contributions = tuple(self.contributions)
        if not contributions or any(
            not isinstance(item, SegmentContribution) for item in contributions
        ):
            raise InvalidScientificProblem(
                "composed schedule requires its segment contributions"
            )
        object.__setattr__(self, "contributions", contributions)

    @property
    def interpolation(self) -> InterpolationKind:
        return self.series.interpolation

    @property
    def unit(self) -> str:
        return self.series.unit

    def value_at(self, instant: Quantity) -> Quantity:
        return self.series.value_at(instant)

    def segment_at(self, instant: Quantity) -> str:
        """The segment that owns this instant, under :data:`SEGMENT_OWNERSHIP`."""
        seconds = _time(instant, "composed schedule query instant").magnitude_in("second")
        last = len(self.contributions) - 1
        for index, item in enumerate(self.contributions):
            if item.owns(seconds, final=index == last):
                return item.segment_id
        raise InvalidScientificProblem(
            f"composed input {self.input_id!r} has no segment owning "
            f"{seconds} second"
        )


@dataclass(frozen=True)
class ComposedOperatingCondition:
    """One declared operating condition across the segments that declare it.

    Same composition rules as a control input: one identity, compatible units,
    no hole in the middle, and the later segment owns a shared boundary.  An
    operating condition an authorized consumer declares must have a value at
    every window, so partial coverage is refused rather than filled in.
    """

    condition_id: str
    values: tuple[tuple[SegmentContribution, OperatingCondition], ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "condition_id", _identifier(self.condition_id, "condition_id")
        )
        values = tuple(self.values)
        if not values:
            raise InvalidScientificProblem(
                "composed operating condition requires at least one segment value"
            )
        object.__setattr__(self, "values", values)

    @property
    def unit(self) -> str:
        return self.values[0][1].value.units

    def _owner(self, instant: Quantity) -> tuple[SegmentContribution, OperatingCondition]:
        seconds = _time(instant, "operating condition query instant").magnitude_in("second")
        last = len(self.values) - 1
        for index, item in enumerate(self.values):
            if item[0].owns(seconds, final=index == last):
                return item
        raise InvalidScientificProblem(
            f"operating condition {self.condition_id!r} has no segment owning "
            f"{seconds} second"
        )

    def value_at(self, instant: Quantity) -> OperatingCondition:
        return self._owner(instant)[1]

    def segment_at(self, instant: Quantity) -> str:
        return self._owner(instant)[0].segment_id


def compose_operating_conditions(
    segments: tuple["ScenarioSegment", ...],
    *,
    start: Quantity,
    end: Quantity,
) -> tuple[ComposedOperatingCondition, ...]:
    ordered = tuple(sorted(segments, key=lambda item: item.start.magnitude_in("second")))
    grouped: dict[str, list[tuple[ScenarioSegment, OperatingCondition]]] = {}
    for segment in ordered:
        for condition in segment.operating_conditions:
            grouped.setdefault(condition.quantity_id, []).append((segment, condition))

    horizon_start = start.magnitude_in("second")
    horizon_end = end.magnitude_in("second")
    composed: list[ComposedOperatingCondition] = []
    for condition_id in sorted(grouped):
        parts = grouped[condition_id]
        unit = parts[0][1].value.units
        for segment, condition in parts[1:]:
            condition.value.require_compatible(
                unit,
                context=(
                    f"operating condition {condition_id!r} in segment "
                    f"{segment.segment_id!r}"
                ),
            )
        indices = [ordered.index(segment) for segment, _ in parts]
        if indices != list(range(indices[0], indices[0] + len(indices))):
            raise InvalidScientificProblem(
                f"operating condition {condition_id!r} skips a segment; a declared "
                f"consumer has no value there"
            )
        span_start = parts[0][0].start.magnitude_in("second")
        span_end = parts[-1][0].end.magnitude_in("second")
        if span_start != horizon_start or span_end != horizon_end:
            raise InvalidScientificProblem(
                f"operating condition {condition_id!r} covers "
                f"[{span_start}, {span_end}] second but the horizon is "
                f"[{horizon_start}, {horizon_end}] second"
            )
        composed.append(
            ComposedOperatingCondition(
                condition_id,
                tuple(
                    (
                        SegmentContribution(segment.segment_id, segment.start, segment.end),
                        condition,
                    )
                    for segment, condition in parts
                ),
            )
        )
    return tuple(composed)


def compose_input_schedules(
    segments: tuple["ScenarioSegment", ...],
    *,
    start: Quantity,
    end: Quantity,
) -> tuple[ComposedInputSchedule, ...]:
    """Merge per-segment time-series inputs into deterministic runtime schedules.

    Refused, rather than reconciled:

    * the same input id declared with incompatible units in two segments;
    * the same input id declared with different interpolation semantics;
    * an input that skips a segment in the middle of its own span, or does not
      cover the whole horizon -- a port that is externally imposed needs a
      value at every window, and filling the hole would be an invented one;
    * a LINEAR input whose value jumps at a shared segment boundary, where the
      limit from the left and the value at the instant disagree.

    Ambiguous overlap is not in that list because it cannot be built: scenario
    segments are validated contiguous and non-overlapping, so exactly one
    segment owns any instant.
    """
    ordered = tuple(sorted(segments, key=lambda item: item.start.magnitude_in("second")))
    grouped: dict[str, list[tuple[ScenarioSegment, TimeSeriesInput]]] = {}
    for segment in ordered:
        for series in segment.inputs:
            grouped.setdefault(series.input_id, []).append((segment, series))

    horizon_start = start.magnitude_in("second")
    horizon_end = end.magnitude_in("second")
    schedules: list[ComposedInputSchedule] = []
    for input_id in sorted(grouped):
        parts = grouped[input_id]
        first_series = parts[0][1]
        unit = first_series.unit
        interpolation = first_series.interpolation
        for segment, series in parts[1:]:
            if series.interpolation is not interpolation:
                raise InvalidScientificProblem(
                    f"scenario input {input_id!r} changes interpolation semantics in "
                    f"segment {segment.segment_id!r}: {interpolation.value} then "
                    f"{series.interpolation.value}"
                )
            series.samples[0].value.require_compatible(
                unit, context=f"scenario input {input_id!r} in segment {segment.segment_id!r}"
            )

        indices = [ordered.index(segment) for segment, _ in parts]
        if indices != list(range(indices[0], indices[0] + len(indices))):
            raise InvalidScientificProblem(
                f"scenario input {input_id!r} skips a segment; an externally imposed "
                f"port has no value there and one would have to be invented"
            )
        span_start = parts[0][0].start.magnitude_in("second")
        span_end = parts[-1][0].end.magnitude_in("second")
        if span_start != horizon_start or span_end != horizon_end:
            raise InvalidScientificProblem(
                f"scenario input {input_id!r} covers [{span_start}, {span_end}] second "
                f"but the horizon is [{horizon_start}, {horizon_end}] second; an "
                f"externally imposed port needs a declared value at every window"
            )

        samples: list[TimeSample] = []
        contributions: list[SegmentContribution] = []
        for position, (segment, series) in enumerate(parts):
            final = position == len(parts) - 1
            boundary = segment.end.magnitude_in("second")
            if not final and interpolation is InterpolationKind.LINEAR:
                following = parts[position + 1][1]
                left = series.samples[-1].value.magnitude_in(unit)
                right = following.samples[0].value.magnitude_in(unit)
                if left != right:
                    raise InvalidScientificProblem(
                        f"LINEAR scenario input {input_id!r} jumps from {left} to "
                        f"{right} {unit} at the {segment.segment_id!r} boundary; the "
                        f"limit from the left and the value at the instant disagree"
                    )
            for sample in series.samples:
                if not final and sample.instant.magnitude_in("second") == boundary:
                    # The next segment owns the shared instant.
                    continue
                samples.append(sample)
            contributions.append(
                SegmentContribution(segment.segment_id, segment.start, segment.end)
            )
        schedules.append(
            ComposedInputSchedule(
                input_id,
                TimeSeriesInput(input_id, tuple(samples), interpolation),
                tuple(contributions),
            )
        )
    return tuple(schedules)


@dataclass(frozen=True)
class ScenarioSpecification:
    scenario_id: str
    version: str
    start: Quantity
    end: Quantity
    state_variables: tuple[StateVariable, ...] = ()
    initial_state: StateSnapshot | None = None
    segments: tuple[ScenarioSegment, ...] = ()
    events: tuple[ScenarioEvent, ...] = ()
    termination_conditions: tuple[TerminationCondition, ...] = ()
    quantities_of_interest: tuple[QuantityOfInterest, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", _identifier(self.scenario_id, "scenario_id"))
        version = str(self.version).strip()
        if not version:
            raise InvalidScientificProblem("scenario version must be non-empty")
        object.__setattr__(self, "version", version)
        start = _time(self.start, "scenario start")
        end = _time(self.end, "scenario end")
        if end.magnitude <= start.magnitude:
            raise InvalidScientificProblem("scenario end must be after start")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        variables = tuple(sorted(self.state_variables))
        variable_map = {item.variable_id: item for item in variables}
        if len(variable_map) != len(variables):
            raise InvalidScientificProblem("scenario contains duplicate state variables")
        object.__setattr__(self, "state_variables", variables)
        if variables and self.initial_state is None:
            raise InvalidScientificProblem("declared state variables require an initial state")
        if self.initial_state is not None:
            if not isinstance(self.initial_state, StateSnapshot) or self.initial_state.instant != start:
                raise InvalidScientificProblem("initial state must be a StateSnapshot at scenario start")
            values = {item.quantity_id: item.value for item in self.initial_state.values}
            if set(values) != set(variable_map):
                raise InvalidScientificProblem("initial state must define every state variable exactly once")
            for key, value in values.items():
                value.require_compatible(variable_map[key].unit, context=f"initial state {key!r}")
        segments = tuple(self.segments)
        if not segments:
            segments = (ScenarioSegment("default", start, end),)
        ordered = tuple(sorted(segments, key=lambda item: item.start.magnitude_in("second")))
        cursor = start.magnitude_in("second")
        for segment in ordered:
            if segment.start.magnitude_in("second") != cursor:
                raise InvalidScientificProblem("scenario segments must cover the horizon contiguously")
            cursor = segment.end.magnitude_in("second")
        if cursor != end.magnitude_in("second"):
            raise InvalidScientificProblem("scenario segments must end at the scenario horizon")
        if len({item.segment_id for item in ordered}) != len(ordered):
            raise InvalidScientificProblem("scenario contains duplicate segment ids")
        object.__setattr__(self, "segments", ordered)
        for label, values, cls, identity in (
            ("events", self.events, ScenarioEvent, lambda item: item.event_id),
            ("termination conditions", self.termination_conditions, TerminationCondition, lambda item: item.condition_id),
            ("quantities of interest", self.quantities_of_interest, QuantityOfInterest, lambda item: item.qoi_id),
        ):
            items = tuple(values)
            if any(not isinstance(item, cls) for item in items) or len({identity(item) for item in items}) != len(items):
                raise InvalidScientificProblem(f"scenario {label} must contain unique typed records")
            object.__setattr__(self, label.replace(" ", "_"), tuple(sorted(items)))
        for event in self.events:
            if not start.magnitude <= event.instant.magnitude <= end.magnitude:
                raise InvalidScientificProblem("scenario event lies outside the horizon")
        qoi_ids = {item.quantity_id for item in self.quantities_of_interest}
        for condition in self.termination_conditions:
            if condition.constraint.metric not in qoi_ids:
                raise InvalidScientificProblem(
                    f"termination condition {condition.condition_id!r} watches "
                    f"{condition.constraint.metric!r}, which is not a declared "
                    f"quantity of interest; execution would have to invent the value "
                    f"it stops on"
                )
        # Composition is validated at construction so an unmergeable schedule is
        # refused where it was authored rather than at the runtime boundary.
        compose_input_schedules(self.segments, start=start, end=end)
        compose_operating_conditions(self.segments, start=start, end=end)

    def segment_at(self, instant: Quantity) -> ScenarioSegment:
        """The one segment that owns this instant, under :data:`SEGMENT_OWNERSHIP`.

        Ownership never depends on iteration order: at a shared boundary the
        later segment owns the instant, and only the final segment owns the
        scenario's terminal endpoint.
        """
        seconds = _time(instant, "scenario query instant").magnitude_in("second")
        if seconds < self.start.magnitude_in("second") or seconds > self.end.magnitude_in("second"):
            raise InvalidScientificProblem("scenario query lies outside the horizon")
        last = len(self.segments) - 1
        for index, item in enumerate(self.segments):
            lower = item.start.magnitude_in("second")
            upper = item.end.magnitude_in("second")
            if lower <= seconds and (seconds <= upper if index == last else seconds < upper):
                return item
        raise InvalidScientificProblem(
            f"no scenario segment owns {seconds} second"
        )

    def composed_input_schedules(self) -> tuple[ComposedInputSchedule, ...]:
        """The deterministic runtime schedules this scenario's segments compose to."""
        return compose_input_schedules(self.segments, start=self.start, end=self.end)

    def composed_operating_conditions(self) -> tuple[ComposedOperatingCondition, ...]:
        """The operating conditions this scenario's segments compose to."""
        return compose_operating_conditions(
            self.segments, start=self.start, end=self.end
        )

    def inputs_at(self, instant: Quantity) -> Mapping[str, Quantity]:
        self.segment_at(instant)
        return {
            item.input_id: item.value_at(instant)
            for item in self.composed_input_schedules()
        }

    def operating_conditions_at(self, instant: Quantity) -> tuple[OperatingCondition, ...]:
        """The operating conditions in force at this instant, by segment ownership."""
        return self.segment_at(instant).operating_conditions

    # `requires_stateful_execution` used to live here: a predicate asking
    # whether a scenario materially participates in execution, so that
    # authorization could decide whether to bind the scenario's identity to the
    # run. It is gone on purpose. Binding was made unconditional -- a GraphPlan
    # carrying a scenario executes in that scenario's world -- and leaving a
    # "does this one count?" predicate lying about would invite the conditional
    # binding back.

    @property
    def unsupported_runtime_features(self) -> tuple[str, ...]:
        """Declared scenario features no runtime in this Core can execute yet.

        State, scheduled events, operating conditions, quantities of interest
        and termination all became executable in the World Runtime round, so
        this list is now what genuinely remains: LINEAR interpolation, which
        the coupling runtime refuses because a value between window boundaries
        is not a value any participant was handed.
        """
        features: list[str] = []
        if any(
            item.interpolation is InterpolationKind.LINEAR
            for segment in self.segments for item in segment.inputs
        ):
            features.append("linear_interpolation")
        return tuple(features)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCENARIO_SCHEMA, "scenario_id": self.scenario_id, "version": self.version, "start": self.start.to_dict(), "end": self.end.to_dict(), "state_variables": [item.to_dict() for item in self.state_variables], "initial_state": None if self.initial_state is None else self.initial_state.to_dict(), "segments": [item.to_dict() for item in self.segments], "events": [item.to_dict() for item in self.events], "termination_conditions": [item.to_dict() for item in self.termination_conditions], "quantities_of_interest": [item.to_dict() for item in self.quantities_of_interest]}

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScenarioSpecification":
        require_schema(payload, SCENARIO_SCHEMA)
        expected = {"schema", "scenario_id", "version", "start", "end", "state_variables", "initial_state", "segments", "events", "termination_conditions", "quantities_of_interest"}
        _strict_keys(payload, expected, "scenario specification")
        initial = payload["initial_state"]
        return cls(payload["scenario_id"], payload["version"], Quantity.from_dict(payload["start"]), Quantity.from_dict(payload["end"]), tuple(StateVariable.from_dict(item) for item in payload["state_variables"]), None if initial is None else StateSnapshot.from_dict(initial), tuple(ScenarioSegment.from_dict(item) for item in payload["segments"]), tuple(ScenarioEvent.from_dict(item) for item in payload["events"]), tuple(TerminationCondition.from_dict(item) for item in payload["termination_conditions"]), tuple(QuantityOfInterest.from_dict(item) for item in payload["quantities_of_interest"]))
