"""Domain-neutral multiphysics declarations and run records."""

from .graph import (
    COUPLING_EDGE_SCHEMA,
    PHYSICS_GRAPH_SCHEMA,
    CouplingEdge,
    PhysicsGraph,
    ReductionOperator,
)
from .mapping import (
    FIELD_MAPPING_SCHEMA,
    MAPPING_DIAGNOSTICS_SCHEMA,
    ExtrapolationPolicy,
    FieldMappingDefinition,
    FieldMappingMethod,
    MappingDiagnostics,
)
from .participant import PARTICIPANT_SCHEMA, ParticipantSpec
from .plan import (
    COUPLING_PLAN_SCHEMA,
    CONVERGENCE_CRITERION_SCHEMA,
    RELAXATION_POLICY_SCHEMA,
    TIME_POLICY_SCHEMA,
    ConvergenceCriterion,
    CouplingPlan,
    CouplingScheme,
    IterationSemantics,
    RelaxationKind,
    RelaxationPolicy,
    ResidualNorm,
    TimePolicy,
)
from .ports import PORT_REF_SCHEMA, PORT_SCHEMA, PortDefinition, PortDirection, PortKind, PortRef
from .report import (
    CouplingIterationRecord,
    CouplingWindowRecord,
    EdgeResidual,
    MultiphysicsRunRecord,
    ParticipantStepRecord,
    WindowOutcome,
)
from .state import CHECKPOINT_SCHEMA, CheckpointRecord

__all__ = [
    "CHECKPOINT_SCHEMA",
    "COUPLING_EDGE_SCHEMA",
    "COUPLING_PLAN_SCHEMA",
    "CONVERGENCE_CRITERION_SCHEMA",
    "FIELD_MAPPING_SCHEMA",
    "MAPPING_DIAGNOSTICS_SCHEMA",
    "PARTICIPANT_SCHEMA",
    "PHYSICS_GRAPH_SCHEMA",
    "PORT_REF_SCHEMA",
    "PORT_SCHEMA",
    "RELAXATION_POLICY_SCHEMA",
    "TIME_POLICY_SCHEMA",
    "CheckpointRecord",
    "ConvergenceCriterion",
    "CouplingEdge",
    "CouplingIterationRecord",
    "CouplingPlan",
    "CouplingScheme",
    "CouplingWindowRecord",
    "EdgeResidual",
    "ExtrapolationPolicy",
    "FieldMappingDefinition",
    "FieldMappingMethod",
    "IterationSemantics",
    "MappingDiagnostics",
    "MultiphysicsRunRecord",
    "ParticipantSpec",
    "ParticipantStepRecord",
    "PhysicsGraph",
    "PortDefinition",
    "PortDirection",
    "PortKind",
    "PortRef",
    "ReductionOperator",
    "RelaxationKind",
    "RelaxationPolicy",
    "ResidualNorm",
    "TimePolicy",
    "WindowOutcome",
]
