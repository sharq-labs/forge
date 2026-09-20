"""Normalizer for reviewed NIST SRD 17 chemical-kinetics exports.

The public SRD 17 interface is HTML/session oriented. Acquisition therefore
produces a reviewed normalized CSV rather than scraping live pages during a
scientific run. ``rate_unit`` in that CSV must already be converted to a
Pint/Forge-compatible unit string while the original source record remains
identified by ``record_id`` and ``reaction``.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from typing import Mapping

from .catalog import NIST_CHEMICAL_KINETICS
from .contracts import (
    ReferenceCondition,
    ReferenceDataset,
    ReferencePoint,
    ToleranceSpec,
)
from .snapshot import SnapshotManifest

R_J_PER_MOL_K = 8.314472


@dataclass(frozen=True)
class NISTArrheniusRecord:
    record_id: str
    reaction: str
    reaction_order: float
    pre_exponential_a: float
    temperature_exponent_n: float
    activation_energy_j_per_mol: float
    temperature_k: float
    reported_k: float
    rate_unit: str
    data_type: str
    uncertainty_fraction: float | None = None

    def reconstructed_k(self) -> float:
        return (
            self.pre_exponential_a
            * (self.temperature_k / 298.0) ** self.temperature_exponent_n
            * math.exp(
                -self.activation_energy_j_per_mol
                / (R_J_PER_MOL_K * self.temperature_k)
            )
        )


_REQUIRED = (
    "record_id",
    "reaction",
    "order",
    "A",
    "n",
    "Ea_J_per_mol",
    "temperature_K",
    "reported_k",
    "rate_unit",
    "data_type",
)


def parse_normalized_nist_kinetics_csv(
    payload: bytes | str,
    manifest: SnapshotManifest,
    *,
    dataset_id: str,
    dataset_version: str,
    tolerance_by_metric: Mapping[str, ToleranceSpec] | None = None,
) -> tuple[ReferenceDataset, tuple[NISTArrheniusRecord, ...]]:
    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else str(payload)
    reader = csv.DictReader(io.StringIO(text))
    missing = [name for name in _REQUIRED if name not in (reader.fieldnames or ())]
    if missing:
        raise ValueError(f"normalized NIST kinetics export is missing columns: {missing}")

    tolerances = dict(tolerance_by_metric or {})
    points: list[ReferencePoint] = []
    records: list[NISTArrheniusRecord] = []
    for row in reader:
        uncertainty_text = str(row.get("uncertainty_fraction", "") or "").strip()
        uncertainty = float(uncertainty_text) if uncertainty_text else None
        if uncertainty is not None and (
            not math.isfinite(uncertainty) or uncertainty < 0.0
        ):
            raise ValueError("uncertainty_fraction must be finite and non-negative")
        record = NISTArrheniusRecord(
            record_id=str(row["record_id"]).strip(),
            reaction=str(row["reaction"]).strip(),
            reaction_order=float(row["order"]),
            pre_exponential_a=float(row["A"]),
            temperature_exponent_n=float(row["n"]),
            activation_energy_j_per_mol=float(row["Ea_J_per_mol"]),
            temperature_k=float(row["temperature_K"]),
            reported_k=float(row["reported_k"]),
            rate_unit=str(row["rate_unit"]).strip(),
            data_type=str(row["data_type"]).strip().lower(),
            uncertainty_fraction=uncertainty,
        )
        numeric_values = (
            record.reaction_order,
            record.pre_exponential_a,
            record.temperature_exponent_n,
            record.activation_energy_j_per_mol,
            record.temperature_k,
            record.reported_k,
        )
        if not all(math.isfinite(value) for value in numeric_values):
            raise ValueError(f"NIST kinetics record {record.record_id!r} is non-finite")
        if not record.record_id or not record.reaction or not record.rate_unit:
            raise ValueError("NIST kinetics record requires id, reaction and rate_unit")
        if record.temperature_k <= 0.0:
            raise ValueError("NIST kinetics temperature must be positive")

        source_uncertainty = None
        if uncertainty is not None:
            source_uncertainty = ToleranceSpec(
                abs(record.reported_k) * uncertainty,
                record.rate_unit,
                "record-level relative uncertainty from normalized SRD 17 source",
            )
        metric = "kinetics.rate_constant"
        points.append(
            ReferencePoint(
                case_id=f"{dataset_id}:record:{record.record_id}",
                metric=metric,
                expected_value=record.reported_k,
                expected_unit=record.rate_unit,
                conditions=(
                    ReferenceCondition("temperature", record.temperature_k, "kelvin"),
                    ReferenceCondition(
                        "reaction_order", record.reaction_order, "dimensionless"
                    ),
                ),
                source_uncertainty=source_uncertainty,
                acceptance_tolerance=tolerances.get(metric),
                tags=(
                    "nist_srd17",
                    f"data_type:{record.data_type or 'unknown'}",
                    f"reaction:{record.reaction}",
                ),
                note=(
                    "normalized SRD 17 record; the broad source contains mixed "
                    "experimental/theoretical/evaluated records"
                ),
            )
        )
        records.append(record)

    if not points:
        raise ValueError("normalized NIST kinetics export contains no records")
    reactions = {record.reaction for record in records}
    if len(reactions) != 1:
        raise ValueError(
            "one promoted kinetics dataset must describe exactly one reaction; "
            "split the normalized export by reaction before validation"
        )
    dataset = ReferenceDataset(
        dataset_id=dataset_id,
        version=dataset_version,
        source=NIST_CHEMICAL_KINETICS,
        source_snapshot_sha256=manifest.sha256,
        source_snapshot_url=manifest.resolved_url,
        points=tuple(points),
        metadata={
            "source_manifest_retrieved_at_utc": manifest.retrieved_at_utc,
            "record_count": len(records),
            "reaction": next(iter(reactions)),
        },
    )
    return dataset, tuple(records)


def arrhenius_reconstruction_error(record: NISTArrheniusRecord) -> float:
    reconstructed = record.reconstructed_k()
    scale = abs(record.reported_k)
    if scale == 0.0:
        return abs(reconstructed - record.reported_k)
    return abs(reconstructed - record.reported_k) / scale


__all__ = [
    "NISTArrheniusRecord",
    "R_J_PER_MOL_K",
    "arrhenius_reconstruction_error",
    "parse_normalized_nist_kinetics_csv",
]
