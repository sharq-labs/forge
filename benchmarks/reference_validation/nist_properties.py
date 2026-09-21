"""Normalizer for NIST SRD 69 thermophysical-property table exports.

The parser accepts tab/comma separated table exports already acquired as an
immutable snapshot. It never assigns a validation tolerance implicitly.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Mapping, Sequence

from .catalog import NIST_SRD69
from .contracts import (
    ReferenceCondition,
    ReferenceDataset,
    ReferencePoint,
    ToleranceSpec,
)
from .snapshot import SnapshotManifest

_HEADER_UNIT = re.compile(
    r"^\s*(?P<name>.*?)\s*(?:\((?P<paren>[^()]*)\)|\[(?P<bracket>[^\[\]]*)\])?\s*$"
)

_PROPERTY_ALIASES = (
    ("density", "thermo.density"),
    ("specific volume", "thermo.specific_volume"),
    ("cp", "thermo.cp"),
    ("cv", "thermo.cv"),
    ("enthalpy", "thermo.enthalpy"),
    ("internal energy", "thermo.internal_energy"),
    ("entropy", "thermo.entropy"),
    ("viscosity", "thermo.viscosity"),
    ("thermal conductivity", "thermo.thermal_conductivity"),
    ("speed of sound", "thermo.speed_of_sound"),
    ("surface tension", "thermo.surface_tension"),
    ("joule-thomson", "thermo.joule_thomson"),
)

_CONDITION_ALIASES = {"temperature": "temperature", "pressure": "pressure"}


def _split_header(header: str) -> tuple[str, str | None]:
    match = _HEADER_UNIT.match(header)
    if not match:
        return header.strip(), None
    name = (match.group("name") or "").strip()
    unit = (match.group("paren") or match.group("bracket") or "").strip() or None
    return name, unit


def _metric_for(name: str) -> str | None:
    normalized = " ".join(name.lower().replace("_", " ").split())
    for alias, metric in _PROPERTY_ALIASES:
        if normalized == alias or normalized.startswith(alias + " "):
            return metric
    return None


def _condition_for(name: str) -> str | None:
    normalized = " ".join(name.lower().replace("_", " ").split())
    for alias, condition in _CONDITION_ALIASES.items():
        if normalized == alias or normalized.startswith(alias + " "):
            return condition
    return None


def parse_nist_srd69_table(
    payload: bytes | str,
    manifest: SnapshotManifest,
    *,
    dataset_id: str,
    dataset_version: str,
    delimiter: str | None = None,
    unit_overrides: Mapping[str, str] | None = None,
    tolerance_by_metric: Mapping[str, ToleranceSpec] | None = None,
    tags: Sequence[str] = (),
    phase_filter: str | None = None,
) -> ReferenceDataset:
    """Normalize one SRD 69 table export into point-wise reference records."""
    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else str(payload)
    if delimiter is None:
        delimiter = "\t" if "\t" in text.partition("\n")[0] else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("NIST table has no header")

    overrides = {str(k): str(v) for k, v in (unit_overrides or {}).items()}
    tolerances = dict(tolerance_by_metric or {})
    columns: list[tuple[str, str, str | None]] = []
    for raw in reader.fieldnames:
        name, declared_unit = _split_header(raw)
        columns.append((raw, name, overrides.get(raw) or declared_unit))

    points: list[ReferencePoint] = []
    row_count = 0
    for row_index, row in enumerate(reader, start=1):
        row_count = row_index
        conditions: list[ReferenceCondition] = []
        phase = ""
        for raw, name, unit in columns:
            condition_name = _condition_for(name)
            if condition_name is not None:
                cell = str(row.get(raw, "") or "").strip()
                if not cell:
                    continue
                if unit is None:
                    raise ValueError(
                        f"NIST condition column {raw!r} has no unit; provide unit_overrides"
                    )
                conditions.append(ReferenceCondition(condition_name, float(cell), unit))
            elif name.strip().lower() == "phase":
                phase = str(row.get(raw, "") or "").strip()

        if phase_filter is not None and phase.lower() != phase_filter.strip().lower():
            continue

        for raw, name, unit in columns:
            metric = _metric_for(name)
            if metric is None:
                continue
            cell = str(row.get(raw, "") or "").strip()
            if not cell:
                continue
            if unit is None:
                raise ValueError(
                    f"NIST property column {raw!r} has no unit; provide unit_overrides"
                )
            point_tags = tuple(tags) + ((f"phase:{phase}",) if phase else ())
            points.append(
                ReferencePoint(
                    case_id=f"{dataset_id}:row:{row_index}",
                    metric=metric,
                    expected_value=float(cell),
                    expected_unit=unit,
                    conditions=tuple(conditions),
                    acceptance_tolerance=tolerances.get(metric),
                    tags=point_tags,
                    note=f"NIST SRD 69 column {raw!r}",
                )
            )

    if not points:
        raise ValueError("NIST table produced no supported property observations")
    return ReferenceDataset(
        dataset_id=dataset_id,
        version=dataset_version,
        source=NIST_SRD69,
        source_snapshot_sha256=manifest.sha256,
        source_snapshot_url=manifest.resolved_url,
        points=tuple(points),
        metadata={
            "source_manifest_retrieved_at_utc": manifest.retrieved_at_utc,
            "row_count": row_count,
            "phase_filter": phase_filter,
        },
    )


__all__ = ["parse_nist_srd69_table"]
