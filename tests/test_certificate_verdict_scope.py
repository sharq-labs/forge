"""F2 (hostile review, HIGH): the certificate covers what decides a verdict's meaning.

The review found committed changes that alter SUPPORTED semantics outside every
certified area: credibility/evidence.py::derive_verdict, claims/verdict.py,
authority/** and blindfold/**. These tests build a committed repository under
the REAL scope table, commit a change to each of those modules, and require the
stored certificate to stop verifying -- while a documentation-only commit does not.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

from tools.certification import core_certificate as cc

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The modules hostile review F2 found outside the certificate, and a committed semantic edit to each.
SEMANTIC_EDITS = {
    "src/engcore/credibility/evidence.py": ("def derive_verdict(", "def _derive_verdict_shadow():\n    return 'supported'\n\n\ndef derive_verdict("),
    "src/engcore/claims/verdict.py": ("\n", "\nFORGED_VERDICT_SHIFT = 'supported'\n"),
    "src/engcore/authority/ledger.py": ('raise AuthorityRefused("genesis signature invalid")', "pass"),
    "src/engcore/blindfold/__init__.py": ("\n", "\nISOLATION_DISABLED = True\n"),
}


def _git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
                          cwd=root, check=True, capture_output=True, text=True).stdout


def _placeholder(pattern: str) -> str:
    return pattern.replace("**/", "").replace("*", "x")


@pytest.fixture()
def committed(tmp_path):
    """A committed repository in which every pattern of the real SCOPE matches, with the real bytes of the F2 modules."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_bytes(b"[project]\nname='f2'\n")
    for area in cc.SCOPE:
        paths = [path for path, _ in area.file_reasons] if area.file_reasons else [_placeholder(p) for p in area.patterns]
        for relative in paths:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(b"# placeholder\n")
    (root / "tests" / "mutation_guards.py").write_bytes(b"MUTATIONS = ()\nTARGETS = ()\n")
    (root / "tests" / "mutation_population_v4.py").write_bytes(b"POPULATION_V4 = ()\n")
    for relative in SEMANTIC_EDITS:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, root / relative)
    (root / "docs").mkdir()
    (root / "docs" / "notes.md").write_bytes(b"# notes\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "certified")
    return root, cc.build_certificate(root, certification_id="F2")


def test_the_real_scope_covers_every_module_f2_named() -> None:
    certified = {name for area in cc.SCOPE for name in cc.enumerate_area(ROOT, area)}
    assert set(SEMANTIC_EDITS) <= certified


def test_the_real_tree_has_no_verdict_module_outside_the_certificate() -> None:
    assert cc.authority_closure_problems(ROOT) == []
    closure = cc.authority_import_closure(ROOT)
    assert "src/engcore/claims/adapters/grounding.py" in closure  # F1's grounding decides admissibility
    assert "src/engcore/credibility/evidence.py" in closure


def test_the_fixture_verifies_before_anything_changes(committed) -> None:
    root, certificate = committed
    result = cc.verify_certificate(root, certificate, require_commit=True)
    assert result.ok, result.render()


@pytest.mark.parametrize("relative", sorted(SEMANTIC_EDITS))
def test_a_committed_change_to_verdict_or_authority_semantics_fails_verification(committed, relative) -> None:
    root, certificate = committed
    old, new = SEMANTIC_EDITS[relative]
    text = (root / relative).read_bytes().decode("utf-8")
    assert old in text
    (root / relative).write_bytes(text.replace(old, new, 1).encode("utf-8"))
    _git(root, "commit", "-q", "-am", f"change {relative}")
    result = cc.verify_certificate(root, certificate, require_commit=False)
    assert not result.ok
    assert f"MODIFIED: {relative}" in result.render()


def test_a_documentation_only_commit_does_not_pretend_semantics_changed(committed) -> None:
    root, certificate = committed
    (root / "docs" / "notes.md").write_bytes(b"# notes\n\nreworded\n")
    _git(root, "commit", "-q", "-am", "docs")
    result = cc.verify_certificate(root, certificate, require_commit=False)
    assert result.ok, result.render()


def test_a_new_module_a_verdict_starts_importing_is_refused_until_certified(tmp_path) -> None:
    root = tmp_path / "repo"
    (root / "src" / "engcore" / "claims").mkdir(parents=True)
    (root / "src" / "engcore" / "decider").mkdir(parents=True)
    (root / "src" / "engcore" / "domains").mkdir(parents=True)
    (root / "src" / "engcore" / "__init__.py").write_bytes(b"")
    (root / "src" / "engcore" / "claims" / "__init__.py").write_bytes(b"")
    (root / "src" / "engcore" / "claims" / "verdict.py").write_bytes(
        b"from ..decider.rule import decide\nfrom engcore.domains.solver import solve\n")
    (root / "src" / "engcore" / "decider" / "__init__.py").write_bytes(b"")
    (root / "src" / "engcore" / "decider" / "rule.py").write_bytes(b"def decide():\n    return 'supported'\n")
    (root / "src" / "engcore" / "domains" / "__init__.py").write_bytes(b"")
    (root / "src" / "engcore" / "domains" / "solver.py").write_bytes(b"def solve():\n    return 1.0\n")
    problems = cc.authority_closure_problems(root, cc.SCOPE)
    assert len(problems) == 1
    assert "src/engcore/decider/rule.py" in problems[0] and "src/engcore/decider/__init__.py" in problems[0]
    assert "domains" not in problems[0]  # an answer producer is exempt by declaration, never by omission
