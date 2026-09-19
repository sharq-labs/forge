from __future__ import annotations

from tools import forge_check


def test_claim_changes_select_the_whole_scientific_regression_pack():
    tags = forge_check.tags_for_paths(["src/engcore/claims/verdict.py"])
    assert tags == set(forge_check.ALL_SCIENTIFIC_TAGS)


def test_credibility_changes_select_authority_and_evidence_sentinels():
    tags = forge_check.tags_for_paths(["src/engcore/credibility/evidence.py"])
    assert {"verdict", "evidence", "context", "uq", "external", "vnv"} <= tags
    assert "compiler" not in tags


def test_documentation_only_change_selects_no_scientific_case():
    assert forge_check.tags_for_paths(["docs/architecture/README.md"]) == set()


def test_build_targets_always_keeps_repository_architecture_guards():
    targets = forge_check.build_targets(["docs/README.md"])
    for nodeid in forge_check.ARCHITECTURE_TESTS:
        assert nodeid in targets


def test_regression_mode_selects_every_manifest_case_once():
    data = forge_check.load_manifest()
    targets = forge_check.build_targets([], regression=True)
    expected = {case["nodeid"] for case in data["cases"]}
    selected = {target for target in targets if "::" in target}
    assert selected == expected


def test_build_command_can_emit_junit_evidence_for_certification():
    command = forge_check.build_command(
        ["tests/test_forge_check.py::test_regression_mode_selects_every_manifest_case_once"],
        4,
        junitxml="/tmp/regression.xml",
    )
    assert "--junitxml" in command
    assert "/tmp/regression.xml" in command


def test_equation_core_changes_select_equation_ir_sentinels():
    tags = forge_check.tags_for_paths(["src/engcore/scientific/equations/dimensions.py"])
    assert {"equation_ir", "compiler", "applicability", "diagnostics", "provenance", "replay"} <= tags
    selected = forge_check.cases_for_tags(tags)
    assert any("test_addition_rejects_incompatible_dimensions" in item for item in selected)
    assert any("test_expression_payload_is_data_not_python_code" in item for item in selected)
    assert any("test_law_reference_rejects_changed_contract_under_same_id" in item for item in selected)


def test_validation_core_changes_select_validation_sentinels():
    tags = forge_check.tags_for_paths(["src/engcore/scientific/validation_core/report.py"])
    assert {"verdict", "vnv", "evidence"} <= tags

def test_replay_core_changes_select_replay_sentinels():
    tags = forge_check.tags_for_paths(["src/engcore/scientific/replay_core/bundle.py"])
    assert {"replay", "provenance"} <= tags

def test_evidence_graph_changes_select_evidence_sentinels():
    tags = forge_check.tags_for_paths(["src/engcore/credibility/evidence_graph/graph.py"])
    assert {"evidence", "provenance"} <= tags

def test_verification_changes_select_vnv_sentinels():
    tags = forge_check.tags_for_paths(["src/engcore/scientific/verification/adjudication.py"])
    assert {"vnv", "evidence"} <= tags

def test_certification_core_changes_select_policy_and_provenance_sentinels():
    tags = forge_check.tags_for_paths(["src/engcore/scientific/certification_core/verifier.py"])
    assert {"vnv", "policy", "provenance"} <= tags


def test_credibility_changes_select_provenance_and_replay_sentinels():
    tags = forge_check.tags_for_paths(["src/engcore/credibility/assurance_bundle.py"])
    assert {"evidence", "provenance", "replay"} <= tags
