from __future__ import annotations

from dataclasses import dataclass
import hashlib,json
from typing import Any,Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema,schema_string
from .claim import KnowledgeClaim
from .source import KnowledgeSource

KNOWLEDGE_SNAPSHOT_SCHEMA=schema_string("scientific_knowledge_snapshot")


@dataclass(frozen=True)
class KnowledgeSnapshot:
    snapshot_id:str
    sources:tuple[KnowledgeSource,...]
    claims:tuple[KnowledgeClaim,...]

    def __post_init__(self)->None:
        sid=str(self.snapshot_id).strip();sources=tuple(self.sources);claims=tuple(self.claims)
        if not sid: raise InvalidScientificProblem("knowledge snapshot requires id")
        if any(not isinstance(x,KnowledgeSource) for x in sources) or any(not isinstance(x,KnowledgeClaim) for x in claims):
            raise InvalidScientificProblem("knowledge snapshot requires typed sources and claims")
        source_ids=[s.source_id for s in sources];claim_ids=[c.claim_id for c in claims]
        if len(source_ids)!=len(set(source_ids)) or len(claim_ids)!=len(set(claim_ids)):
            raise InvalidScientificProblem("knowledge snapshot contains duplicate source or claim ids")
        by_id={s.source_id:s for s in sources}
        for claim in claims:
            source=by_id.get(claim.source_id)
            if source is None: raise InvalidScientificProblem(f"claim {claim.claim_id!r} references source absent from snapshot")
            if source.document_digest!=claim.source_document_digest:
                raise InvalidScientificProblem(f"claim {claim.claim_id!r} source digest does not match snapshot source")
        object.__setattr__(self,"snapshot_id",sid);object.__setattr__(self,"sources",sources);object.__setattr__(self,"claims",claims)

    def to_dict(self)->dict[str,Any]:
        return {"schema":KNOWLEDGE_SNAPSHOT_SCHEMA,"snapshot_id":self.snapshot_id,
                "sources":[s.to_dict() for s in self.sources],"claims":[c.to_dict() for c in self.claims]}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"KnowledgeSnapshot":
        require_schema(payload,KNOWLEDGE_SNAPSHOT_SCHEMA)
        return cls(payload["snapshot_id"],tuple(KnowledgeSource.from_dict(x) for x in payload.get("sources",())),
                   tuple(KnowledgeClaim.from_dict(x) for x in payload.get("claims",())))

    @property
    def digest(self)->str:
        payload={"snapshot_id":self.snapshot_id,
                 "sources":[s.to_dict() for s in sorted(self.sources,key=lambda x:x.source_id)],
                 "claims":[c.to_dict() for c in sorted(self.claims,key=lambda x:x.claim_id)]}
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
