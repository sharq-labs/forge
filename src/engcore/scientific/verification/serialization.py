from __future__ import annotations

from typing import Any, Mapping

from ..serialization import require_schema, schema_string
from .adjudication import VerificationDecision, adjudicate
from .comparison import RouteComparison
from .independence import IndependenceEvidence, IndependenceLevel
from .report import VerificationReport

VERIFICATION_REPORT_SCHEMA=schema_string("independent_verification_report")


def verification_to_dict(report:VerificationReport)->dict[str,Any]:
    return {
        "schema":VERIFICATION_REPORT_SCHEMA,
        "decision":report.decision.value,
        "comparisons":[{"primary_route_id":c.primary_route_id,
                        "verification_route_id":c.verification_route_id,
                        "agreement":c.agreement,
                        "normalized_error":c.normalized_error} for c in report.comparisons],
        "independence":[{"primary_route_id":i.primary_route_id,
                         "verification_route_id":i.verification_route_id,
                         "level":i.level.value,
                         "shared_components":list(i.shared_components),
                         "rationale":i.rationale} for i in report.independence],
    }


def verification_from_dict(payload:Mapping[str,Any])->VerificationReport:
    require_schema(payload,VERIFICATION_REPORT_SCHEMA)
    comparisons=tuple(RouteComparison(**item) for item in payload.get("comparisons",()))
    independence=tuple(
        IndependenceEvidence(
            item["primary_route_id"],
            item["verification_route_id"],
            IndependenceLevel(item["level"]),
            tuple(item.get("shared_components",())),
            item.get("rationale",""),
        )
        for item in payload.get("independence",())
    )
    derived=adjudicate(comparisons,independence)
    declared=VerificationDecision(payload["decision"])
    if declared is not derived:
        raise ValueError(f"serialized verification decision {declared.value!r} does not match derived {derived.value!r}")
    return VerificationReport(derived,comparisons,independence)
