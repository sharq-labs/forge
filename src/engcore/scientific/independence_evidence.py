"""Artifact-backed evidence for cross-solver route independence.

``consensus.RouteDependencies`` answers *what* each route says it uses and the
core checks that declaration against domain pins. That is stronger than route
labels, but a declaration can still be wrong about the world: two wrappers may
name different implementations while loading the same binary/image/source
artifact.

Each route therefore binds artifact byte identities to the dependency
declaration it is evidence for. Strong independence requires evidence for every
canonical dependency identity in every solver-independence dimension, not just
one artifact for the dimension as a whole. The evidence must name the exact
dependency digest carried by the route, every artifact must explicitly bind to
a dependency identity declared in that dimension, the declared artifact
digests are freshly recomputed from supplied bytes, and no verified artifact
digest may be shared between two routes.

A digest string by itself is never evidence here. Serialized fingerprints are
portable declarations of expected byte identity; callers must present the bytes
again at the trust boundary before those fingerprints can influence a
``CROSS_SOLVER_VALIDATED`` claim. Legacy fingerprints without a dependency
binding remain readable, but they cannot establish strong independence. Byte
hashing reuses
:class:`~engcore.scientific.results.execution_manifest.ArtifactDigest`, so the
execution manifest and independence gate cannot disagree about artifact byte
identity.

A digest proves byte identity, not semantic independence. Different digests do
not prove independent development, so this remains an additional gate rather
than a replacement for declaration-level checks.
"""

from __future__ import annotations

from collections.abc import Mapping as RuntimeMapping
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .consensus import (
    IndependenceDimension,
    SOLVER_INDEPENDENCE_DIMENSIONS,
    SolveRoute,
    canonical_component_identity,
)
from .errors import ScientificValidationError
from .results.execution_manifest import ArtifactDigest
from .results.immutable import freeze
from .serialization import require_schema, schema_string

ARTIFACT_FINGERPRINT_SCHEMA = schema_string("route_artifact_fingerprint")
ROUTE_EVIDENCE_SCHEMA = schema_string("route_independence_evidence")
INDEPENDENCE_EVIDENCE_REPORT_SCHEMA = schema_string("independence_evidence_report")


def _digest(value: Any, *, label: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ScientificValidationError(
            f"{label} must be a 64-character SHA-256 hex digest, got {value!r}"
        )
    return text


def _artifact_digest(name: str, payload: bytes) -> str:
    """Byte identity under the same contract as execution manifests."""
    return ArtifactDigest.from_bytes(name, payload, role="independence").digest


def _normalise_artifact_bytes(
    supplied: Mapping[IndependenceDimension, Mapping[str, bytes]] | None,
) -> dict[IndependenceDimension, Mapping[str, bytes]]:
    if supplied is None:
        return {}
    if not isinstance(supplied, RuntimeMapping):
        raise ScientificValidationError(
            "artifact bytes for a route must be a mapping by independence dimension"
        )
    normalised: dict[IndependenceDimension, Mapping[str, bytes]] = {}
    for raw_dimension, raw_items in supplied.items():
        try:
            dimension = IndependenceDimension(raw_dimension)
        except ValueError:
            raise ScientificValidationError(
                f"artifact bytes name unknown independence dimension {raw_dimension!r}"
            ) from None
        if not isinstance(raw_items, RuntimeMapping):
            raise ScientificValidationError(
                f"artifact bytes for {dimension.value} must be a mapping from "
                "artifact name to bytes"
            )
        normalised[dimension] = raw_items
    return normalised


@dataclass(frozen=True, order=True)
class ArtifactFingerprint:
    """Expected byte identity of one implementation/runtime artifact.

    ``dependency_identity`` names the exact canonical route dependency this
    artifact evidences. It is additive on the wire: an older fingerprint can be
    deserialized with no binding, but an unbound fingerprint is deliberately
    insufficient for strong independence.

    The direct constructor stays available because fingerprints must deserialize
    without carrying bulk bytes. Construction validates only the declaration;
    trust is established later by re-hashing supplied bytes.
    """

    digest: str
    name: str = field(compare=False)
    kind: str = field(default="artifact", compare=False)
    algorithm: str = field(default="sha256", compare=False)
    dependency_identity: str = field(default="")

    def __post_init__(self) -> None:
        name, kind = str(self.name).strip(), str(self.kind).strip()
        if not name or not kind:
            raise ScientificValidationError("artifact fingerprint requires name and kind")
        if self.algorithm != "sha256":
            raise ScientificValidationError(
                f"unsupported artifact fingerprint algorithm {self.algorithm!r}"
            )
        raw_identity = str(self.dependency_identity or "").strip()
        if raw_identity:
            dependency_identity = canonical_component_identity(raw_identity)
        else:
            dependency_identity = ""
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "dependency_identity", dependency_identity)
        object.__setattr__(self, "digest", _digest(self.digest, label="artifact fingerprint"))

    @classmethod
    def from_bytes(
        cls,
        name: str,
        payload: bytes,
        *,
        kind: str = "artifact",
        dependency_identity: str | None = None,
    ) -> "ArtifactFingerprint":
        if not isinstance(payload, bytes):
            raise ScientificValidationError(
                f"artifact {name!r} payload must be bytes; got {type(payload).__name__}"
            )
        return cls(
            digest=_artifact_digest(name, payload),
            name=name,
            kind=kind,
            dependency_identity=dependency_identity or "",
        )

    def verifies(self, payload: bytes) -> bool:
        return isinstance(payload, bytes) and _artifact_digest(self.name, payload) == self.digest

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema": ARTIFACT_FINGERPRINT_SCHEMA,
            "digest": self.digest,
            "name": self.name,
            "kind": self.kind,
            "algorithm": self.algorithm,
        }
        if self.dependency_identity:
            payload["dependency_identity"] = self.dependency_identity
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactFingerprint":
        require_schema(payload, ARTIFACT_FINGERPRINT_SCHEMA)
        return cls(
            digest=payload["digest"],
            name=payload["name"],
            kind=payload.get("kind", "artifact"),
            algorithm=payload.get("algorithm", "sha256"),
            dependency_identity=payload.get("dependency_identity", ""),
        )


