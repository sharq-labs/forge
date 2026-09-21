"""Immutable identity for external reference data.

A live URL is not scientific authority.  What can be cited is a *snapshot*: an
exact byte sequence, hashed, retrieved once, from a host the source declared.
Everything downstream -- normalization, tolerance review, campaigns, trust
promotion -- hangs off that digest, so a source that changes underneath a claim
invalidates the claim rather than silently altering it.

Three numbers that are constantly confused are kept apart here and stay apart
through the whole corpus:

``expected``
    what the source reports.
``source_uncertainty``
    what the source says about its own number.
``acceptance_tolerance``
    what Forge reviewed and decided it would accept as agreement.

They answer different questions.  Only the third is a Forge policy statement,
and its absence is never agreement.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping
from urllib.parse import urlparse

from ..errors import InvalidScientificProblem
from ..serialization import require_schema, schema_string
from ..units.quantity import Quantity, dimensionality, require_spread_unit
from ..units.validation import require_same_dimension

REFERENCE_SOURCE_SCHEMA = schema_string("corpus_reference_source")
SOURCE_SNAPSHOT_SCHEMA = schema_string("corpus_source_snapshot")
TOLERANCE_SCHEMA = schema_string("corpus_tolerance")


class CorpusError(InvalidScientificProblem):
    """The validation corpus refuses to treat this as evidence."""


class CorpusLeakageError(CorpusError):
    """Evidence was about to act as two independent things at once."""


def text(value: object, *, label: str) -> str:
    result = str(value).strip()
    if not result:
        raise CorpusError(f"{label} must be non-empty")
    return result


def sha256_hex(value: object, *, label: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise CorpusError(f"{label} must be a SHA-256 hex digest")
    return digest


def https_url(value: object, *, label: str) -> str:
    url = text(value, label=label)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise CorpusError(f"{label} must be an absolute HTTPS URL")
    return url


class ToleranceBasis(str, Enum):
    """Why a number is what it is. Never inferred from its value."""

    #: Stated by the source about its own measurement or computation.
    SOURCE_REPORTED = "source_reported"
    #: Reviewed by a person and recorded as Forge's acceptance policy.
    REVIEWED_ACCEPTANCE = "reviewed_acceptance"


@dataclass(frozen=True, order=True)
class ToleranceSpec:
    """A non-negative spread with a unit, a basis and a written rationale.

    The rationale is required. A tolerance with no stated reason is a number
    somebody picked, and a campaign built on it cannot be reviewed.
    """

    value: Quantity
    basis: ToleranceBasis
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, Quantity):
            raise CorpusError("tolerance value must be a Quantity")
        require_spread_unit(self.value.units, context="tolerance")
        if self.value.magnitude < 0.0:
            raise CorpusError("tolerance must be non-negative")
        object.__setattr__(self, "basis", ToleranceBasis(self.basis))
        object.__setattr__(
            self, "rationale", text(self.rationale, label="tolerance rationale")
        )

    def magnitude_in(self, unit: str) -> float:
        """This spread, read as a difference in ``unit``."""
        return self.value.magnitude_as_spread_in(unit)

    def require_comparable(self, expected: Quantity, *, context: str) -> None:
        require_same_dimension(self.value, expected, context=context)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TOLERANCE_SCHEMA,
            "value": self.value.to_dict(),
            "basis": self.basis.value,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ToleranceSpec":
        require_schema(payload, TOLERANCE_SCHEMA)
        return cls(
            Quantity.from_dict(payload["value"]),
            ToleranceBasis(payload["basis"]),
            payload["rationale"],
        )


@dataclass(frozen=True, order=True)
class ReferenceSource:
    """The authority a dataset is cited from, and the hosts it may come from."""

    source_id: str
    authority: str
    domain: str
    source_version: str
    landing_url: str
    allowed_hosts: tuple[str, ...]
    license_note: str = ""
    scale_note: str = ""

    def __post_init__(self) -> None:
        for label in ("source_id", "authority", "domain", "source_version"):
            object.__setattr__(self, label, text(getattr(self, label), label=label))
        object.__setattr__(
            self, "landing_url", https_url(self.landing_url, label="landing_url")
        )
        hosts = tuple(
            sorted({text(host, label="allowed host").lower() for host in self.allowed_hosts})
        )
        if not hosts:
            raise CorpusError("a reference source must declare at least one allowed host")
        object.__setattr__(self, "allowed_hosts", hosts)
        object.__setattr__(self, "license_note", str(self.license_note).strip())
        object.__setattr__(self, "scale_note", str(self.scale_note).strip())

    @property
    def key(self) -> tuple[str, str]:
        return self.source_id, self.source_version

    def permits(self, url: str) -> bool:
        parsed = urlparse(str(url))
        return parsed.scheme == "https" and (parsed.hostname or "").lower() in self.allowed_hosts

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REFERENCE_SOURCE_SCHEMA,
            "source_id": self.source_id,
            "authority": self.authority,
            "domain": self.domain,
            "source_version": self.source_version,
            "landing_url": self.landing_url,
            "allowed_hosts": list(self.allowed_hosts),
            "license_note": self.license_note,
            "scale_note": self.scale_note,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReferenceSource":
        require_schema(payload, REFERENCE_SOURCE_SCHEMA)
        return cls(
            payload["source_id"],
            payload["authority"],
            payload["domain"],
            payload["source_version"],
            payload["landing_url"],
            tuple(payload.get("allowed_hosts", ())),
            payload.get("license_note", ""),
            payload.get("scale_note", ""),
        )


@dataclass(frozen=True, order=True)
class SourceSnapshot:
    """Exact bytes, retrieved once, from a host the source declared.

    This is the link in the provenance chain that makes a citation checkable:
    official source -> snapshot -> sha256 -> normalization -> normalized digest
    -> reviewed tolerances -> campaign -> trust decision. A dataset that cannot
    name its snapshot digest cannot enter the corpus.
    """

    source_id: str
    source_version: str
    snapshot_sha256: str
    snapshot_url: str
    byte_length: int
    retrieved_at_utc: str
    content_type: str = ""

    def __post_init__(self) -> None:
        for label in ("source_id", "source_version", "retrieved_at_utc"):
            object.__setattr__(self, label, text(getattr(self, label), label=label))
        object.__setattr__(
            self,
            "snapshot_sha256",
            sha256_hex(self.snapshot_sha256, label="snapshot_sha256"),
        )
        object.__setattr__(
            self, "snapshot_url", https_url(self.snapshot_url, label="snapshot_url")
        )
        if isinstance(self.byte_length, bool) or int(self.byte_length) != self.byte_length:
            raise CorpusError("snapshot byte_length must be an integer")
        if int(self.byte_length) <= 0:
            raise CorpusError("snapshot byte_length must be positive")
        object.__setattr__(self, "byte_length", int(self.byte_length))
        object.__setattr__(self, "content_type", str(self.content_type).strip())

    def require_from(self, source: ReferenceSource) -> None:
        """Refuse a snapshot that does not belong to this source."""
        if (self.source_id, self.source_version) != source.key:
            raise CorpusError(
                f"snapshot {self.source_id}@{self.source_version} does not belong to "
                f"source {source.source_id}@{source.source_version}"
            )
        if not source.permits(self.snapshot_url):
            raise CorpusError(
                f"snapshot was taken from {self.snapshot_url!r}, which source "
                f"{source.source_id!r} does not permit"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SOURCE_SNAPSHOT_SCHEMA,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "snapshot_sha256": self.snapshot_sha256,
            "snapshot_url": self.snapshot_url,
            "byte_length": self.byte_length,
            "retrieved_at_utc": self.retrieved_at_utc,
            "content_type": self.content_type,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SourceSnapshot":
        require_schema(payload, SOURCE_SNAPSHOT_SCHEMA)
        return cls(
            payload["source_id"],
            payload["source_version"],
            payload["snapshot_sha256"],
            payload["snapshot_url"],
            payload["byte_length"],
            payload["retrieved_at_utc"],
            payload.get("content_type", ""),
        )


def require_quantity(value: object, *, label: str) -> Quantity:
    if not isinstance(value, Quantity):
        raise CorpusError(f"{label} must be a Quantity; units are never implicit")
    return value


def same_dimension(left: Quantity, right: Quantity) -> bool:
    return dimensionality(left.units) == dimensionality(right.units)


__all__ = [
    "REFERENCE_SOURCE_SCHEMA",
    "SOURCE_SNAPSHOT_SCHEMA",
    "TOLERANCE_SCHEMA",
    "CorpusError",
    "CorpusLeakageError",
    "ReferenceSource",
    "SourceSnapshot",
    "ToleranceBasis",
    "ToleranceSpec",
    "https_url",
    "require_quantity",
    "same_dimension",
    "sha256_hex",
    "text",
]
