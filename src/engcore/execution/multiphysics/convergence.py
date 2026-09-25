"""Coupling convergence over typed scalar and field values."""

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
            old = self._field_array(previous, comparison_unit)
            new = self._field_array(current, comparison_unit)
            if old.shape != new.shape:
                raise InvalidScientificProblem(
                    "coupling field changed shape between iterations"
                )

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

        relative = absolute / max(
            scale,
            np.finfo(np.float64).tiny,
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
