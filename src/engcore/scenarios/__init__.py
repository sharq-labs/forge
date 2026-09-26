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
from .environment import (
    STANDARD_ENVIRONMENT_KINDS, ChannelRepresentation, EnvironmentChannel,
    EnvironmentInterpolation, EnvironmentKindRegistry, EnvironmentQuantityKind,
    EnvironmentSample, EnvironmentSource, EnvironmentSourceKind, EnvironmentState,
    EnvironmentTimeline, EnvironmentValue, InterpolationContract, ReferenceContext,
    ValueDerivation,
)
from .lifecycle import (
    AggregateForm, AggregateRequirement, ApplicabilityBound, DegradationModel, DegradationModelIdentity,
    DegradationStepRecord, GatheredInput, HistoryFeature, InputBinding, InputRequirement, InputSource,
    LifecycleChain, StepStatus, carry_forward, evaluate_degradation, evaluate_degradation_step, run_digest,
    run_lifecycle,
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
    # Environment Engine
    "STANDARD_ENVIRONMENT_KINDS", "ChannelRepresentation", "EnvironmentChannel",
    "EnvironmentInterpolation", "EnvironmentKindRegistry", "EnvironmentQuantityKind",
    "EnvironmentSample", "EnvironmentSource", "EnvironmentSourceKind", "EnvironmentState",
    "EnvironmentTimeline", "EnvironmentValue", "InterpolationContract", "ReferenceContext",
    "ValueDerivation",
    # Lifecycle Engine
    "AggregateForm", "AggregateRequirement", "HistoryFeature", "evaluate_degradation_step",
    "ApplicabilityBound", "DegradationModel", "DegradationModelIdentity", "DegradationStepRecord",
    "GatheredInput", "InputBinding", "InputRequirement", "InputSource", "LifecycleChain", "StepStatus",
    "carry_forward", "evaluate_degradation", "run_digest", "run_lifecycle",
]
