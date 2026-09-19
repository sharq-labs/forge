from __future__ import annotations
from dataclasses import dataclass
import re
from .estimators import ModelFormEstimatorKind

_SHA256=re.compile(r"^[0-9a-f]{64}$")

@dataclass(frozen=True)
class ProducerQualification:
    producer_id:str
    method_id:str
    validation_digest:str
    independent_reviewer_id:str
    independent_review_digest:str
    approved_quantities:tuple[str,...]
    approved_estimator_methods:tuple[str,...]=(ModelFormEstimatorKind.CONSERVATIVE_MAX_EXCESS.value,)

    def __post_init__(self)->None:
        producer=str(self.producer_id).strip();method=str(self.method_id).strip();reviewer=str(self.independent_reviewer_id).strip()
        quantities=tuple(sorted(set(str(q).strip() for q in self.approved_quantities)))
        estimators=tuple(sorted(set(ModelFormEstimatorKind(x).value for x in self.approved_estimator_methods)))
        if not producer or not method or not reviewer or not quantities or any(not q for q in quantities): raise ValueError("model-form producer qualification requires producer, method, independent reviewer and approved quantities")
        if producer==reviewer:
            raise ValueError("model-form independent reviewer must not be the producer")
        if not estimators: raise ValueError("qualification requires at least one approved estimator method")
        for label in ("validation_digest","independent_review_digest"):
            digest=str(getattr(self,label)).strip().lower()
            if not _SHA256.fullmatch(digest): raise ValueError(f"{label} must be lowercase SHA-256")
            object.__setattr__(self,label,digest)
        object.__setattr__(self,"producer_id",producer);object.__setattr__(self,"method_id",method)
        object.__setattr__(self,"independent_reviewer_id",reviewer)
        object.__setattr__(self,"approved_quantities",quantities);object.__setattr__(self,"approved_estimator_methods",estimators)

    def approves(self,quantity:str,estimator:ModelFormEstimatorKind)->bool:
        return str(quantity).strip() in self.approved_quantities and ModelFormEstimatorKind(estimator).value in self.approved_estimator_methods
