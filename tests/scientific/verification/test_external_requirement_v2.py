from engcore.scientific.verification import *

def test_require_external_policy_is_incomplete_when_only_internal_strong_route_exists():
    primary=VerificationRoute("p",VerificationRouteKind.DIFFERENT_IMPLEMENTATION,"a"*64)
    pm=RouteDependencyManifest("p",(DependencyComponent("p-family","a"*64,DependencyRole.SOLVER),),"ours")
    route=VerificationRoute("v",VerificationRouteKind.ANALYTICAL_REFERENCE,"b"*64)
    vm=RouteDependencyManifest("v",(DependencyComponent("v-family","b"*64,DependencyRole.SOLVER),),"ours")
    plan=plan_verification(primary,pm,(VerificationCandidate(route,vm),),
                           VerificationPolicy(require_external=True))
    assert plan.selected
    assert not plan.complete
