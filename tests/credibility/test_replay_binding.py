from engcore.credibility.assurance_bundle import AssuranceBundle
from engcore.credibility.replay_binding import assurance_artifact,law_artifact
from engcore.scientific.equations import (
    Equation, EquationSymbol, LawDefinition, LawReference, Symbol,
)

def test_assurance_bundle_becomes_content_addressed_replay_artifact():
    b=AssuranceBundle("a"*64,"b"*64,"c"*64,"d"*64,"e"*64,"f"*64)
    a=assurance_artifact(b)
    assert a.digest==b.digest

def test_law_reference_replay_artifact_preserves_exact_contract_identity():
    law=LawDefinition("identity","Identity",Equation(Symbol("x"),Symbol("y")),(EquationSymbol("x","meter"),EquationSymbol("y","meter")))
    ref=LawReference.from_law(law)
    a=law_artifact(ref)
    assert a.identifier=="identity" and a.digest==ref.fingerprint
