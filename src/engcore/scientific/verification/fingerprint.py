from __future__ import annotations

import hashlib,json
from .report import VerificationReport


def verification_report_fingerprint(report:VerificationReport)->str:
    payload={
        "decision":report.decision.value,
        "comparisons":[vars(c) for c in report.comparisons],
        "independence":[{
            "primary_route_id":i.primary_route_id,
            "verification_route_id":i.verification_route_id,
            "level":i.level.value,
            "shared_components":list(i.shared_components),
            "rationale":i.rationale,
        } for i in report.independence],
    }
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
