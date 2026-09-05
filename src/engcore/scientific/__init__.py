"""Scientific Core V0 — domain-neutral contracts for scientific computation.

Principle
---------
We do not reinvent decades of validated scientific work, and we do not reduce
our platform to a thin wrapper around existing packages.

What this package owns: the scientific IR, model representation and validity,
solver orchestration contracts, validation semantics, uncertainty, provenance,
experiment representation, scientific-twin representation, and the optimizer
integration boundary.

What it deliberately does not own: numerical algorithms. Mature libraries
(SciPy, SUNDIALS, FEniCSx, Cantera, ngspice, ...) will be reached through
adapters that satisfy :class:`~engcore.scientific.solvers.ScientificSolver`.

Independence
------------
Nothing here imports an LLM provider, a web framework, a database, or a
visualization layer — and nothing may. If every AI provider disappeared, the
Scientific Core would remain fully usable.

Status: **V0 foundation.** Contracts only; no physical domain is implemented.
"""

from __future__ import annotations

from .errors import (
    AmbiguousSolverError,
    DuplicateRegistrationError,
    InvalidModelRealization,
    InvalidScientificCapability,
    InvalidScientificProblem,
    ModelNotFoundError,
    RealizationNotFoundError,
    ModelValidityError,
    ScientificCoreError,
    ScientificValidationError,
    SolverNotFoundError,
    UnitCompatibilityError,
)
from .capabilities import (
    ScientificCapability,
    capability_identifiers,
    scientific_capabilities,
)
from .experiments import (
    CandidateCodec,
    EvaluationStatus,
    ExperimentBudget,
    NumericSearchBackend,
    ObjectiveEncoder,
    OptimizerAdapter,
    ScientificEvaluation,
    ScientificExperiment,
)
from .ir import (
    BooleanValue,
    BoundaryCondition,
    BoundaryKind,
    ConstraintCheck,
    ConstraintDefinition,
    CategoricalValue,
    ConstraintOperator,
    InitialCondition,
    IntegerValue,
    ModelReference,
    ObjectiveDefinition,
    ObjectiveDirection,
    ScientificParameter,
    ScientificProblem,
    ScientificValue,
    ScientificVariable,
    UncertaintyRequirement,
    UncertaintySpecification,
    ValueKind,
    VariableKind,
    VariableRole,
    decode_value,
    encode_value,
    value_kind,
)
from .models import (
    BindingIssue,
    BindingIssueKind,
    CategoryCondition,
    FlagCondition,
    InputSourceKind,
    ModelBindingReport,
    ModelInputSpec,
    ModelOutputSpec,
    ModelRegistry,
    ModelType,
    ModelValidationStatus,
    RangeCondition,
    ScientificModelDefinition,
    ValidityAssessment,
    ValidityDomain,
    ValidityStatus,
)
from .composition import (
    QUANTITY_DEPENDENCY_SCHEMA,
    QuantityDependency,
    externally_imposed,
    unresolved_inputs,
)
from .realizations import (
    ImplementationReference,
    ModelFormulation,
    ModelRealizationDefinition,
    RealizationReference,
    RealizationRegistry,
)
from .results import (
    ExecutionBinding,
    ProvenanceRecord,
    ScientificDataReference,
    ScientificResult,
    Uncertainty,
    UncertaintyKind,
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
    unverified_report,
)
from .serialization import to_json
from .solvers import (
    ConvergenceState,
    CoreCapabilities,
    PreparedSolve,
    RawSolverOutput,
    ScientificSolver,
    SolverCapability,
    SolverCapabilityId,
    SolverIdentity,
    SolverRegistry,
    SolverSettings,
)
from .twins import ScientificTwin, TwinDatum, TwinDatumRole, TwinKind, TwinReference
from .units import Quantity, coerce_quantity, dimensionality, normalize_unit

SCIENTIFIC_CORE_VERSION = "0.1.0-v0-foundation"

__all__ = [
    "SCIENTIFIC_CORE_VERSION",
    # errors
    "ScientificCoreError",
    "InvalidScientificProblem",
    "UnitCompatibilityError",
    "ModelNotFoundError",
    "ModelValidityError",
    "SolverNotFoundError",
    "AmbiguousSolverError",
    "DuplicateRegistrationError",
    "ScientificValidationError",
    "InvalidScientificCapability",
    "InvalidModelRealization",
    "RealizationNotFoundError",
    # units
    "Quantity",
    "coerce_quantity",
    "dimensionality",
    "normalize_unit",
    # ir
    "ScientificProblem",
    "ScientificVariable",
    "ScientificParameter",
    "VariableKind",
    "VariableRole",
    "ScientificValue",
    "ValueKind",
    "IntegerValue",
    "BooleanValue",
    "CategoricalValue",
    "encode_value",
    "decode_value",
    "value_kind",
    "ObjectiveDefinition",
    "ObjectiveDirection",
    "ConstraintDefinition",
    "ConstraintOperator",
    "ConstraintCheck",
    "InitialCondition",
    "BoundaryCondition",
    "BoundaryKind",
    "ModelReference",
    "UncertaintySpecification",
    "UncertaintyRequirement",
    # models
    "ScientificModelDefinition",
    "ModelInputSpec",
    "ModelOutputSpec",
    "ModelBindingReport",
    "BindingIssue",
    "BindingIssueKind",
    "InputSourceKind",
    "ModelType",
    "ModelValidationStatus",
    "ModelRegistry",
    "ValidityDomain",
    "ValidityStatus",
    "ValidityAssessment",
    "RangeCondition",
    "CategoryCondition",
    "FlagCondition",
    # scientific capability identity
    "ScientificCapability",
    "scientific_capabilities",
    "capability_identifiers",
    # computational realizations
    "ModelRealizationDefinition",
    "ModelFormulation",
    "ImplementationReference",
    "RealizationReference",
    "RealizationRegistry",
    # system composition
    "QuantityDependency",
    "QUANTITY_DEPENDENCY_SCHEMA",
    "unresolved_inputs",
    "externally_imposed",
    # solvers
    "ScientificSolver",
    "SolverIdentity",
    "SolverSettings",
    "SolverCapability",
    "SolverCapabilityId",
    "CoreCapabilities",
    "SolverRegistry",
    "PreparedSolve",
    "RawSolverOutput",
    "ConvergenceState",
    # results
    "ScientificDataReference",
    "ScientificResult",
    "ValidationReport",
    "ValidationCheck",
    "ValidationOutcome",
    "ValidationLevel",
    "unverified_report",
    "Uncertainty",
    "UncertaintyKind",
    "ProvenanceRecord",
    "ExecutionBinding",
    # twins
    "ScientificTwin",
    "TwinDatum",
    "TwinDatumRole",
    "TwinKind",
    "TwinReference",
    # experiments
    "ScientificExperiment",
    "ExperimentBudget",
    "ScientificEvaluation",
    "EvaluationStatus",
    "OptimizerAdapter",
    "CandidateCodec",
    "ObjectiveEncoder",
    "NumericSearchBackend",
    # serialization
    "to_json",
]
