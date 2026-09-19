"""Immutable, digestable declarations for a Forge Domain Pack."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from ..scientific.capabilities import ScientificCapability
from .errors import InvalidDomainPackManifest

DOMAIN_PACK_SCHEMA = "forge.domain_pack/1"
DOMAIN_PACK_API = "forge.domainpack_api/1"

_ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")


def _text(value: object, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise InvalidDomainPackManifest(f"{field} must be non-empty")
    return text


def _identifier(value: object, field: str) -> str:
    text = _text(value, field)
    if not _ID.fullmatch(text):
        raise InvalidDomainPackManifest(
            f"{field} {text!r} must be lowercase dotted identifier segments"
        )
    return text


@dataclass(frozen=True, order=True)
class ArtifactRef:
    """Stable identity of one artifact exposed by a pack."""

    artifact_id: str
    version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", _identifier(self.artifact_id, "artifact_id"))
        object.__setattr__(self, "version", _text(self.version, "artifact version"))

    def to_dict(self) -> dict[str, str]:
        return {"artifact_id": self.artifact_id, "version": self.version}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactRef":
        if set(payload) != {"artifact_id", "version"}:
            raise InvalidDomainPackManifest(
                "artifact ref must contain exactly artifact_id and version"
            )
        return cls(payload["artifact_id"], payload["version"])


def _refs(values: tuple[ArtifactRef, ...], field: str) -> tuple[ArtifactRef, ...]:
    refs = tuple(values)
    if any(not isinstance(item, ArtifactRef) for item in refs):
        raise InvalidDomainPackManifest(f"{field} must contain ArtifactRef records")
    if len(set(refs)) != len(refs):
        raise InvalidDomainPackManifest(f"{field} contains duplicate artifact identities")
    return tuple(sorted(refs))


@dataclass(frozen=True)
class DomainPackManifest:
    """What a pack claims to expose, before any implementation is trusted."""

    pack_id: str
    pack_version: str
    domain: str
    compatible_core_apis: tuple[str, ...]
    capabilities: tuple[str, ...] = ()
    models: tuple[ArtifactRef, ...] = ()
    realizations: tuple[ArtifactRef, ...] = ()
    solvers: tuple[ArtifactRef, ...] = ()
    calibration_protocols: tuple[ArtifactRef, ...] = ()
    validation_protocols: tuple[ArtifactRef, ...] = ()
    uq_producers: tuple[ArtifactRef, ...] = ()
    measurement_adapters: tuple[ArtifactRef, ...] = ()
    transformations: tuple[ArtifactRef, ...] = ()
    benchmarks: tuple[ArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "pack_id", _identifier(self.pack_id, "pack_id"))
        object.__setattr__(self, "pack_version", _text(self.pack_version, "pack_version"))
        object.__setattr__(self, "domain", _identifier(self.domain, "domain"))

        apis = tuple(sorted({_text(v, "compatible_core_api") for v in self.compatible_core_apis}))
        if not apis:
            raise InvalidDomainPackManifest("compatible_core_apis may not be empty")
        object.__setattr__(self, "compatible_core_apis", apis)

        capabilities = tuple(sorted({
            ScientificCapability.parse(value).identifier for value in self.capabilities
        }))
        object.__setattr__(self, "capabilities", capabilities)

        for field in (
            "models", "realizations", "solvers", "calibration_protocols",
            "validation_protocols", "uq_producers", "measurement_adapters",
            "transformations", "benchmarks",
        ):
            object.__setattr__(self, field, _refs(getattr(self, field), field))

    @property
    def key(self) -> tuple[str, str]:
        return (self.pack_id, self.pack_version)

    @property
    def compatible_with_current_core(self) -> bool:
        return DOMAIN_PACK_API in self.compatible_core_apis

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": DOMAIN_PACK_SCHEMA,
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "domain": self.domain,
            "compatible_core_apis": list(self.compatible_core_apis),
            "capabilities": list(self.capabilities),
            "models": [v.to_dict() for v in self.models],
            "realizations": [v.to_dict() for v in self.realizations],
            "solvers": [v.to_dict() for v in self.solvers],
            "calibration_protocols": [v.to_dict() for v in self.calibration_protocols],
            "validation_protocols": [v.to_dict() for v in self.validation_protocols],
            "uq_producers": [v.to_dict() for v in self.uq_producers],
            "measurement_adapters": [v.to_dict() for v in self.measurement_adapters],
            "transformations": [v.to_dict() for v in self.transformations],
            "benchmarks": [v.to_dict() for v in self.benchmarks],
        }

    @property
    def digest(self) -> str:
        payload = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DomainPackManifest":
        if payload.get("schema") != DOMAIN_PACK_SCHEMA:
            raise InvalidDomainPackManifest(
                f"unsupported schema {payload.get('schema')!r}; expected {DOMAIN_PACK_SCHEMA!r}"
            )
        expected = {
            "schema", "pack_id", "pack_version", "domain", "compatible_core_apis",
            "capabilities", "models", "realizations", "solvers",
            "calibration_protocols", "validation_protocols", "uq_producers",
            "measurement_adapters", "transformations", "benchmarks",
        }
        if set(payload) != expected:
            missing = sorted(expected - set(payload))
            extra = sorted(set(payload) - expected)
            raise InvalidDomainPackManifest(
                f"domain pack manifest shape mismatch; missing={missing}, extra={extra}"
            )
        decode = lambda name: tuple(ArtifactRef.from_dict(v) for v in payload[name])
        return cls(
            pack_id=payload["pack_id"],
            pack_version=payload["pack_version"],
            domain=payload["domain"],
            compatible_core_apis=tuple(payload["compatible_core_apis"]),
            capabilities=tuple(payload["capabilities"]),
            models=decode("models"),
            realizations=decode("realizations"),
            solvers=decode("solvers"),
            calibration_protocols=decode("calibration_protocols"),
            validation_protocols=decode("validation_protocols"),
            uq_producers=decode("uq_producers"),
            measurement_adapters=decode("measurement_adapters"),
            transformations=decode("transformations"),
            benchmarks=decode("benchmarks"),
        )
