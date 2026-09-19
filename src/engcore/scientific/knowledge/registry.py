from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ..errors import InvalidScientificProblem
from .claim import KnowledgeClaim
from .query import KnowledgeQuery
from .resolution import KnowledgeSetAssessment, assess_knowledge_set
from .snapshot import KnowledgeSnapshot
from .source import KnowledgeSource
from .versioning import SourceSupersession, SourceVersionKey


@dataclass(frozen=True)
class ScientificKnowledgeRegistry:
    """Immutable in-memory registry of pinned knowledge records.

    The registry is intentionally offline.  Fetching/parsing external material
    belongs outside this class; only content-addressed source and claim records
    enter here.
    """

    sources: tuple[KnowledgeSource, ...] = ()
    claims: tuple[KnowledgeClaim, ...] = ()
    supersessions: tuple[SourceSupersession, ...] = ()

    def __post_init__(self) -> None:
        sources = tuple(self.sources)
        claims = tuple(self.claims)
        supersessions = tuple(self.supersessions)
        source_keys = [
            (s.source_id, s.issuer, s.version, s.document_digest) for s in sources
        ]
        if len(source_keys) != len(set(source_keys)):
            raise InvalidScientificProblem(
                "knowledge registry contains duplicate source versions"
            )
        claim_ids = [c.claim_id for c in claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise InvalidScientificProblem(
                "knowledge registry contains duplicate claim ids"
            )

        by_exact = {
            (s.source_id, s.document_digest): s
            for s in sources
        }
        for claim in claims:
            if (claim.source_id, claim.source_document_digest) not in by_exact:
                raise InvalidScientificProblem(
                    f"claim {claim.claim_id!r} references a source version "
                    "not present in the registry"
                )

        known_versions = {SourceVersionKey.from_source(s) for s in sources}
        successor_of: dict[SourceVersionKey, SourceVersionKey] = {}
        for relation in supersessions:
            if relation.predecessor not in known_versions:
                raise InvalidScientificProblem(
                    "source supersession predecessor is absent from registry"
                )
            if relation.successor not in known_versions:
                raise InvalidScientificProblem(
                    "source supersession successor is absent from registry"
                )
            if relation.predecessor in successor_of:
                raise InvalidScientificProblem(
                    "one source version has multiple declared successors"
                )
            successor_of[relation.predecessor] = relation.successor

        # Refuse supersession cycles.  A version history is a lineage, not a
        # graph in which "latest" can loop back to an old document.
        for start in successor_of:
            seen = set()
            current = start
            while current in successor_of:
                if current in seen:
                    raise InvalidScientificProblem(
                        "knowledge source supersession lineage contains a cycle"
                    )
                seen.add(current)
                current = successor_of[current]

        object.__setattr__(self, "sources", sources)
        object.__setattr__(self, "claims", claims)
        object.__setattr__(self, "supersessions", supersessions)

    def query(self, query: KnowledgeQuery) -> tuple[KnowledgeClaim, ...]:
        if not isinstance(query, KnowledgeQuery):
            raise TypeError("query must be KnowledgeQuery")
        return tuple(
            sorted(
                (claim for claim in self.claims if query.matches(claim)),
                key=lambda c: c.claim_id,
            )
        )

    def assess(self, query: KnowledgeQuery) -> KnowledgeSetAssessment:
        return assess_knowledge_set(self.query(query))

    def active_sources(self) -> tuple[KnowledgeSource, ...]:
        superseded = {relation.predecessor for relation in self.supersessions}
        active = [
            source
            for source in self.sources
            if SourceVersionKey.from_source(source) not in superseded
        ]
        return tuple(
            sorted(
                active,
                key=lambda s: (
                    s.source_id,
                    s.issuer,
                    s.version,
                    s.document_digest,
                ),
            )
        )

    def snapshot(
        self,
        snapshot_id: str,
        query: KnowledgeQuery,
        *,
        active_sources_only: bool = True,
    ) -> KnowledgeSnapshot:
        claims = self.query(query)
        allowed_sources = (
            self.active_sources() if active_sources_only else self.sources
        )
        source_keys = {
            (source.source_id, source.document_digest): source
            for source in allowed_sources
        }
        filtered = tuple(
            claim
            for claim in claims
            if (claim.source_id, claim.source_document_digest) in source_keys
        )
        source_refs = {
            (claim.source_id, claim.source_document_digest)
            for claim in filtered
        }
        sources = tuple(
            sorted(
                (
                    source
                    for key, source in source_keys.items()
                    if key in source_refs
                ),
                key=lambda s: (
                    s.source_id,
                    s.issuer,
                    s.version,
                    s.document_digest,
                ),
            )
        )
        return KnowledgeSnapshot(snapshot_id, sources, filtered)

    def with_records(
        self,
        *,
        sources: tuple[KnowledgeSource, ...] = (),
        claims: tuple[KnowledgeClaim, ...] = (),
        supersessions: tuple[SourceSupersession, ...] = (),
    ) -> "ScientificKnowledgeRegistry":
        return ScientificKnowledgeRegistry(
            self.sources + tuple(sources),
            self.claims + tuple(claims),
            self.supersessions + tuple(supersessions),
        )
