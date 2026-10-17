"""Relaxation, Aitken and interface quasi-Newton (IQN-ILS) over scalar or field coupling values."""

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
from ...scientific.units.quantity import Quantity, base_unit, is_ratio_scale
from .participant import CouplingValue


@dataclass
class RelaxationController:
    policy: RelaxationPolicy
    resolver: BulkDataResolver
    store: BulkDataStore
    meshes: Mapping[str, MeshSupport]
    _omega: dict[str, float] = field(default_factory=dict)
    _previous_residual: dict[str, np.ndarray] = field(default_factory=dict)
    #: IQN-ILS history of the JOINT interface vector within the current window:
    #: residuals r_i = H(x_i) - x_i and images H(x_i), the edge layout, and each
    #: edge's scale, fixed at the first iteration its residual is non-zero.
    _iqn_residuals: list[np.ndarray] = field(default_factory=list)
    _iqn_images: list[np.ndarray] = field(default_factory=list)
    _iqn_layout: tuple[tuple[str, int], ...] = ()
    _iqn_scales: dict[str, float] = field(default_factory=dict)

    def reset_window(self) -> None:
        self._omega.clear()
        self._previous_residual.clear()
        self._iqn_residuals.clear()
        self._iqn_images.clear()
        self._iqn_layout = ()
        self._iqn_scales.clear()

    def propagate_uncertainty(
        self,
        previous: Uncertainty,
        raw: Uncertainty,
        *,
        factor: float | None,
        unit: str,
        edge_id: str,
    ) -> Uncertainty:
        """Uncertainty of the relaxed iterate, by the rule of the update actually used."""
        if self.policy.kind is RelaxationKind.IQN_ILS or factor is None:
            return Uncertainty.unknown(
                f"coupling edge {edge_id} was updated by interface quasi-Newton "
                f"(a least-squares combination of the iterate history); no "
                f"uncertainty propagation rule is declared for it"
            )
        return relax_uncertainty(previous, raw, factor=factor, unit=unit, edge_id=edge_id)

    def relax_joint(
        self,
        items: Mapping[str, tuple[CouplingValue, CouplingValue, str]],
    ) -> dict[str, CouplingValue]:
        """One IQN-ILS step over the JOINT interface vector of every edge.

        ``items`` maps edge id -> (previous iterate x_k, raw transfer H(x_k),
        unit).  The step is ``x_{k+1} = H(x_k) + W c`` with
        ``c = argmin || D (V c + r_k) ||``.  ``V`` and ``W`` hold the
        differences of the residuals and of H over the last ``iqn_columns``
        iterations of THIS window.  ``D`` scales each edge by the RMS of its
        first non-zero residual in the window, so the least-squares weighting
        does not depend on the units an edge is declared in (residuals are
        differences, so an affine unit offset cancels).  Until an edge's
        residual is non-zero, its rows in ``V`` and ``r`` are identically zero
        and its weight is irrelevant.  The first iteration, or a solve that is
        not finite, falls back to constant relaxation with the declared
        factor.
        """
        if self.policy.kind is not RelaxationKind.IQN_ILS:
            raise InvalidScientificProblem("relax_joint is the IQN-ILS update only")
        order = tuple(sorted(items))
        olds: list[np.ndarray] = []
        news: list[np.ndarray] = []
        for edge_id in order:
            previous, raw, unit = items[edge_id]
            old = self._vector(previous, unit=unit)
            new = self._vector(raw, unit=unit)
            if old.shape != new.shape:
                raise InvalidScientificProblem(
                    f"relaxation edge {edge_id!r} changed shape {old.shape}->{new.shape}"
                )
            olds.append(old)
            news.append(new)
        layout = tuple((edge_id, vector.size) for edge_id, vector in zip(order, olds))
        if self._iqn_layout and layout != self._iqn_layout:
            raise InvalidScientificProblem(
                "IQN-ILS interface layout changed inside a coupling window"
            )
        old = np.concatenate(olds)
        new = np.concatenate(news)
        residual = new - old
        self._iqn_layout = layout
        weights = []
        for (edge_id, size), vector_old, vector_new in zip(layout, olds, news):
            if edge_id not in self._iqn_scales:
                scale = float(np.linalg.norm(vector_new - vector_old)) / np.sqrt(max(1, size))
                if scale > 0.0 and np.isfinite(scale):
                    self._iqn_scales[edge_id] = scale
            weights.append(np.full(size, 1.0 / self._iqn_scales.get(edge_id, 1.0)))
        weight = np.concatenate(weights)
        self._iqn_residuals.append(residual.copy())
        self._iqn_images.append(new.copy())
        keep = self.policy.iqn_columns + 1
        del self._iqn_residuals[:-keep]
        del self._iqn_images[:-keep]
        step = old + self.policy.factor * residual
        if len(self._iqn_residuals) >= 2:
            pairs = list(zip(self._iqn_residuals, self._iqn_residuals[1:]))
            v = np.column_stack([b - a for a, b in pairs])
            w = np.column_stack(
                [b - a for a, b in zip(self._iqn_images, self._iqn_images[1:])]
            )
            scaled = v * weight[:, None]
            if np.all(np.isfinite(scaled)) and float(np.max(np.abs(scaled))) > np.finfo(np.float64).tiny:
                coefficients, *_ = np.linalg.lstsq(
                    scaled, -residual * weight, rcond=None
                )
                candidate = new + w @ coefficients
                if np.all(np.isfinite(candidate)):
                    step = candidate
        out: dict[str, CouplingValue] = {}
        offset = 0
        for edge_id, size in layout:
            _, raw, unit = items[edge_id]
            out[edge_id] = self._from_vector(raw, step[offset:offset + size], unit=unit)
            offset += size
        return out

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
        """The relaxed iterate and its scalar factor (scalar-mix relaxations only)."""
        old = self._vector(previous, unit=unit)
        new = self._vector(raw, unit=unit)
        if old.shape != new.shape:
            raise InvalidScientificProblem(
                f"relaxation edge {edge_id!r} changed shape {old.shape}->{new.shape}"
            )
        if self.policy.kind is RelaxationKind.IQN_ILS:
            raise InvalidScientificProblem(
                "IQN-ILS updates the joint interface vector (relax_joint); it has no per-edge step"
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
        # a width is a spread: on a scale with a conventional zero (degC) it
        # is stated in the ratio-scale base unit, never as an absolute point
        spread_unit = unit if is_ratio_scale(unit) else base_unit(unit)
        old_width = previous.standard_uncertainty.magnitude_as_spread_in(spread_unit)
        raw_width = raw.standard_uncertainty.magnitude_as_spread_in(spread_unit)
        width = abs(a) * old_width + abs(b) * raw_width
        return Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(width, spread_unit),
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
        # The relaxed bounds hold whenever every CONTRIBUTING iterate lies in
        # its own interval; with no independence assumed only the union bound
        # 1 - sum(1 - c_i) over the contributing terms is guaranteed.
        levels = [
            item.confidence_level
            for coefficient, item in ((a, previous), (b, raw))
            if coefficient != 0.0
        ]
        common_confidence = None
        if levels and all(level is not None for level in levels):
            bound = 1.0 - sum(1.0 - float(level) for level in levels)
            if bound > 0.0:
                common_confidence = bound
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
