from engcore.scientific.verification import *
from engcore.scientific.units.quantity import Quantity

def route(rid,kind,digit): return VerificationRoute(rid,kind,digit*64)
def manifest(rid,family,digit,authority="ours",external=False):
    return RouteDependencyManifest(rid,(DependencyComponent(family,digit*64,DependencyRole.SOLVER),),authority,external)

def plan():
    p=route("p",VerificationRouteKind.DIFFERENT_IMPLEMENTATION,"a")
    pm=manifest("p","p-family","a")
    c=VerificationCandidate(route("v",VerificationRouteKind.EXTERNAL_SOLVER,"b"),manifest("v","v-family","b","lab",True))
    return plan_verification(p,pm,(c,),VerificationPolicy(minimum_level=VerificationLevel.V2))

def test_plan_observations_produce_verified_report_only_when_all_required_routes_arrive_and_agree():
    p=plan()
    primary=VerificationObservation("p",Quantity(300,"kelvin"),"1"*64,True)
    candidate=VerificationObservation("v",Quantity(300.2,"kelvin"),"2"*64,True)
    report=build_execution_report(p,primary,(candidate,),Quantity(1,"kelvin"))
    assert report.complete
    assert report.verification.decision is VerificationDecision.VERIFIED

def test_route_disagreement_is_authoritative_disagreement():
    p=plan();primary=VerificationObservation("p",Quantity(300,"kelvin"),"1"*64,True)
    candidate=VerificationObservation("v",Quantity(303,"kelvin"),"2"*64,True)
    report=build_execution_report(p,primary,(candidate,),Quantity(1,"kelvin"))
    assert report.verification.decision is VerificationDecision.DISAGREEMENT

def test_missing_planned_route_never_becomes_verified():
    p=plan();primary=VerificationObservation("p",Quantity(300,"kelvin"),"1"*64,True)
    report=build_execution_report(p,primary,(),Quantity(1,"kelvin"))
    assert not report.complete
    assert report.verification.decision is VerificationDecision.NO_VERIFICATION
