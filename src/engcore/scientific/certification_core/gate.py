from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CertificationGateResult:
    gate_id:str
    passed:bool
    evidence_digest:str

    def __post_init__(self)->None:
        gate=str(self.gate_id).strip()
        digest=str(self.evidence_digest).strip().lower()
        if not gate or len(digest)!=64:
            raise ValueError("certification gate requires id and SHA-256 evidence_digest")
        if not isinstance(self.passed,bool):
            raise ValueError("certification gate passed must be bool")
        object.__setattr__(self,"gate_id",gate)
        object.__setattr__(self,"evidence_digest",digest)
