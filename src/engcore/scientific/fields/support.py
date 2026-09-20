"""Common field-support contract across structured and unstructured meshes."""

from __future__ import annotations

from typing import Any, Mapping, TypeAlias

from ..errors import InvalidScientificProblem
from .mesh import MESH_SCHEMA, StructuredMesh
from .unstructured import UNSTRUCTURED_MESH_SCHEMA, UnstructuredMesh

MeshSupport: TypeAlias = StructuredMesh | UnstructuredMesh


def read_mesh_support(payload: Mapping[str, Any]) -> MeshSupport:
    schema = payload.get("schema")
    if schema == MESH_SCHEMA:
        return StructuredMesh.from_dict(payload)
    if schema == UNSTRUCTURED_MESH_SCHEMA:
        return UnstructuredMesh.from_dict(payload)
    raise InvalidScientificProblem(
        f"unknown mesh support schema {schema!r}; expected "
        f"{MESH_SCHEMA!r} or {UNSTRUCTURED_MESH_SCHEMA!r}"
    )


__all__ = ["MeshSupport", "read_mesh_support"]
