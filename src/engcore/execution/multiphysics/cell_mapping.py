"""Shared declared-kind arithmetic after geometry and coverage admission.

Internal kernel: callers own qualified intersections, support identity and units.
No integral diagnostic establishes local physical validity or numerical error.
"""
from __future__ import annotations

import numpy as np

from ...scientific.errors import InvalidScientificProblem
from ...scientific.fields.semantics import FieldKind


def remap_cells(values, overlap, source_measures, target_measures, kind):
    """Return target values and same-kind reverse values for scalar columns."""
    if kind not in (FieldKind.CELL_AVERAGE_DENSITY, FieldKind.CELL_INTEGRATED, FieldKind.INTENSIVE):
        raise InvalidScientificProblem("unsupported declared field kind; interface execution requires A-4")
    if (not np.all(np.isfinite(source_measures)) or not np.all(source_measures > 0)
            or not np.all(np.isfinite(target_measures)) or not np.all(target_measures > 0)
            or not np.all(np.isfinite(values))):
        raise InvalidScientificProblem("mapping requires finite values and positive finite cell measures")
    if kind is FieldKind.CELL_INTEGRATED:
        mapped = np.asarray(overlap.T @ (values / source_measures[:, None]))
        reverse = np.asarray(overlap @ (mapped / target_measures[:, None]))
    else:
        mapped = np.asarray(overlap.T @ values) / target_measures[:, None]
        reverse = np.asarray(overlap @ mapped) / source_measures[:, None]
    if not np.all(np.isfinite(mapped)) or not np.all(np.isfinite(reverse)):
        raise InvalidScientificProblem("mapping produced non-finite values")
    return mapped, reverse


def conservation_totals(values, mapped, source_measures, target_measures, kind):
    """Raw totals in value-unit times canonical measure (or value-unit for amounts)."""
    if kind is FieldKind.INTENSIVE:
        return None
    source_amounts = values if kind is FieldKind.CELL_INTEGRATED else values * source_measures[:, None]
    target_amounts = mapped if kind is FieldKind.CELL_INTEGRATED else mapped * target_measures[:, None]
    before, after = source_amounts.sum(axis=0), target_amounts.sum(axis=0)
    scale = np.abs(source_amounts).sum(axis=0)
    residual = np.abs(after-before)
    relative = np.divide(residual, scale, out=np.zeros_like(residual), where=scale > 0)
    if not all(np.all(np.isfinite(x)) for x in (before, after, scale, residual, relative)):
        raise InvalidScientificProblem("non-finite conservation diagnostics")
    if np.any((scale == 0) & (residual != 0)):
        raise InvalidScientificProblem("nonzero residual with zero source magnitude")
    return before, after, residual, scale, float(np.max(relative))
