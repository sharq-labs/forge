from engcore.execution.verification_runner import execute_verification_plan
from engcore.scientific.verification import *

def make_plan():
    p=VerificationRoute("p",VerificationRouteKind.DIFFERENT_IMPLEMENTATION,"a"*64)
    pm=RouteDependencyManifest("p",(DependencyComponent("p","a"*64,DependencyRole.SOLVER),),"ours")
    v=VerificationRoute("v",VerificationRouteKind.DIFFERENT_IMPLEMENTATION,"b"*64)
    vm=RouteDependencyManifest("v",(DependencyComponent("v","b"*64,DependencyRole.SOLVER),),"ours")
    return plan_verification(p,pm,(VerificationCandidate(v,vm),),VerificationPolicy())

class Wrong:
    route_id="another"
    def run(self): raise AssertionError("must not run")

def test_backend_identity_must_match_planned_route_before_execution():
    result=execute_verification_plan(make_plan(),{"v":Wrong()})
    assert result.problems==("v:backend_route_identity_mismatch",)
