from __future__ import annotations
from dataclasses import dataclass
from .artifact import CertificationArtifact
from .gate import CertificationGateResult
from .profile import CertificationProfile

@dataclass(frozen=True)
class CertificationRecord:
    commit_sha:str
    profile:CertificationProfile
    gates:tuple[CertificationGateResult,...]
    artifacts:tuple[CertificationArtifact,...]

    def __post_init__(self)->None:
        sha=str(self.commit_sha).strip().lower()
        if len(sha)!=40 or any(ch not in "0123456789abcdef" for ch in sha):
            raise ValueError("certification record commit_sha must be 40-char git SHA")
        object.__setattr__(self,"commit_sha",sha)
        object.__setattr__(self,"gates",tuple(self.gates))
        object.__setattr__(self,"artifacts",tuple(self.artifacts))
        gate_ids=[g.gate_id for g in self.gates]
        if len(gate_ids)!=len(set(gate_ids)):
            raise ValueError("certification record contains duplicate gates")
        names=[a.name for a in self.artifacts]
        if len(names)!=len(set(names)):
            raise ValueError("certification record contains duplicate artifacts")
