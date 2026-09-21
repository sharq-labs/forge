"""Contracts for frozen external-reference datasets.

A source record, a source uncertainty and a Forge acceptance tolerance are
different scientific statements.  This module keeps them separate so missing
policy can never be silently interpreted as a passing validation case.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from engcore.scientific.oracles import (
    OracleEvidenceSet,
    OracleKind,
    OracleObservation,
)
from engcore.scientific.units.quantity import Quantity


def _text(value: Any, *, label: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{label} must be non-empty")
    return result


def _finite(value: Any, *, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _sha256(value: Any, *, label: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(f"{label} must be a SHA-256 hex digest")
    return digest


@dataclass(frozen=True)
class ReferenceSourceSpec:
    source_id: str
    domain: str
    authority: str
    source_version: str
    landing_url: str
    oracle_kind: OracleKind
    allowed_hosts: tuple[str, ...]
    scale_note: str = ""
    license_note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text(self.source_id, label="source_id"))
        object.__setattr__(self, "domain", _text(self.domain, label="domain"))
        object.__setattr__(self, "authority", _text(self.authority, label="authority"))
        object.__setattr__(
            self, "source_version", _text(self.source_version, label="source_version")
        )
        parsed = urlparse(_text(self.landing_url, label="landing_url"))
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("landing_url must be an absolute HTTPS URL")
        hosts = tuple(sorted({_text(host, label="allowed host").lower() for host in self.allowed_hosts}))
        if not hosts:
            raise ValueError("reference source must declare at least one allowed host")
        object.__setattr__(self, "allowed_hosts", hosts)
        object.__setattr__(self, "oracle_kind", OracleKind(self.oracle_kind))


@dataclass(frozen=True)
class ReferenceCondition:
    name: str
    value: float
    unit: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, label="condition name"))
        object.__setattr__(self, "value", _finite(self.value, label=f"{self.name} value"))
        object.__setattr__(self, "unit", _text(self.unit, label=f"{self.name} unit"))

    def quantity(self) -> Quantity:
        return Quantity(self.value, self.unit)


@dataclass(frozen=True)
class ToleranceSpec:
    value: float
    unit: str
    rationale: str

    def __post_init__(self) -> None:
        value = _finite(self.value, label="tolerance value")
        if value < 0.0:
            raise ValueError("tolerance value must be non-negative")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "unit", _text(self.unit, label="tolerance unit"))
        object.__setattr__(self, "rationale", _text(self.rationale, label="tolerance rationale"))

    def quantity(self) -> Quantity:
        return Quantity(self.value, self.unit)


@dataclass(frozen=True)
class ReferencePoint:
    case_id: str
    metric: str
    expected_value: float
    expected_unit: str
    conditions: tuple[ReferenceCondition, ...] = ()
    source_uncertainty: ToleranceSpec | None = None
    acceptance_tolerance: ToleranceSpec | None = None
    tags: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _text(self.case_id, label="case_id"))
        object.__setattr__(self, "metric", _text(self.metric, label="metric"))
        object.__setattr__(
            self,
            "expected_value",
            _finite(self.expected_value, label=f"{self.case_id} expected value"),
        )
        object.__setattr__(
            self, "expected_unit", _text(self.expected_unit, label="expected_unit")
        )
        conditions = tuple(self.conditions)
        if any(not isinstance(item, ReferenceCondition) for item in conditions):
            raise TypeError("conditions must be ReferenceCondition records")
        names = [item.name for item in conditions]
        if len(names) != len(set(names)):
            raise ValueError(f"{self.case_id} repeats a condition name")
        object.__setattr__(self, "conditions", conditions)
        object.__setattr__(self, "tags", tuple(sorted({_text(x, label="tag") for x in self.tags})))
        if self.source_uncertainty is not None and not isinstance(
            self.source_uncertainty, ToleranceSpec
        ):
            raise TypeError("source_uncertainty must be ToleranceSpec or None")
        if self.acceptance_tolerance is not None and not isinstance(
            self.acceptance_tolerance, ToleranceSpec
        ):
            raise TypeError("acceptance_tolerance must be ToleranceSpec or None")
        object.__setattr__(self, "note", str(self.note))

    @property
    def key(self) -> tuple[str, str]:
        return self.case_id, self.metric

    def oracle_observation(self) -> OracleObservation:
        if self.acceptance_tolerance is None:
            raise ValueError(
                f"{self.case_id}/{self.metric} has no reviewed acceptance tolerance"
            )
        uncertainty_note = ""
        if self.source_uncertainty is not None:
            uncertainty_note = (
                f" source uncertainty={self.source_uncertainty.value:g} "
                f"{self.source_uncertainty.unit} "
                f"({self.source_uncertainty.rationale})."
            )
        return OracleObservation(
            metric=self.metric,
            expected=Quantity(self.expected_value, self.expected_unit),
            absolute_tolerance=self.acceptance_tolerance.quantity(),
            note=(self.note + uncertainty_note).strip(),
            conditions={item.name: item.quantity() for item in self.conditions},
        )


TolerancePolicy = Callable[[ReferencePoint], ToleranceSpec | None]


@dataclass(frozen=True)
class ReferenceDataset:
    dataset_id: str
    version: str
    source: ReferenceSourceSpec
    source_snapshot_sha256: str
    source_snapshot_url: str
    points: tuple[ReferencePoint, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_id", _text(self.dataset_id, label="dataset_id"))
        object.__setattr__(self, "version", _text(self.version, label="version"))
        if not isinstance(self.source, ReferenceSourceSpec):
            raise TypeError("source must be ReferenceSourceSpec")
        object.__setattr__(
            self,
            "source_snapshot_sha256",
            _sha256(self.source_snapshot_sha256, label="source snapshot digest"),
        )
        snapshot_url = _text(self.source_snapshot_url, label="source_snapshot_url")
        parsed = urlparse(snapshot_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("source_snapshot_url must be an absolute HTTPS URL")
        object.__setattr__(self, "source_snapshot_url", snapshot_url)
        points = tuple(self.points)
        if not points:
            raise ValueError("reference dataset requires at least one point")
        if any(not isinstance(item, ReferencePoint) for item in points):
            raise TypeError("points must be ReferencePoint records")
        keys = [item.key for item in points]
        if len(keys) != len(set(keys)):
            raise ValueError("reference dataset repeats a case_id/metric pair")
        observation_keys = [
            (
                item.metric,
                tuple(
                    sorted(
                        (condition.name, condition.unit, condition.value)
                        for condition in item.conditions
                    )
                ),
            )
            for item in points
        ]
        if len(observation_keys) != len(set(observation_keys)):
            raise ValueError(
                "reference dataset repeats one metric at one numeric operating "
                "point; split categorical regimes (for example fluid phase or "
                "reaction identity) into separate datasets before promotion"
            )
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def normalized_digest(self) -> str:
        payload = {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "source_id": self.source.source_id,
            "source_version": self.source.source_version,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "source_snapshot_url": self.source_snapshot_url,
            "points": [
                {
                    "case_id": point.case_id,
                    "metric": point.metric,
                    "expected_value": point.expected_value,
                    "expected_unit": point.expected_unit,
                    "conditions": [
                        {"name": c.name, "value": c.value, "unit": c.unit}
                        for c in point.conditions
                    ],
                    "source_uncertainty": (
                        None
                        if point.source_uncertainty is None
                        else {
                            "value": point.source_uncertainty.value,
                            "unit": point.source_uncertainty.unit,
                            "rationale": point.source_uncertainty.rationale,
                        }
                    ),
                    "acceptance_tolerance": (
                        None
                        if point.acceptance_tolerance is None
                        else {
                            "value": point.acceptance_tolerance.value,
                            "unit": point.acceptance_tolerance.unit,
                            "rationale": point.acceptance_tolerance.rationale,
                        }
                    ),
                    "tags": list(point.tags),
                    "note": point.note,
                }
                for point in sorted(self.points, key=lambda item: item.key)
            ],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def is_scored(self) -> bool:
        return all(point.acceptance_tolerance is not None for point in self.points)

    def bind_tolerances(self, policy: TolerancePolicy) -> "ReferenceDataset":
        rebound: list[ReferencePoint] = []
        missing: list[str] = []
        for point in self.points:
            tolerance = point.acceptance_tolerance or policy(point)
            if tolerance is None:
                missing.append(f"{point.case_id}/{point.metric}")
                rebound.append(point)
            else:
                rebound.append(replace(point, acceptance_tolerance=tolerance))
        if missing:
            raise ValueError(
                "tolerance policy does not cover every point; missing: "
                + ", ".join(sorted(missing))
            )
        return replace(self, points=tuple(rebound))

    def to_oracle_evidence(self) -> OracleEvidenceSet:
        if not self.is_scored:
            raise ValueError(
                "dataset has unscored points; missing acceptance tolerance must "
                "never be interpreted as validation success"
            )
        return OracleEvidenceSet.create(
            oracle_id=self.dataset_id,
            version=self.version,
            kind=self.source.oracle_kind,
            reference=(
                f"{self.source.authority}: {self.source.landing_url}; "
                f"source snapshot sha256:{self.source_snapshot_sha256}; "
                f"normalized sha256:{self.normalized_digest}"
            ),
            observations=tuple(point.oracle_observation() for point in self.points),
        )


__all__ = [
    "ReferenceCondition",
    "ReferenceDataset",
    "ReferencePoint",
    "ReferenceSourceSpec",
    "TolerancePolicy",
    "ToleranceSpec",
]