@dataclass(frozen=True)
class RouteIndependenceEvidence:
    """Artifact declarations for one exact ``RouteDependencies`` declaration."""

    route_id: str
    dependency_digest: str
    artifacts: Mapping[IndependenceDimension, frozenset[ArtifactFingerprint]]

    def __post_init__(self) -> None:
        route_id = str(self.route_id).strip()
        if not route_id:
            raise ScientificValidationError("route independence evidence needs route_id")
        object.__setattr__(self, "route_id", route_id)
        object.__setattr__(
            self, "dependency_digest", _digest(self.dependency_digest, label="dependency_digest")
        )
        normalized: dict[IndependenceDimension, frozenset[ArtifactFingerprint]] = {}
        for raw_dimension, raw_artifacts in dict(self.artifacts).items():
            try:
                dimension = IndependenceDimension(raw_dimension)
            except ValueError:
                raise ScientificValidationError(
                    f"artifact evidence names unknown independence dimension {raw_dimension!r}"
                ) from None
            values = frozenset(raw_artifacts)
            if any(not isinstance(item, ArtifactFingerprint) for item in values):
                raise ScientificValidationError(
                    f"artifact evidence for {dimension.value} must contain ArtifactFingerprint records"
                )
            normalized[dimension] = values
        object.__setattr__(self, "artifacts", freeze(normalized))

    def evidence_gap(
        self,
        route: SolveRoute,
        artifact_bytes: Mapping[IndependenceDimension, Mapping[str, bytes]] | None = None,
    ) -> tuple[str, ...]:
        """Return every reason this evidence cannot establish independence.

        Every declared fingerprint is recomputed from bytes during assessment,
        and every canonical dependency identity in each solver-independence
        dimension must be covered by at least one explicitly bound fingerprint.
        Different caller-supplied hex strings or one artifact standing in for an
        entire dimension can therefore no longer manufacture independence.
        """
        reasons: list[str] = []
        canonical_dependencies: dict[
            IndependenceDimension, frozenset[str]
        ] | None = None
        if route.route_id != self.route_id:
            reasons.append(
                f"evidence is for route {self.route_id!r}, not {route.route_id!r}"
            )
        if route.dependencies is None:
            reasons.append("route declares no dependencies")
        else:
            try:
                canonical_dependencies = route.dependencies.canonical()
                actual = route.dependencies.digest
            except ScientificValidationError as exc:
                reasons.append(f"route dependencies cannot be resolved ({exc})")
            else:
                if actual != self.dependency_digest:
                    reasons.append(
                        f"evidence binds dependency digest {self.dependency_digest[:12]}…, "
                        f"route declares {actual[:12]}…"
                    )

        supplied = _normalise_artifact_bytes(artifact_bytes)
        for dimension in SOLVER_INDEPENDENCE_DIMENSIONS:
            fingerprints = self.artifacts.get(dimension)
            if not fingerprints:
                reasons.append(
                    f"no artifact evidence for required dimension {dimension.value}"
                )
                continue

            declared_identities = (
                canonical_dependencies.get(dimension, frozenset())
                if canonical_dependencies is not None
                else frozenset()
            )
            covered_identities: set[str] = set()
            for artifact in sorted(fingerprints):
                if not artifact.dependency_identity:
                    reasons.append(
                        f"{dimension.value} artifact {artifact.name!r} is not bound to "
                        "a dependency identity"
                    )
                elif declared_identities and artifact.dependency_identity not in declared_identities:
                    reasons.append(
                        f"{dimension.value} artifact {artifact.name!r} binds undeclared "
                        f"dependency identity {artifact.dependency_identity!r}"
                    )
                else:
                    covered_identities.add(artifact.dependency_identity)

            if canonical_dependencies is not None:
                for identity in sorted(declared_identities - covered_identities):
                    reasons.append(
                        f"no artifact evidence bound to dependency identity {identity!r} "
                        f"in required dimension {dimension.value}"
                    )

            dimension_bytes = supplied.get(dimension)
            if dimension_bytes is None:
                reasons.append(
                    f"no artifact bytes supplied for required dimension {dimension.value}"
                )
                continue
            for artifact in sorted(fingerprints):
                if artifact.name not in dimension_bytes:
                    reasons.append(
                        f"no bytes supplied for {dimension.value} artifact {artifact.name!r}"
                    )
                    continue
                raw = dimension_bytes[artifact.name]
                if not isinstance(raw, bytes):
                    reasons.append(
                        f"bytes for {dimension.value} artifact {artifact.name!r} are "
                        f"{type(raw).__name__}, not bytes"
                    )
                    continue
                actual_digest = _artifact_digest(artifact.name, raw)
                if actual_digest != artifact.digest:
                    reasons.append(
                        f"{dimension.value} artifact {artifact.name!r} declares "
                        f"sha256:{artifact.digest[:12]}… but supplied bytes hash to "
                        f"sha256:{actual_digest[:12]}…"
                    )
        return tuple(reasons)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ROUTE_EVIDENCE_SCHEMA,
            "route_id": self.route_id,
            "dependency_digest": self.dependency_digest,
            "artifacts": {
                dimension.value: [item.to_dict() for item in sorted(items)]
                for dimension, items in sorted(
                    self.artifacts.items(), key=lambda item: item[0].value
                )
            },
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RouteIndependenceEvidence":
        require_schema(payload, ROUTE_EVIDENCE_SCHEMA)
        return cls(
            route_id=payload["route_id"],
            dependency_digest=payload["dependency_digest"],
            artifacts={
                IndependenceDimension(dimension): frozenset(
                    ArtifactFingerprint.from_dict(item) for item in items
                )
                for dimension, items in dict(payload.get("artifacts") or {}).items()
            },
        )


