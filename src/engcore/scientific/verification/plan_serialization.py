from __future__ import annotations

from typing import Any,Mapping
from ..errors import InvalidScientificProblem
from ..serialization import require_schema,schema_string
from .dependencies import RouteDependencyManifest
from .independence import IndependenceLevel
from .ladder import VerificationLevel
from .planning import VerificationCandidate,VerificationPlan,VerificationPolicy,plan_verification
from .route import VerificationRoute,VerificationRouteKind

VERIFICATION_PLAN_SCHEMA=schema_string("verification_plan")


def _route_to_dict(route:VerificationRoute)->dict[str,Any]:
    return {"route_id":route.route_id,"kind":route.kind.value,
            "implementation_digest":route.implementation_digest}

def _route_from_dict(payload:Mapping[str,Any])->VerificationRoute:
    return VerificationRoute(payload["route_id"],VerificationRouteKind(payload["kind"]),
                             payload["implementation_digest"])

def plan_to_dict(plan:VerificationPlan)->dict[str,Any]:
    return {"schema":VERIFICATION_PLAN_SCHEMA,
        "primary_route":_route_to_dict(plan.primary_route),
        "primary_dependencies":plan.primary_dependencies.to_dict(),
        "candidates":[{"route":_route_to_dict(c.route),"dependencies":c.dependencies.to_dict()} for c in plan.candidates],
        "policy":{"minimum_level":int(plan.policy.minimum_level),
                  "minimum_independence":plan.policy.minimum_independence.value,
                  "minimum_routes":plan.policy.minimum_routes,
                  "require_external":plan.policy.require_external},
        "selected":[x.candidate.route.route_id for x in plan.selected],
        "rejected":[list(x) for x in plan.rejected],
        "complete":plan.complete}

def plan_from_dict(payload:Mapping[str,Any])->VerificationPlan:
    require_schema(payload,VERIFICATION_PLAN_SCHEMA)
    pp=payload["policy"]
    policy=VerificationPolicy(VerificationLevel(pp["minimum_level"]),
        IndependenceLevel(pp["minimum_independence"]),pp["minimum_routes"],pp["require_external"])
    candidates=tuple(VerificationCandidate(
        _route_from_dict(x["route"]),RouteDependencyManifest.from_dict(x["dependencies"]))
        for x in payload.get("candidates",()))
    plan=plan_verification(_route_from_dict(payload["primary_route"]),
        RouteDependencyManifest.from_dict(payload["primary_dependencies"]),candidates,policy)
    derived_selected=[x.candidate.route.route_id for x in plan.selected]
    derived_rejected=[list(x) for x in plan.rejected]
    if payload.get("selected")!=derived_selected or payload.get("rejected")!=derived_rejected or payload.get("complete") is not plan.complete:
        raise InvalidScientificProblem("serialized verification plan selection is forged or stale")
    return plan
