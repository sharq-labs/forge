"""Relaxation and Aitken acceleration over scalar or field coupling values."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

from ...data.field import FieldValue
from ...data.resolver import BulkDataResolver
from ...data.store import BulkDataStore
from ...scientific.errors import InvalidScientificProblem
from ...scientific.fields import FieldRecord, MeshSupport
from ...scientific.multiphysics import RelaxationKind, RelaxationPolicy
from ...scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
    UncertaintySource,
)
from ...scientific.units.quantity import Quantity
from .participant import CouplingValue


@dataclass
class RelaxationController:
    policy: RelaxationPolicy
    resolver: BulkDataResolver
    store: BulkDataStore
    meshes: Mapping[str, MeshSupport]
    _omega: dict[str, float] = field(default_factory=dict)
    _previous_residual: dict[str, np.ndarray] = field(default_factory=dict)

    def reset_window(self) -> None:
        self._omega.clear()
        self._previous_residual.clear()

    def factor(self, edge_id: str) -> float:
        if self.policy.kind is RelaxationKind.NONE:
            return 1.0
        return self._omega.get(edge_id, self.policy.factor)

    def _vector(self, value: CouplingValue, *, unit: str) -> np.ndarray:
        if isinstance(value, Quantity):
            return np.asarray([value.magnitude_in(unit)], dtype=np.float64)
        mesh = self.meshes.get(value.definition.mesh_id)
        if mesh is None:
            raise InvalidScientificProblem(
                f"no mesh registered for field {value.definition.field_id!r}"
            )
        field = FieldValue.from_record(value, mesh, self.resolver).to_unit(unit)
        return np.asarray(field.values, dtype=np.float64).reshape(-1)

    def _from_vector(self, template: CouplingValue, vector: np.ndarray, *, unit: str) -> CouplingValue:
        if isinstance(template, Quantity):
            return Quantity(float(vector[0]), unit)
        mesh = self.meshes[template.definition.mesh_id]
        definition = template.definition
        if definition.unit != unit:
            from ...scientific.fields import FieldDefinition
            definition = FieldDefinition(
                definition.field_id,
                unit,
                definition.mesh_id,
                definition.location,
                definition.components,
                definition.description,
            )
        field = FieldValue(definition, mesh, vector.reshape(template.shape))
        record, _ = field.store(self.store)
        return record

    def relax(self, edge_id: str, previous: CouplingValue, raw: CouplingValue, *, unit: str) -> tuple[CouplingValue, float]:
        old = self._vector(previous, unit=unit)
        new = self._vector(raw, unit=unit)
        if old.shape != new.shape:
            raise InvalidScientificProblem(
                f"relaxation edge {edge_id!r} changed shape {old.shape}->{new.shape}"
            )
        residual = new - old
        omega = self.factor(edge_id)

        if self.policy.kind is RelaxationKind.AITKEN and edge_id in self._previous_residual:
            prior = self._previous_residual[edge_id]
            delta = residual - prior
            denominator = float(np.dot(delta, delta))
            if denominator > np.finfo(np.float64).tiny:
                candidate = (
                    -omega
                    * float(np.dot(prior, delta))
                    / denominator
                )
                if np.isfinite(candidate):
                    omega = min(
                        self.policy.maximum_factor,
                        max(self.policy.minimum_factor, candidate),
                    )
        elif self.policy.kind is RelaxationKind.NONE:
            omega = 1.0

        relaxed = old + omega * residual
        self._omega[edge_id] = omega
        self._previous_residual[edge_id] = residual.copy()
        return self._from_vector(raw, relaxed, unit=unit), omega



def relax_uncertainty(
    previous: Uncertainty,
    raw: Uncertainty,
    *,
    factor: float,
    unit: str,
    edge_id: str,
) -> Uncertainty:
    """Propagate uncertainty through numerical iterate mixing.

    The relaxed iterate is (1-w)*old + w*raw. No independence is assumed, so
    STANDARD widths combine linearly by absolute coefficients. INTERVAL bounds
    are propagated through the affine expression exactly, including
    over-relaxation where one coefficient is negative.
    """
    if not isinstance(previous, Uncertainty) or not isinstance(raw, Uncertainty):
        raise InvalidScientificProblem(
            "relaxation uncertainty requires Uncertainty records"
        )
    weight = float(factor)
    if not np.isfinite(weight):
        raise InvalidScientificProblem("relaxation factor must be finite")
    if (
        previous.kind is UncertaintyKind.UNKNOWN
        or raw.kind is UncertaintyKind.UNKNOWN
    ):
        return Uncertainty.unknown(
            f"coupling relaxation on edge {edge_id} mixed an iterate with "
            f"UNKNOWN uncertainty"
        )
    if previous.kind is not raw.kind:
        return Uncertainty.unknown(
            f"coupling relaxation on edge {edge_id} mixed different "
            f"uncertainty representations"
        )

    a, b = 1.0 - weight, weight
    source = f"coupling_relaxation:{edge_id}"

    if raw.kind is UncertaintyKind.STANDARD:
        assert previous.standard_uncertainty is not None
        assert raw.standard_uncertainty is not None
        old_width = previous.standard_uncertainty.magnitude_as_spread_in(unit)
        raw_width = raw.standard_uncertainty.magnitude_as_spread_in(unit)
        width = abs(a) * old_width + abs(b) * raw_width
        return Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(width, unit),
            source=source,
            source_kind=UncertaintySource.COMBINED,
            method="coupling_relaxation_linear_bound",
            notes=(
                f"iterate uncertainties combined as |1-w|*u_old + "
                f"|w|*u_raw with w={weight:g}; no independence assumption"
            ),
        )

    if raw.kind is UncertaintyKind.INTERVAL:
        assert previous.lower is not None and previous.upper is not None
        assert raw.lower is not None and raw.upper is not None
        old_lo = previous.lower.magnitude_in(unit)
        old_hi = previous.upper.magnitude_in(unit)
        raw_lo = raw.lower.magnitude_in(unit)
        raw_hi = raw.upper.magnitude_in(unit)

        old_terms = (a * old_lo, a * old_hi)
        raw_terms = (b * raw_lo, b * raw_hi)
        lower = min(old_terms) + min(raw_terms)
        upper = max(old_terms) + max(raw_terms)
        common_confidence = (
            raw.confidence_level
            if raw.confidence_level == previous.confidence_level
            else None
        )
        return Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(lower, unit),
            upper=Quantity(upper, unit),
            confidence_level=common_confidence,
            source=source,
            source_kind=UncertaintySource.COMBINED,
            method="coupling_relaxation_affine_interval",
            notes=(
                f"interval propagated through (1-w)*old + w*raw with "
                f"w={weight:g}; coefficient signs were respected"
            ),
        )

    return Uncertainty.unknown(
        f"coupling relaxation on edge {edge_id} has no rule for "
        f"{raw.kind.value}"
    )
