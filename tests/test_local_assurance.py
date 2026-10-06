"""Hostile checks for the local-only assurance execution path."""

from __future__ import annotations

import pathlib

import pytest

from tools.certification import branch_policy
from tools.certification.local_assurance import (
    LocalAssuranceError,
    _build_evidence_manifest,
    _require_clean,
    _require_head,
    _resolve_python,
    _verify_evidence_manifest,
)

REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "workflow",
    (
        ".github/workflows/tests.yml",
        ".github/workflows/recertify-hardened-core.yml",
        ".github/workflows/branch-policy.yml",
        ".github/workflows/trust-mutations.yml",
    ),
)
def test_github_workflows_are_manual_only(workflow):
    text = (REPO / workflow).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "\n  pull_request:" not in text
    assert "\n  push:" not in text
    assert "\n  schedule:" not in text


def test_forge_policy_requires_no_github_status_checks():
    assert branch_policy.REQUIRED_STATUS_CHECKS == ()
    required = branch_policy.POLICY["rules"]["required_status_checks"]["required_status_checks"]
    assert required == []


def test_missing_required_python_is_refused(tmp_path):
    with pytest.raises(LocalAssuranceError, match="was not found"):
        _resolve_python("definitely-not-a-python-executable", tmp_path, "3.11")


def test_dirty_tree_is_refused(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "tracked.txt").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "add", "tracked.txt"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "commit", "-q", "-m", "source"], cwd=root, check=True)
    (root / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(LocalAssuranceError, match="dirty"):
        _require_clean(root, "test")


def test_changed_head_is_refused(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "tracked.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "add", "tracked.txt"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "commit", "-q", "-m", "one"], cwd=root, check=True)
    first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                           capture_output=True, text=True).stdout.strip()
    (root / "tracked.txt").write_text("two\n", encoding="utf-8")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "add", "tracked.txt"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "commit", "-q", "-m", "two"], cwd=root, check=True)
    with pytest.raises(LocalAssuranceError, match="HEAD moved"):
        _require_head(root, first, "test")


def test_frozen_evidence_manifest_detects_tampering(tmp_path):
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "pyproject.toml").write_text("[project]\nname='x'\nversion='0'\n", encoding="utf-8")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "add", "pyproject.toml"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                    "commit", "-q", "-m", "source"], cwd=root, check=True)
    source = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                            capture_output=True, text=True).stdout.strip()

    evidence = tmp_path / "run" / "evidence"
    evidence.mkdir(parents=True)
    artifact = evidence / "gate.json"
    artifact.write_text('{"ok": true}\n', encoding="utf-8")
    manifest, digest, count = _build_evidence_manifest(root, source, evidence)
    assert _verify_evidence_manifest(manifest, evidence) == (digest, count)

    artifact.write_text('{"ok": false}\n', encoding="utf-8")
    with pytest.raises(LocalAssuranceError, match="changed after"):
        _verify_evidence_manifest(manifest, evidence)
