from __future__ import annotations

from dataclasses import dataclass

from ..errors import InvalidScientificProblem
from .claim import KnowledgeClaim, KnowledgeKind


@dataclass(frozen=True)
class KnowledgeQuery:
    context_digest: str
    subject: str = ""
    quantity_name: str = ""
    kind: KnowledgeKind | None = None
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        import re

        context = str(self.context_digest).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", context):
            raise InvalidScientificProblem(
                "knowledge query context_digest must be lowercase SHA-256"
            )
        source_ids = tuple(sorted(set(str(x).strip() for x in self.source_ids)))
        if any(not x for x in source_ids):
            raise InvalidScientificProblem(
                "knowledge query source ids must be non-empty"
            )
        object.__setattr__(self, "context_digest", context)
        object.__setattr__(self, "subject", str(self.subject).strip())
        object.__setattr__(self, "quantity_name", str(self.quantity_name).strip())
        object.__setattr__(self, "source_ids", source_ids)
        if self.kind is not None:
            object.__setattr__(self, "kind", KnowledgeKind(self.kind))

    def matches(self, claim: KnowledgeClaim) -> bool:
        if claim.applicability_context_digest != self.context_digest:
            return False
        if self.subject and claim.subject != self.subject:
            return False
        if self.quantity_name and claim.quantity_name != self.quantity_name:
            return False
        if self.kind is not None and claim.kind is not self.kind:
            return False
        if self.source_ids and claim.source_id not in self.source_ids:
            return False
        return True
