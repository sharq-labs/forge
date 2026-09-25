"""Coordinate-frame transforms as scientific topology declarations."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string

FRAME_TRANSFORM_SCHEMA = schema_string(
    "multiphysics_frame_transform"
)


@dataclass(frozen=True)
class FrameTransform:
    """Orthonormal 2D/3D transform between two named coordinate frames."""

    transform_id: str
    source_frame: str
    target_frame: str
    matrix: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        transform_id = str(self.transform_id).strip()
        source = str(self.source_frame).strip()
        target = str(self.target_frame).strip()
        if not transform_id or not source or not target:
            raise InvalidScientificProblem(
                "frame transform requires id and named source/target frames"
            )
        if source == target:
            raise InvalidScientificProblem(
                "frame transform source and target frames must differ"
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
                "frame transform matrix must be 2x2 or 3x3"
            )
        if any(
            not math.isfinite(value)
            for row in matrix
            for value in row
        ):
            raise InvalidScientificProblem(
                "frame transform matrix must be finite"
            )

        tolerance = 1e-10
        for i in range(dimension):
            for j in range(dimension):
                dot = sum(
                    matrix[k][i] * matrix[k][j]
                    for k in range(dimension)
                )
                expected = 1.0 if i == j else 0.0
                if not math.isclose(
                    dot,
                    expected,
                    rel_tol=tolerance,
                    abs_tol=1e-12,
                ):
                    raise InvalidScientificProblem(
                        "frame transform must be orthonormal"
                    )

        if dimension == 2:
            determinant = (
                matrix[0][0] * matrix[1][1]
                - matrix[0][1] * matrix[1][0]
            )
        else:
            determinant = (
                matrix[0][0] * (
                    matrix[1][1] * matrix[2][2]
                    - matrix[1][2] * matrix[2][1]
                )
                - matrix[0][1] * (
                    matrix[1][0] * matrix[2][2]
                    - matrix[1][2] * matrix[2][0]
                )
                + matrix[0][2] * (
                    matrix[1][0] * matrix[2][1]
                    - matrix[1][1] * matrix[2][0]
                )
            )
        if not math.isclose(
            determinant, 1.0, rel_tol=tolerance, abs_tol=1e-12
        ):
            raise InvalidScientificProblem(
                "frame transform must be a proper rotation with determinant +1; "
                "reflections change handedness and require an explicit semantic "
                "conversion rather than a coordinate rotation"
            )

        object.__setattr__(self, "transform_id", transform_id)
        object.__setattr__(self, "source_frame", source)
        object.__setattr__(self, "target_frame", target)
        object.__setattr__(self, "matrix", matrix)

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
                tuple(float(value) for value in row)
                for row in payload["matrix"]
            ),
        )
