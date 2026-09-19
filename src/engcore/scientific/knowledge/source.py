from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any,Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema,schema_string

SOURCE_RECORD_SCHEMA=schema_string("scientific_knowledge_source")
_SHA256=re.compile(r"^[0-9a-f]{64}$")


class KnowledgeSourceClass(str,Enum):
    PEER_REVIEWED="peer_reviewed"
    STANDARD="standard"
    OFFICIAL_DATA="official_data"
    REFERENCE_DATABASE="reference_database"
    MANUFACTURER_DATASHEET="manufacturer_datasheet"
    EXPERIMENTAL_DATASET="experimental_dataset"
    OTHER="other"


@dataclass(frozen=True)
class KnowledgeSource:
    source_id:str
    issuer:str
    document_digest:str
    version:str
    locator:str
    source_class:KnowledgeSourceClass
    published_at:str=""
    retrieved_at:str=""

    def __post_init__(self)->None:
        sid=str(self.source_id).strip();issuer=str(self.issuer).strip();version=str(self.version).strip();locator=str(self.locator).strip()
        digest=str(self.document_digest).strip().lower()
        if not sid or not issuer or not version or not locator or not _SHA256.fullmatch(digest):
            raise InvalidScientificProblem("knowledge source requires id issuer version locator and SHA-256 document digest")
        object.__setattr__(self,"source_id",sid);object.__setattr__(self,"issuer",issuer)
        object.__setattr__(self,"version",version);object.__setattr__(self,"locator",locator)
        object.__setattr__(self,"document_digest",digest);object.__setattr__(self,"source_class",KnowledgeSourceClass(self.source_class))

    def to_dict(self)->dict[str,Any]:
        return {"schema":SOURCE_RECORD_SCHEMA,"source_id":self.source_id,"issuer":self.issuer,
                "document_digest":self.document_digest,"version":self.version,"locator":self.locator,
                "source_class":self.source_class.value,"published_at":self.published_at,"retrieved_at":self.retrieved_at}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"KnowledgeSource":
        require_schema(payload,SOURCE_RECORD_SCHEMA)
        return cls(payload["source_id"],payload["issuer"],payload["document_digest"],payload["version"],
                   payload["locator"],KnowledgeSourceClass(payload["source_class"]),
                   payload.get("published_at",""),payload.get("retrieved_at",""))
