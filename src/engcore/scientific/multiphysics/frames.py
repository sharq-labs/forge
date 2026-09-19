"""Coordinate-frame transformations declared as part of PhysicsGraph."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string

FRAME_TRANSFORM_SCHEMA = schema_string("multiphysics_frame_transform")
_ORTHONORMAL_TOLERANCE = 1e-10


@dataclass(frozen=True)
class FrameTransform:
    transform_id: str
    source_frame: str
    target_frame: str
    matrix: tuple[tuple[float, ...], ...]
    description: str = ""

    def __post_init__(self) -> None:
        transform_id = str(self.transform_id).strip()
        source = str(self.source_frame).strip()
        target = str(self.target_frame).strip()
        if (
            not transform_id
            or not source
            or not target
            or source == target
        ):
            raise InvalidScientificProblem(
                "frame transform requires id and two distinct named frames"
            )
        matrix = tuple(
            tuple(float(value) for value in row)
            for row in self.matrix
        )
        dimension = len(matrix)
        if dimension not in (2, 3) or any(
            len(row) != dimension for row in matrix
        ):
            raise InvalidScientificProblem(
                "frame transform matrix must be square 2D or 3D"
            )
        if any(
            not math.isfinite(value)
            for row in matrix
            for value in row
        ):
            raise InvalidScientificProblem(
                "frame transform matrix must be finite"
            )
        for i in range(dimension):
            for j in range(dimension):
                dot = math.fsum(
                    matrix[k][i] * matrix[k][j]
                    for k in range(dimension)
                )
                expected = 1.0 if i == j else 0.0
                if abs(dot - expected) > _ORTHONORMAL_TOLERANCE:
                    raise InvalidScientificProblem(
                        "frame transform matrix must be orthonormal"
                    )
        object.__setattr__(self, "transform_id", transform_id)
        object.__setattr__(self, "source_frame", source)
        object.__setattr__(self, "target_frame", target)
        object.__setattr__(self, "matrix", matrix)
        object.__setattr__(
            self, "description", str(self.description).strip()
        )

    @property
    def dimension(self) -> int:
        return len(self.matrix)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FRAME_TRANSFORM_SCHEMA,
            "transform_id": self.transform_id,
            "source_frame": self.source_frame,
            "target_frame": self.target_frame,
            "matrix": [list(row) for row in self.matrix],
            "description": self.description,
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "FrameTransform":
        require_schema(payload, FRAME_TRANSFORM_SCHEMA)
        return cls(
            transform_id=payload["transform_id"],
            source_frame=payload["source_frame"],
            target_frame=payload["target_frame"],
            matrix=tuple(
                tuple(row) for row in payload["matrix"]
            ),
            description=payload.get("description", ""),
        )
