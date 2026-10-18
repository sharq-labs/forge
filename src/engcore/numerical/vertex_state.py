"""OD-6 M1B local vertex/dual state adapter; no transient solve or evidence authority."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math

import numpy as np

from ..data.store import store_values
from ..execution.multiphysics.mapping import CONSERVATIVE_COVERAGE_ROUNDOFF
from ..scenarios.timeline import canonical_digest
from ..scientific.fields.semantics import FieldKind, FieldSemantics
from ..scientific.knowledge.source import KnowledgeSource
from ..scientific.results.data_reference import ScientificDataReference
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity, dimensionality, is_ratio_scale, normalize_unit
from .core import NumericalRefusal
from .field_mapping import map_cells_1d
from .interval_transfer import AdaptiveMesh1D
from .mesh_adaptation import Grid1D, MeshVersion1D, _AuditOnlyRecord, _IssuedRecords


class StateAdapterAdmission(str, Enum):
    OD6_VERTEX_DUAL_STATE_V1 = "od6_vertex_dual_state/1"


class StatePlacement(str, Enum):
    VERTEX_INTENSIVE = "vertex_intensive"
    DUAL_CELL_DENSITY = "dual_cell_density"
    DUAL_CELL_INTEGRATED = "dual_cell_integrated"


_KINDS = {StatePlacement.VERTEX_INTENSIVE: FieldKind.INTENSIVE,
          StatePlacement.DUAL_CELL_DENSITY: FieldKind.CELL_AVERAGE_DENSITY,
          StatePlacement.DUAL_CELL_INTEGRATED: FieldKind.CELL_INTEGRATED}


@dataclass(frozen=True)
class DualSupport1D(_AuditOnlyRecord):
    mesh: MeshVersion1D
    intervals: Grid1D

    @property
    def record_id(self):
        return canonical_digest(self.to_dict())

    def to_dict(self):
        return {"schema": "vertex_dual_support/1", "mesh_version": self.mesh.version_id,
                "frame": self.mesh.coordinate_frame, "primal": self.mesh.grid.to_dict(),
                "dual_boundaries": self.intervals.to_dict(), "rule": "endpoint_midpoint_vertex_dual/1"}


def _dual_grid(mesh):
    x = mesh.grid.nodes
    boundaries = (x[0], *(0.5*a + 0.5*b for a, b in zip(x[:-1], x[1:])), x[-1])
    result = Grid1D(boundaries, mesh.grid.unit)
    if len(result.cell_widths) != len(x) or not np.all(np.isfinite(result.cell_widths)):
        raise NumericalRefusal("unrepresentable vertex dual control volumes")
    return result


@dataclass(frozen=True)
class VertexState1D(_AuditOnlyRecord):
    name: str
    support: DualSupport1D
    placement: StatePlacement
    semantics: FieldSemantics
    unit: str
    data: ScientificDataReference
    uncertainty: Uncertainty
    context_digest: str
    source: KnowledgeSource | None
    parents: tuple[str, ...] = ()

    @property
    def record_id(self):
        return canonical_digest(self.to_dict())

    def to_dict(self):
        return {"schema": "vertex_dual_state/1", "name": self.name, "support": self.support.record_id,
                "mesh_version": self.support.mesh.version_id, "placement": self.placement.value,
                "semantics": self.semantics.to_dict(), "unit": self.unit, "data": self.data.to_dict(),
                "uncertainty": self.uncertainty.to_dict(), "context": self.context_digest,
                "source": None if self.source is None else self.source.to_dict(), "parents": list(self.parents)}


@dataclass(frozen=True)
class LinearStorage1D(_AuditOnlyRecord):
    """Declared A_i=C_i*u_i. C is already integrated on this exact dual support."""
    name: str
    support: DualSupport1D
    intensive: FieldSemantics
    integrated: FieldSemantics
    unit: str
    data: ScientificDataReference
    uncertainty: Uncertainty
    context_digest: str
    source: KnowledgeSource
    density: FieldSemantics | None = None

    @property
    def record_id(self):
        return canonical_digest(self.to_dict())

    def to_dict(self):
        return {"schema": "vertex_linear_storage/1", "name": self.name, "support": self.support.record_id,
                "intensive": self.intensive.to_dict(), "integrated": self.integrated.to_dict(),
                "unit": self.unit, "data": self.data.to_dict(), "uncertainty": self.uncertainty.to_dict(),
                "context": self.context_digest, "source": self.source.to_dict(), "law": "A_i=C_i*u_i/1",
                "density": None if self.density is None else self.density.to_dict()}


@dataclass(frozen=True)
class DualInvalidation1D(_AuditOnlyRecord):
    primal: object
    before: DualSupport1D
    after: DualSupport1D
    fields: tuple[str, ...]
    coefficients: tuple[str, ...]

    @property
    def record_id(self):
        return canonical_digest(self.to_dict())

    def to_dict(self):
        return {"schema": "dual_state_invalidation/1", "primal": self.primal.to_dict(),
                "before": self.before.record_id, "after": self.after.record_id,
                "fields": list(self.fields), "coefficients": list(self.coefficients)}


@dataclass(frozen=True)
class DualTransferReceipt(_AuditOnlyRecord):
    transition_id: str
    source_id: str
    target_id: str
    source_coverage: tuple[float, ...]
    target_coverage: tuple[float, ...]
    source_total: float
    target_total: float
    absolute_residual: float
    relative_residual: float
    conserved_unit: str
    source_unit: str
    target_unit: str
    uncertainty: Uncertainty
    #: the declared :class:`AmountDistribution1D` (its ``to_dict``), or None for the uniform-per-length default;
    #: carried whole so an auditor holding the receipt can see the split that was assumed
    distribution: dict | None = None

    @property
    def record_id(self):
        return canonical_digest(self.to_dict())

    def to_dict(self):
        return {"schema": "dual_state_transfer/1", "transition": self.transition_id,
                "source": self.source_id, "target": self.target_id,
                "source_coverage": list(self.source_coverage), "target_coverage": list(self.target_coverage),
                "source_total": self.source_total, "target_total": self.target_total,
                "absolute_residual": self.absolute_residual, "relative_residual": self.relative_residual,
                "conserved_unit": self.conserved_unit, "source_unit": self.source_unit,
                "target_unit": self.target_unit, "roundoff_allowance": CONSERVATIVE_COVERAGE_ROUNDOFF,
                "uncertainty": self.uncertainty.to_dict(),
                # absent when undeclared: existing receipts keep their identity
                **({"distribution": self.distribution} if self.distribution is not None else {}),
                "classification": "constructed_dual_transfer_not_pointwise_accuracy_or_physical_validation"}


@dataclass(frozen=True)
class AmountDistribution1D:
    """A declared positive weight ``w(x)``, constant on each ``[breakpoints[k], breakpoints[k+1]]``.

    Within every source dual the conserved amount is split over the target duals it overlaps in proportion to
    ``integral of w`` over each overlap, instead of in proportion to overlap length. For a storage law
    ``A_i = C_i * u_i`` with one intensive value per dual, ``w = capacity per length`` (e.g. ``c * area``) is the
    split the discrete state itself implies: a uniform ``u`` is transferred to a uniform ``u`` across a jump in
    ``w``, where the length split moves amount between materials. The weight is a declared assumption, carried
    whole on the receipt; it is not evidence, is not checked against any registered storage, and quantifies no
    transfer error. Only ratios of ``w`` are used, so ``unit`` is normalized and recorded, never converted.
    """

    breakpoints: tuple[float, ...]
    breakpoint_unit: str
    weights: tuple[float, ...]
    unit: str

    def __post_init__(self):
        points = tuple(float(x) for x in self.breakpoints)
        weights = tuple(self.weights)
        if (len(points) < 2 or not all(math.isfinite(x) for x in points)
                or any(b <= a for a, b in zip(points, points[1:]))):
            raise NumericalRefusal("amount distribution breakpoints must be finite and strictly increasing")
        if (len(weights) != len(points) - 1 or any(isinstance(w, bool) or not isinstance(w, (int, float)) for w in weights)
                or not all(math.isfinite(float(w)) and float(w) > 0 for w in weights)):
            raise NumericalRefusal("amount distribution needs one finite positive weight per breakpoint interval")
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise NumericalRefusal("amount distribution weight unit must be declared")
        try:
            object.__setattr__(self, "unit", normalize_unit(self.unit))
        except Exception as exc:  # UnitCompatibilityError: an unparsable unit is not a declaration
            raise NumericalRefusal(f"amount distribution weight unit is not a unit: {self.unit!r}") from exc
        if (not isinstance(self.breakpoint_unit, str) or not is_ratio_scale(self.breakpoint_unit)
                or dimensionality(self.breakpoint_unit) != dimensionality("m")):
            raise NumericalRefusal("amount distribution breakpoints require an explicit ratio-scale length unit")
        object.__setattr__(self, "breakpoints", points)
        object.__setattr__(self, "breakpoint_unit", normalize_unit(self.breakpoint_unit))
        object.__setattr__(self, "weights", tuple(float(w) for w in weights))

    def to_dict(self):
        return {"schema": "dual_amount_distribution/1", "breakpoints": [x.hex() for x in self.breakpoints],
                "breakpoint_unit": self.breakpoint_unit, "weights": [w.hex() for w in self.weights], "unit": self.unit,
                "rule": "piecewise_constant_weight_overlap_split/1"}

    @property
    def digest(self):
        return canonical_digest(self.to_dict())

    def integrate(self, left, right):
        """``integral of w`` over ``[left, right]`` (metres, broadcast arrays); zero where ``right <= left``."""
        factor = Quantity(1, self.breakpoint_unit).magnitude_in("m")
        b = np.asarray(self.breakpoints, dtype=float)*factor
        lo, hi = np.asarray(left, dtype=float)[..., None], np.asarray(right, dtype=float)[..., None]
        segments = np.maximum(0.0, np.minimum(hi, b[1:]) - np.maximum(lo, b[:-1]))
        return segments @ np.asarray(self.weights, dtype=float)

    def span_m(self):
        factor = Quantity(1, self.breakpoint_unit).magnitude_in("m")
        return self.breakpoints[0]*factor, self.breakpoints[-1]*factor


def normalized_input_bytes(*, support: DualSupport1D, role: str, name: str, values,
                           unit: str, context_digest: str, contract: dict, uncertainty: Uncertainty):
    """Normalized artifact format, not an extraction or physical-source qualification API."""
    return json.dumps({"schema": "vertex_normalized_input/1", "support": support.record_id,
                       "role": role, "name": name, "values": [float(x).hex() for x in values],
                       "unit": normalize_unit(unit), "context": context_digest, "contract": contract,
                       "uncertainty": uncertainty.to_dict()},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


class VertexDualAdapter1D:
    """Serial, session-local OD-6 state adaptation, independent of legacy transient admission."""
    def __init__(self, grid: Grid1D, *, admission: StateAdapterAdmission, root_context: str,
                 coordinate_frame: str, store):
        if admission is not StateAdapterAdmission.OD6_VERTEX_DUAL_STATE_V1:
            raise NumericalRefusal("explicit versioned OD-6 vertex-state admission required; no transient solver")
        self._runtime = AdaptiveMesh1D(grid, root_context=root_context, coordinate_frame=coordinate_frame, store=store)
        self._issued = _IssuedRecords()
        self._support = self._issued.issue(DualSupport1D(self._runtime.mesh, _dual_grid(self._runtime.mesh)))
        self._fields, self._coefficients = {}, {}
        self._consumed = set()
        self._unusable = False

    def _guard(self):
        if self._unusable:
            raise NumericalRefusal("dual adapter unusable after unsafe mesh transition")
        self._runtime._guard()
        self._issued.verify()
        self._issued.require(self._support)
        if self._support.mesh is not self._runtime.mesh:
            raise NumericalRefusal("stale dual support/primal version")
        if self._support.intervals != _dual_grid(self._runtime.mesh):
            raise NumericalRefusal("dual geometry inconsistent with issued primal version")

    @property
    def support(self):
        self._guard()
        return self._support

    @property
    def mesh(self):
        self._guard()
        return self._runtime.mesh

    def _values(self, values):
        raw = np.asarray(values, dtype=float)
        if raw.shape != (len(self.mesh.grid.nodes),) or not np.all(np.isfinite(raw)):
            raise NumericalRefusal("values require one finite scalar per exact vertex/dual cell; primal arrays refused")
        return raw

    @staticmethod
    def _source(source, source_bytes, expected):
        if (not isinstance(source, KnowledgeSource) or type(source_bytes) is not bytes
                or hashlib.sha256(source_bytes).hexdigest() != source.document_digest
                or source_bytes != expected):
            raise NumericalRefusal("missing, unsupported or inconsistent normalized-input source provenance")

    def _state_contract(self, placement, semantics, unit, uncertainty, context_digest):
        if not isinstance(placement, StatePlacement) or not isinstance(semantics, FieldSemantics):
            raise NumericalRefusal("explicit typed vertex/dual placement and field meaning required")
        if semantics.kind is not _KINDS[placement]:
            raise NumericalRefusal("state placement and field kind disagree")
        self._runtime._state_contract(semantics, unit, uncertainty, context_digest)

    def _publish(self, name, values, placement, semantics, unit, uncertainty, context, source, parents=()):
        if not isinstance(name, str) or not name.strip() or name in self._fields:
            raise NumericalRefusal("named unpopulated dual state slot required; overwrite refused")
        values = self._values(values)
        self._state_contract(placement, semantics, unit, uncertainty, context)
        data = store_values(self._runtime._store, name, values, unit=normalize_unit(unit))
        self._runtime._resolver.resolve(data)
        state = self._issued.issue(VertexState1D(name, self.support, placement, semantics, normalize_unit(unit),
                                                data, uncertainty, context, source, tuple(parents)))
        self._fields[name] = state.record_id
        return state

    def register_state(self, name, values, *, placement: StatePlacement, semantics: FieldSemantics,
                       unit: str, uncertainty: Uncertainty, context_digest: str,
                       source: KnowledgeSource, source_bytes: bytes):
        self._guard()
        self._state_contract(placement, semantics, unit, uncertainty, context_digest)
        raw = self._values(values)
        expected = normalized_input_bytes(support=self.support, role="initial_state", name=name, values=raw,
            unit=unit, context_digest=context_digest, contract={"placement": placement.value,
            "semantics": semantics.to_dict()}, uncertainty=uncertainty)
        self._source(source, source_bytes, expected)
        return self._publish(name, raw, placement, semantics, unit, uncertainty, context_digest, source)

    def _current(self, record, registry):
        self._guard()
        self._issued.require(record)
        self._require_parents(record)
        if record.support is not self.support or registry.get(record.name) != record.record_id:
            raise NumericalRefusal("stale vertex field or dual coefficient")

    def _require_parents(self, record, seen=None):
        seen = set() if seen is None else seen
        self._issued.require(record)
        if record.record_id in seen:
            raise NumericalRefusal("cyclic derived state ancestry")
        seen.add(record.record_id)
        if isinstance(record, DualSupport1D):
            self._runtime._lineage.require(record.mesh)
            if record.intervals != _dual_grid(record.mesh):
                raise NumericalRefusal("ancestor dual geometry inconsistent with primal lineage")
        elif isinstance(record, (VertexState1D, LinearStorage1D)):
            self._require_parents(record.support, seen.copy())
            for key in getattr(record, "parents", ()):
                parent = self._issued.lookup(key, (VertexState1D, LinearStorage1D, DualInvalidation1D))
                self._require_parents(parent, seen.copy())
        elif isinstance(record, DualInvalidation1D):
            self._require_parents(record.before, seen.copy())
            self._require_parents(record.after, seen.copy())
            self._runtime._issued.require(record.primal)
            change = record.primal.change
            self._runtime._lineage.require(change)
            if record.before.mesh is not change.before or record.after.mesh is not change.after:
                raise NumericalRefusal("dual/primal transition ancestry differs")

    def read_state(self, state: VertexState1D):
        if not isinstance(state, VertexState1D):
            raise NumericalRefusal("primal-cell records are not vertex/dual states")
        self._current(state, self._fields)
        return self._runtime._resolver.resolve(state.data)

    def register_storage(self, name, coefficients, *, intensive: FieldSemantics, integrated: FieldSemantics,
                         unit: str, uncertainty: Uncertainty, context_digest: str,
                         source: KnowledgeSource, source_bytes: bytes, density: FieldSemantics | None = None):
        self._guard()
        self._state_contract(StatePlacement.VERTEX_INTENSIVE, intensive, intensive.quantity.unit,
                             Uncertainty.unknown(), context_digest)
        self._state_contract(StatePlacement.DUAL_CELL_INTEGRATED, integrated, integrated.quantity.unit,
                             Uncertainty.unknown(), context_digest)
        if density is not None:
            self._state_contract(StatePlacement.DUAL_CELL_DENSITY, density, density.quantity.unit,
                                 Uncertainty.unknown(), context_digest)
            if density.conserved_quantity != integrated.conserved_quantity:
                raise NumericalRefusal("storage density and integrated conserved meanings differ")
        expected_unit = f"({integrated.quantity.unit})/({intensive.quantity.unit})"
        if not is_ratio_scale(unit) or dimensionality(unit) != dimensionality(expected_unit):
            raise NumericalRefusal("storage requires explicit integrated-amount/intensive units")
        # Reuse the existing unit/UQ checks without assigning a new field meaning to coefficients.
        if not isinstance(uncertainty, Uncertainty):
            raise NumericalRefusal("storage requires explicit uncertainty")
        for q in (uncertainty.standard_uncertainty, uncertainty.lower, uncertainty.upper):
            if q is not None and q.dimensionality != dimensionality(unit):
                raise NumericalRefusal("coefficient uncertainty dimensions disagree")
        raw = self._values(coefficients)
        if np.any(raw <= 0):
            raise NumericalRefusal("missing/nonpositive storage makes intensive reconstruction underdetermined")
        if not isinstance(name, str) or not name.strip() or name in self._coefficients:
            raise NumericalRefusal("named unpopulated storage slot required")
        contract = {"intensive": intensive.to_dict(), "integrated": integrated.to_dict(), "law": "A_i=C_i*u_i/1",
                    "density": None if density is None else density.to_dict()}
        expected = normalized_input_bytes(support=self.support, role="integrated_storage", name=name, values=raw,
            unit=unit, context_digest=context_digest, contract=contract, uncertainty=uncertainty)
        self._source(source, source_bytes, expected)
        data = store_values(self._runtime._store, name, raw, unit=normalize_unit(unit))
        self._runtime._resolver.resolve(data)
        law = self._issued.issue(LinearStorage1D(name, self.support, intensive, integrated, normalize_unit(unit),
                                                 data, uncertainty, context_digest, source, density))
        self._coefficients[name] = law.record_id
        return law

    def convert_storage(self, state: VertexState1D, storage: LinearStorage1D, *, name: str):
        values = np.asarray(self.read_state(state), dtype=float)
        if not isinstance(storage, LinearStorage1D):
            raise NumericalRefusal("explicit current storage law required; intensive state is underdetermined")
        self._current(storage, self._coefficients)
        if state.context_digest != storage.context_digest:
            raise NumericalRefusal("storage and state contexts differ")
        coeff = np.asarray(self._runtime._resolver.resolve(storage.data), dtype=float)
        if np.any(coeff <= 0) or not np.all(np.isfinite(coeff)):
            raise NumericalRefusal("invalid storage coefficients")
        if state.placement is StatePlacement.VERTEX_INTENSIVE:
            if state.semantics != storage.intensive:
                raise NumericalRefusal("storage law intensive meaning differs")
            factor = Quantity(1, f"({storage.unit})*({state.unit})").magnitude_in(storage.integrated.quantity.unit)
            if not math.isfinite(factor) or factor <= 0:
                raise NumericalRefusal("unrepresentable storage unit conversion")
            out, placement, sem = coeff*values*factor, StatePlacement.DUAL_CELL_INTEGRATED, storage.integrated
            recovered, original = out/coeff/factor, values
        else:
            # Density means amount per dual length; no area/material factor is silently supplied.
            if state.placement is StatePlacement.DUAL_CELL_INTEGRATED:
                if state.semantics != storage.integrated:
                    raise NumericalRefusal("storage law conserved meaning differs")
                amounts, raw_unit = values, state.unit
            else:
                if state.semantics != storage.density:
                    raise NumericalRefusal("storage law density conserved meaning differs")
                lengths = self._lengths(state.support)
                amounts, raw_unit = values*lengths, f"({state.unit})*m"
            factor = Quantity(1, f"({raw_unit})/({storage.unit})").magnitude_in(storage.intensive.quantity.unit)
            if not math.isfinite(factor) or factor <= 0:
                raise NumericalRefusal("unrepresentable storage unit conversion")
            out, placement, sem = amounts/coeff*factor, StatePlacement.VERTEX_INTENSIVE, storage.intensive
            recovered, original = out*coeff/factor, amounts
        if (not np.all(np.isfinite(out)) or not np.all(np.isfinite(recovered))
                or np.any(np.abs(recovered-original) > CONSERVATIVE_COVERAGE_ROUNDOFF*np.abs(original))):
            raise NumericalRefusal("storage arithmetic loses declared content beyond roundoff allowance")
        return self._publish(name, out, placement, sem, sem.quantity.unit, self._unknown(), state.context_digest,
                             None, (state.record_id, storage.record_id))

    @staticmethod
    def _unknown():
        return Uncertainty.unknown("input, storage-law discrepancy and spatial transfer error are unquantified")

    @staticmethod
    def _lengths(support):
        return np.asarray([Quantity(v, support.intervals.unit).magnitude_in("m")
                           for v in support.intervals.cell_widths])

    def bind_resource(self, name, kind, container):
        self._guard()
        return self._runtime.bind_resource(name, kind, container)

    def require_resource(self, binding):
        self._guard()
        return self._runtime.require_resource(binding)

    def _change(self, operation, *args, **kwargs):
        self._guard()
        before, fields, coefficients = self.support, tuple(sorted(self._fields.values())), tuple(sorted(self._coefficients.values()))
        try:
            primal = operation(*args, **kwargs)
            self._fields.clear()
            self._coefficients.clear()
            self._support = self._issued.issue(DualSupport1D(self._runtime.mesh, _dual_grid(self._runtime.mesh)))
            return self._issued.issue(DualInvalidation1D(primal, before, self.support, fields, coefficients))
        except Exception:
            if self._runtime._version is not before.mesh or self._runtime._lineage.current is not before.mesh:
                self._unusable = True
            raise

    def refine(self, cell_ids, *, minimum_cell: Quantity, max_ratio: float):
        return self._change(self._runtime.refine, cell_ids, minimum_cell=minimum_cell, max_ratio=max_ratio)

    def coarsen(self, bisections, *, max_ratio: float):
        return self._change(self._runtime.coarsen, bisections, max_ratio=max_ratio)

    def transfer_state(self, source: VertexState1D, transition: DualInvalidation1D, *, target_unit=None,
                       distribution: AmountDistribution1D | None = None):
        """Move one conserved dual state across an issued transition.

        Default: each source dual's amount is split over overlapping target duals by overlap LENGTH (uniform per
        length inside a dual). With a declared ``distribution`` (integrated placement only) it is split by the
        integral of the declared weight instead -- see :class:`AmountDistribution1D`. Either way the totals are
        conserved and checked; neither is a pointwise accuracy statement.
        """
        self._guard()
        if not isinstance(source, VertexState1D) or not isinstance(transition, DualInvalidation1D):
            raise NumericalRefusal("explicit issued vertex/dual source and transition required")
        if distribution is not None and not isinstance(distribution, AmountDistribution1D):
            raise NumericalRefusal("a declared amount distribution must be an AmountDistribution1D")
        self._issued.require(source)
        self._issued.require(transition)
        self._issued.require(source.support)
        self._require_parents(source)
        self._require_parents(transition)
        self._runtime._lineage.require(transition.primal.change)
        change = transition.primal.change
        if (source.support is not transition.before or transition.after is not self.support
                or source.support.mesh is not change.before or self.mesh is not change.after
                or source.record_id not in transition.fields):
            raise NumericalRefusal("unrelated or stale dual transfer; immediate issued transition required")
        key = (transition.record_id, source.record_id)
        if key in self._consumed or source.name in self._fields:
            raise NumericalRefusal("transition consumed or destination populated")
        if source.placement is StatePlacement.VERTEX_INTENSIVE:
            raise NumericalRefusal("vertex interpolation/reconstruction unsupported; transfer conserved content then declare target storage")
        if distribution is not None and source.placement is not StatePlacement.DUAL_CELL_INTEGRATED:
            raise NumericalRefusal("a declared amount distribution applies to dual-integrated amounts only")
        unit = normalize_unit(source.unit if target_unit is None else target_unit)
        self._state_contract(source.placement, source.semantics, unit, source.uncertainty, source.context_digest)
        values = np.asarray(self._runtime._resolver.resolve(source.data), dtype=float)
        a, b = source.support.intervals, self.support.intervals
        result = map_cells_1d(values, a, b, source_semantics=source.semantics, target_semantics=source.semantics,
            source_unit=source.unit, target_unit=unit, source_fingerprint=a.digest, target_fingerprint=b.digest,
            coordinate_frame=self.mesh.coordinate_frame)
        mapped = self._values(result.values)
        x = np.asarray([Quantity(v, a.unit).magnitude_in("m") for v in a.nodes])
        y = np.asarray([Quantity(v, b.unit).magnitude_in("m") for v in b.nodes])
        va, vb = np.diff(x), np.diff(y)
        overlap = np.maximum(0, np.minimum(x[1:, None], y[None, 1:])-np.maximum(x[:-1, None], y[None, :-1]))
        ca, cb = overlap.sum(axis=1)/va, overlap.sum(axis=0)/vb
        if any(not np.all(np.isfinite(c)) or np.max(np.abs(c-1)) > CONSERVATIVE_COVERAGE_ROUNDOFF for c in (ca, cb)):
            raise NumericalRefusal("partial source or destination dual coverage")
        if distribution is not None:
            # the length split above validated meaning, unit and frame; the amounts are re-split by the weight
            lo, hi = distribution.span_m()
            span = x[-1] - x[0]
            if abs(lo - x[0]) > CONSERVATIVE_COVERAGE_ROUNDOFF*span or abs(hi - x[-1]) > CONSERVATIVE_COVERAGE_ROUNDOFF*span:
                raise NumericalRefusal("amount distribution does not cover exactly the dual support")
            shares = distribution.integrate(np.maximum(x[:-1, None], y[None, :-1]), np.minimum(x[1:, None], y[None, 1:]))
            own = distribution.integrate(x[:-1], x[1:])
            if (not np.all(np.isfinite(shares)) or not np.all(own > 0)
                    or np.max(np.abs(shares.sum(axis=1)/own - 1)) > CONSERVATIVE_COVERAGE_ROUNDOFF):
                raise NumericalRefusal("amount distribution weight does not partition every source dual")
            factor = Quantity(1, source.unit).magnitude_in(unit)
            mapped = self._values(((values/own) @ shares)*factor)
        integrated = source.placement is StatePlacement.DUAL_CELL_INTEGRATED
        av, bv = (values, mapped) if integrated else (values*va, mapped*vb)
        cq = source.semantics.conserved_quantity
        af = Quantity(1, source.unit if integrated else f"({source.unit})*m").magnitude_in(cq.unit)
        bf = Quantity(1, unit if integrated else f"({unit})*m").magnitude_in(cq.unit)
        ta, tb = math.fsum(float(v)*af for v in av), math.fsum(float(v)*bf for v in bv)
        l1 = math.fsum(abs(float(v)*af) for v in av)
        absolute = abs(ta-tb)
        relative = 0.0 if l1 == 0 and absolute == 0 else absolute/l1 if l1 > 0 else math.inf
        if not all(math.isfinite(v) for v in (ta, tb, l1, absolute, relative)) or relative > CONSERVATIVE_COVERAGE_ROUNDOFF:
            raise NumericalRefusal("actual dual amounts violate declared conservation tolerance")
        target = self._publish(source.name, mapped, source.placement, source.semantics, unit, self._unknown(),
                               source.context_digest, None, (source.record_id, transition.record_id))
        receipt = self._issued.issue(DualTransferReceipt(transition.record_id, source.record_id, target.record_id,
            tuple(map(float, ca)), tuple(map(float, cb)), ta, tb, absolute, relative, cq.unit, source.unit, unit, self._unknown(),
            None if distribution is None else distribution.to_dict()))
        self._consumed.add(key)
        return target, receipt
