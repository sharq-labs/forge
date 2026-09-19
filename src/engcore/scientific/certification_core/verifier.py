from __future__ import annotations
from dataclasses import dataclass
from .policy import CertificationPolicy
from .record import CertificationRecord

@dataclass(frozen=True)
class CertificationVerification:
    verified:bool
    problems:tuple[str,...]

def verify_certification_record(record:CertificationRecord,policy:CertificationPolicy=CertificationPolicy())->CertificationVerification:
    problems=[]
    by_gate={g.gate_id:g for g in record.gates}
    if policy.require_all_profile_gates:
        missing=[g for g in record.profile.required_gates if g not in by_gate]
        if missing:
            problems.append(f"missing required gates {missing}")
    if policy.refuse_failed_gate:
        failed=[g.gate_id for g in record.gates if not g.passed]
        if failed:
            problems.append(f"failed gates {failed}")
    if policy.require_artifacts and not record.artifacts:
        problems.append("no certification artifacts")
    return CertificationVerification(not problems,tuple(problems))
