from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CertificationProfile:
    profile_id:str
    required_gates:tuple[str,...]

    def __post_init__(self)->None:
        pid=str(self.profile_id).strip()
        gates=tuple(str(x).strip() for x in self.required_gates)
        if not pid or not gates or any(not x for x in gates):
            raise ValueError("certification profile requires id and required gates")
        if len(gates)!=len(set(gates)):
            raise ValueError("certification profile contains duplicate gate ids")
        object.__setattr__(self,"profile_id",pid)
        object.__setattr__(self,"required_gates",gates)
