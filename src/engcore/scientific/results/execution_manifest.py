"""Deterministic execution manifests and explicit artifact byte identity.

This module closes a provenance gap without pretending to provide more proof
than a digest can provide.  A manifest binds the serializable scientific
problem, solver identity/settings, raw solver record, explicit environment
facts, output data references, and caller-supplied artifact bytes.  Any change
to those facts changes the manifest digest.

It is *tamper evidence*, not proof that a computation physically executed.
``PreparedSolve.payload`` is deliberately opaque to the core; it is covered
only when the caller supplies a canonical byte image for it.  Likewise the
module never scans the host, environment variables, files, containers or
installed packages automatically.  Reproducibility facts are explicit inputs,
so collecting a manifest cannot silently exfiltrate machine state.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..errors import ScientificCoreError
from ..ir.problem import ScientificProblem
from ..serialization import require_schema, schema_string
from ..solvers.protocol import PreparedSolve, RawSolverOutput, SolverIdentity
from .data_reference import ScientificDataReference

ARTIFACT_DIGEST_SCHEMA = schema_string("execution_artifact_digest")
EXECUTION_MANIFEST_SCHEMA = schema_string("execution_manifest")
_SHA256 = "sha256"
_MANIFEST_TAG = b"crafty.execution.manifest/1\x00"
_ARTIFACT_TAG = b"crafty.execution.artifact/1\x00"


def _hex_digest(value: Any, *, label: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ScientificCoreError(
            f"{label} must be a 64-character lowercase-compatible SHA-256 hex digest"
        )
    return text


def _normalise_json(value: Any) -> Any:
    """Canonical JSON-compatible semantics including failed-solve non-finites."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"$float": "nan"}
        if math.isinf(value):
            return {"$float": "+inf" if value > 0 else "-inf"}
        # JSON preserves -0.0, which matters because this hashes the record that
        # was written, not mathematical equivalence between two computations.
        return value
    if isinstance(value, Mapping):
        pairs: list[tuple[str, Any]] = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise ScientificCoreError(
                    f"execution manifest cannot canonicalize non-string mapping key {key!r}"
                )
            pairs.append((key, _normalise_json(item)))
        return {key: item for key, item in sorted(pairs)}
    if isinstance(value, (tuple, list)):
        return [_normalise_json(item) for item in value]
    raise ScientificCoreError(
        f"execution manifest cannot canonicalize {type(value).__name__}; "
        "only serialized scientific records may cross this boundary"
    )


def canonical_record_digest(value: Mapping[str, Any]) -> str:
    """Stable SHA-256 identity for one serialized scientific record."""
    canonical = _normalise_json(value)
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(_MANIFEST_TAG)
    digest.update(payload)
    return digest.hexdigest()


@dataclass(frozen=True)
class ArtifactDigest:
    """Byte identity of an explicitly supplied execution artifact."""

    name: str
    digest: str
    size_bytes: int
    role: str = "output"
    algorithm: str = _SHA256

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        role = str(self.role).strip()
        if not name:
            raise ScientificCoreError("execution artifact requires a non-empty name")
        if not role:
            raise ScientificCoreError("execution artifact requires a non-empty role")
        if self.algorithm != _SHA256:
            raise ScientificCoreError(
                f"unsupported execution artifact digest algorithm {self.algorithm!r}"
            )
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
            raise ScientificCoreError("execution artifact size_bytes must be an int")
        if self.size_bytes < 0:
            raise ScientificCoreError("execution artifact size_bytes must be non-negative")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "digest", _hex_digest(self.digest, label="artifact digest"))

    @classmethod
    def from_bytes(cls, name: str, payload: bytes, *, role: str = "output") -> "ArtifactDigest":
        if not isinstance(payload, bytes):
            raise ScientificCoreError(
                f"artifact {name!r} payload must be bytes; got {type(payload).__name__}"
            )
        digest = hashlib.sha256()
        digest.update(_ARTIFACT_TAG)
        digest.update(payload)
        return cls(name=name, digest=digest.hexdigest(), size_bytes=len(payload), role=role)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ARTIFACT_DIGEST_SCHEMA,
            "name": self.name,
            "digest": self.digest,
            "size_bytes": self.size_bytes,
            "role": self.role,
            "algorithm": self.algorithm,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactDigest":
        require_schema(payload, ARTIFACT_DIGEST_SCHEMA)
        return cls(
            name=payload["name"],
            digest=payload["digest"],
            size_bytes=payload["size_bytes"],
            role=payload.get("role", "output"),
            algorithm=payload.get("algorithm", _SHA256),
        )


