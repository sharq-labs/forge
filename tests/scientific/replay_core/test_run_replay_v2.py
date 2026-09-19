import pytest

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.replay_core import *
from engcore.scientific.units.quantity import Quantity


def profile():
    return RunManifestProfile("p",("scientific_law",),("scientific_law",),False)

def artifact(digit="1"):
    return (ArtifactIdentity("scientific_law","law",digit*64),)

def env(digit="a"):
    return RuntimeEnvironment("Python 3.12","linux",digit*64)

def expected():
    return ScientificRunManifest("source",profile(),artifact(),env(),3)

def actual(exp=None,**kwargs):
    exp=exp or expected()
    return ScientificRunManifest(
        "replay",profile(),kwargs.pop("artifacts",artifact()),
        kwargs.pop("environment",env()),kwargs.pop("random_seed",3),
        replay_of_manifest_digest=kwargs.pop("replay_of",exp.digest),
    )

def record(actual_manifest=None,observations=None):
    exp=expected()
    act=actual_manifest or actual(exp)
    return RunReplayRecord(
        exp,act,
        (OutputExpectation("q",Quantity(10,"meter"),Quantity(0.1,"meter"),0),),
        observations if observations is not None else
        (OutputObservation("q",Quantity(10.05,"meter"),"b"*64),),
    )

def test_replay_requires_binding_to_exact_expected_manifest_and_matching_contract():
    exp=expected()
    wrong=actual(exp,replay_of="f"*64)
    assert not verify_run_manifest(exp,wrong).verified
    drift=actual(exp,artifacts=artifact("2"))
    assert not verify_run_manifest(exp,drift).verified

def test_end_to_end_run_replay_requires_manifest_and_outputs():
    result=record().verification
    assert result.verified
    assert result.manifest.verified

def test_missing_or_out_of_tolerance_output_refuses_replay():
    assert not record(observations=()).verification.verified
    far=(OutputObservation("q",Quantity(11,"meter"),"b"*64),)
    assert not record(observations=far).verification.verified

def test_run_replay_wire_verification_is_rederived():
    payload=record().to_dict()
    payload["verification"]["verified"]=False
    with pytest.raises(InvalidScientificProblem,match="forged"):
        RunReplayRecord.from_dict(payload)

def test_environment_drift_refuses_run_replay():
    exp=expected()
    drift=actual(exp,environment=env("b"))
    assert not record(actual_manifest=drift).verification.verified


def test_run_replay_boundary_requires_typed_manifests_expectations_and_observations():
    exp=expected()
    act=actual(exp)
    with pytest.raises(InvalidScientificProblem,match="ScientificRunManifest"):
        RunReplayRecord("not-a-manifest",act,(),())
    with pytest.raises(InvalidScientificProblem,match="OutputExpectation"):
        RunReplayRecord(exp,act,("not-an-expectation",),())
    with pytest.raises(InvalidScientificProblem,match="OutputObservation"):
        RunReplayRecord(exp,act,(),("not-an-observation",))
