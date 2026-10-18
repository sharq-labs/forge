"""Declared scalar 1D overlap transfer; no transient solver or A-4 execution."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from ..execution.multiphysics.cell_mapping import remap_cells, conservation_totals
from ..execution.multiphysics.mapping import CONSERVATIVE_COVERAGE_ROUNDOFF
from ..scientific.errors import InvalidScientificProblem
from ..scientific.fields.semantics import FieldKind, FieldSemantics
from ..scientific.multiphysics.mapping import MappingDiagnostics
from ..scientific.results.uncertainty import Uncertainty
from ..scientific.units.quantity import Quantity, dimensionality, is_ratio_scale
from .mesh_adaptation import Grid1D


@dataclass(frozen=True)
class CellMapping1DResult:
    values: tuple[float, ...]
    diagnostics: MappingDiagnostics
    uncertainty: Uncertainty


def map_cells_1d(values, source: Grid1D, target: Grid1D, *, source_semantics: FieldSemantics,
                 target_semantics: FieldSemantics, source_unit: str, target_unit: str,
                 source_fingerprint: str, target_fingerprint: str, coordinate_frame: str) -> CellMapping1DResult:
    """Map on one declared common axis, refusing dropped or extrapolated cells.

    Supplied grid digests must match the grids. Origin of the supplied values
    remains caller-owned; these checks do not authenticate values or lineage.
    Decreasing axes/normal sign execution are unsupported, never silently reversed.
    Values remain the caller's declared field; matching labels do not verify physics.
    """
    if not isinstance(source, Grid1D) or not isinstance(target, Grid1D):
        raise InvalidScientificProblem("1D mapping requires declared Grid1D supports")
    if not isinstance(coordinate_frame, str) or not coordinate_frame.strip():
        raise InvalidScientificProblem("1D mapping requires one explicit common coordinate frame")
    if source_fingerprint != source.digest or target_fingerprint != target.digest:
        raise InvalidScientificProblem("stale 1D support identity")
    if not isinstance(source_semantics, FieldSemantics) or not isinstance(target_semantics, FieldSemantics):
        raise InvalidScientificProblem("1D mapping requires declared field kind semantics")
    source_semantics.require_cell_mapping(target_semantics, 1)
    for grid in (source, target):
        if not is_ratio_scale(grid.unit) or dimensionality(grid.unit) != dimensionality("m"):
            raise InvalidScientificProblem("1D support coordinates require ratio-scale length units")
    for unit in (source_unit, target_unit):
        if dimensionality(unit) != dimensionality(source_semantics.quantity.unit):
            raise InvalidScientificProblem("value units do not match field quantity semantics")
        if source_semantics.kind is not FieldKind.INTENSIVE and not is_ratio_scale(unit):
            raise InvalidScientificProblem("conserved fields require ratio-scale units")
    a = np.asarray([Quantity(x, source.unit).magnitude_in("m") for x in source.nodes])
    b = np.asarray([Quantity(x, target.unit).magnitude_in("m") for x in target.nodes])
    va, vb = np.diff(a), np.diff(b)
    overlap = np.maximum(0, np.minimum(a[1:, None], b[None, 1:]) - np.maximum(a[:-1, None], b[None, :-1]))
    if (np.any(np.abs(overlap.sum(axis=1)/va-1) > CONSERVATIVE_COVERAGE_ROUNDOFF)
            or np.any(np.abs(overlap.sum(axis=0)/vb-1) > CONSERVATIVE_COVERAGE_ROUNDOFF)):
        raise InvalidScientificProblem("partial coverage: source and target must cover each other; no extrapolation")
    raw = np.asarray(values, dtype=float)
    if raw.shape != va.shape or not np.all(np.isfinite(raw)):
        raise InvalidScientificProblem("1D values must be finite scalar cells of the declared support")
    zero = Quantity(0, source_unit).magnitude_in(target_unit)
    scale = Quantity(1, source_unit).magnitude_in(target_unit)-zero
    converted = (raw * scale + zero)[:, None]
    kind = source_semantics.kind
    mapped, _ = remap_cells(converted, overlap, va, vb, kind)
    totals = conservation_totals(converted, mapped, va, vb, kind)
    raw_unit = target_unit if kind is FieldKind.CELL_INTEGRATED else f"({target_unit}) * m"
    conservation = {}
    if totals is not None:
        before, after, residual, l1, relative = totals
        unit = source_semantics.conserved_quantity.unit
        factor = Quantity(1, raw_unit).magnitude_in(unit)
        conservation = {"source_total": float(before[0]*factor), "target_total": float(after[0]*factor),
                        "absolute_residual": float(residual[0]*factor), "scale_l1": float(l1[0]*factor),
                        "conserved_unit": unit}
    diagnostics = MappingDiagnostics(
        mapping_id="declared_cells_1d", source_count=len(va), target_count=len(vb),
        extrapolated_count=0, coverage_fraction=1.0, round_trip_relative_l2=None,
        conservation_relative_error=None if totals is None else totals[-1],
        provenance={"method": "exact_interval_overlap", "field_semantics": source_semantics.to_dict(),
                    "source_support": source.digest, "target_support": target.digest,
                    "coordinate_frame": coordinate_frame, "orientation": "increasing_common_axis",
                    "source_unit": source_unit, "target_unit": target_unit,
                    "coverage_roundoff_allowance": CONSERVATIVE_COVERAGE_ROUNDOFF,
                    "notice": "piecewise-constant transfer; conservation is not local physical validity or an error bound",
                    **conservation})
    return CellMapping1DResult(tuple(float(x) for x in mapped[:, 0]), diagnostics,
                              Uncertainty.unknown("spatial transfer error and model discrepancy are unquantified"))
