"""Typed multiphysics transfer, frame transformation and fan-in reduction."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

import numpy as np

from ...data.field import FieldValue
from ...data.resolver import BulkDataResolver
from ...data.store import BulkDataStore
from ...scientific.errors import InvalidScientificProblem
from ...scientific.fields import (
    FieldDefinition,
    FieldRecord,
    MeshSupport,
)
from ...scientific.multiphysics import (
    CouplingEdge,
    FieldAlgebra,
    FrameTransform,
    MappingDiagnostics,
    PhysicsGraph,
    PortKind,
    ReductionOperator,
)
from ...scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from ...scientific.units.quantity import Quantity
from ...scientific.results.uncertainty_mapping import (
    propagate_declared_mapping_uncertainty,
)
from .mapping import FieldMapper
from .participant import CouplingValue


@dataclass(frozen=True)
class TransferResult:
    edge_id: str
    value: CouplingValue
    source_value: CouplingValue
    losses: Mapping[str, Quantity]
    uncertainty: Uncertainty
    mapping: MappingDiagnostics | None = None

    def __post_init__(self) -> None:
        edge_id = str(self.edge_id).strip()
        if not edge_id:
            raise InvalidScientificProblem(
                "transfer result requires edge_id"
            )
        if not isinstance(self.uncertainty, Uncertainty):
            raise InvalidScientificProblem(
                "transfer result uncertainty must be Uncertainty"
            )
        object.__setattr__(self, "edge_id", edge_id)

    def diagnostics(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "losses": {
                key: value.to_dict()
                for key, value in sorted(self.losses.items())
            },
            "uncertainty": self.uncertainty.to_dict(),
            "mapping": (
                None
                if self.mapping is None
                else self.mapping.to_dict()
            ),
        }


class TransferEngine:
    def __init__(
        self,
        graph: PhysicsGraph,
        *,
        resolver: BulkDataResolver,
        store: BulkDataStore,
    ) -> None:
        self.graph = graph
        self.resolver = resolver
        self.store = store
        self.meshes = {
            support.mesh_id: support
            for support in graph.supports
        }
        self.frame_transforms = {
            transform.transform_id: transform
            for transform in graph.frame_transforms
        }
        self.mapper = FieldMapper(resolver, store)

    def _transform_field(
        self,
        record: FieldRecord,
        *,
        algebra: FieldAlgebra,
        transform: FrameTransform,
        target_definition: FieldDefinition,
        target_mesh: MeshSupport,
    ) -> FieldRecord:
        field = FieldValue.from_record(
            record, target_mesh, self.resolver
        )
        matrix = np.asarray(transform.matrix, dtype=np.float64)

        if algebra is FieldAlgebra.VECTOR:
            dimension = target_definition.components
            if matrix.shape != (dimension, dimension):
                raise InvalidScientificProblem(
                    f"frame transform {transform.transform_id!r} is "
                    f"{matrix.shape[0]}D but vector field "
                    f"{target_definition.field_id!r} is {dimension}D"
                )
            values = field.values.reshape(-1, dimension)
            transformed = values @ matrix.T
            reshaped = transformed.reshape(field.shape)

        elif algebra is FieldAlgebra.TENSOR_2:
            components = target_definition.components
            dimension = math.isqrt(components)
            if (
                dimension * dimension != components
                or matrix.shape != (dimension, dimension)
            ):
                raise InvalidScientificProblem(
                    f"frame transform {transform.transform_id!r} is "
                    f"{matrix.shape[0]}D but tensor field "
                    f"{target_definition.field_id!r} has "
                    f"{components} components"
                )
            tensors = field.values.reshape(
                -1, dimension, dimension
            )
            transformed = np.einsum(
                "ij,njk,lk->nil",
                matrix,
                tensors,
                matrix,
            )
            reshaped = transformed.reshape(field.shape)

        else:
            raise InvalidScientificProblem(
                f"field algebra {algebra.value!r} has no generic "
                "coordinate-frame transform rule"
            )

        out, _ = FieldValue(
            target_definition,
            target_mesh,
            reshaped,
        ).store(self.store)
        return out

    def transfer(
        self,
        edge: CouplingEdge,
        source_value: CouplingValue,
        source_uncertainty: Uncertainty,
        *,
        instant: str,
    ) -> TransferResult:
        source_port = self.graph.participant(
            edge.source.participant_id
        ).port(edge.source.port_id)
        target_port = self.graph.participant(
            edge.target.participant_id
        ).port(edge.target.port_id)

        if source_port.kind is PortKind.SCALAR:
            if not isinstance(source_value, Quantity):
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} expected scalar source value"
                )
            arrived = source_value
            losses: Mapping[str, Quantity] = {}
            if edge.conversion is not None:
                outcome = edge.conversion.convert(source_value)
                if outcome.value is None:
                    raise InvalidScientificProblem(
                        f"edge {edge.edge_id!r} conversion "
                        f"{edge.conversion.name!r} has no usable efficiency: "
                        f"{outcome.reason}"
                    )
                arrived = outcome.value
                losses = dict(outcome.losses)

            target_value = arrived.to(target_port.unit)
            propagated = propagate_declared_mapping_uncertainty(
                source_value=source_value,
                target_value=target_value,
                source_uncertainty=source_uncertainty,
                source_label=edge.source.key,
                target_label=edge.target.key,
                instant=instant,
                conversion=edge.conversion,
            )
            return TransferResult(
                edge_id=edge.edge_id,
                value=target_value,
                source_value=source_value,
                losses=losses,
                uncertainty=propagated,
            )

        if not isinstance(source_value, FieldRecord):
            raise InvalidScientificProblem(
                f"edge {edge.edge_id!r} expected FieldRecord source value"
            )
        source_mesh = self.meshes.get(source_port.field.mesh_id)
        target_mesh = self.meshes.get(target_port.field.mesh_id)
        if source_mesh is None or target_mesh is None:
            raise InvalidScientificProblem(
                f"edge {edge.edge_id!r} requires registered source "
                "and target mesh supports"
            )

        mapped = self.mapper.execute(
            source_value,
            source_mesh,
            target_port.field,
            target_mesh,
            edge.mapping,
        )
        value = mapped.record

        if source_port.coordinate_frame != target_port.coordinate_frame:
            transform = self.frame_transforms.get(
                edge.coordinate_transform_id
            )
            if transform is None:
                raise InvalidScientificProblem(
                    f"edge {edge.edge_id!r} requires frame transform "
                    f"{edge.coordinate_transform_id!r}"
                )
            if (
                transform.source_frame
                != source_port.coordinate_frame
                or transform.target_frame
                != target_port.coordinate_frame
            ):
                raise InvalidScientificProblem(
                    f"frame transform {transform.transform_id!r} "
                    "does not match edge frame declaration"
                )
            value = self._transform_field(
                value,
                algebra=source_port.algebra,
                transform=transform,
                target_definition=target_port.field,
                target_mesh=target_mesh,
            )

        return TransferResult(
            edge_id=edge.edge_id,
            value=value,
            source_value=source_value,
            losses={},
            uncertainty=Uncertainty.unknown(
                "field crossed a spatial mapping; current core has no "
                "spatial uncertainty-field representation"
            ),
            mapping=mapped.diagnostics,
        )

    def reduce_for_target(
        self,
        edges: tuple[CouplingEdge, ...],
        values: Mapping[str, CouplingValue],
    ) -> CouplingValue:
        if not edges:
            raise InvalidScientificProblem(
                "cannot reduce an empty coupling input"
            )
        if len(edges) == 1:
            return values[edges[0].edge_id]

        operator = edges[0].reduction
        if any(edge.reduction is not operator for edge in edges):
            raise InvalidScientificProblem(
                "fan-in edges disagree on reduction"
            )
        target_port = self.graph.participant(
            edges[0].target.participant_id
        ).port(edges[0].target.port_id)
        incoming = [
            values[edge.edge_id] for edge in edges
        ]

        if target_port.kind is PortKind.SCALAR:
            numbers = [
                value.magnitude_in(target_port.unit)
                for value in incoming
                if isinstance(value, Quantity)
            ]
            if len(numbers) != len(incoming):
                raise InvalidScientificProblem(
                    "scalar fan-in received a field"
                )
            if operator is ReductionOperator.SUM:
                result = sum(numbers)
            elif operator is ReductionOperator.MEAN:
                result = sum(numbers) / len(numbers)
            elif operator is ReductionOperator.MIN:
                result = min(numbers)
            elif operator is ReductionOperator.MAX:
                result = max(numbers)
            else:
                raise InvalidScientificProblem(
                    "fan-in requires explicit reduction"
                )
            return Quantity(result, target_port.unit)

        mesh = self.meshes.get(target_port.field.mesh_id)
        if mesh is None:
            raise InvalidScientificProblem(
                f"fan-in target mesh "
                f"{target_port.field.mesh_id!r} is not registered"
            )
        arrays = [
            FieldValue.from_record(
                value, mesh, self.resolver
            ).to_unit(target_port.unit).values
            for value in incoming
            if isinstance(value, FieldRecord)
        ]
        if len(arrays) != len(incoming):
            raise InvalidScientificProblem(
                "field fan-in received a scalar"
            )
        stack = np.stack(arrays, axis=0)
        if operator is ReductionOperator.SUM:
            reduced = np.sum(stack, axis=0)
        elif operator is ReductionOperator.MEAN:
            reduced = np.mean(stack, axis=0)
        elif operator is ReductionOperator.MIN:
            reduced = np.min(stack, axis=0)
        elif operator is ReductionOperator.MAX:
            reduced = np.max(stack, axis=0)
        else:
            raise InvalidScientificProblem(
                "fan-in requires explicit reduction"
            )
        record, _ = FieldValue(
            target_port.field,
            mesh,
            reduced,
        ).store(self.store)
        return record


def combine_fan_in_uncertainty(
    graph: PhysicsGraph,
    edges: tuple[CouplingEdge, ...],
    uncertainty: Mapping[str, Uncertainty],
) -> Uncertainty:
    """Conservatively propagate uncertainty through an explicit fan-in.

    No independence is assumed. STANDARD widths add linearly for SUM/MEAN.
    INTERVAL bounds pass through monotone SUM/MEAN/MIN/MAX exactly. Mixed
    representations, nonlinear source selection over STANDARD widths, and
    spatial fields stay UNKNOWN rather than being coerced.
    """
    if not edges:
        raise InvalidScientificProblem(
            "cannot combine uncertainty for empty fan-in"
        )
    if len(edges) == 1:
        return uncertainty[edges[0].edge_id]

    operator = edges[0].reduction
    target = graph.participant(
        edges[0].target.participant_id
    ).port(edges[0].target.port_id)
    incoming = [
        uncertainty[edge.edge_id] for edge in edges
    ]

    if target.kind is PortKind.FIELD:
        return Uncertainty.unknown(
            "fan-in produced a field; current core has no spatial "
            "uncertainty-field representation"
        )
    if any(
        item.kind is UncertaintyKind.UNKNOWN
        for item in incoming
    ):
        return Uncertainty.unknown(
            "at least one fan-in source has UNKNOWN uncertainty; "
            "UNKNOWN is not treated as zero"
        )

    kinds = {item.kind for item in incoming}
    source = "fan_in:" + ",".join(
        edge.edge_id for edge in edges
    )

    if kinds == {UncertaintyKind.STANDARD}:
        if operator not in (
            ReductionOperator.SUM,
            ReductionOperator.MEAN,
        ):
            return Uncertainty.unknown(
                f"{operator.value} over STANDARD uncertainties is "
                "nonlinear and source-selection probabilities were not "
                "declared"
            )
        widths = []
        for item in incoming:
            assert item.standard_uncertainty is not None
            widths.append(
                item.standard_uncertainty.magnitude_as_spread_in(
                    target.unit
                )
            )
        width = sum(widths)
        if operator is ReductionOperator.MEAN:
            width /= len(widths)
        return Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(width, target.unit),
            source=source,
            source_kind=UncertaintySource.COMBINED,
            method="fan_in_linear_bound_no_independence",
            notes=(
                "source standard uncertainties were combined by a "
                "linear absolute bound; no independence/correlation "
                "structure was assumed"
            ),
        )

    if kinds == {UncertaintyKind.INTERVAL}:
        lowers: list[float] = []
        uppers: list[float] = []
        confidence: list[float | None] = []
        for item in incoming:
            assert item.lower is not None
            assert item.upper is not None
            lowers.append(
                item.lower.magnitude_in(target.unit)
            )
            uppers.append(
                item.upper.magnitude_in(target.unit)
            )
            confidence.append(item.confidence_level)

        if operator is ReductionOperator.SUM:
            lower, upper = sum(lowers), sum(uppers)
        elif operator is ReductionOperator.MEAN:
            lower = sum(lowers) / len(lowers)
            upper = sum(uppers) / len(uppers)
        elif operator is ReductionOperator.MIN:
            lower, upper = min(lowers), min(uppers)
        elif operator is ReductionOperator.MAX:
            lower, upper = max(lowers), max(uppers)
        else:
            return Uncertainty.unknown(
                "fan-in reduction has no uncertainty rule"
            )

        common_confidence = (
            confidence[0]
            if confidence
            and all(level == confidence[0] for level in confidence)
            else None
        )
        return Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(lower, target.unit),
            upper=Quantity(upper, target.unit),
            confidence_level=common_confidence,
            source=source,
            source_kind=UncertaintySource.COMBINED,
            method=f"fan_in_interval_{operator.value}",
            notes=(
                "interval bounds were propagated through the monotone "
                "fan-in operator without a distribution or independence "
                "assumption"
            ),
        )

    return Uncertainty.unknown(
        "fan-in sources use mixed uncertainty representations; "
        "no coercion rule is declared"
    )
