"""Normalizer for NASA Ames PCoE Li-ion battery aging MAT files."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Mapping as TypingMapping

import numpy as np
from scipy.io import loadmat

from .catalog import NASA_BATTERY_AGING
from .contracts import (
    ReferenceCondition,
    ReferenceDataset,
    ReferencePoint,
    ToleranceSpec,
)
from .snapshot import SnapshotManifest


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _array(obj: Any, name: str) -> np.ndarray:
    value = _get(obj, name)
    if value is None:
        return np.asarray([], dtype=float)
    return np.asarray(value).reshape(-1)


def _root_with_cycles(mat: Mapping[str, Any]) -> Any:
    candidates = [
        value
        for key, value in mat.items()
        if not key.startswith("__") and _get(value, "cycle") is not None
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"expected exactly one NASA battery root carrying cycles, found {len(candidates)}"
        )
    return candidates[0]


def _condition_tuple(
    *,
    cycle_index: int,
    ambient_temperature_c: float | None,
    elapsed_time_s: float | None = None,
    load_current_a: float | None = None,
) -> tuple[ReferenceCondition, ...]:
    values = [ReferenceCondition("cycle_index", float(cycle_index), "dimensionless")]
    if ambient_temperature_c is not None and np.isfinite(ambient_temperature_c):
        values.append(
            ReferenceCondition("ambient_temperature", ambient_temperature_c, "degC")
        )
    if elapsed_time_s is not None and np.isfinite(elapsed_time_s):
        values.append(ReferenceCondition("elapsed_time", elapsed_time_s, "second"))
    if load_current_a is not None and np.isfinite(load_current_a):
        values.append(ReferenceCondition("load_current", load_current_a, "ampere"))
    return tuple(values)


def parse_nasa_battery_mat(
    path: str,
    manifest: SnapshotManifest,
    *,
    dataset_id: str,
    dataset_version: str,
    tolerance_by_metric: TypingMapping[str, ToleranceSpec] | None = None,
    include_discharge: bool = True,
    include_impedance: bool = True,
) -> ReferenceDataset:
    """Extract measured outputs while keeping measured load as a condition.

    Charge cycles are intentionally excluded from the first campaign because
    the existing Forge battery vertical is discharge-oriented. Unsupported
    source records are skipped explicitly rather than counted as validation.
    """
    mat = loadmat(path, squeeze_me=True, struct_as_record=False)
    root = _root_with_cycles(mat)
    cycles = np.atleast_1d(_get(root, "cycle"))
    tolerances = dict(tolerance_by_metric or {})
    points: list[ReferencePoint] = []

    for cycle_index, cycle in enumerate(cycles):
        cycle_type = str(_get(cycle, "type", "")).strip().lower()
        ambient_raw = _get(cycle, "ambient_temperature")
        ambient = (
            None
            if ambient_raw is None
            else float(np.asarray(ambient_raw).reshape(-1)[0])
        )
        data = _get(cycle, "data")
        if data is None:
            continue

        if cycle_type == "discharge" and include_discharge:
            time = _array(data, "Time")
            voltage = _array(data, "Voltage_measured")
            temperature = _array(data, "Temperature_measured")
            current = _array(data, "Current_measured")
            nonempty_lengths = [
                arr.size for arr in (time, voltage, temperature) if arr.size
            ]
            sample_count = min(nonempty_lengths) if nonempty_lengths else 0

            for sample_index in range(sample_count):
                elapsed = float(time[sample_index]) if sample_index < time.size else None
                load = float(current[sample_index]) if sample_index < current.size else None
                conditions = _condition_tuple(
                    cycle_index=cycle_index,
                    ambient_temperature_c=ambient,
                    elapsed_time_s=elapsed,
                    load_current_a=load,
                )
                if sample_index < voltage.size:
                    points.append(
                        ReferencePoint(
                            case_id=f"{dataset_id}:cycle:{cycle_index}:sample:{sample_index}",
                            metric="battery.terminal_voltage",
                            expected_value=float(voltage[sample_index]),
                            expected_unit="volt",
                            conditions=conditions,
                            acceptance_tolerance=tolerances.get("battery.terminal_voltage"),
                            tags=("nasa", "discharge"),
                        )
                    )
                if sample_index < temperature.size:
                    points.append(
                        ReferencePoint(
                            case_id=f"{dataset_id}:cycle:{cycle_index}:sample:{sample_index}",
                            metric="battery.cell_temperature",
                            expected_value=float(temperature[sample_index]),
                            expected_unit="degC",
                            conditions=conditions,
                            acceptance_tolerance=tolerances.get("battery.cell_temperature"),
                            tags=("nasa", "discharge"),
                        )
                    )

            capacity = _array(data, "Capacity")
            if capacity.size:
                points.append(
                    ReferencePoint(
                        case_id=f"{dataset_id}:cycle:{cycle_index}:capacity",
                        metric="battery.discharge_capacity",
                        expected_value=float(np.real(capacity.reshape(-1)[0])),
                        expected_unit="ampere_hour",
                        conditions=_condition_tuple(
                            cycle_index=cycle_index,
                            ambient_temperature_c=ambient,
                        ),
                        acceptance_tolerance=tolerances.get("battery.discharge_capacity"),
                        tags=("nasa", "discharge", "capacity"),
                    )
                )

        elif cycle_type == "impedance" and include_impedance:
            for source_name, metric in (
                ("Re", "battery.electrolyte_resistance"),
                ("Rct", "battery.charge_transfer_resistance"),
            ):
                values = _array(data, source_name)
                if not values.size:
                    continue
                value = float(np.real(values.reshape(-1)[0]))
                points.append(
                    ReferencePoint(
                        case_id=f"{dataset_id}:cycle:{cycle_index}:{source_name}",
                        metric=metric,
                        expected_value=value,
                        expected_unit="ohm",
                        conditions=_condition_tuple(
                            cycle_index=cycle_index,
                            ambient_temperature_c=ambient,
                        ),
                        acceptance_tolerance=tolerances.get(metric),
                        tags=("nasa", "impedance"),
                    )
                )

    if not points:
        raise ValueError(
            "NASA MAT file produced no supported discharge/impedance observations"
        )
    return ReferenceDataset(
        dataset_id=dataset_id,
        version=dataset_version,
        source=NASA_BATTERY_AGING,
        source_snapshot_sha256=manifest.sha256,
        source_snapshot_url=manifest.resolved_url,
        points=tuple(points),
        metadata={
            "source_manifest_retrieved_at_utc": manifest.retrieved_at_utc,
            "cycle_count": int(len(cycles)),
        },
    )


__all__ = ["NASA_BATTERY_ARCHIVE_URL", "parse_nasa_battery_mat"]