@dataclass(frozen=True)
class SharedArtifact:
    digest: str
    routes: tuple[str, ...]
    dimensions: tuple[str, ...]
    names: tuple[str, ...]


@dataclass(frozen=True)
class IndependenceEvidenceReport:
    route_findings: tuple[tuple[str, tuple[str, ...]], ...]
    shared_artifacts: tuple[SharedArtifact, ...]

    @property
    def all_routes_verified(self) -> bool:
        return bool(self.route_findings) and all(not reasons for _, reasons in self.route_findings)

    @property
    def artifact_disjoint(self) -> bool:
        return not self.shared_artifacts

    @property
    def strongly_independent(self) -> bool:
        return self.all_routes_verified and self.artifact_disjoint and len(self.route_findings) >= 2

    @property
    def reason(self) -> str:
        if len(self.route_findings) < 2:
            return "at least two routes are required for an independence statement"
        failures = [(route, reasons) for route, reasons in self.route_findings if reasons]
        if failures:
            return f"artifact evidence is incomplete, unverified or mismatched for routes {failures}"
        if self.shared_artifacts:
            labels = [
                f"{item.digest[:12]}… shared by {list(item.routes)} as {list(item.names)}"
                for item in self.shared_artifacts
            ]
            return f"routes share implementation/runtime artifacts: {labels}"
        return (
            "every route binds verified artifact bytes to every declared dependency identity "
            "and no verified artifact digest is shared; this strengthens the declaration-level "
            "independence claim but does not prove independent development"
        )


