"""Generic scenario and transient-study contracts."""

from .contracts import (
    SEGMENT_OWNERSHIP,
    ComposedInputSchedule,
    ComposedOperatingCondition,
    InterpolationKind,
    NamedQuantity,
    OperatingCondition,
    QuantityOfInterest,
    ScenarioEvent,
    ScenarioSegment,
    ScenarioSpecification,
    SegmentContribution,
    StateSnapshot,
    StateVariable,
    TerminationCondition,
    TimeSample,
    TimeSeriesInput,
    compose_input_schedules,
    compose_operating_conditions,
)

__all__ = [
    "SEGMENT_OWNERSHIP", "ComposedInputSchedule", "ComposedOperatingCondition", "InterpolationKind",
    "NamedQuantity", "OperatingCondition",
    "QuantityOfInterest", "ScenarioEvent", "ScenarioSegment",
    "ScenarioSpecification", "SegmentContribution", "StateSnapshot",
    "StateVariable", "TerminationCondition", "TimeSample", "TimeSeriesInput",
    "compose_input_schedules", "compose_operating_conditions",
]
