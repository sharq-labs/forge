"""Field + mesh core (BIG 7) on the Core field/mesh records.  Gmsh/meshio are providers only."""

from .mesh import CoordinateFrame, GroupKind, MeshProvenance, PhysicalGroup, SpatialMesh, SpatialRefusal, SpatialRegion
from .fields import (
    Conservation, Derivation, Discretization, Location, MappingRecord, Rank, RegionMaterialMap, SpatialField,
    SpatialFieldDefinition, interpolate_p1_to_mesh, node_to_cell_average,
)
from .providers import gmsh_available, gmsh_two_region_plate, read_meshio, write_meshio

__all__ = [
    "CoordinateFrame", "GroupKind", "MeshProvenance", "PhysicalGroup", "SpatialMesh", "SpatialRefusal", "SpatialRegion",
    "Conservation", "Derivation", "Discretization", "Location", "MappingRecord", "Rank", "RegionMaterialMap", "SpatialField",
    "SpatialFieldDefinition", "interpolate_p1_to_mesh", "node_to_cell_average",
    "gmsh_available", "gmsh_two_region_plate", "read_meshio", "write_meshio",
]
