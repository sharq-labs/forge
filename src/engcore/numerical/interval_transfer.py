"""M1A managed lineage/state transfer. No transient solver or scientific evidence."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import numpy as np

from ..data.resolver import BulkDataResolver
from ..data.store import store_values
from ..execution.multiphysics.mapping import CONSERVATIVE_COVERAGE_ROUNDOFF
from ..scenarios.timeline import canonical_digest
from ..scientific.fields.semantics import FieldKind, FieldSemantics
from ..scientific.multiphysics.mapping import MappingDiagnostics
from ..scientific.results.data_reference import ScientificDataReference
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity, dimensionality, is_ratio_scale, normalize_unit
from .core import NumericalRefusal
from .field_mapping import map_cells_1d
from .mesh_adaptation import Grid1D, MeshLineage1D, MeshVersion1D, MeshChange1D, _AuditOnlyRecord, _IssuedRecords


class IntensiveTransferRule(str, Enum):
    PIECEWISE_CONSTANT_OVERLAP = "piecewise_constant_overlap"


class MeshResourceKind(str, Enum):
    SOLVER_CACHE = "solver_cache"
    COUPLING_HISTORY = "coupling_history"


@dataclass(frozen=True)
class BoundState1D(_AuditOnlyRecord):
    name: str
    mesh: MeshVersion1D
    semantics: FieldSemantics
    unit: str
    data: ScientificDataReference
    uncertainty: Uncertainty
    context_digest: str

    def _material(self):
        return {"schema": "bound_state_1d/1", "name": self.name, "mesh_version": self.mesh.version_id,
                "coordinate_frame": self.mesh.coordinate_frame,
                "semantics": self.semantics.to_dict(), "unit": self.unit, "data": self.data.to_dict(),
                "uncertainty": self.uncertainty.to_dict(), "context_digest": self.context_digest}

    @property
    def record_id(self):
        return canonical_digest(self._material())

    def to_dict(self):
        return {**self._material(), "state_id": self.record_id}


@dataclass(frozen=True)
class MeshResourceBinding(_AuditOnlyRecord):
    name: str
    mesh_version_id: str
    kind: MeshResourceKind

    @property
    def record_id(self):
        return canonical_digest({"schema": "mesh_resource_1d/1", "name": self.name,
                                 "mesh_version": self.mesh_version_id, "kind": self.kind.value})

    def to_dict(self):
        return {"schema": "mesh_resource_1d/1", "resource_id": self.record_id, "name": self.name,
                "mesh_version": self.mesh_version_id, "kind": self.kind.value}


@dataclass(frozen=True)
class MeshInvalidation1D(_AuditOnlyRecord):
    change: MeshChange1D
    fields: tuple[str, ...]
    resources: tuple[str, ...]

    @property
    def record_id(self):
        return canonical_digest({"schema": "mesh_invalidation_1d/1", "change": self.change.record_id,
                                 "fields": list(self.fields), "resources": list(self.resources)})

    def to_dict(self):
        return {"schema": "mesh_invalidation_1d/1", "invalidation_id": self.record_id,
                "change": self.change.to_dict(), "invalidated_fields": list(self.fields),
                "cleared_resources": list(self.resources)}


@dataclass(frozen=True)
class IntervalTransferReceipt(_AuditOnlyRecord):
    change_id: str
    source_state_id: str
    target_state_id: str
    diagnostics: MappingDiagnostics
    uncertainty: Uncertainty
    intensive_rule: IntensiveTransferRule | None

    def _material(self):
        return {"schema": "interval_transfer_receipt/1", "change_id": self.change_id,
                "source_state_id": self.source_state_id, "target_state_id": self.target_state_id,
                "diagnostics": self.diagnostics.to_dict(), "uncertainty": self.uncertainty.to_dict(),
                "intensive_rule": None if self.intensive_rule is None else self.intensive_rule.value,
                "classification": "constructed_state_transfer_not_physical_validation"}

    @property
    def record_id(self):
        return canonical_digest(self._material())

    def to_dict(self):
        return {**self._material(), "receipt_id": self.record_id}


class AdaptiveMesh1D:
    """Serial local manager. External caches and producer provenance are not authenticated."""
    def __init__(self, grid: Grid1D, *, root_context: str, coordinate_frame: str, store):
        if not isinstance(coordinate_frame, str) or not coordinate_frame.strip():
            raise NumericalRefusal("managed 1D state requires explicit common coordinate frame")
        self._lineage = MeshLineage1D(grid, root_context=root_context, coordinate_frame=coordinate_frame)
        self._version = self._lineage.current
        self._frame, self._store = coordinate_frame, store
        self._resolver = BulkDataResolver(store)
        self._issued = _IssuedRecords()
        self._active_fields, self._active_resources = {}, {}
        self._transferred = set()

    @property
    def mesh(self):
        self._guard()
        return self._version

    def _guard(self):
        self._lineage.verify()
        self._issued.verify()
        if self._lineage.current is not self._version:
            raise NumericalRefusal("mesh changed outside managed invalidation; session is unusable")
        if self._frame != self._version.coordinate_frame:
            raise NumericalRefusal("managed frame differs from issued mesh context")

    @staticmethod
    def _state_contract(semantics, unit, uncertainty, context_digest):
        if not isinstance(semantics, FieldSemantics) or not isinstance(uncertainty, Uncertainty):
            raise NumericalRefusal("state requires existing typed field semantics and explicit uncertainty")
        semantics.require_cell_mapping(semantics, 1)
        if not is_ratio_scale(unit) or dimensionality(unit) != dimensionality(semantics.quantity.unit):
            raise NumericalRefusal("M1 state units must match meaning and be ratio-scale; affine units refused")
        for value in (uncertainty.standard_uncertainty, uncertainty.lower, uncertainty.upper):
            if value is not None and value.dimensionality != dimensionality(unit):
                raise NumericalRefusal("state uncertainty dimensions do not match the declared value unit")
        if not isinstance(context_digest, str) or len(context_digest) != 64 or any(c not in "0123456789abcdef" for c in context_digest):
            raise NumericalRefusal("state requires explicit producer/context digest, not invented provenance")

    def register_state(self, name, values, *, semantics: FieldSemantics, unit: str,
                       uncertainty: Uncertainty, context_digest: str):
        self._guard()
        self._state_contract(semantics, unit, uncertainty, context_digest)
        if not isinstance(name, str) or not name.strip():
            raise NumericalRefusal("state requires a name")
        values = np.asarray(values, dtype=float)
        if values.shape != (len(self.mesh.cells),) or not np.all(np.isfinite(values)):
            raise NumericalRefusal("state values must be finite scalar cells on exact current mesh")
        unit = normalize_unit(unit)
        data = store_values(self._store, name, values, unit=unit)
        self._resolver.resolve(data)  # Verify actual bytes before making a live binding.
        state = self._issued.issue(BoundState1D(name, self.mesh, semantics, unit, data, uncertainty, context_digest))
        self._active_fields[name] = state.record_id
        return state

    def read_state(self, state: BoundState1D):
        self._guard()
        self._issued.require(state)
        if state.mesh is not self.mesh or self._active_fields.get(state.name) != state.record_id:
            raise NumericalRefusal("stale or superseded field cannot execute on current mesh version")
        return self._resolver.resolve(state.data)

    def bind_resource(self, name, kind: MeshResourceKind, container):
        self._guard()
        kind = MeshResourceKind(kind)
        if not isinstance(name, str) or not name.strip() or type(container) not in (dict, list):
            raise NumericalRefusal("managed cache/history requires a named built-in dict/list container")
        key = (kind, name)
        if key in self._active_resources:
            raise NumericalRefusal("conflicting managed resource binding")
        binding = self._issued.issue(MeshResourceBinding(name, self.mesh.version_id, kind))
        self._active_resources[key] = (binding, container)
        return binding

    def require_resource(self, binding):
        self._guard()
        self._issued.require(binding)
        entry = self._active_resources.get((binding.kind, binding.name))
        if entry is None or entry[0] is not binding or binding.mesh_version_id != self.mesh.version_id:
            raise NumericalRefusal("stale mesh-dependent solver cache or coupling history")
        return entry[1]

    def _invalidate(self, change):
        fields = tuple(sorted(self._active_fields.values()))
        resources = tuple(sorted(binding.record_id for binding, _ in self._active_resources.values()))
        for _, container in self._active_resources.values():
            container.clear()  # Actual contents, not just an invalidation label.
        self._active_resources.clear()
        self._active_fields.clear()
        self._version = change.after
        return self._issued.issue(MeshInvalidation1D(change, fields, resources))

    def refine(self, cell_ids, *, minimum_cell: Quantity, max_ratio: float):
        self._guard()
        change = self._lineage.refine(cell_ids, minimum_cell=minimum_cell, max_ratio=max_ratio)
        return self._invalidate(change)

    def coarsen(self, bisections, *, max_ratio: float):
        self._guard()
        change = self._lineage.coarsen(bisections, max_ratio=max_ratio)
        return self._invalidate(change)

    def transfer_state(self, source: BoundState1D, invalidation: MeshInvalidation1D, *,
                       target_unit: str | None = None, intensive_rule: IntensiveTransferRule | None = None):
        self._guard()
        self._issued.require(source)
        self._issued.require(invalidation)
        change = invalidation.change
        self._lineage.require(change)
        if (change.after is not self.mesh or source.mesh is not change.before
                or source.record_id not in invalidation.fields):
            raise NumericalRefusal("transfer requires exact issued source, immediate mesh change and current destination")
        transfer_key = (invalidation.record_id, source.record_id)
        if transfer_key in self._transferred or source.name in self._active_fields:
            raise NumericalRefusal("destination already populated or transition consumed; stale source transfer refused")
        unit = normalize_unit(source.unit if target_unit is None else target_unit)
        self._state_contract(source.semantics, unit, source.uncertainty, source.context_digest)
        intensive = source.semantics.kind is FieldKind.INTENSIVE
        if intensive:
            if intensive_rule is None or IntensiveTransferRule(intensive_rule) is not IntensiveTransferRule.PIECEWISE_CONSTANT_OVERLAP:
                raise NumericalRefusal("intensive transfer requires explicit qualified piecewise-constant overlap rule")
            intensive_rule = IntensiveTransferRule(intensive_rule)
        elif intensive_rule is not None:
            raise NumericalRefusal("intensive rule cannot relabel a conserved field")
        values = np.asarray(self._resolver.resolve(source.data), dtype=float)
        before, after = change.before.grid, change.after.grid
        result = map_cells_1d(values, before, after, source_semantics=source.semantics,
            target_semantics=source.semantics, source_unit=source.unit, target_unit=unit,
            source_fingerprint=before.digest, target_fingerprint=after.digest, coordinate_frame=self._frame)
        mapped = np.asarray(result.values, dtype=float)
        if mapped.shape != (len(change.after.cells),) or not np.all(np.isfinite(mapped)):
            raise NumericalRefusal("mapped state has invalid destination shape or non-finite values")
        # Independent admission: never accept a stored 'conserved' flag or a reported zero residual.
        a = np.asarray([Quantity(x, before.unit).magnitude_in("m") for x in before.nodes])
        b = np.asarray([Quantity(x, after.unit).magnitude_in("m") for x in after.nodes])
        va, vb = np.diff(a), np.diff(b)
        overlap = np.maximum(0, np.minimum(a[1:,None], b[None,1:])-np.maximum(a[:-1,None], b[None,:-1]))
        ca, cb = overlap.sum(axis=1)/va, overlap.sum(axis=0)/vb
        if (not np.all(np.isfinite(ca)) or not np.all(np.isfinite(cb))
                or np.max(np.abs(ca-1)) > CONSERVATIVE_COVERAGE_ROUNDOFF
                or np.max(np.abs(cb-1)) > CONSERVATIVE_COVERAGE_ROUNDOFF):
            raise NumericalRefusal("partial source or destination coverage; transfer refused")
        provenance = {"method": "lineage_bound_interval_overlap", "change_id": change.record_id,
            "source_mesh_version": change.before.version_id, "target_mesh_version": change.after.version_id,
            "source_support": before.digest, "target_support": after.digest, "source_unit": source.unit,
            "target_unit": unit, "field_semantics": source.semantics.to_dict(), "coordinate_frame": self._frame,
            "source_coverage_fraction": min(1.0, float(np.sum(overlap)/np.sum(va))),
            "target_coverage_fraction": min(1.0, float(np.sum(overlap)/np.sum(vb))),
            "max_source_coverage_deficit": float(np.max(np.abs(ca-1))),
            "max_target_coverage_deficit": float(np.max(np.abs(cb-1))),
            "roundoff_allowance": CONSERVATIVE_COVERAGE_ROUNDOFF,
            "notice": "constructed transfer arithmetic; no physical validity, error bound or source provenance established"}
        relative = None
        if not intensive:
            cq = source.semantics.conserved_quantity
            integrated = source.semantics.kind is FieldKind.CELL_INTEGRATED
            source_amounts = values if integrated else values*va
            target_amounts = mapped if integrated else mapped*vb
            source_factor = Quantity(1, source.unit if integrated else f"({source.unit})*m").magnitude_in(cq.unit)
            target_factor = Quantity(1, unit if integrated else f"({unit})*m").magnitude_in(cq.unit)
            total_a = math.fsum(float(x)*source_factor for x in source_amounts)
            total_b = math.fsum(float(x)*target_factor for x in target_amounts)
            l1 = math.fsum(abs(float(x)*source_factor) for x in source_amounts)
            residual = abs(total_a-total_b)
            relative = 0.0 if l1 == 0 and residual == 0 else residual/l1 if l1 > 0 else math.inf
            if not all(math.isfinite(x) for x in (total_a, total_b, l1, residual, relative)) or relative > CONSERVATIVE_COVERAGE_ROUNDOFF:
                raise NumericalRefusal("actual transferred amounts do not conserve the declared measure")
            provenance.update(source_total=total_a, target_total=total_b, conserved_unit=cq.unit,
                              absolute_residual=residual, scale_l1=l1)
        elif result.diagnostics.conservation_relative_error is not None:
            raise NumericalRefusal("intensive interpolation cannot claim conservation")
        diagnostics = MappingDiagnostics("lineage_interval", len(values), len(mapped), 0, 1.0,
                                         conservation_relative_error=relative, provenance=provenance)
        uncertainty = Uncertainty.unknown("spatial transfer error and model discrepancy are unquantified")
        target = self.register_state(source.name, mapped, semantics=source.semantics, unit=unit,
                                     uncertainty=uncertainty, context_digest=source.context_digest)
        receipt = self._issued.issue(IntervalTransferReceipt(change.record_id, source.record_id, target.record_id,
                                                            diagnostics, uncertainty, intensive_rule))
        self._transferred.add(transfer_key)
        return target, receipt
