from __future__ import annotations

import subprocess

import pytest

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


def test_knowledge_core_changes_select_knowledge_evidence_and_replay_sentinels():
    tags = forge_check.tags_for_paths(["src/engcore/scientific/knowledge/admission.py"])
    assert {"knowledge","evidence","provenance","replay","applicability","policy"} <= tags
    selected = forge_check.cases_for_tags(tags)
    assert any("test_changed_context_is_refused_even_for_pinned_current_source" in item for item in selected)
    assert any("test_ingestion_receipt_refuses_missing_or_extra_claim_digest" in item for item in selected)
    assert any("test_evidence_wire_trust_status_is_rederived_not_trusted" in item for item in selected)


# ---------------------------------------------------------------------------
# Conservative classification: an unmapped scientific path is never narrowed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "src/engcore/scientific/units/quantity.py",
        "src/engcore/systems/electrothermal/coupled.py",
        "src/engcore/product/capabilities.py",
        "src/engcore/inference/grid.py",
        "src/engcore/execution/sweep.py",
        "src/engcore/brand_new_package/module.py",
        "pyproject.toml",
        "tests/conftest.py",
        "tests/scientific_regression/manifest.json",
        "tools/forge_check.py",
    ],
)
def test_an_unmapped_scientific_or_configuration_change_selects_the_whole_pack(path):
    assert forge_check.unclassified_paths([path]) == [path]
    assert forge_check.tags_for_paths([path]) == set(forge_check.ALL_SCIENTIFIC_TAGS)
    targets = forge_check.build_targets([path])
    pack = {case["nodeid"] for case in forge_check.load_manifest()["cases"]}
    assert pack <= set(targets)


def test_windows_separators_are_classified_like_posix_ones():
    assert forge_check.unclassified_paths(["src\\engcore\\scientific\\units\\quantity.py"]) == [
        "src/engcore/scientific/units/quantity.py"
    ]
    assert forge_check.tags_for_paths(["src\\engcore\\credibility\\evidence.py"]) == forge_check.tags_for_paths(
        ["src/engcore/credibility/evidence.py"]
    )


def test_a_mapped_path_keeps_its_narrow_selection():
    assert forge_check.unclassified_paths(["src/engcore/credibility/evidence.py"]) == []
    assert "compiler" not in forge_check.tags_for_paths(["src/engcore/credibility/evidence.py"])


def test_a_changed_test_module_is_run_itself_and_a_deleted_one_is_not():
    targets = forge_check.build_targets(["tests/claims/test_quantitative_uq.py", "tests/claims/test_deleted_long_ago.py"])
    assert "tests/claims/test_quantitative_uq.py" in targets
    assert "tests/claims/test_deleted_long_ago.py" not in targets
    assert forge_check.changed_test_files(["tests/claims/claims_support.py"]) == []


# ---------------------------------------------------------------------------
# Change detection: committed, staged, unstaged, untracked, deleted, renamed
# ---------------------------------------------------------------------------


def _git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    for name in ("a.py", "b.py", "c.py", "moved.py", "gone.py"):
        (tmp_path / name).write_bytes(f"# {name} with enough distinct content to be a rename source\n".encode() * 8)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "checkout", "-q", "-b", "work")
    monkeypatch.setattr(forge_check, "ROOT", tmp_path)
    return tmp_path


def test_every_kind_of_change_is_detected_and_committed_only_is_narrower(repo):
    (repo / "a.py").write_bytes(b"committed edit\n")
    _git(repo, "mv", "moved.py", "renamed.py")
    _git(repo, "rm", "-q", "gone.py")
    _git(repo, "commit", "-q", "-am", "work")
    (repo / "b.py").write_bytes(b"staged edit\n")
    _git(repo, "add", "b.py")
    (repo / "c.py").write_bytes(b"unstaged edit\n")
    (repo / "new.py").write_bytes(b"untracked\n")

    everything = forge_check.changed_files("main")
    assert everything == ["a.py", "b.py", "c.py", "gone.py", "moved.py", "new.py", "renamed.py"]
    committed = forge_check.changed_files("main", working_tree=False)
    assert committed == ["a.py", "gone.py", "moved.py", "renamed.py"]


def test_an_uncommitted_change_on_the_base_branch_itself_is_detected(repo):
    _git(repo, "checkout", "-q", "main")
    (repo / "a.py").write_bytes(b"uncommitted\n")
    assert forge_check.changed_files("main") == ["a.py"]
    assert forge_check.changed_files("main", working_tree=False) == []


def test_an_unknown_base_fails_loudly(repo):
    with pytest.raises(SystemExit):
        forge_check.changed_files("no-such-ref")
