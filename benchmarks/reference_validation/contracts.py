"""An authoring shape for frozen external-reference datasets.

This package is deliberately outside ``engcore.scientific``: it reaches the
network, and the Scientific Core does not. What it is NOT, any more, is a
second implementation of validation.

The normalized identity, the split authority, the comparison and every verdict
now live once, in :mod:`engcore.scientific.corpus`. What remains here is a flat
point table that is pleasant to write a catalog in, plus
:meth:`ReferenceDataset.promote`, which turns it into the Core corpus records
that actually carry authority. ``normalized_digest`` delegates to the promoted
dataset for the same reason: two digests for one dataset would be two
identities, and a trust decision pinned to the wrong one is not pinned.

A source record, a source uncertainty and a Forge acceptance tolerance remain
three different scientific statements, kept apart here and in Core, so missing
policy can never be silently interpreted as a passing validation case.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from engcore.scientific.corpus import (
    Applicability,
    DatasetSplit,
    ReferenceCase,
    ReferenceCondition as CorpusCondition,
    ReferenceDataset as CorpusDataset,
    ReferenceObservation,
    ReferenceSource,
    SourceSnapshot,
    ToleranceBasis,
    ToleranceSpec as CorpusTolerance,
)
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

    @property
    def core_source(self) -> ReferenceSource:
        """The Core corpus record this spec authors. One source, one identity."""
        return ReferenceSource(
            source_id=self.source_id,
            authority=self.authority,
            domain=self.domain,
            source_version=self.source_version,
            landing_url=self.landing_url,
            allowed_hosts=self.allowed_hosts,
            license_note=self.license_note,
            scale_note=self.scale_note,
        )


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
    #: Which role this point is permitted to play. Defaulting to VALIDATION is
    #: the conservative choice: a point nobody classified must not be able to
    #: influence a fit by omission.
    split: DatasetSplit = DatasetSplit.VALIDATION
    #: Evidence that is not independent of other evidence shares a group. An
    #: empty group means "this point alone", which is only correct when it is.
    independence_group: str = ""

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
        object.__setattr__(self, "split", DatasetSplit(self.split))
        object.__setattr__(
            self,
            "independence_group",
            str(self.independence_group).strip() or self.case_id,
        )

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

    def promote(
        self,
        *,
        retrieved_at_utc: str = "1970-01-01T00:00:00+00:00",
        byte_length: int = 1,
        content_type: str = "",
    ) -> CorpusDataset:
        """Turn this authored table into the Core corpus records that carry authority.

        Every point becomes a case and an observation. Conditions travel as
        unit-bearing coordinates so coverage and envelope reasoning can index
        them, and the split and independence group travel with the case so the
        Core split authority -- not this module -- decides what may influence a
        fit.

        Snapshot metadata that the catalog does not record (retrieval time,
        byte length) is supplied by the caller. It is outside the normalized
        digest, so a catalog promoted twice has one identity.
        """
        source = self.source.core_source
        snapshot = SourceSnapshot(
            source_id=source.source_id,
            source_version=source.source_version,
            snapshot_sha256=self.source_snapshot_sha256,
            snapshot_url=self.source_snapshot_url,
            byte_length=byte_length,
            retrieved_at_utc=retrieved_at_utc,
            content_type=content_type,
        )

        def tolerance(spec: "ToleranceSpec | None", basis: ToleranceBasis):
            if spec is None:
                return None
            return CorpusTolerance(spec.quantity(), basis, spec.rationale)

        cases: dict[str, ReferenceCase] = {}
        observations: list[ReferenceObservation] = []
        for point in self.points:
            conditions = tuple(
                CorpusCondition(item.name, item.quantity()) for item in point.conditions
            )
            existing = cases.get(point.case_id)
            candidate = ReferenceCase(
                case_id=point.case_id,
                split=point.split,
                independence_group=point.independence_group,
                conditions=conditions,
                applicability=Applicability.UNDECLARED,
                tags=point.tags,
            )
            if existing is not None and existing != candidate:
                raise ValueError(
                    f"case {point.case_id!r} is described two different ways by its "
                    f"points; one operating point is one case"
                )
            cases[point.case_id] = candidate
            observations.append(
                ReferenceObservation(
                    case_id=point.case_id,
                    metric=point.metric,
                    expected=Quantity(point.expected_value, point.expected_unit),
                    source_uncertainty=tolerance(
                        point.source_uncertainty, ToleranceBasis.SOURCE_REPORTED
                    ),
                    acceptance_tolerance=tolerance(
                        point.acceptance_tolerance, ToleranceBasis.REVIEWED_ACCEPTANCE
                    ),
                    note=point.note,
                )
            )
        return CorpusDataset(
            dataset_id=self.dataset_id,
            version=self.version,
            source=source,
            snapshot=snapshot,
            cases=tuple(cases.values()),
            observations=tuple(observations),
        )

    @property
    def normalized_digest(self) -> str:
        """The Core corpus identity for this dataset. There is only one."""
        return self.promote().normalized_digest

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
