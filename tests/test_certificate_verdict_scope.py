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


# ---- third review B1-B4: the builder and the verifier enforce the closure, past dynamic imports too ----


def _closure_tree(root: pathlib.Path, verdict_source: bytes) -> list[cc.ScopeArea]:
    for package in ("claims", "decider", "domains"):
        (root / "src" / "engcore" / package).mkdir(parents=True)
        (root / "src" / "engcore" / package / "__init__.py").write_bytes(b"")
    (root / "src" / "engcore" / "__init__.py").write_bytes(b"")
    (root / "src" / "engcore" / "claims" / "verdict.py").write_bytes(verdict_source)
    (root / "src" / "engcore" / "decider" / "rule.py").write_bytes(b"def decide():\n    return 'supported'\n")
    return [cc.ScopeArea("claims", "CORE_CERTIFIED", ("src/engcore/__init__.py", "src/engcore/claims/**/*.py",
                                                      "src/engcore/domains/__init__.py"), "test")]


def test_b2_an_exempt_package_init_is_not_exempt(tmp_path) -> None:
    scope = _closure_tree(tmp_path, b"from engcore.domains.solver import solve\n")
    (tmp_path / "src" / "engcore" / "domains" / "solver.py").write_bytes(b"def solve():\n    return 1.0\n")
    unpinned = [cc.ScopeArea("claims", "CORE_CERTIFIED", ("src/engcore/__init__.py", "src/engcore/claims/**/*.py"), "t")]
    assert cc.authority_closure_problems(tmp_path, scope) == []
    (problem,) = cc.authority_closure_problems(tmp_path, unpinned)
    assert "src/engcore/domains/__init__.py" in problem and "solver.py" not in problem


def test_b4_the_manifest_builder_refuses_a_closure_gap(tmp_path) -> None:
    scope = _closure_tree(tmp_path, b"from ..decider.rule import decide\n")
    with pytest.raises(cc.CertificationError, match="outside every certified area"):
        cc.build_manifest(tmp_path, scope)


