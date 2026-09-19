import copy
import pytest
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.units.quantity import Quantity
from engcore.scientific.verification import *

def route(rid,kind,digit): return VerificationRoute(rid,kind,digit*64)
def manifest(rid,family,digit,authority="ours",external=False):
    return RouteDependencyManifest(rid,(DependencyComponent(family,digit*64,DependencyRole.SOLVER),),authority,external)

def make_plan():
    p=route("p",VerificationRouteKind.DIFFERENT_IMPLEMENTATION,"a")
    c=VerificationCandidate(route("v",VerificationRouteKind.EXTERNAL_SOLVER,"b"),
                            manifest("v","v-family","b","lab",True))
    return plan_verification(p,manifest("p","p-family","a"),(c,),VerificationPolicy())

def test_verification_plan_round_trip_rederives_selection():
    p=make_plan()
    assert plan_to_dict(plan_from_dict(plan_to_dict(p)))==plan_to_dict(p)

def test_verification_plan_refuses_forged_selected_route():
    payload=plan_to_dict(make_plan());payload["selected"]=[]
    with pytest.raises(InvalidScientificProblem,match="forged"):
        plan_from_dict(payload)

def test_verification_run_round_trip_rederives_verdict():
    p=make_plan()
    record=VerificationRunRecord(
        p,VerificationObservation("p",Quantity(300,"kelvin"),"1"*64,True),
        (VerificationObservation("v",Quantity(300.2,"kelvin"),"2"*64,True),),
        Quantity(1,"kelvin"))
    assert VerificationRunRecord.from_dict(record.to_dict()).to_dict()==record.to_dict()

def test_verification_run_refuses_forged_verdict():
    p=make_plan()
    record=VerificationRunRecord(
        p,VerificationObservation("p",Quantity(300,"kelvin"),"1"*64,True),
        (VerificationObservation("v",Quantity(300.2,"kelvin"),"2"*64,True),),
        Quantity(1,"kelvin"))
    payload=record.to_dict()
    payload["result"]["verification"]["decision"]="disagreement"
    with pytest.raises(InvalidScientificProblem,match="forged"):
        VerificationRunRecord.from_dict(payload)
