"""Coupling convergence over typed scalar and field values.

The residual measured here is the change of one interface between two
iterates (``H(x_k) - x_k`` when the runtime passes the unrelaxed transfer).  It
is an iterate-consistency measure only: it is not the error of the coupled
solution, and it does not establish physical conservation.

Field residuals compare the stored values site by site.  ``l2`` is therefore
the root mean square over stored values, not a mesh-measure-weighted L2 norm;
on a non-uniform support the two differ.  Two fields are compared only on the
same support, location and component count.
"""

from __future__ import annotations

import math
from typing import Mapping

import numpy as np

from ...data.field import FieldValue
from ...data.resolver import BulkDataResolver
from ...scientific.errors import InvalidScientificProblem
from ...scientific.fields import FieldRecord, MeshSupport
from ...scientific.multiphysics import (
    ConvergenceCriterion,
    EdgeResidual,
    ResidualNorm,
)
from ...scientific.units.quantity import Quantity, base_unit
from .participant import CouplingValue


class NonFiniteCouplingResidual(InvalidScientificProblem):
    """A coupling residual or its scale overflowed: the iterate is numerically lost.

    The runtime reports it as a window that failed numerically, never as an
    unconverged-but-acceptable iteration.
    """


class ResidualCalculator:
    def __init__(
        self,
        resolver: BulkDataResolver,
        meshes: Mapping[str, MeshSupport],
    ) -> None:
        self.resolver = resolver
        self.meshes = dict(meshes)

    def _field_array(
        self,
        value: FieldRecord,
        unit: str,
    ) -> np.ndarray:
        mesh = self.meshes.get(value.definition.mesh_id)
        if mesh is None:
            raise InvalidScientificProblem(
                f"no mesh registered for field "
                f"{value.definition.field_id!r}"
            )
        return (
            FieldValue.from_record(
                value, mesh, self.resolver
            )
            .to_unit(unit)
            .values.reshape(-1)
        )

    def compare(
        self,
        criterion: ConvergenceCriterion,
        previous: CouplingValue,
        current: CouplingValue,
        *,
        unit: str,
    ) -> EdgeResidual:
        if isinstance(previous, Quantity) != isinstance(
            current, Quantity
        ):
            raise InvalidScientificProblem(
                "coupling value changed scalar/field kind between iterations"
            )

        comparison_unit = base_unit(unit)
        if isinstance(previous, Quantity):
            old = np.asarray(
                [previous.magnitude_in(comparison_unit)],
                dtype=np.float64,
            )
            new = np.asarray(
                [current.magnitude_in(comparison_unit)],
                dtype=np.float64,
            )
        else:
            before, after = previous.definition, current.definition
            if (
                before.mesh_id != after.mesh_id
                or before.location is not after.location
                or before.components != after.components
            ):
                # equal shapes on two supports are two different fields; a
                # site-by-site difference between them measures nothing
                raise InvalidScientificProblem(
                    f"coupling field on edge {criterion.edge_id!r} changed support "
                    f"between iterations ({before.mesh_id}/{before.location.value}/"
                    f"{before.components} -> {after.mesh_id}/{after.location.value}/"
                    f"{after.components})"
                )
            old = self._field_array(previous, comparison_unit)
            new = self._field_array(current, comparison_unit)
            if old.shape != new.shape:
                raise InvalidScientificProblem(
                    "coupling field changed shape between iterations"
                )

        # overflow is detected below and refused, never silently propagated
        with np.errstate(over="ignore", invalid="ignore"):
            delta = new - old
            if criterion.norm is ResidualNorm.LINF:
                absolute = (
                    float(np.max(np.abs(delta)))
                    if delta.size
                    else 0.0
                )
                scale = (
                    float(np.max(np.abs(new)))
                    if new.size
                    else 0.0
                )
            else:
                absolute = float(
                    np.linalg.norm(delta)
                    / math.sqrt(max(1, delta.size))
                )
                scale = float(
                    np.linalg.norm(new)
                    / math.sqrt(max(1, new.size))
                )

        if not (math.isfinite(absolute) and math.isfinite(scale)):
            raise NonFiniteCouplingResidual(
                f"coupling residual on edge {criterion.edge_id!r} is not finite "
                f"(residual {absolute!r}, scale {scale!r} in {comparison_unit}); "
                f"the iterate overflowed"
            )
        relative = absolute / max(
            scale,
            np.finfo(np.float64).tiny,
        )
        if not math.isfinite(relative):
            raise NonFiniteCouplingResidual(
                f"relative coupling residual on edge {criterion.edge_id!r} overflowed "
                f"(residual {absolute!r} over scale {scale!r})"
            )
        absolute_limit = (
            criterion.absolute_tolerance.magnitude_as_spread_in(
                comparison_unit
            )
        )
        # bool(): a unit conversion may yield a NumPy scalar, whose comparison
        # is numpy.bool_ -- the residual record requires a Python bool.
        satisfied = bool(
            absolute <= absolute_limit
            or relative <= criterion.relative_tolerance
        )
        return EdgeResidual(
            edge_id=criterion.edge_id,
            absolute=Quantity(absolute, comparison_unit),
            relative=relative,
            norm=criterion.norm.value,
            satisfied=satisfied,
        )
