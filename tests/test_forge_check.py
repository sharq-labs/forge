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
