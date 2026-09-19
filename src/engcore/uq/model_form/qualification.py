from __future__ import annotations

from dataclasses import dataclass
import re

_SHA256=re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProducerQualification:
    producer_id:str
    method_id:str
    validation_digest:str
    independent_review_digest:str
    approved_quantities:tuple[str,...]

    def __post_init__(self)->None:
        producer=str(self.producer_id).strip()
        method=str(self.method_id).strip()
        quantities=tuple(sorted(set(str(q).strip() for q in self.approved_quantities)))
        if not producer or not method or not quantities or any(not q for q in quantities):
            raise ValueError("model-form producer qualification requires producer, method and approved quantities")
        for label in ("validation_digest","independent_review_digest"):
            digest=str(getattr(self,label)).strip().lower()
            if not _SHA256.fullmatch(digest):
                raise ValueError(f"{label} must be lowercase SHA-256")
            object.__setattr__(self,label,digest)
        object.__setattr__(self,"producer_id",producer)
        object.__setattr__(self,"method_id",method)
        object.__setattr__(self,"approved_quantities",quantities)

    def approves(self,quantity:str)->bool:
        return str(quantity).strip() in self.approved_quantities
