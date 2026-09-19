from engcore.scientific.verification import *

def route(rid,kind,digit): return VerificationRoute(rid,kind,digit*64)
def manifest(rid,family,digit,authority="ours",external=False):
    return RouteDependencyManifest(rid,(DependencyComponent(family,digit*64,DependencyRole.SOLVER),),authority,external)

def test_plan_rejects_low_verification_level_and_partial_independence():
    primary=route("p",VerificationRouteKind.DIFFERENT_IMPLEMENTATION,"a")
    pm=manifest("p","shared","a")
    low=VerificationCandidate(route("low",VerificationRouteKind.DIFFERENT_ALGORITHM,"b"),manifest("low","other","b"))
    partial=VerificationCandidate(route("partial",VerificationRouteKind.EXTERNAL_SOLVER,"c"),manifest("partial","shared","c","lab",True))
    plan=plan_verification(primary,pm,(low,partial),VerificationPolicy(minimum_level=VerificationLevel.V2))
    assert not plan.complete
    assert {x[0] for x in plan.rejected}=={"low","partial"}

def test_plan_can_require_a_distinct_external_authority():
    primary=route("p",VerificationRouteKind.DIFFERENT_IMPLEMENTATION,"a")
    pm=manifest("p","p-family","a")
    strong=VerificationCandidate(route("strong",VerificationRouteKind.ANALYTICAL_REFERENCE,"b"),manifest("strong","s-family","b"))
    external=VerificationCandidate(route("external",VerificationRouteKind.EXTERNAL_SOLVER,"c"),manifest("external","e-family","c","lab",True))
    plan=plan_verification(primary,pm,(strong,external),
        VerificationPolicy(minimum_level=VerificationLevel.V2,require_external=True))
    assert plan.complete
    assert any(x.independence.level is IndependenceLevel.EXTERNAL for x in plan.selected)
