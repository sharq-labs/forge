from engcore.scientific.verification import *

def component(family,digest,role):
    return DependencyComponent(family,digest*64,role)

def manifest(route,components,authority="ours",external=False):
    return RouteDependencyManifest(route,tuple(components),authority,external)

def test_dependency_manifests_derive_none_partial_strong_and_external():
    primary=manifest("p",(component("model","a",DependencyRole.MODEL),component("solver-a","b",DependencyRole.SOLVER)))
    identical=manifest("same-copy",(component("model","a",DependencyRole.MODEL),component("solver-a","b",DependencyRole.SOLVER)))
    partial=manifest("partial",(component("model","c",DependencyRole.MODEL),component("solver-b","d",DependencyRole.SOLVER)))
    strong=manifest("strong",(component("model-b","e",DependencyRole.MODEL),component("solver-c","f",DependencyRole.SOLVER)))
    external=manifest("external",(component("model-c","1",DependencyRole.MODEL),component("solver-d","2",DependencyRole.SOLVER)),"lab",True)
    assert derive_independence(primary,identical).level is IndependenceLevel.NONE
    assert derive_independence(primary,partial).level is IndependenceLevel.PARTIAL
    assert derive_independence(primary,strong).level is IndependenceLevel.STRONG
    assert derive_independence(primary,external).level is IndependenceLevel.EXTERNAL

def test_dependency_manifest_round_trip_preserves_authority_boundary():
    m=manifest("x",(component("m","a",DependencyRole.MODEL),),"lab",True)
    assert RouteDependencyManifest.from_dict(m.to_dict())==m
