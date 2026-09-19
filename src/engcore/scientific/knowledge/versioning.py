from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..errors import InvalidScientificProblem
from .source import KnowledgeSource


class SourceVersionRelation(str, Enum):
    SAME = "same"
    NEWER = "newer"
    OLDER = "older"
    DIVERGENT = "divergent"


@dataclass(frozen=True)
class SourceVersionKey:
    source_id: str
    issuer: str
    version: str
    document_digest: str

    @classmethod
    def from_source(cls, source: KnowledgeSource) -> "SourceVersionKey":
        return cls(
            source.source_id,
            source.issuer,
            source.version,
            source.document_digest,
        )


@dataclass(frozen=True)
class SourceSupersession:
    predecessor: SourceVersionKey
    successor: SourceVersionKey
    reason: str

    def __post_init__(self) -> None:
        reason = str(self.reason).strip()
        if not reason:
            raise InvalidScientificProblem(
                "source supersession requires a non-empty reason"
            )
        if self.predecessor.source_id != self.successor.source_id:
            raise InvalidScientificProblem(
                "source supersession must remain within one source_id"
            )
        if self.predecessor == self.successor:
            raise InvalidScientificProblem(
                "source supersession cannot point a version to itself"
            )
        object.__setattr__(self, "reason", reason)


def compare_source_versions(
    left: KnowledgeSource,
    right: KnowledgeSource,
) -> SourceVersionRelation:
    if left.source_id != right.source_id or left.issuer != right.issuer:
        return SourceVersionRelation.DIVERGENT
    if (
        left.version == right.version
        and left.document_digest == right.document_digest
    ):
        return SourceVersionRelation.SAME
    # Version strings are intentionally not parsed as semver: standards,
    # datasets and publications use heterogeneous version schemes.  An
    # ordering exists only when registry lineage explicitly declares it.
    return SourceVersionRelation.DIVERGENT