@dataclass(frozen=True)
class ExecutionManifest:
    """Content-addressed binding of one prepared solve and raw result.

    ``coverage`` is intentionally visible.  ``control_plane`` means the opaque
    prepared payload was not attested.  ``control_plane+prepared_payload``
    means the caller supplied a canonical byte image for that payload too.
    Neither spelling claims trusted-hardware execution proof or a signature.
    """

    problem_id: str
    problem_digest: str
    solver: SolverIdentity
    settings_digest: str
    raw_output_digest: str
    artifacts: tuple[ArtifactDigest, ...] = ()
    data_references: tuple[ScientificDataReference, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()
    preparation_notes: tuple[str, ...] = ()
    prepared_payload: ArtifactDigest | None = None
    realization_id: str | None = None

    def __post_init__(self) -> None:
        problem_id = str(self.problem_id).strip()
        if not problem_id:
            raise ScientificCoreError("execution manifest requires problem_id")
        if not isinstance(self.solver, SolverIdentity):
            raise ScientificCoreError("execution manifest solver must be SolverIdentity")
        object.__setattr__(self, "problem_id", problem_id)
        for field_name in ("problem_digest", "settings_digest", "raw_output_digest"):
            object.__setattr__(
                self, field_name, _hex_digest(getattr(self, field_name), label=field_name)
            )

        artifacts = tuple(sorted(self.artifacts, key=lambda item: item.name))
        if any(not isinstance(item, ArtifactDigest) for item in artifacts):
            raise ScientificCoreError("execution manifest artifacts must be ArtifactDigest records")
        names = [item.name for item in artifacts]
        if len(set(names)) != len(names):
            raise ScientificCoreError("execution manifest artifact names must be unique")
        object.__setattr__(self, "artifacts", artifacts)

        references = tuple(sorted(self.data_references, key=lambda item: item.name))
        if any(not isinstance(item, ScientificDataReference) for item in references):
            raise ScientificCoreError(
                "execution manifest data_references must be ScientificDataReference records"
            )
        if len({item.name for item in references}) != len(references):
            raise ScientificCoreError("execution manifest data-reference names must be unique")
        object.__setattr__(self, "data_references", references)

        env: list[tuple[str, str]] = []
        for pair in self.environment:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ScientificCoreError("execution environment entries must be (key, value) pairs")
            key, value = pair
            key, value = str(key).strip(), str(value).strip()
            if not key or not value:
                raise ScientificCoreError("execution environment keys and values must be non-empty")
            env.append((key, value))
        env.sort()
        if len({key for key, _ in env}) != len(env):
            raise ScientificCoreError("execution environment keys must be unique")
        object.__setattr__(self, "environment", tuple(env))
        object.__setattr__(self, "preparation_notes", tuple(str(v) for v in self.preparation_notes))

        if self.prepared_payload is not None:
            if not isinstance(self.prepared_payload, ArtifactDigest):
                raise ScientificCoreError("prepared_payload must be an ArtifactDigest")
            if self.prepared_payload.role != "prepared_payload":
                raise ScientificCoreError(
                    "prepared_payload artifact must carry role='prepared_payload'"
                )
        if self.realization_id is not None:
            realization = str(self.realization_id).strip()
            if not realization:
                raise ScientificCoreError("realization_id must be non-empty when supplied")
            object.__setattr__(self, "realization_id", realization)

    @property
    def coverage(self) -> str:
        return (
            "control_plane+prepared_payload"
            if self.prepared_payload is not None
            else "control_plane"
        )

    def _unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema": EXECUTION_MANIFEST_SCHEMA,
            "problem_id": self.problem_id,
            "problem_digest": self.problem_digest,
            "solver": self.solver.to_dict(),
            "settings_digest": self.settings_digest,
            "raw_output_digest": self.raw_output_digest,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "data_references": [item.to_dict() for item in self.data_references],
            "environment": [[key, value] for key, value in self.environment],
            "preparation_notes": list(self.preparation_notes),
            "prepared_payload": self.prepared_payload.to_dict() if self.prepared_payload else None,
            "realization_id": self.realization_id,
            "coverage": self.coverage,
        }

    @property
    def manifest_digest(self) -> str:
        return canonical_record_digest(self._unsigned_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self._unsigned_dict()
        payload["manifest_digest"] = self.manifest_digest
        return payload

    @classmethod
    def from_execution(
        cls,
        prepared: PreparedSolve,
        raw: RawSolverOutput,
        *,
        artifact_bytes: Mapping[str, bytes] | None = None,
        prepared_payload_bytes: bytes | None = None,
        environment: Mapping[str, str] | None = None,
        realization_id: str | None = None,
    ) -> "ExecutionManifest":
        if not isinstance(prepared, PreparedSolve):
            raise ScientificCoreError("execution manifest requires a PreparedSolve")
        if not isinstance(raw, RawSolverOutput):
            raise ScientificCoreError("execution manifest requires a RawSolverOutput")
        if not isinstance(prepared.problem, ScientificProblem):
            raise ScientificCoreError(
                "execution manifest requires PreparedSolve.problem to be ScientificProblem"
            )

        artifact_bytes = dict(artifact_bytes or {})
        declared = tuple(raw.artifacts)
        if len(set(declared)) != len(declared):
            raise ScientificCoreError("raw solver output declares duplicate artifact names")
        missing = sorted(set(declared) - set(artifact_bytes))
        extra = sorted(set(artifact_bytes) - set(declared))
        if missing or extra:
            raise ScientificCoreError(
                f"artifact attestation must cover exactly raw.artifacts; missing={missing}, extra={extra}"
            )
        artifacts = tuple(
            ArtifactDigest.from_bytes(name, artifact_bytes[name])
            for name in sorted(declared)
        )
        prepared_artifact = (
            ArtifactDigest.from_bytes(
                "prepared_payload", prepared_payload_bytes, role="prepared_payload"
            )
            if prepared_payload_bytes is not None
            else None
        )
        env = tuple((str(k), str(v)) for k, v in (environment or {}).items())
        return cls(
            problem_id=prepared.problem.problem_id,
            problem_digest=canonical_record_digest(prepared.problem.to_dict()),
            solver=prepared.solver,
            settings_digest=canonical_record_digest(prepared.settings.to_dict()),
            raw_output_digest=canonical_record_digest(raw.to_dict()),
            artifacts=artifacts,
            data_references=raw.data_references,
            environment=env,
            preparation_notes=prepared.notes,
            prepared_payload=prepared_artifact,
            realization_id=realization_id,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExecutionManifest":
        require_schema(payload, EXECUTION_MANIFEST_SCHEMA)
        prepared_payload = payload.get("prepared_payload")
        record = cls(
            problem_id=payload["problem_id"],
            problem_digest=payload["problem_digest"],
            solver=SolverIdentity.from_dict(payload["solver"]),
            settings_digest=payload["settings_digest"],
            raw_output_digest=payload["raw_output_digest"],
            artifacts=tuple(ArtifactDigest.from_dict(v) for v in payload.get("artifacts", ())),
            data_references=tuple(
                ScientificDataReference.from_dict(v)
                for v in payload.get("data_references", ())
            ),
            environment=tuple(tuple(v) for v in payload.get("environment", ())),
            preparation_notes=tuple(payload.get("preparation_notes", ())),
            prepared_payload=(
                ArtifactDigest.from_dict(prepared_payload) if prepared_payload else None
            ),
            realization_id=payload.get("realization_id"),
        )
        claimed = payload.get("manifest_digest")
        if claimed is None:
            raise ScientificCoreError("serialized execution manifest is missing manifest_digest")
        if _hex_digest(claimed, label="manifest_digest") != record.manifest_digest:
            raise ScientificCoreError(
                "execution manifest digest mismatch: serialized content was changed after attestation"
            )
        if payload.get("coverage", record.coverage) != record.coverage:
            raise ScientificCoreError("execution manifest coverage does not match its payload")
        return record

    def verify_execution(
        self,
        prepared: PreparedSolve,
        raw: RawSolverOutput,
        *,
        artifact_bytes: Mapping[str, bytes] | None = None,
        prepared_payload_bytes: bytes | None = None,
        environment: Mapping[str, str] | None = None,
        realization_id: str | None = None,
    ) -> None:
        current = type(self).from_execution(
            prepared,
            raw,
            artifact_bytes=artifact_bytes,
            prepared_payload_bytes=prepared_payload_bytes,
            environment=environment,
            realization_id=realization_id,
        )
        if current != self:
            raise ScientificCoreError(
                "execution manifest does not match the supplied execution records/artifacts"
            )


__all__ = ["ArtifactDigest", "ExecutionManifest", "canonical_record_digest"]
