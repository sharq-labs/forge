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
from ..scientific.serialization import require_schema, schema_string
from ..scientific.units.quantity import Quantity, dimensionality, normalize_unit

SCENARIO_VALUE_SCHEMA = schema_string("scenario_named_quantity")
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity_id", _identifier(self.quantity_id, "quantity_id"))
        if not isinstance(self.value, Quantity):
            raise InvalidScientificProblem("scenario values must be Quantity records")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCENARIO_VALUE_SCHEMA, "quantity_id": self.quantity_id, "value": self.value.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NamedQuantity":
        require_schema(payload, SCENARIO_VALUE_SCHEMA)
        _strict_keys(payload, {"schema", "quantity_id", "value"}, "scenario value")
        return cls(payload["quantity_id"], Quantity.from_dict(payload["value"]))


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
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "OperatingCondition":
        require_schema(payload, OPERATING_CONDITION_SCHEMA)
        _strict_keys(
            payload,
            {"schema", "quantity_id", "value"},
            "operating condition",
        )
        return cls(payload["quantity_id"], Quantity.from_dict(payload["value"]))


@dataclass(frozen=True, order=True)
class ScenarioEvent:
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
    condition_id: str
    constraint: ConstraintDefinition

    def __post_init__(self) -> None:
        object.__setattr__(self, "condition_id", _identifier(self.condition_id, "termination condition_id"))
        if not isinstance(self.constraint, ConstraintDefinition):
            raise InvalidScientificProblem("termination condition requires ConstraintDefinition")

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

    def inputs_at(self, instant: Quantity) -> Mapping[str, Quantity]:
        seconds = _time(instant, "scenario query instant").magnitude_in("second")
        start = self.start.magnitude_in("second")
        end = self.end.magnitude_in("second")
        if seconds < start or seconds > end:
            raise InvalidScientificProblem("scenario query lies outside the horizon")
        segment = next(
            item for item in self.segments
            if item.start.magnitude_in("second") <= seconds <= item.end.magnitude_in("second")
        )
        return {item.input_id: item.value_at(instant) for item in segment.inputs}

    @property
    def requires_stateful_execution(self) -> bool:
        """Whether executing this scenario requires runtime semantics beyond time.

        This is intentionally conservative.  A bound-but-ignored field would
        make authorization claim that a computation consumed science it did
        not consume.
        """
        return bool(
            self.state_variables
            or self.initial_state is not None
            or self.events
            or self.termination_conditions
            or self.quantities_of_interest
            or any(
                segment.inputs or segment.operating_conditions
                for segment in self.segments
            )
        )

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
