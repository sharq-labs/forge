from __future__ import annotations

import json

from tools import forge_diagnose


def test_optional_mapping_refuses_non_object(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    try:
        forge_diagnose._optional_mapping(str(path), label="sensitivity")
    except ValueError as exc:
        assert "sensitivity must be a JSON object" in str(exc)
    else:
        raise AssertionError("non-object sensitivity must be refused")


def test_parser_accepts_optional_diagnostic_artifacts():
    args = forge_diagnose.build_parser().parse_args(
        ["assessment.json", "--sensitivity", "s.json", "--robustness", "r.json"]
    )
    assert args.assessment == "assessment.json"
    assert args.sensitivity == "s.json"
    assert args.robustness == "r.json"


def test_verified_record_requires_bundle_for_custom_trust():
    payload = {"schema": "claim_assessment/1", "external_trust_registry": "custom"}
    class Registry:
        pass
    try:
        forge_diagnose._verified_record(payload, Registry(), source="assessment.json")
    except ValueError as exc:
        assert "replay bundle" in str(exc)
    else:
        raise AssertionError("custom-trust raw assessment must require a replay bundle")


def test_the_diagnostic_carries_what_offline_verification_can_say(tmp_path):
    """Trust Repair Pass 1: a diagnosis that restates a verdict never presents a REPLAY_REQUIRED record as verified."""
    import sys

    sys.path.insert(0, "tests/claims")
    from claims_support import et_claim, t3_claim
    from engcore.claims import assess_claim
    from engcore.claims.replay.bundle import make_bundle
    from engcore.mcp.capabilities import production_registry

    registry = production_registry()
    et = make_bundle(assess_claim(et_claim(), registry), registry)
    _, standing = forge_diagnose._verified_record_and_standing(et, registry, source="et.json")
    assert standing["bundle_status"] == "replay_required" and standing["reasons"]
    t3 = assess_claim(t3_claim(), registry).to_dict()
    _, standing = forge_diagnose._verified_record_and_standing(t3, registry, source="t3.json")
    assert standing["revalidation"] == "scientifically_revalidated"

    path = tmp_path / "et.json"
    path.write_text(json.dumps(et), encoding="utf-8")
    out = tmp_path / "out.json"
    assert forge_diagnose.main([str(path), "--output", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["offline_verification"]["bundle_status"] == "replay_required"
