"""An applicability evaluator failure is a compiler blocker, never ready to execute."""

from dataclasses import replace

from engcore.claims import CapabilityRegistry, CompilationStatus, GapKind, RepairKind, compile_claim
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.models.definition import ValidityDomain
from tests.claims.test_claims_selection import _capability, _claim, _model


def test_compiler_exposes_evaluator_failure_without_running_or_inventing_an_input(monkeypatch):
    calls = []
    declaration = replace(_capability("syn.broken", _model("syn.beam")),
                          executor=lambda *a, **k: calls.append("executed"))

    def fail(*a, **k):
        raise InvalidScientificProblem("declared applicability evaluator failed")

    monkeypatch.setattr(ValidityDomain, "assess", fail)
    compiled = compile_claim(_claim(), CapabilityRegistry((declaration,)))
    assert compiled.status is CompilationStatus.UNSUPPORTED_CAPABILITY
    assert not compiled.ready and not calls
    assert compiled.missing_inputs == ()
    (gap,) = [g for g in compiled.predicted_gaps if g.kind is GapKind.APPLICABILITY_UNASSESSABLE]
    assert gap.target == "syn.beam#*"
    assert "declared applicability evaluator failed" in gap.detail
    assert "UNKNOWN" in gap.detail
    assert any(r.kind is RepairKind.EXTEND_CAPABILITY and r.target == gap.target for r in compiled.repairs)
    assert not any(r.kind is RepairKind.SUPPLY_INPUT for r in compiled.repairs)
    assert compile_claim(_claim(), CapabilityRegistry((declaration,))).digest == compiled.digest


def test_normal_declared_applicability_still_compiles_without_new_gaps():
    compiled = compile_claim(_claim(), CapabilityRegistry((_capability("syn.known", _model("syn.beam")),)))
    assert compiled.status is CompilationStatus.READY
    assert not any(g.kind is GapKind.APPLICABILITY_UNASSESSABLE for g in compiled.predicted_gaps)
