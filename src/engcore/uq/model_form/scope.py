from __future__ import annotations

from dataclasses import dataclass
import hashlib, json, re
from typing import Any, Mapping

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.serialization import require_schema, schema_string
from engcore.scientific.units.validation import require_unit

MODEL_FORM_SCOPE_SCHEMA=schema_string("model_form_scope")
_SHA256=re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ModelFormScope:
    model_id:str
    model_fingerprint:str
    operating_context_digest:str
    evidence_dataset_digest:str
    quantity:str
    units:str

    def __post_init__(self)->None:
        model_id=str(self.model_id).strip()
        quantity=str(self.quantity).strip()
        if not model_id or not quantity:
            raise InvalidScientificProblem("model-form scope requires model_id and quantity")
        object.__setattr__(self,"model_id",model_id)
        object.__setattr__(self,"quantity",quantity)
        object.__setattr__(self,"units",require_unit(self.units,context="model-form scope units"))
        for label in ("model_fingerprint","operating_context_digest","evidence_dataset_digest"):
            value=str(getattr(self,label)).strip().lower()
            if not _SHA256.fullmatch(value):
                raise InvalidScientificProblem(f"{label} must be lowercase SHA-256")
            object.__setattr__(self,label,value)

    def to_dict(self)->dict[str,Any]:
        return {"schema":MODEL_FORM_SCOPE_SCHEMA,"model_id":self.model_id,
                "model_fingerprint":self.model_fingerprint,
                "operating_context_digest":self.operating_context_digest,
                "evidence_dataset_digest":self.evidence_dataset_digest,
                "quantity":self.quantity,"units":self.units}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"ModelFormScope":
        require_schema(payload,MODEL_FORM_SCOPE_SCHEMA)
        return cls(payload["model_id"],payload["model_fingerprint"],
                   payload["operating_context_digest"],payload["evidence_dataset_digest"],
                   payload["quantity"],payload["units"])

    @property
    def digest(self)->str:
        return hashlib.sha256(json.dumps(self.to_dict(),sort_keys=True,separators=(",",":")).encode()).hexdigest()
