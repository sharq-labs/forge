from __future__ import annotations

from typing import Any, Mapping

from ..serialization import require_schema, schema_string
from .artifact import CertificationArtifact
from .gate import CertificationGateResult
from .profile import CertificationProfile
from .record import CertificationRecord
from .verifier import verify_certification_record

CERTIFICATION_RECORD_SCHEMA=schema_string("scientific_certification_record")


def certification_to_dict(record:CertificationRecord)->dict[str,Any]:
    verification=verify_certification_record(record)
    return {
        "schema":CERTIFICATION_RECORD_SCHEMA,
        "commit_sha":record.commit_sha,
        "profile":{"profile_id":record.profile.profile_id,
                   "required_gates":list(record.profile.required_gates)},
        "gates":[{"gate_id":g.gate_id,"passed":g.passed,
                  "evidence_digest":g.evidence_digest} for g in record.gates],
        "artifacts":[{"name":a.name,"digest":a.digest} for a in record.artifacts],
        "verified":verification.verified,
        "problems":list(verification.problems),
    }


def certification_from_dict(payload:Mapping[str,Any])->CertificationRecord:
    require_schema(payload,CERTIFICATION_RECORD_SCHEMA)
    profile_payload=payload["profile"]
    record=CertificationRecord(
        payload["commit_sha"],
        CertificationProfile(profile_payload["profile_id"],tuple(profile_payload["required_gates"])),
        tuple(CertificationGateResult(i["gate_id"],i["passed"],i["evidence_digest"])
              for i in payload.get("gates",())),
        tuple(CertificationArtifact(i["name"],i["digest"])
              for i in payload.get("artifacts",())),
    )
    verification=verify_certification_record(record)
    if "verified" in payload and bool(payload["verified"]) != verification.verified:
        raise ValueError("serialized certification verification is forged or stale")
    if "problems" in payload and tuple(payload["problems"]) != verification.problems:
        raise ValueError("serialized certification problems do not match recomputed problems")
    return record
