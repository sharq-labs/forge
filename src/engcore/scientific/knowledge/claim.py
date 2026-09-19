from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
from typing import Any,Mapping

from ..errors import InvalidScientificProblem
from ..results.uncertainty import Uncertainty,UncertaintyKind
from ..serialization import require_schema,schema_string
from ..units.quantity import Quantity
from ..units.validation import require_same_dimension

KNOWLEDGE_CLAIM_SCHEMA=schema_string("scientific_knowledge_claim")
_SHA256=re.compile(r"^[0-9a-f]{64}$")


class KnowledgeKind(str,Enum):
    CONSTANT="constant"
    MATERIAL_PROPERTY="material_property"
    MODEL_PARAMETER="model_parameter"
    VALIDITY_LIMIT="validity_limit"
    LAW_REFERENCE="law_reference"
    OTHER="other"


@dataclass(frozen=True)
class KnowledgeClaim:
    claim_id:str
    kind:KnowledgeKind
    subject:str
    quantity_name:str
    numeric_value:Quantity|None
    text_value:str
    uncertainty:Uncertainty|None
    source_id:str
    source_document_digest:str
    applicability_context_digest:str

    def __post_init__(self)->None:
        cid=str(self.claim_id).strip();subject=str(self.subject).strip();q=str(self.quantity_name).strip()
        source=str(self.source_id).strip();digest=str(self.source_document_digest).strip().lower()
        context=str(self.applicability_context_digest).strip().lower();text=str(self.text_value).strip()
        if not cid or not subject or not source or not _SHA256.fullmatch(digest) or not _SHA256.fullmatch(context):
            raise InvalidScientificProblem("knowledge claim requires identity subject source/document and context digests")
        numeric=self.numeric_value is not None
        textual=bool(text)
        if numeric==textual: raise InvalidScientificProblem("knowledge claim requires exactly one numeric or text value")
        if numeric and not isinstance(self.numeric_value,Quantity): raise InvalidScientificProblem("numeric knowledge value must be Quantity")
        if numeric and not q: raise InvalidScientificProblem("numeric knowledge claim requires quantity_name")
        if self.uncertainty is not None:
            if not numeric: raise InvalidScientificProblem("text knowledge claim cannot carry numeric uncertainty")
            if not isinstance(self.uncertainty,Uncertainty) or self.uncertainty.kind is UncertaintyKind.UNKNOWN:
                raise InvalidScientificProblem("claim uncertainty must be quantified when supplied")
            if self.uncertainty.kind is UncertaintyKind.STANDARD:
                require_same_dimension(self.uncertainty.standard_uncertainty,self.numeric_value,context="knowledge claim uncertainty")
            else:
                require_same_dimension(self.uncertainty.lower,self.numeric_value,context="knowledge claim interval")
                require_same_dimension(self.uncertainty.upper,self.numeric_value,context="knowledge claim interval")
        object.__setattr__(self,"claim_id",cid);object.__setattr__(self,"kind",KnowledgeKind(self.kind))
        object.__setattr__(self,"subject",subject);object.__setattr__(self,"quantity_name",q)
        object.__setattr__(self,"text_value",text);object.__setattr__(self,"source_id",source)
        object.__setattr__(self,"source_document_digest",digest);object.__setattr__(self,"applicability_context_digest",context)

    def to_dict(self)->dict[str,Any]:
        return {"schema":KNOWLEDGE_CLAIM_SCHEMA,"claim_id":self.claim_id,"kind":self.kind.value,
                "subject":self.subject,"quantity_name":self.quantity_name,
                "numeric_value":None if self.numeric_value is None else self.numeric_value.to_dict(),
                "text_value":self.text_value,
                "uncertainty":None if self.uncertainty is None else self.uncertainty.to_dict(),
                "source_id":self.source_id,"source_document_digest":self.source_document_digest,
                "applicability_context_digest":self.applicability_context_digest}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"KnowledgeClaim":
        require_schema(payload,KNOWLEDGE_CLAIM_SCHEMA)
        numeric=payload.get("numeric_value");uncertainty=payload.get("uncertainty")
        return cls(payload["claim_id"],KnowledgeKind(payload["kind"]),payload["subject"],
                   payload.get("quantity_name",""),Quantity.from_dict(numeric) if numeric is not None else None,
                   payload.get("text_value",""),Uncertainty.from_dict(uncertainty) if uncertainty is not None else None,
                   payload["source_id"],payload["source_document_digest"],payload["applicability_context_digest"])

    @property
    def digest(self)->str:
        return hashlib.sha256(json.dumps(self.to_dict(),sort_keys=True,separators=(",",":")).encode()).hexdigest()
