"""First-class field records: a support, regions on it, and fields over it.

The Scientific Core states scalar quantities well and states spatial ones not
at all: ``ScientificVariable`` has no shape, no location and no support;
``InitialCondition`` holds one ``Quantity``; a boundary region is a string the
core does not interpret; and a bulk data reference names a *count*, which its
own docstring is explicit is not a shape. ``tests/test_field_ir_ceiling.py``
demonstrates each of those rather than asserting them.

This package is the declaration half of the answer, and it holds **no values**.
That is the same boundary DATA-BOUNDARY0 drew and for the same reason: the
control plane carries identity, shape, units and summaries, while the numbers
live in the runtime plane behind a content-addressed reference. The core
imports no array library, and this package does not change that.

    scientific/fields/     what a support is, what a field is, where a
                           condition applies, what a transfer would have to
                           prove                                (this package)
    data/field.py          one unit-bearing array bound to those declarations
    domains/…              the physics that produces and consumes them

Scope, stated so it is not mistaken for a framework: one structured
two-dimensional rectilinear support, four edge regions, scalar or
multi-component fields at nodes or cells, and the two boundary-condition
families a conduction slice needs. Everything else — unstructured supports,
refinement, curvilinear geometry, faces, ghost layers — is absent rather than
stubbed.
"""

from .conditions import (
    FIELD_BOUNDARY_CONDITION_SCHEMA,
    FIELD_INITIAL_CONDITION_SCHEMA,
    FieldBoundaryCondition,
    FieldInitialCondition,
    require_complete_boundary,
)
from .definition import (
    FIELD_DEFINITION_SCHEMA,
    FieldDefinition,
    FieldLocation,
)
from .mesh import (
    CANONICAL_LENGTH,
    MESH_SCHEMA,
    MINIMUM_NODES,
    MeshTopology,
    StructuredMesh,
)
from .regions import (
    REGION_SCHEMA,
    BoundaryEdge,
    MeshRegion,
    boundary_regions,
)
from .result import (
    FIELD_RECORD_SCHEMA,
    FIELD_SUMMARY_SCHEMA,
    FieldRecord,
    FieldSummary,
)
from .profiles import (
    SPATIAL_PROFILE_SCHEMA,
    ConstantProfile,
    HarmonicProfile1D,
    Interpolation,
    LinearProfile1D,
    ProfileAxis,
    SeparableProfile2D,
    SpatialProfile,
    TabulatedProfile1D,
    as_profile,
    edge_axis,
    load_profile,
)
from .transfer import (
    FIELD_DEPENDENCY_SCHEMA,
    FIELD_TRANSFER_SCHEMA,
    FieldDependency,
    FieldTransferContract,
    FieldTransferVerdict,
    TransferKind,
    check_field_transfer,
)

__all__ = [
    "CANONICAL_LENGTH",
    "FIELD_BOUNDARY_CONDITION_SCHEMA",
    "FIELD_DEFINITION_SCHEMA",
    "FIELD_INITIAL_CONDITION_SCHEMA",
    "FIELD_RECORD_SCHEMA",
    "FIELD_SUMMARY_SCHEMA",
    "SPATIAL_PROFILE_SCHEMA",
    "ConstantProfile",
    "HarmonicProfile1D",
    "Interpolation",
    "LinearProfile1D",
    "ProfileAxis",
    "SeparableProfile2D",
    "SpatialProfile",
    "TabulatedProfile1D",
    "as_profile",
    "edge_axis",
    "load_profile",
    "FIELD_DEPENDENCY_SCHEMA",
    "FIELD_TRANSFER_SCHEMA",
    "FieldDependency",
    "MESH_SCHEMA",
    "MINIMUM_NODES",
    "REGION_SCHEMA",
    "BoundaryEdge",
    "FieldBoundaryCondition",
    "FieldDefinition",
    "FieldInitialCondition",
    "FieldLocation",
    "FieldRecord",
    "FieldSummary",
    "FieldTransferContract",
    "FieldTransferVerdict",
    "MeshRegion",
    "MeshTopology",
    "StructuredMesh",
    "TransferKind",
    "boundary_regions",
    "check_field_transfer",
    "require_complete_boundary",
]