def test_b4_the_verifier_refuses_a_committed_closure_gap(committed) -> None:
    root, certificate = committed
    (root / "src" / "engcore" / "decider").mkdir(parents=True)
    (root / "src" / "engcore" / "decider" / "__init__.py").write_bytes(b"")
    (root / "src" / "engcore" / "decider" / "rule.py").write_bytes(b"def decide():\n    return 'supported'\n")
    verdict = root / "src" / "engcore" / "claims" / "verdict.py"
    verdict.write_bytes(verdict.read_bytes() + b"\nfrom ..decider.rule import decide  # noqa\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "a verdict starts importing an uncertified module")
    result = cc.verify_certificate(root, certificate, require_commit=False)
    assert not result.ok
    assert any("src/engcore/decider/rule.py" in problem for problem in result.problems), result.render()


def test_b1_a_literal_import_module_is_followed_like_an_import(tmp_path) -> None:
    scope = _closure_tree(tmp_path, b"import importlib\nRULE = importlib.import_module('engcore.decider.rule')\n")
    problems = cc.authority_closure_problems(tmp_path, scope)
    assert len(problems) == 1 and "src/engcore/decider/rule.py" in problems[0]


@pytest.mark.parametrize("source", [
    b"import importlib\nNAME = 'engcore.decider.rule'\nRULE = importlib.import_module(NAME)\n",
    b"import pkgutil\nimport engcore\nFOUND = list(pkgutil.walk_packages(engcore.__path__))\n",
    b"RULE = __import__('engcore.' + 'decider')\n",
    # fourth review: loaders the first detector missed
    b"from importlib import import_module as load\nRULE = load('engcore.' + 'decider.rule')\n",
    b"import importlib\nRULE = getattr(importlib, 'import_module')('engcore.decider.rule')\n",
    b"import importlib.util\nSPEC = importlib.util.spec_from_file_location('r', 'src/engcore/decider/rule.py')\n",
    b"import runpy\nNS = runpy.run_path('src/engcore/decider/rule.py')\n",
    b"exec(open('src/engcore/decider/rule.py').read())\n",
    b"import importlib\nRULE = importlib.import_module('.rule', 'engcore.decider')\n",
    b"from importlib.metadata import entry_points\nPLUGINS = entry_points(group='forge')\n",
    b"import importlib\nload = importlib.import_module\nRULE = load('engcore.decider.rule')\n",  # fifth review
])
def test_b1_an_undeclared_dynamic_import_in_the_closure_is_refused(tmp_path, source) -> None:
    scope = _closure_tree(tmp_path, source)
    problems = cc.authority_closure_problems(tmp_path, scope)
    assert any("DYNAMIC_REACH" in problem and "src/engcore/claims/verdict.py" in problem for problem in problems), problems


def test_b1_every_declared_dynamic_reach_is_real_and_covered() -> None:
    closure = set(cc.authority_import_closure(ROOT))
    for file, reach, why in cc.DYNAMIC_REACH:
        assert (ROOT / file).is_file() and why
        assert cc.dynamic_imports(ROOT / file), f"{file} is declared dynamic and has no dynamic import"
    undeclared = [name for name in closure if cc.dynamic_imports(ROOT / name)
                  and name not in {file for file, _, _ in cc.DYNAMIC_REACH}]
    assert undeclared == []


def test_b1_the_model_index_walks_only_the_declaring_package_and_refuses_a_shadow(monkeypatch) -> None:
    import pkgutil
    import sys
    import types
    from dataclasses import replace

    from engcore.credibility import evidence
    from engcore.credibility.errors import CredibilityEvidenceError

    monkeypatch.setattr(evidence, "_MODEL_INDEX", None)
    real = dict(evidence._declared_models())
    assert real
    walked: list[str] = []
    original = pkgutil.walk_packages

    def recording(path=None, prefix="", onerror=None):
        top = not walked
        walked.append(prefix)
        if not top:  # pkgutil recurses through its own global name: let the inner walks through untouched
            yield from original(path, prefix, onerror)
            return
        yield from original(path, prefix, onerror)
        yield pkgutil.ModuleInfo(None, prefix + "zz_shadow", False)

    key, definition = sorted(real.items())[0]
    shadow = types.ModuleType("engcore.domains.zz_shadow")
    shadow.SHADOW = replace(definition, exclusions=(), excludes_nothing_because="a shadow claims to exclude nothing")
    assert shadow.SHADOW != definition
    monkeypatch.setitem(sys.modules, "engcore.domains.zz_shadow", shadow)
    monkeypatch.setattr(pkgutil, "walk_packages", recording)
    monkeypatch.setattr(evidence, "_MODEL_INDEX", None)
    with pytest.raises(CredibilityEvidenceError, match="two different model definitions"):
        evidence._declared_models()
    assert walked[0] == "engcore.domains." and all(p.startswith("engcore.domains.") for p in walked)


def test_b3_the_production_registry_is_pinned_and_a_moved_registry_fails() -> None:
    actual = cc.production_registry_identity(ROOT)
    assert actual is not None and len(actual["digest"]) == 64
    assert cc.registry_problems(ROOT, {"manifest": {"production_registry": actual}}) == []
    moved = {**actual, "capabilities": {**actual["capabilities"]}}
    first = sorted(moved["capabilities"])[0]
    moved["capabilities"][first] = {**moved["capabilities"][first], "executor": "engcore.elsewhere:run"}
    problems = cc.registry_problems(ROOT, {"manifest": {"production_registry": moved}})
    assert problems and first in problems[0]
    assert "predates the pin" in cc.registry_problems(ROOT, {"manifest": {}})[0]


def test_b3_the_verifier_and_the_builder_carry_the_registry_pin(committed, monkeypatch) -> None:
    root, certificate = committed
    monkeypatch.setattr(cc, "registry_problems", lambda r, c: ["REGISTRY SENTINEL"])
    assert "REGISTRY SENTINEL" in cc.verify_certificate(root, certificate, require_commit=False).problems
    monkeypatch.setattr(cc, "production_registry_identity", lambda r: {"digest": "d" * 64, "capabilities": {}})
    assert cc.build_manifest(root)["production_registry"]["digest"] == "d" * 64

def test_fourth_review_the_registry_pin_covers_source_bytes_and_model_modules() -> None:
    actual = cc.production_registry_identity(ROOT)
    for declaration in actual["capabilities"].values():
        executor = declaration["executor"]
        assert executor["source"].startswith("src/") and len(executor["sha256"]) == 64
        assert executor["sha256"] == cc.file_digest(ROOT / executor["source"])
    models = actual["model_definition_modules"]
    assert models and all(entry["sha256"] == cc.file_digest(ROOT / entry["source"]) for entry in models.values())
    assert all(name.startswith("engcore.domains.") for name in models)


def test_fourth_review_the_registry_probe_is_not_steered_by_the_environment(monkeypatch) -> None:
    baseline = cc.production_registry_identity(ROOT)
    monkeypatch.setenv("FORGE_DOMAIN_PACKS", "some.external:pack")
    monkeypatch.setenv("PYTHONPATH", "/nonexistent-shadow")
    assert cc.production_registry_identity(ROOT) == baseline


def test_fourth_review_a_claims_tree_without_its_registry_entry_cannot_be_certified(tmp_path) -> None:
    (tmp_path / "src" / "engcore" / "claims").mkdir(parents=True)
    (tmp_path / "src" / "engcore" / "claims" / "assessment.py").write_bytes(b"")
    with pytest.raises(cc.CertificationError, match="cannot be pinned"):
        cc.production_registry_identity(tmp_path)


def test_fourth_review_a_domain_module_that_does_not_import_fails_the_model_index(monkeypatch) -> None:
    import pkgutil

    from engcore.credibility import evidence
    from engcore.credibility.errors import CredibilityEvidenceError

    original = pkgutil.walk_packages

    def broken(path=None, prefix="", onerror=None):
        yield from original(path, prefix, onerror)
        if prefix == "engcore.domains.":
            yield pkgutil.ModuleInfo(None, prefix + "zz_does_not_exist", False)

    monkeypatch.setattr(pkgutil, "walk_packages", broken)
    monkeypatch.setattr(evidence, "_MODEL_INDEX", None)
    with pytest.raises(CredibilityEvidenceError, match="model index incomplete"):
        evidence._declared_models()

def test_fifth_review_the_pin_covers_the_code_that_builds_the_evidence() -> None:
    code = cc.production_registry_identity(ROOT)["evidence_code"]
    # product/battery.py builds the battery CredibilityEvidenceReport itself; product/problem.py runs electrothermal
    assert {"src/engcore/product/battery.py", "src/engcore/product/problem.py", "src/engcore/product/capabilities.py"} <= set(code)
    answers = [n for n in code if n.startswith(("src/engcore/domains/", "src/engcore/systems/"))]
    assert set(answers) <= {"src/engcore/domains/__init__.py", "src/engcore/systems/__init__.py"}, answers  # packages' own __init__ only
    assert all(code[name] == cc.file_digest(ROOT / name) for name in code)


def test_fifth_review_a_moved_evidence_module_fails_verification() -> None:
    actual = cc.production_registry_identity(ROOT)
    stored = {**actual, "evidence_code": {**actual["evidence_code"], "src/engcore/product/battery.py": "0" * 64}}
    (problem,) = cc.registry_problems(ROOT, {"manifest": {"production_registry": stored}})
    assert "src/engcore/product/battery.py" in problem