from __future__ import annotations

import json

from engcore.claims.analysis.impact import ChangeKind
from tools import forge_impact


def _record() -> dict:
    return {
        "verdict": "supported",
        "compilation": {"claim_identity": "claim-digest"},
        "claim": {"decision": {"decision_id": "decision-1"}},
        "plan": {
            "content": {
                "core_digest": "plan-digest",
                "capability": {
                    "capability_id": "capability.demo",
                    "version": "1",
                    "digest": "capability-digest",
                },
                "models": [{"model_id": "model.demo", "version": "1"}],
                "solvers": [{"solver_id": "solver.demo", "version": "1"}],
                "decision": {"charter_digest": "charter-digest"},
            }
        },
        "external_evidence": [],
        "external_evidence_assessments": [],
        "external_trust_registry": "trust-old",
        "evidence": None,
        "policy": None,
    }


def test_records_from_payload_accepts_record_list_and_bundle():
    record = _record()
    assert forge_impact.records_from_payload(record) == [record]
    assert forge_impact.records_from_payload([record]) == [record]
    assert forge_impact.records_from_payload({"records": [record]}) == [record]
    assert forge_impact.records_from_payload({"record": record, "bundle_digest": "x"}) == [record]


def test_query_reports_the_assessment_and_identity_chain():
    record = _record()
    report = forge_impact.report_for_change(
        [record],
        kind=ChangeKind.MODEL,
        key="model.demo",
        detail="model implementation changed",
    )
    assert len(report["requires_reassessment"]) == 1
    affected = report["requires_reassessment"][0]
    assert affected["claim_identity"] == "claim-digest"
    chain = affected["because"][0]["chain"]
    assert chain[-1] == "model:model.demo@1"


def test_query_can_target_the_external_trust_registry():
    record = _record()
    report = forge_impact.report_for_change(
        [record],
        kind=ChangeKind.TRUST_REGISTRY,
        key="trust-old",
    )
    assert len(report["requires_reassessment"]) == 1


def test_load_records_reads_bundle_and_list_files(tmp_path):
    record = _record()
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps({"record": record}), encoding="utf-8")
    many = tmp_path / "many.json"
    many.write_text(json.dumps([record]), encoding="utf-8")
    assert forge_impact.load_records([bundle, many]) == [record, record]
