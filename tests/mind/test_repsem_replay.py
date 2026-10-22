"""BR-MIND-REPSEM-01: every new role, hypothesis, disposition and refusal serializes deterministically and replays."""

from __future__ import annotations

import json

import pytest

from benchmarks.mind_repsem_v1 import fixtures as fx
from engcore.mind.repsem import (
    Assessment, ReplayMismatch, RoleTable, ScientificHypothesis, ScopedClaim, assess, canonical_bytes, replay,
)


@pytest.mark.parametrize("name", fx.FIXTURES)
def test_assessment_replays_exactly(name):
    spec = fx.build(name, 0)
    record = assess(spec, fx.FAMILIES).to_dict()
    again = json.loads(canonical_bytes(record))
    result = replay(again, spec, fx.FAMILIES)
    assert result["status"] == "EXACT", result


def test_every_record_round_trips_byte_exactly():
    spec = fx.build("MODEL_DISCREPANCY", 1)
    a = assess(spec, fx.FAMILIES)
    table = RoleTable.from_spec(spec)
    assert canonical_bytes(RoleTable.from_dict(table.to_dict()).to_dict()) == canonical_bytes(table.to_dict())
    for claim in a.claims.values():
        assert canonical_bytes(ScopedClaim.from_dict(claim.to_dict()).to_dict()) == canonical_bytes(claim.to_dict())
    h = a.hypothesis
    assert canonical_bytes(ScientificHypothesis.from_dict(h.to_dict()).to_dict()) == canonical_bytes(h.to_dict())
    assert canonical_bytes(Assessment.from_dict(a.to_dict()).to_dict()) == canonical_bytes(a.to_dict())


def test_two_runs_are_byte_identical():
    spec = fx.build("CROSS_DOMAIN_TRANSFER_FAIL", 2)
    assert canonical_bytes(assess(spec, fx.FAMILIES).to_dict()) == canonical_bytes(assess(spec, fx.FAMILIES).to_dict())


def test_a_tampered_record_does_not_replay():
    spec = fx.build("IDENTIFIABLE", 0)
    record = assess(spec, fx.FAMILIES).to_dict()
    record["claims"]["MODEL_ADEQUACY"]["disposition"] = "NOT_SUPPORTED"
    with pytest.raises(ReplayMismatch):
        replay(record, spec, fx.FAMILIES)


def test_a_record_against_another_problem_does_not_replay():
    record = assess(fx.build("IDENTIFIABLE", 0), fx.FAMILIES).to_dict()
    with pytest.raises(ReplayMismatch, match="problem"):
        replay(record, fx.build("IDENTIFIABLE", 1), fx.FAMILIES)


def test_hypothesis_has_no_generic_law_field():
    h = assess(fx.build("IDENTIFIABLE", 0), fx.FAMILIES).hypothesis.to_dict()
    assert "law" not in h
    for key in ("model_family", "parameter_set", "applicability_domain", "variable_roles", "claims",
                "competing_alternatives", "evidence_for", "evidence_against", "unresolved_discriminators"):
        assert key in h
    h["law"] = "V = f(I)"
    with pytest.raises(ValueError, match="law"):
        ScientificHypothesis.from_dict(h)
