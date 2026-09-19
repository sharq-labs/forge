"""Curated measurement-dataset contracts.

A public dataset is not automatically evidence. This module records where a
measurement dataset came from, which columns were observed, and what context is
still missing before one row may become a :class:`MeasurementRecord`.

The fail-closed rule is deliberate: a dataset row with no calibrated
measurement uncertainty or incomplete operating context remains a dataset
observation. It cannot be handed to the claim assessor as admissible
measurement evidence by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..scientific.results.uncertainty import Uncertainty, UncertaintySource
from ..scientific.serialization import schema_string
from ..scientific.units.quantity import Quantity
from ._records import require_bool, require_keys, require_mapping, require_schema_exact, require_text, tagged_digest
from .capabilities import CapabilityDeclaration, InputRole
from .errors import ClaimContractError
from .external_evidence import MeasurementRecord

MEASUREMENT_DATASET_SCHEMA = schema_string("claim_measurement_dataset_manifest")
_DATASET_TAG = "crafty.claims.measurement_dataset/1"


class MeasurementDatasetError(ClaimContractError):
    """A dataset row cannot be interpreted without inventing scientific facts."""


class DatasetSplit(str, Enum):
    CALIBRATION = "calibration"
    VALIDATION = "validation"


@dataclass(frozen=True)
class MeasurementDatasetManifest:
    dataset_id: str
    title: str
    publisher: str
    citation: str
    landing_page: str
    resource_url: str
    license_url: str
    version: str
    catalog_source_hash: str
    columns: tuple[str, ...]
    value_columns: Mapping[str, tuple[str, str]]
    condition_columns: Mapping[str, tuple[str, str]]
    independence_unit: str
    measurement_uncertainty_declared: bool
    notes: str = ""

    def __post_init__(self) -> None:
        for label in (
            "dataset_id", "title", "publisher", "citation", "landing_page",
            "resource_url", "license_url", "version", "catalog_source_hash",
            "independence_unit",
        ):
            object.__setattr__(self, label, require_text(getattr(self, label), field=f"dataset.{label}"))
        columns = tuple(require_text(c, field="dataset.column") for c in self.columns)
        if len(set(columns)) != len(columns):
            raise MeasurementDatasetError("dataset columns must be unique")
        object.__setattr__(self, "columns", columns)
        values = {
            require_text(name, field="dataset.value quantity"): (
                require_text(spec[0], field=f"dataset.value_columns.{name}.column"),
                require_text(spec[1], field=f"dataset.value_columns.{name}.unit"),
            )
            for name, spec in dict(self.value_columns).items()
        }
        conditions = {
            require_text(path, field="dataset.condition path"): (
                require_text(spec[0], field=f"dataset.condition_columns.{path}.column"),
                require_text(spec[1], field=f"dataset.condition_columns.{path}.unit"),
            )
            for path, spec in dict(self.condition_columns).items()
        }
        referenced = {column for column, _ in (*values.values(), *conditions.values())}
        missing = sorted(referenced - set(columns))
        if missing:
            raise MeasurementDatasetError(f"dataset mappings reference columns not declared by the manifest: {missing}")
        if len(self.catalog_source_hash) != 64 or any(ch not in "0123456789abcdef" for ch in self.catalog_source_hash.lower()):
            raise MeasurementDatasetError("catalog_source_hash must be a 64-character hexadecimal SHA-256")
        object.__setattr__(self, "value_columns", dict(sorted(values.items())))
        object.__setattr__(self, "condition_columns", dict(sorted(conditions.items())))
        require_bool(
            self.measurement_uncertainty_declared,
            field="dataset.measurement_uncertainty_declared",
            error=MeasurementDatasetError,
        )
        object.__setattr__(self, "notes", str(self.notes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MEASUREMENT_DATASET_SCHEMA,
            "dataset_id": self.dataset_id,
            "title": self.title,
            "publisher": self.publisher,
            "citation": self.citation,
            "landing_page": self.landing_page,
            "resource_url": self.resource_url,
            "license_url": self.license_url,
            "version": self.version,
            "catalog_source_hash": self.catalog_source_hash,
            "columns": list(self.columns),
            "value_columns": {k: {"column": c, "unit": u} for k, (c, u) in self.value_columns.items()},
            "condition_columns": {k: {"column": c, "unit": u} for k, (c, u) in self.condition_columns.items()},
            "independence_unit": self.independence_unit,
            "measurement_uncertainty_declared": self.measurement_uncertainty_declared,
            "notes": self.notes,
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_DATASET_TAG, self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MeasurementDatasetManifest":
        payload = require_mapping(payload, field="measurement dataset")
        required = (
            "schema", "dataset_id", "title", "publisher", "citation", "landing_page",
            "resource_url", "license_url", "version", "catalog_source_hash", "columns",
            "value_columns", "condition_columns", "independence_unit",
            "measurement_uncertainty_declared", "notes",
        )
        require_keys(payload, required=required, record="measurement dataset")
        require_schema_exact(payload, MEASUREMENT_DATASET_SCHEMA, record="measurement dataset")
        values = {
            name: (spec["column"], spec["unit"])
            for name, spec in require_mapping(payload["value_columns"], field="value_columns").items()
        }
        conditions = {
            path: (spec["column"], spec["unit"])
            for path, spec in require_mapping(payload["condition_columns"], field="condition_columns").items()
        }
        return cls(
            payload["dataset_id"], payload["title"], payload["publisher"], payload["citation"],
            payload["landing_page"], payload["resource_url"], payload["license_url"],
            payload["version"], payload["catalog_source_hash"], tuple(payload["columns"]),
            values, conditions, payload["independence_unit"],
            payload["measurement_uncertainty_declared"], payload["notes"],
        )


@dataclass(frozen=True)
class DatasetObservation:
    """One row interpreted without upgrading it into evidence."""

    manifest_digest: str
    observation_id: str
    independence_group: str
    split: DatasetSplit
    quantity: str
    value: Quantity
    conditions: Mapping[str, Quantity]
    uncertainty: Uncertainty
    calibration_ref: str | None
    provenance_ref: str
    dataset_version: str
    observed_at: str | None
    missing_context: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifest_digest", require_text(self.manifest_digest, field="observation.manifest_digest"))
        object.__setattr__(self, "observation_id", require_text(self.observation_id, field="observation.observation_id"))
        object.__setattr__(self, "independence_group", require_text(self.independence_group, field="observation.independence_group"))
        object.__setattr__(self, "split", DatasetSplit(self.split))
        object.__setattr__(self, "quantity", require_text(self.quantity, field="observation.quantity"))
        if not isinstance(self.value, Quantity):
            raise MeasurementDatasetError("observation.value must be a Quantity")
        if not isinstance(self.uncertainty, Uncertainty):
            raise MeasurementDatasetError("observation.uncertainty must be an Uncertainty")
        conditions = dict(self.conditions)
        bad = sorted(path for path, value in conditions.items() if not isinstance(value, Quantity))
        if bad:
            raise MeasurementDatasetError(f"observation conditions must be Quantity records: {bad}")
        object.__setattr__(self, "conditions", dict(sorted(conditions.items())))
        object.__setattr__(self, "missing_context", tuple(sorted(set(self.missing_context))))

    @property
    def ready_for_measurement_evidence(self) -> bool:
        return (
            not self.missing_context
            and self.uncertainty.is_quantified
            and UncertaintySource(self.uncertainty.source_kind) is UncertaintySource.MEASUREMENT
            and bool(self.calibration_ref)
        )

    def to_measurement_record(self) -> MeasurementRecord:
        if self.missing_context:
            raise MeasurementDatasetError(
                f"observation {self.observation_id!r} is missing exact operating context {list(self.missing_context)}"
            )
        if not self.uncertainty.is_quantified:
            raise MeasurementDatasetError(
                f"observation {self.observation_id!r} has no quantified measurement uncertainty; UNKNOWN is not zero"
            )
        if UncertaintySource(self.uncertainty.source_kind) is not UncertaintySource.MEASUREMENT:
            raise MeasurementDatasetError("dataset observation uncertainty must be attributed to MEASUREMENT")
        if not self.calibration_ref:
            raise MeasurementDatasetError("dataset observation needs a calibration reference before it can become evidence")
        return MeasurementRecord(
            quantity=self.quantity,
            value=self.value,
            uncertainty=self.uncertainty,
            calibration_ref=self.calibration_ref,
            provenance_ref=self.provenance_ref,
            conditions=self.conditions,
            dataset_version=self.dataset_version,
            observed_at=self.observed_at,
            independence_roots=(self.independence_group, self.provenance_ref),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_digest": self.manifest_digest,
            "observation_id": self.observation_id,
            "independence_group": self.independence_group,
            "split": self.split.value,
            "quantity": self.quantity,
            "value": self.value.to_dict(),
            "conditions": {k: v.to_dict() for k, v in self.conditions.items()},
            "uncertainty": self.uncertainty.to_dict(),
            "calibration_ref": self.calibration_ref,
            "provenance_ref": self.provenance_ref,
            "dataset_version": self.dataset_version,
            "observed_at": self.observed_at,
            "missing_context": list(self.missing_context),
            "ready_for_measurement_evidence": self.ready_for_measurement_evidence,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DatasetObservation":
        if not isinstance(payload, Mapping):
            raise MeasurementDatasetError("dataset observation must be an object")
        required = {
            "manifest_digest", "observation_id", "independence_group", "split",
            "quantity", "value", "conditions", "uncertainty", "calibration_ref",
            "provenance_ref", "dataset_version", "observed_at", "missing_context",
            "ready_for_measurement_evidence",
        }
        if set(payload) != required:
            raise MeasurementDatasetError(
                f"dataset observation shape mismatch: "
                f"missing={sorted(required-set(payload))}, "
                f"extra={sorted(set(payload)-required)}"
            )
        item = cls(
            manifest_digest=payload["manifest_digest"],
            observation_id=payload["observation_id"],
            independence_group=payload["independence_group"],
            split=DatasetSplit(payload["split"]),
            quantity=payload["quantity"],
            value=Quantity.from_dict(payload["value"]),
            conditions={
                path: Quantity.from_dict(value)
                for path, value in dict(payload["conditions"]).items()
            },
            uncertainty=Uncertainty.from_dict(payload["uncertainty"]),
            calibration_ref=payload["calibration_ref"],
            provenance_ref=payload["provenance_ref"],
            dataset_version=payload["dataset_version"],
            observed_at=payload["observed_at"],
            missing_context=tuple(payload["missing_context"]),
        )
        if bool(payload["ready_for_measurement_evidence"]) != item.ready_for_measurement_evidence:
            raise MeasurementDatasetError(
                "dataset observation's derived readiness flag does not match its contents"
            )
        return item


def required_physical_context(declaration: CapabilityDeclaration) -> tuple[str, ...]:
    """Required non-identity, non-numerical inputs that bind a real-world comparison."""
    return tuple(sorted(
        item.path
        for item in declaration.inputs
        if item.required and item.role not in (InputRole.IDENTITY, InputRole.NUMERICS)
    ))


def observation_from_row(
    manifest: MeasurementDatasetManifest,
    row: Mapping[str, Any],
    *,
    observation_id: str,
    independence_group: str,
    split: DatasetSplit,
    quantity: str,
    required_context: tuple[str, ...],
    context_overrides: Mapping[str, Quantity] | None = None,
    uncertainty: Uncertainty | None = None,
    calibration_ref: str | None = None,
    provenance_ref: str,
    observed_at: str | None = None,
) -> DatasetObservation:
    row = dict(row)
    missing_columns = sorted(set(manifest.columns) - set(row))
    if missing_columns:
        raise MeasurementDatasetError(f"row is missing dataset columns {missing_columns}")
    if quantity not in manifest.value_columns:
        raise MeasurementDatasetError(f"dataset manifest has no value mapping for {quantity!r}")
    value_column, value_unit = manifest.value_columns[quantity]
    try:
        value = Quantity(float(row[value_column]), value_unit)
    except (TypeError, ValueError) as exc:
        raise MeasurementDatasetError(f"{value_column!r} is not a numeric measurement") from exc

    conditions: dict[str, Quantity] = {}
    for path, (column, unit) in manifest.condition_columns.items():
        raw = row.get(column)
        if raw in (None, ""):
            continue
        try:
            conditions[path] = Quantity(float(raw), unit)
        except (TypeError, ValueError) as exc:
            raise MeasurementDatasetError(f"{column!r} is not a numeric condition") from exc
    for path, value_override in dict(context_overrides or {}).items():
        if not isinstance(value_override, Quantity):
            raise MeasurementDatasetError(f"context override {path!r} must be a Quantity")
        conditions[path] = value_override

    missing_context = tuple(sorted(set(required_context) - set(conditions)))
    if uncertainty is None:
        uncertainty = Uncertainty.unknown(
            "dataset source metadata does not declare per-observation calibrated measurement uncertainty"
        )
    return DatasetObservation(
        manifest_digest=manifest.digest,
        observation_id=observation_id,
        independence_group=independence_group,
        split=split,
        quantity=quantity,
        value=value,
        conditions=conditions,
        uncertainty=uncertainty,
        calibration_ref=calibration_ref,
        provenance_ref=provenance_ref,
        dataset_version=manifest.version,
        observed_at=observed_at,
        missing_context=missing_context,
    )


__all__ = [
    "DatasetObservation",
    "DatasetSplit",
    "MEASUREMENT_DATASET_SCHEMA",
    "MeasurementDatasetError",
    "MeasurementDatasetManifest",
    "observation_from_row",
    "required_physical_context",
]
