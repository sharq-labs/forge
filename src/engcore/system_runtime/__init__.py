"""System runtime (BIG 12): one deterministic execution runtime over the existing authorities.

A canonical, content-bound :class:`SystemRunRequest` compiles to a deterministic
:class:`SystemExecutionPlan`; :func:`preflight` refuses what is knowable in advance;
:class:`SystemExecutor` runs the nodes through their pinned authorities (delegating coupling to
BIG 9, long horizons to BIG 10, providers to BIG 11), commits authoritative state atomically,
blocks dependents of failures, protects against stale output, and produces a
:class:`SystemRunResult` that can be traced, checkpointed, resumed and replayed.

It is an orchestration layer.  It computes nothing scientific itself, validates nothing, and
issues no verdict: successful execution is not scientific support (see :func:`trust_handoff`).
"""

from .assess import (
    BalanceSpec, ConservationAssessment, ConstraintAssessment, TermSource, assess_conservation, assess_constraints, trust_handoff,
)
from .authorities import CallbackAuthority, MultiphysicsAuthority, MultiscaleAuthority, ProviderAuthority, scalar_outputs
from .checkpoint import ResumeRefused, verify_checkpoint
from .executor import ExecutionCache, SystemExecutor, output_stamp
from .plan import PlanNode, SystemExecutionPlan, compile_plan
from .preflight import DeferredCheck, Finding, PreflightReport, PreflightStatus, preflight
from .records import (
    ApplicabilityReport, ArtifactRef, AuthorityMismatch, AuthorityRegistry, InputValue, NodeAuthority, NodeCall, NodeOutcome, NodeReceipt, NodeStatus,
    OutputValue, ProviderRecordRef, RuntimeContext, StateProposal,
)
from .replay import OutputDifference, RunComparison, compare_runs
from .request import (
    AuthorityRef, ConstraintObservation, ContentRef, EnvironmentRequirement, ExecutionProfile, LiteralInput, MaterialPropertyRef, ModelSelection,
    NodeInput, NodeKind, NodeOutputSpec, NodeSpec, OperationalContext, ProviderBinding, RequestedObservable, SystemRunRequest,
)
from .result import (
    Availability, AuthorityCheckpoint, ObservableResult, ResultTrace, RunStatus, SystemCheckpoint, SystemRunResult, TraceLink, TrustInputs, trace_result,
)
from .state import InitialStateSpec, OwnerState, ProviderCheckpointRef, SystemState

__all__ = [
    "BalanceSpec", "ConservationAssessment", "ConstraintAssessment", "TermSource", "assess_conservation", "assess_constraints", "trust_handoff",
    "CallbackAuthority", "MultiphysicsAuthority", "MultiscaleAuthority", "ProviderAuthority", "scalar_outputs",
    "ResumeRefused", "verify_checkpoint", "ExecutionCache", "SystemExecutor", "output_stamp",
    "PlanNode", "SystemExecutionPlan", "compile_plan", "DeferredCheck", "Finding", "PreflightReport", "PreflightStatus", "preflight",
    "ApplicabilityReport", "ArtifactRef", "AuthorityMismatch", "AuthorityRegistry", "InputValue", "NodeAuthority", "NodeCall", "NodeOutcome",
    "NodeReceipt", "NodeStatus", "OutputValue", "ProviderRecordRef", "RuntimeContext", "StateProposal",
    "OutputDifference", "RunComparison", "compare_runs",
    "AuthorityRef", "ConstraintObservation", "ContentRef", "EnvironmentRequirement", "ExecutionProfile", "LiteralInput", "MaterialPropertyRef",
    "ModelSelection", "NodeInput", "NodeKind", "NodeOutputSpec", "NodeSpec", "OperationalContext", "ProviderBinding", "RequestedObservable",
    "SystemRunRequest",
    "Availability", "AuthorityCheckpoint", "ObservableResult", "ResultTrace", "RunStatus", "SystemCheckpoint", "SystemRunResult", "TraceLink",
    "TrustInputs", "trace_result",
    "InitialStateSpec", "OwnerState", "ProviderCheckpointRef", "SystemState",
]
