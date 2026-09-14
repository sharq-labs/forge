"""Artifact-backed evidence for cross-solver route independence.

``consensus.RouteDependencies`` answers *what* each route says it uses and the
core checks that declaration against domain pins. That is stronger than route
labels, but a declaration can still be wrong about the world: two wrappers may
name different implementations while loading the same binary/image/source
artifact.

Each route therefore presents artifact bytes as evidence for the dependency
declaration it carries. What a route's evidence establishes, and in what order:

1. the evidence names the exact dependency digest the route carries;
2. every artifact is explicitly bound to one dependency identity, and that
   binding canonicalises to an identity the route declares in the same
   solver-independence dimension;
3. bytes for the artifact were supplied, are ``bytes``, and re-hash to the
   fingerprint's digest;
4. ONLY THEN is that canonical dependency identity counted as evidenced;
5. every canonical dependency identity in every solver-independence dimension is
   evidenced this way;
6. within the route, one verified artifact byte identity evidences at most one
   canonical dependency identity. Dependencies that are one artifact are one
   dependency, and must be declared as one;
7. across the compared routes, no verified artifact digest is shared.

Rules 6 and 7 are different rules. Rule 6 stops one genuine artifact, presented
several times under several labels, from standing in for several dependencies
of the same route. Rule 7 stops two routes from sharing machinery under
different labels.

A digest string by itself is never evidence here. Serialized fingerprints are
portable declarations of expected byte identity; callers must present the bytes
again at the trust boundary before those fingerprints can influence a
``CROSS_SOLVER_VALIDATED`` claim. A fingerprint stores its dependency binding
as declared and is canonicalised only at assessment, so reading a record never
imports anything and stays readable where the named dependency is not
installed. Legacy fingerprints without a binding remain readable and cannot
establish independence. Byte hashing reuses
:class:`~engcore.scientific.results.execution_manifest.ArtifactDigest`, so the
execution manifest and independence gate cannot disagree about artifact byte
identity.

What this does NOT establish
----------------------------
The bytes are presented by the caller. Nothing here observes the solver loading
or executing them, so verified artifact identity is not proof of runtime use.
A digest proves byte identity, not semantic independence: different digests do
not prove independent development or an independent scientific formulation.
This remains an additional gate beside the declaration-level checks, not a
replacement for them. Runtime-use attestation is a separate, later mechanism.
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

    ``dependency_identity`` names the route dependency this artifact is presented
    as evidence for. It is stored as declared (trimmed) and is deliberately NOT
    canonicalised here: canonicalising a ``py:`` identity imports the module it
    names, and reading a record must neither run import-time code chosen by the
    record nor fail where that dependency is not installed.
    :meth:`canonical_dependency_identity` resolves it at the trust boundary.

    ``None`` and a blank string mean unbound, which is what a fingerprint written
    before bindings existed deserialises to; an unbound fingerprint can never
    establish independence. Any other non-string value is refused rather than
    read as unbound.

    The binding participates in equality and hashing: the same bytes bound to
    two identities are two records, so an assessment can see -- and name -- a
    single artifact presented as evidence for two dependencies.

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
        declared = self.dependency_identity
        if declared is None:
            binding = ""
        elif isinstance(declared, str):
            binding = str(declared).strip()
        else:
            raise ScientificValidationError(
                "artifact fingerprint dependency_identity must be a string, or None "
                f"for an unbound legacy fingerprint; got {type(declared).__name__} "
                f"{declared!r}"
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "dependency_identity", binding)
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
            dependency_identity=dependency_identity,
        )

    def verifies(self, payload: bytes) -> bool:
        return isinstance(payload, bytes) and _artifact_digest(self.name, payload) == self.digest

    def canonical_dependency_identity(self) -> str | None:
        """The authoritative spelling of the binding, or ``None`` when unbound.

        Resolves ``py:`` identities to the object they name, which imports that
        module: call this at the trust boundary, never while reading a record.
        Raises :class:`ScientificValidationError` when the binding cannot be
        canonicalised.
        """
        if not self.dependency_identity:
            return None
        return canonical_component_identity(self.dependency_identity)

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
            dependency_identity=payload.get("dependency_identity"),
        )


@dataclass(frozen=True)
class RouteEvidenceAssessment:
    """What one route's artifact evidence established, dependency by dependency.

    ``covered`` holds, per solver-independence dimension, the canonical dependency
    identities whose bound artifact bytes were re-hashed and matched -- nothing is
    in it on the strength of a label alone. ``artifact_identities`` maps each
    verified artifact digest to the canonical identities it was presented as
    evidence for across the whole route; more than one is a refusal. ``reasons``
    is every reason the evidence cannot support independence, empty when it can.
    """

    route_id: str
    covered: Mapping[IndependenceDimension, frozenset[str]]
    artifact_identities: Mapping[str, frozenset[str]]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "covered", freeze(dict(self.covered)))
        object.__setattr__(self, "artifact_identities", freeze(dict(self.artifact_identities)))
        object.__setattr__(self, "reasons", tuple(self.reasons))

    @property
    def verified(self) -> bool:
        return not self.reasons


def _declared_binding(
    artifact: ArtifactFingerprint,
    dimension: IndependenceDimension,
    declared_identities: frozenset[str],
    reasons: list[str],
) -> str | None:
    """The canonical identity ``artifact`` validly binds in ``dimension``, or ``None``."""
    if not artifact.dependency_identity:
        reasons.append(
            f"{dimension.value} artifact {artifact.name!r} is not bound to "
            "a dependency identity"
        )
        return None
    try:
        identity = canonical_component_identity(artifact.dependency_identity)
    except ScientificValidationError as exc:
        reasons.append(
            f"{dimension.value} artifact {artifact.name!r} binds dependency identity "
            f"{artifact.dependency_identity!r}, which cannot be canonicalised ({exc})"
        )
        return None
    if identity not in declared_identities:
        reasons.append(
            f"{dimension.value} artifact {artifact.name!r} binds undeclared "
            f"dependency identity {identity!r}"
        )
        return None
    return identity


def _verified_against_bytes(
    artifact: ArtifactFingerprint,
    dimension: IndependenceDimension,
    dimension_bytes: Mapping[str, bytes] | None,
    reasons: list[str],
) -> bool:
    """True only when bytes were supplied, are ``bytes`` and re-hash to the digest."""
    if dimension_bytes is None:
        return False  # the dimension-level reason is recorded once by the caller
    if artifact.name not in dimension_bytes:
        reasons.append(
            f"no bytes supplied for {dimension.value} artifact {artifact.name!r}"
        )
        return False
    raw = dimension_bytes[artifact.name]
    if not isinstance(raw, bytes):
        reasons.append(
            f"bytes for {dimension.value} artifact {artifact.name!r} are "
            f"{type(raw).__name__}, not bytes"
        )
        return False
    actual_digest = _artifact_digest(artifact.name, raw)
    if actual_digest != artifact.digest:
        reasons.append(
            f"{dimension.value} artifact {artifact.name!r} declares "
            f"sha256:{artifact.digest[:12]}… but supplied bytes hash to "
            f"sha256:{actual_digest[:12]}…"
        )
        return False
    return True


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

    def assess(
        self,
        route: SolveRoute,
        artifact_bytes: Mapping[IndependenceDimension, Mapping[str, bytes]] | None = None,
    ) -> RouteEvidenceAssessment:
        """Assess this evidence against ``route`` and freshly supplied bytes.

        For each fingerprint, in this order: the binding must canonicalise to an
        identity the route declares in that dimension; bytes must be supplied, be
        ``bytes``, and re-hash to the fingerprint's digest. Only a fingerprint that
        passes every step adds its canonical identity to the coverage, so an
        unverified artifact contributes nothing. Then every declared identity must
        be covered, and no verified digest may be presented for two identities
        anywhere in the route.
        """
        reasons: list[str] = []
        declared: dict[IndependenceDimension, frozenset[str]] | None = None
        if route.route_id != self.route_id:
            reasons.append(
                f"evidence is for route {self.route_id!r}, not {route.route_id!r}"
            )
        if route.dependencies is None:
            reasons.append("route declares no dependencies")
        else:
            try:
                declared = route.dependencies.canonical()
                actual = route.dependencies.digest
            except ScientificValidationError as exc:
                declared = None
                reasons.append(f"route dependencies cannot be resolved ({exc})")
            else:
                if actual != self.dependency_digest:
                    reasons.append(
                        f"evidence binds dependency digest {self.dependency_digest[:12]}…, "
                        f"route declares {actual[:12]}…"
                    )

        supplied = _normalise_artifact_bytes(artifact_bytes)
        covered: dict[IndependenceDimension, frozenset[str]] = {}
        # verified digest -> canonical identity -> where it was presented, route-wide
        presented: dict[str, dict[str, set[str]]] = {}
        for dimension in SOLVER_INDEPENDENCE_DIMENSIONS:
            declared_identities = (
                declared.get(dimension, frozenset()) if declared is not None else frozenset()
            )
            covered_identities: set[str] = set()
            fingerprints = self.artifacts.get(dimension)
            if not fingerprints:
                reasons.append(
                    f"no artifact evidence for required dimension {dimension.value}"
                )
            else:
                dimension_bytes = supplied.get(dimension)
                if dimension_bytes is None:
                    reasons.append(
                        f"no artifact bytes supplied for required dimension {dimension.value}"
                    )
                for artifact in sorted(fingerprints):
                    identity = _declared_binding(artifact, dimension, declared_identities, reasons)
                    if not _verified_against_bytes(artifact, dimension, dimension_bytes, reasons):
                        continue
                    if identity is None:
                        continue
                    covered_identities.add(identity)
                    presented.setdefault(artifact.digest, {}).setdefault(identity, set()).add(
                        f"{dimension.value}:{artifact.name}"
                    )
            if declared is not None:
                for identity in sorted(declared_identities - covered_identities):
                    reasons.append(
                        f"no artifact evidence bound to dependency identity {identity!r} "
                        f"in required dimension {dimension.value} was verified against "
                        "supplied bytes"
                    )
            covered[dimension] = frozenset(covered_identities)

        for digest, by_identity in sorted(presented.items()):
            if len(by_identity) > 1:
                where = sorted(place for places in by_identity.values() for place in places)
                reasons.append(
                    f"one verified artifact sha256:{digest[:12]}… is presented as evidence "
                    f"for {len(by_identity)} distinct dependency identities "
                    f"{sorted(by_identity)} (as {where}); one verified artifact byte "
                    "identity cannot establish more than one declared dependency. "
                    "Dependencies that are one artifact must be declared as one "
                    "dependency identity"
                )

        return RouteEvidenceAssessment(
            route_id=self.route_id,
            covered=covered,
            artifact_identities={
                digest: frozenset(by_identity) for digest, by_identity in presented.items()
            },
            reasons=tuple(reasons),
        )

    def evidence_gap(
        self,
        route: SolveRoute,
        artifact_bytes: Mapping[IndependenceDimension, Mapping[str, bytes]] | None = None,
    ) -> tuple[str, ...]:
        """Return every reason this evidence cannot establish independence.

        See :meth:`assess`, which this reads: coverage accrues only from
        re-hashed bytes, every declared identity must be covered, and one verified
        artifact cannot stand in for several dependencies.
        """
        return self.assess(route, artifact_bytes).reasons

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
        """Every compared route's evidence passed :meth:`RouteIndependenceEvidence.assess`.

        Verified means the caller-presented bytes re-hashed to the declared
        fingerprints under the binding rules -- not that any route used them.
        """
        return bool(self.route_findings) and all(not reasons for _, reasons in self.route_findings)

    @property
    def artifact_disjoint(self) -> bool:
        """No verified artifact digest is shared between two compared routes."""
        return not self.shared_artifacts

    @property
    def strongly_independent(self) -> bool:
        """At least two routes, every route verified, and no verified digest shared.

        The name predates this evidence's scope and overstates it. True means the
        artifact evidence is complete, per-dependency, byte-verified and disjoint:
        identity evidence about caller-presented artifacts. It does not mean the
        routes were observed using those artifacts, nor that they are
        semantically, developmentally or scientifically independent.
        """
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
            "every route binds its exact dependency declaration; every declared "
            "dependency identity is evidenced by its own artifact whose presented "
            "bytes were re-hashed; no verified artifact evidences two dependency "
            "identities within a route, and no verified artifact digest is shared "
            "between routes. This is identity evidence about caller-presented "
            "artifact bytes: it does not show the routes used those artifacts at "
            "runtime, and it does not prove semantic independence, independent "
            "development or an independent scientific formulation"
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
    "RouteEvidenceAssessment",
    "RouteIndependenceEvidence",
    "SharedArtifact",
    "IndependenceEvidenceReport",
    "assess_independence_evidence",
    "require_strong_independence",
]
