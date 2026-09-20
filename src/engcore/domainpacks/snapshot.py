"""Serializable provenance snapshot of the exact Domain Pack selected."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .manifest import ArtifactRef
from .registry import RegisteredDomainPack

SNAPSHOT_SCHEMA = "forge.domain_pack_snapshot/2"


@dataclass(frozen=True)
class DomainPackSnapshot:
    pack_id: str
    pack_version: str
    domain: str
    manifest_digest: str
    origin_kind: str
    distribution_name: str | None
    distribution_version: str | None
    entry_point: str | None
    capabilities: tuple[str, ...]
    models: tuple[ArtifactRef, ...]
    realizations: tuple[ArtifactRef, ...]
    solvers: tuple[ArtifactRef, ...]
    calibration_protocols: tuple[ArtifactRef, ...]
    validation_protocols: tuple[ArtifactRef, ...]
    uq_producers: tuple[ArtifactRef, ...]
    measurement_adapters: tuple[ArtifactRef, ...]
    transformations: tuple[ArtifactRef, ...]
    benchmarks: tuple[ArtifactRef, ...]
    implementation_digest: str
    implementation_fingerprints: tuple[dict[str, str], ...]
    semantic_authority: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "domain": self.domain,
            "manifest_digest": self.manifest_digest,
            "origin": {
                "kind": self.origin_kind,
                "distribution_name": self.distribution_name,
                "distribution_version": self.distribution_version,
                "entry_point": self.entry_point,
            },
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
            "implementation_digest": self.implementation_digest,
            "implementation_fingerprints": list(
                self.implementation_fingerprints
            ),
            "semantic_authority": self.semantic_authority,
        }

    @property
    def digest(self) -> str:
        payload = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def snapshot_domain_pack(registration: RegisteredDomainPack) -> DomainPackSnapshot:
    manifest = registration.provider.manifest
    origin = registration.origin
    return DomainPackSnapshot(
        pack_id=manifest.pack_id,
        pack_version=manifest.pack_version,
        domain=manifest.domain,
        manifest_digest=manifest.digest,
        origin_kind=origin.kind,
        distribution_name=origin.distribution_name,
        distribution_version=origin.distribution_version,
        entry_point=origin.entry_point,
        capabilities=manifest.capabilities,
        models=manifest.models,
        realizations=manifest.realizations,
        solvers=manifest.solvers,
        calibration_protocols=manifest.calibration_protocols,
        validation_protocols=manifest.validation_protocols,
        uq_producers=manifest.uq_producers,
        measurement_adapters=manifest.measurement_adapters,
        transformations=manifest.transformations,
        benchmarks=manifest.benchmarks,
        implementation_digest=registration.implementation_digest,
        implementation_fingerprints=tuple(
            item.to_dict()
            for item in registration.implementation_fingerprints
        ),
        semantic_authority=(
            None
            if registration.semantic_authority is None
            else registration.semantic_authority.to_dict()
        ),
    )
