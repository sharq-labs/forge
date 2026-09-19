from __future__ import annotations

from dataclasses import dataclass
import math,re
from typing import Any,Mapping

from ..errors import InvalidScientificProblem
from ..serialization import require_schema,schema_string
from ..units.quantity import Quantity

VERIFICATION_OBSERVATION_SCHEMA=schema_string("verification_observation")
_SHA256=re.compile(r"^[0-9a-f]{64}$")

@dataclass(frozen=True)
class VerificationObservation:
    route_id:str
    value:Quantity
    evidence_digest:str
    converged:bool

    def __post_init__(self)->None:
        route=str(self.route_id).strip();digest=str(self.evidence_digest).strip().lower()
        if not route or not isinstance(self.value,Quantity) or not _SHA256.fullmatch(digest):
            raise InvalidScientificProblem("verification observation requires route, Quantity and evidence SHA-256")
        if not math.isfinite(float(self.value.magnitude)):
            raise InvalidScientificProblem("verification observation value must be finite")
        if not isinstance(self.converged,bool): raise InvalidScientificProblem("verification convergence must be bool")
        object.__setattr__(self,"route_id",route);object.__setattr__(self,"evidence_digest",digest)

    def to_dict(self)->dict[str,Any]:
        return {"schema":VERIFICATION_OBSERVATION_SCHEMA,"route_id":self.route_id,
                "value":self.value.to_dict(),"evidence_digest":self.evidence_digest,
                "converged":self.converged}

    @classmethod
    def from_dict(cls,payload:Mapping[str,Any])->"VerificationObservation":
        require_schema(payload,VERIFICATION_OBSERVATION_SCHEMA)
        return cls(payload["route_id"],Quantity.from_dict(payload["value"]),
                   payload["evidence_digest"],payload["converged"])
