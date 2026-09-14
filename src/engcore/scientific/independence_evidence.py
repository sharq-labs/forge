"""Artifact-backed evidence for cross-solver route independence.

``consensus.RouteDependencies`` answers *what* each route says it uses and the
core checks that declaration against domain pins.  That is stronger than route
labels, but a declaration can still be wrong about the world: two wrappers may
name different implementations while loading the same binary/image/source
artifact.

This module adds a second, deliberately conservative layer.  Each route binds
artifact byte identities to the dependency declaration it is evidence for.  A
strong-independence report is available only when every solver-independence
dimension has artifact evidence, the evidence names the exact dependency digest
carried by the route, and no artifact digest is shared between two routes.

A digest proves byte identity, not semantic independence.  Different digests do
*not* prove two pieces of software were independently developed.  Therefore the
result is named ``artifact_disjoint``/``strongly_independent`` and is suitable
as an additional gate, never as a replacement for the declaration-level checks
already performed by :mod:`engcore.scientific.consensus`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .consensus import (
    IndependenceDimension,
    SOLVER_INDEPENDENCE_DIMENSIONS,
    SolveRoute,
)
from .errors import ScientificValidationError
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


@dataclass(frozen=True, order=True)
class ArtifactFingerprint:
    """Byte identity of one implementation/runtime artifact.

    ``name`` is descriptive and never decides equality across routes; ``digest``
    is the load-bearing identity.  ``kind`` keeps reports readable (source,
    binary, container, library, generated-code, ...), but is intentionally an
    open string because the core cannot enumerate every packaging technology.
    """

    digest: str
    name: str = field(compare=False)
    kind: str = field(default="artifact", compare=False)
    algorithm: str = field(default="sha256", compare=False)

    def __post_init__(self) -> None:
        name, kind = str(self.name).strip(), str(self.kind).strip()
        if not name or not kind:
            raise ScientificValidationError("artifact fingerprint requires name and kind")
        if self.algorithm != "sha256":
            raise ScientificValidationError(
                f"unsupported artifact fingerprint algorithm {self.algorithm!r}"
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "digest", _digest(self.digest, label="artifact fingerprint"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ARTIFACT_FINGERPRINT_SCHEMA,
            "digest": self.digest,
            "name": self.name,
            "kind": self.kind,
            "algorithm": self.algorithm,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactFingerprint":
        require_schema(payload, ARTIFACT_FINGERPRINT_SCHEMA)
        return cls(
            digest=payload["digest"],
            name=payload["name"],
            kind=payload.get("kind", "artifact"),
            algorithm=payload.get("algorithm", "sha256"),
        )


@dataclass(frozen=True)
class RouteIndependenceEvidence:
    """Artifact evidence for one exact ``RouteDependencies`` declaration."""

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

    def evidence_gap(self, route: SolveRoute) -> tuple[str, ...]:
        reasons: list[str] = []
        if route.route_id != self.route_id:
            reasons.append(
                f"evidence is for route {self.route_id!r}, not {route.route_id!r}"
            )
        if route.dependencies is None:
            reasons.append("route declares no dependencies")
        else:
            try:
                actual = route.dependencies.digest
            except ScientificValidationError as exc:
                reasons.append(f"route dependencies cannot be resolved ({exc})")
            else:
                if actual != self.dependency_digest:
                    reasons.append(
                        f"evidence binds dependency digest {self.dependency_digest[:12]}…, "
                        f"route declares {actual[:12]}…"
                    )
        for dimension in SOLVER_INDEPENDENCE_DIMENSIONS:
            if not self.artifacts.get(dimension):
                reasons.append(
                    f"no artifact evidence for required dimension {dimension.value}"
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
            return f"artifact evidence is incomplete or mismatched for routes {failures}"
        if self.shared_artifacts:
            labels = [
                f"{item.digest[:12]}… shared by {list(item.routes)} as {list(item.names)}"
                for item in self.shared_artifacts
            ]
            return f"routes share implementation/runtime artifacts: {labels}"
        return (
            "every route binds artifact evidence to its declared dependencies and "
            "no artifact digest is shared; this strengthens the declaration-level "
            "independence claim but does not prove independent development"
        )


def assess_independence_evidence(
    routes: Sequence[SolveRoute],
    evidence: Sequence[RouteIndependenceEvidence],
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

    findings: list[tuple[str, tuple[str, ...]]] = []
    # digest -> route -> [(dimension, fingerprint)]
    observed: dict[str, dict[str, list[tuple[IndependenceDimension, ArtifactFingerprint]]]] = {}
    for route in routes:
        item = by_id.get(route.route_id)
        if item is None:
            findings.append((route.route_id, ("no artifact evidence supplied",)))
            continue
        gaps = item.evidence_gap(route)
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
    routes: Sequence[SolveRoute], evidence: Sequence[RouteIndependenceEvidence]
) -> IndependenceEvidenceReport:
    report = assess_independence_evidence(routes, evidence)
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
