from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CertificationPolicy:
    refuse_failed_gate:bool=True
    require_all_profile_gates:bool=True
    require_artifacts:bool=True
