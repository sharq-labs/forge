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

# NO `from __future__ import annotations` HERE, deliberately.
#
# This file contains no annotations -- checked, not assumed: an AST walk finds
# zero AnnAssign nodes, zero annotated arguments and zero return annotations
# across its 17 statements -- so the directive changed nothing about how the
# module compiled. What it DID do was bind the name `annotations` at package
# scope, which made
#
#     from engcore.scientific import annotations
#
# a working import returning a `__future__._Feature`. That is accidental public
# surface, and the Sprint 10 inventory found it as the only non-submodule leak
# in the whole Core.
#
# Any module under this package that DOES carry annotations keeps its own
# future import; this is about the package's `__init__` namespace, not about
# the codebase's style.

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
from .equations import (
    BinaryExpression,
    BinaryOperator,
    Constant,
    DimensionReport,
    DimensionVector,
    Equation,
    EquationDimensionError,
    EquationEvaluation,
    EquationEvaluationError,
    EquationIRError,
    EquationSymbol,
    FunctionExpression,
    FunctionName,
    LawAssumption,
    LawDefinition,
    PowerExpression,
    Symbol,
    UnaryExpression,
    UnaryOperator,
    assess_equation_dimensions,
    evaluate_equation,
    evaluate_expression,
    infer_dimension,
    require_equation_dimensions,
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
    UnknownCondition,
    UnknownReason,
    ValidityAssessment,
    ValidityDomain,
    ValidityStatus,
)
from .composition import (
    QUANTITY_DEPENDENCY_SCHEMA,
    ConversionOutcome,
    EnergyConversion,
    LossPath,
    QuantityDependency,
    QuantityTransfer,
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
from .consensus import (
    CONSENSUS_SCHEMA,
    ComponentKind,
    CrossSolverConsensus,
    IndependenceVerdict,
    RouteComparison,
    SharedComponent,
    SolveRoute,
)
from .solvers import (
    ConvergenceState,
    CoreCapabilities,
    PreparedSolve,
    RawSolverOutput,
    DeclaredSupport,
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
    # universal equations / laws
    "EquationIRError",
    "EquationDimensionError",
    "EquationEvaluationError",
    "Symbol",
    "Constant",
    "UnaryExpression",
    "BinaryExpression",
    "PowerExpression",
    "FunctionExpression",
    "UnaryOperator",
    "BinaryOperator",
    "FunctionName",
    "Equation",
    "DimensionVector",
    "DimensionReport",
    "infer_dimension",
    "assess_equation_dimensions",
    "require_equation_dimensions",
    "EquationEvaluation",
    "evaluate_expression",
    "evaluate_equation",
    "EquationSymbol",
    "LawAssumption",
    "LawDefinition",
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
    "UnknownCondition",
    "UnknownReason",
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
    "ConversionOutcome",
    "EnergyConversion",
    "LossPath",
    "QuantityDependency",
    "QuantityTransfer",
    "QUANTITY_DEPENDENCY_SCHEMA",
    "unresolved_inputs",
    "externally_imposed",
    # solvers
    "DeclaredSupport",
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
    # cross-solver consensus
    "CrossSolverConsensus",
    "SolveRoute",
    "SharedComponent",
    "ComponentKind",
    "IndependenceVerdict",
    "RouteComparison",
    "CONSENSUS_SCHEMA",
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
