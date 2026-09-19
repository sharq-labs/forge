from engcore.execution.verification_runner import execute_verification_plan
from engcore.scientific.verification import *
from engcore.scientific.units.quantity import Quantity

def route(rid,kind,digit): return VerificationRoute(rid,kind,digit*64)
def manifest(rid,family,digit): return RouteDependencyManifest(rid,(DependencyComponent(family,digit*64,DependencyRole.SOLVER),),"ours")
def plan():
    p=route("p",VerificationRouteKind.DIFFERENT_IMPLEMENTATION,"a")
    c=VerificationCandidate(route("v",VerificationRouteKind.DIFFERENT_IMPLEMENTATION,"b"),manifest("v","v","b"))
    return plan_verification(p,manifest("p","p","a"),(c,),VerificationPolicy())

class Backend:
    route_id="v"
    def run(self): return VerificationObservation("v",Quantity(1,"volt"),"c"*64,True)

class BadBackend:
    route_id="v"
    def run(self): raise RuntimeError("boom")

def test_execution_runner_returns_typed_observations():
    result=execute_verification_plan(plan(),{"v":Backend()})
    assert len(result.observations)==1 and not result.problems

def test_execution_runner_records_backend_failure_without_inventing_observation():
    result=execute_verification_plan(plan(),{"v":BadBackend()})
    assert not result.observations and result.problems==("v:backend_exception:RuntimeError",)
