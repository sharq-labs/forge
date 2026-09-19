from __future__ import annotations
import hashlib,json
from .record import CertificationRecord

def certification_record_fingerprint(record:CertificationRecord)->str:
    payload={
        "commit_sha":record.commit_sha,
        "profile":{"profile_id":record.profile.profile_id,"required_gates":list(record.profile.required_gates)},
        "gates":[{"gate_id":g.gate_id,"passed":g.passed,"evidence_digest":g.evidence_digest} for g in sorted(record.gates,key=lambda x:x.gate_id)],
        "artifacts":[{"name":a.name,"digest":a.digest} for a in sorted(record.artifacts,key=lambda x:x.name)],
    }
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
