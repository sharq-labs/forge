"""Field + mesh core (BIG 7) and provider-neutral geometry (Big Rocks B-D).  Gmsh/meshio are providers only."""

from .mesh import CoordinateFrame, GroupKind, MeshProvenance, PhysicalGroup, SpatialMesh, SpatialRefusal, SpatialRegion
from .fields import (
    Conservation, Derivation, Discretization, Location, MappingRecord, Rank, RegionMaterialMap, SpatialField,
    SpatialFieldDefinition, interpolate_p1_to_mesh, node_to_cell_average,
)
from .providers import gmsh_available, gmsh_two_region_plate, read_meshio, write_meshio
from .geometry import (
    Body, Boundary, BoundaryBinding, FeatureRef, FeatureSelector, FrameDefinition, GeometryEntity, GeometryModel, GeometryReceipt,
    GeometryRefusal, ImportedSource, Interface, MaterialBinding, MeshBinding, ProviderEntityMap, Region, RoleAssignment, Shape,
    ShapeKind, TopologyRelation, Transform, region_material_map,
)
from .parametric import GeometryBuilderRegistry, GeometryParameter, GeometryVariant, ParameterKind, ParametricGeometry
from .gmsh_adapter import GeometryMeshResult, GmshGeometryProvider, GmshMeshRequest, mesh_geometry

__all__ = [
    "CoordinateFrame", "GroupKind", "MeshProvenance", "PhysicalGroup", "SpatialMesh", "SpatialRefusal", "SpatialRegion",
    "Conservation", "Derivation", "Discretization", "Location", "MappingRecord", "Rank", "RegionMaterialMap", "SpatialField",
    "SpatialFieldDefinition", "interpolate_p1_to_mesh", "node_to_cell_average",
    "gmsh_available", "gmsh_two_region_plate", "read_meshio", "write_meshio",
    "Body", "Boundary", "BoundaryBinding", "FeatureRef", "FeatureSelector", "FrameDefinition", "GeometryEntity", "GeometryModel",
    "GeometryReceipt", "GeometryRefusal", "ImportedSource", "Interface", "MaterialBinding", "MeshBinding", "ProviderEntityMap", "Region",
    "RoleAssignment", "Shape", "ShapeKind", "TopologyRelation", "Transform", "region_material_map",
    "GeometryBuilderRegistry", "GeometryParameter", "GeometryVariant", "ParameterKind", "ParametricGeometry",
    "GeometryMeshResult", "GmshGeometryProvider", "GmshMeshRequest", "mesh_geometry",
]
