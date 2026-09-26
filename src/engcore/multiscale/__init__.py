"""Multi-timescale runtime (BIG 10): an orchestration layer, not a new authority.

Macro windows on BIG 2 time; representative fast windows executed by a
:class:`FastSystem` (a BIG 9 coupled system); explicit aggregation with
stated information loss; BIG 4 degradation of SLOW state; BIG 5 material
re-resolution by the next fast execution; checkpoint / resume.

Nothing here is evidence or validation.  Representative repetition is an
approximation contract; replay and resume agreement are reproducibility.
"""

from .aggregation import (
    AggregationRecord, AggregationSpec, CompressedHistory, DomainAggregator, OutputSample, OutputSeries,
    aggregate, compress_history,
)
from .approximation import ApproximationEntry, ApproximationLedger, ComponentStatus, ErrorComponent, ReferenceDiscrepancy
from .checkpoint import MacroCheckpoint
from .fast import (
    FastExecutionRequest, FastExecutionResult, FastSystem, FastSystemIdentity, MaterialBinding, check_material_reresolution,
)
from .runtime import (
    FastStateAtMacroStart, LifecycleBinding, MacroStepRecord, MultiTimescaleRefusal, MultiTimescaleRunRecord,
    MultiTimescaleRuntime, RepresentativeExecution, ResumeComparison, ResumeRefused, compare_resume,
)
from .scales import ScaleHierarchy, ScaleLevel, ScaleRole, StateOwnership
from .windows import (
    AdaptationDecision, AdaptationRule, AdaptationTrigger, ApproximationStatus, EventHandling, MacroStepPolicy,
    RefinementDecision, RepresentativePolicy, RepresentativeWindow, SelectionMethod, StateChangeLimit, ThresholdWatch,
)

__all__ = [
    "AggregationRecord", "AggregationSpec", "CompressedHistory", "DomainAggregator", "OutputSample", "OutputSeries",
    "aggregate", "compress_history",
    "ApproximationEntry", "ApproximationLedger", "ComponentStatus", "ErrorComponent", "ReferenceDiscrepancy",
    "MacroCheckpoint",
    "FastExecutionRequest", "FastExecutionResult", "FastSystem", "FastSystemIdentity", "MaterialBinding",
    "check_material_reresolution",
    "FastStateAtMacroStart", "LifecycleBinding", "MacroStepRecord", "MultiTimescaleRefusal", "MultiTimescaleRunRecord",
    "MultiTimescaleRuntime", "RepresentativeExecution", "ResumeComparison", "ResumeRefused", "compare_resume",
    "ScaleHierarchy", "ScaleLevel", "ScaleRole", "StateOwnership",
    "AdaptationDecision", "AdaptationRule", "AdaptationTrigger", "ApproximationStatus", "EventHandling", "MacroStepPolicy",
    "RefinementDecision", "RepresentativePolicy", "RepresentativeWindow", "SelectionMethod", "StateChangeLimit", "ThresholdWatch",
]
