from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.results.uncertainty import Uncertainty,UncertaintyKind,UncertaintySource
from engcore.scientific.serialization import require_schema,schema_string

CONTRIBUTION_SCHEMA=schema_string("combined_uq_contribution")
_SHA256=re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class UncertaintyContribution:
    contribution_id:str
    uncertainty:Uncertainty
    evidence_digest:str
    lineage_digests:tuple[str,...]
    independence_group:str

    def __post_init__(self)->None:
        cid=str(self.contribution_id).strip();group=str(self.independence_group).strip()
        if not cid or not group: raise InvalidScientificProblem("uncertainty contribution requires id and independence group")
        if not isinstance(self.uncertainty,Uncertainty): raise InvalidScientificProblem("contribution uncertainty must be Uncertainty")
        if self.uncertainty.kind is UncertaintyKind.UNKNOWN: raise InvalidScientificProblem("UNKNOWN uncertainty cannot enter a combined budget")
        source=UncertaintySource(self.uncertainty.source_kind)
        if source in {UncertaintySource.UNSPECIFIED,UncertaintySource.COMBINED}:
            raise InvalidScientificProblem("combined UQ accepts only attributed primitive uncertainty sources")
        evidence=str(self.evidence_digest).strip().lower()
        lineage=tuple(sorted(set(str(x).strip().lower() for x in self.lineage_digests)))
        if not _SHA256.fullmatch(evidence): raise InvalidScientificProblem("contribution evidence_digest must be SHA-256")
        if not lineage or any(not _SHA256.fullmatch(x) for x in lineage):
            raise InvalidScientificProblem("contribution lineage_digests must be non-empty SHA-256 identities")
        object.__setattr__(self,"contribution_id",cid);object.__setattr__(self,"independence_group",group)
        object.__setattr__(self,"evidence_digest",evidence);object.__setattr__(self,"lineage_digests",lineage)

    @property
    def source_kind(self)->UncertaintySource:
        return UncertaintySource(self.uncertainty.source_kind)

    def to_dict(self)->dict[str,Any]:
        return {"schema":CONTRIBUTION_SCHEMA,"contribution_id":self.contribution_id,
                "uncertainty":self.uncertainty.to_dict(),"evidence_digest":self.evidence_digest,
                "lineage_digests":list(self.lineage_digests),"independence_group":self.independence_group}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"UncertaintyContribution":
        require_schema(payload,CONTRIBUTION_SCHEMA)
        return cls(payload["contribution_id"],Uncertainty.from_dict(payload["uncertainty"]),
                   payload["evidence_digest"],tuple(payload.get("lineage_digests",())),
                   payload["independence_group"])