def assess_independence_evidence(
    routes: Sequence[SolveRoute],
    evidence: Sequence[RouteIndependenceEvidence],
    *,
    artifact_bytes: Mapping[
        str, Mapping[IndependenceDimension, Mapping[str, bytes]]
    ] | None = None,
) -> IndependenceEvidenceReport:
    """Evaluate artifact-backed independence for an exact set of routes."""
    routes = tuple(routes)
    evidence = tuple(evidence)
    route_ids = [route.route_id for route in routes]
    if len(set(route_ids)) != len(route_ids):
        raise ScientificValidationError("independence evidence cannot assess duplicate route ids")
    evidence_ids = [item.route_id for item in evidence]
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ScientificValidationError("independence evidence contains duplicate route ids")

    by_id = {item.route_id: item for item in evidence}
    extra = sorted(set(by_id) - set(route_ids))
    if extra:
        raise ScientificValidationError(
            f"independence evidence supplied for routes not being compared: {extra}"
        )

    bytes_by_route = dict(artifact_bytes or {})
    extra_bytes = sorted(set(bytes_by_route) - set(route_ids))
    if extra_bytes:
        raise ScientificValidationError(
            f"artifact bytes supplied for routes not being compared: {extra_bytes}"
        )

    findings: list[tuple[str, tuple[str, ...]]] = []
    observed: dict[str, dict[str, list[tuple[IndependenceDimension, ArtifactFingerprint]]]] = {}
    for route in routes:
        item = by_id.get(route.route_id)
        if item is None:
            findings.append((route.route_id, ("no artifact evidence supplied",)))
            continue
        gaps = item.evidence_gap(route, bytes_by_route.get(route.route_id))
        findings.append((route.route_id, gaps))
        if gaps:
            continue
        for dimension in SOLVER_INDEPENDENCE_DIMENSIONS:
            for artifact in item.artifacts[dimension]:
                observed.setdefault(artifact.digest, {}).setdefault(route.route_id, []).append(
                    (dimension, artifact)
                )

    shared: list[SharedArtifact] = []
    for digest, per_route in observed.items():
        if len(per_route) < 2:
            continue
        dimensions = sorted(
            {dimension.value for entries in per_route.values() for dimension, _ in entries}
        )
        names = sorted({artifact.name for entries in per_route.values() for _, artifact in entries})
        shared.append(
            SharedArtifact(
                digest=digest,
                routes=tuple(sorted(per_route)),
                dimensions=tuple(dimensions),
                names=tuple(names),
            )
        )
    shared.sort(key=lambda item: item.digest)
    return IndependenceEvidenceReport(tuple(sorted(findings)), tuple(shared))


def require_strong_independence(
    routes: Sequence[SolveRoute],
    evidence: Sequence[RouteIndependenceEvidence],
    *,
    artifact_bytes: Mapping[
        str, Mapping[IndependenceDimension, Mapping[str, bytes]]
    ] | None = None,
) -> IndependenceEvidenceReport:
    report = assess_independence_evidence(
        routes,
        evidence,
        artifact_bytes=artifact_bytes,
    )
    if not report.strongly_independent:
        raise ScientificValidationError(
            f"strong solver-independence evidence not established: {report.reason}"
        )
    return report


__all__ = [
    "ArtifactFingerprint",
    "RouteIndependenceEvidence",
    "SharedArtifact",
    "IndependenceEvidenceReport",
    "assess_independence_evidence",
    "require_strong_independence",
]
