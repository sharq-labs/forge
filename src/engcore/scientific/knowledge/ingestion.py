from __future__ import annotations

from dataclasses import dataclass
import hashlib,re

from ..errors import InvalidScientificProblem
from .source import KnowledgeSource


@dataclass(frozen=True)
class KnowledgeIngestionReceipt:
    source:KnowledgeSource
    raw_payload_digest:str
    parser_id:str
    parser_version:str
    imported_claim_digests:tuple[str,...]

    def __post_init__(self)->None:
        parser=str(self.parser_id).strip();version=str(self.parser_version).strip()
        raw=str(self.raw_payload_digest).strip().lower();claims=tuple(self.imported_claim_digests)
        if not isinstance(self.source,KnowledgeSource) or not parser or not version:
            raise InvalidScientificProblem("knowledge ingestion receipt requires source and parser identity")
        if not re.fullmatch(r"[0-9a-f]{64}",raw) or any(not re.fullmatch(r"[0-9a-f]{64}",x) for x in claims):
            raise InvalidScientificProblem("knowledge ingestion digests must be SHA-256")
        if raw!=self.source.document_digest:
            raise InvalidScientificProblem("raw payload digest must equal pinned source document digest")
        object.__setattr__(self,"raw_payload_digest",raw);object.__setattr__(self,"parser_id",parser)
        object.__setattr__(self,"parser_version",version);object.__setattr__(self,"imported_claim_digests",claims)

    @classmethod
    def from_payload(cls,source:KnowledgeSource,payload:bytes,parser_id:str,parser_version:str,
                     claim_digests:tuple[str,...])->"KnowledgeIngestionReceipt":
        return cls(source,hashlib.sha256(payload).hexdigest(),parser_id,parser_version,claim_digests)
