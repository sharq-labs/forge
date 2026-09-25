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
from .timeline import (
    CycleCount, CycleHistory, CycleRecord, HistoryEntry, HistoryKind,
    HistoryRepresentation, HistoryValue, QuantityHistory, ReplayComparison,
    StateIdentity, TimeBasis, TimeBasisKind, Timeline, TimelineCheckpoint,
    TimelineEvent, TimelineEventKind, TimePoint, TimeWindow, ValueStatus,
    WindowClosure, canonical_digest, compare_replay, order_events,
)

__all__ = [
    "SEGMENT_OWNERSHIP", "ComposedInputSchedule", "ComposedOperatingCondition", "InterpolationKind",
    "NamedQuantity", "OperatingCondition",
    "QuantityOfInterest", "ScenarioEvent", "ScenarioSegment",
    "ScenarioSpecification", "SegmentContribution", "StateSnapshot",
    "StateVariable", "TerminationCondition", "TimeSample", "TimeSeriesInput",
    "compose_input_schedules", "compose_operating_conditions",
    # Time Engine
    "CycleCount", "CycleHistory", "CycleRecord", "HistoryEntry", "HistoryKind",
    "HistoryRepresentation", "HistoryValue", "QuantityHistory", "ReplayComparison",
    "StateIdentity", "TimeBasis", "TimeBasisKind", "Timeline", "TimelineCheckpoint",
    "TimelineEvent", "TimelineEventKind", "TimePoint", "TimeWindow", "ValueStatus",
    "WindowClosure", "canonical_digest", "compare_replay", "order_events",
]
