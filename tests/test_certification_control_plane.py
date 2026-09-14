"""The code that decides what "certificate valid" means is pinned by the certificate.

Finding B of the certification trust-closure round. A change to the verifier, to
the workflows that run it, or to the self-checks the certificate child executes
used to change the meaning of PASS while the certified manifest stayed
byte-identical. The ``certification_control`` scope area pins those bytes, and
these tests prove a change to any of them stops the certificate verifying.

The semantics, stated as tests:

* the area enumerates every ``tools/certification/*.py`` module, both
  certification workflows, the two self-check test modules, the freeze probe the
  freeze verifier loads, and ``tools/__init__.py`` -- and nothing broader;
* every file in it carries its own reason, and the builder refuses a file
  without one or a reason without a file;
* ``certification/current_core_v2.json`` is never in any area (no fixed point);
* a certificate written under an older scope table is refused, not accepted
  because the bytes it does name still agree.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from tests import certification_fixtures as fx
from tools.certification import core_certificate
from tools.certification.core_certificate import (
    CERTIFICATION_CONTROL_FILES,
    SCOPE,
    CertificationError,
    ScopeArea,
    build_certificate,
    build_manifest,
    scope_problems,
    verify_certificate,
)
from tools.certification.hardening_assurance import (
    control_plane_identity,
    executed_scope_problems,
)
from tools.certification.recertification_scope import CERTIFICATE_PATH, match

REPO = pathlib.Path(__file__).resolve().parents[1]


def _area(name):
    return next(a for a in SCOPE if a.name == name)


# ---- the real control plane ----------------------------------------------------------------
def test_the_real_control_plane_pins_the_verifier_the_workflows_and_the_self_checks():
    files = set(core_certificate.enumerate_area(REPO, _area("certification_control")))
    assert {
        "tools/certification/core_certificate.py",
        "tools/certification/core_freeze.py",
        "tools/certification/recertification_scope.py",
        "tools/certification/certificate_lineage.py",
        "tools/certification/hardening_assurance.py",
        "tools/certification/mutation_population.py",
        "tools/certification/assert_clean_tree.py",
        ".github/workflows/recertify-hardened-core.yml",
        ".github/workflows/tests.yml",
        "tests/test_core_certificate.py",
        "tests/test_core_freeze_manifest.py",
        "benchmarks/core_freeze_v1/audit/reproduce.py",
    } <= files


def test_every_certification_module_on_disk_is_in_the_control_plane():
    on_disk = {p.relative_to(REPO).as_posix() for p in (REPO / "tools" / "certification").glob("*.py")}
    assert on_disk <= set(core_certificate.enumerate_area(REPO, _area("certification_control")))


def test_the_control_plane_is_narrow():
    files = core_certificate.enumerate_area(REPO, _area("certification_control"))
    assert not any(f.startswith(".github/") and "workflows/" not in f for f in files)
    assert ".github/workflows/trust-mutations.yml" not in files
    assert "tests/conftest.py" not in files
    assert len(files) == len(CERTIFICATION_CONTROL_FILES)


def test_every_control_plane_file_has_its_own_reason_and_the_real_build_accepts_them():
    manifest = build_manifest(REPO)
    control = manifest["areas"]["certification_control"]
    assert set(control["file_reasons"]) == set(control["files"])
    assert all(reason.strip() for reason in control["file_reasons"].values())


def test_the_certificate_is_never_inside_its_own_scope():
    for area in SCOPE:
        for pattern in area.patterns:
            assert not match(pattern, CERTIFICATE_PATH), (area.name, pattern)
    manifest = build_manifest(REPO)
    assert not any(CERTIFICATE_PATH in area["files"] for area in manifest["areas"].values())


def test_the_dependency_manifest_is_certified():
    assert core_certificate.enumerate_area(REPO, _area("runtime_dependencies")) == ["pyproject.toml"]


# ---- behaviour on a synthetic repository ---------------------------------------------------------
@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    monkeypatch.setattr(core_certificate, "SCOPE", fx.SCOPE)
    root = tmp_path / "repo"
    fx.make_repo(root)
    return root, build_certificate(root, certification_id="SYNTHETIC")


def test_a_modified_verifier_invalidates_the_certificate(synthetic):
    root, certificate = synthetic
    fx.write(root, "tools/certification/verifier.py", "def verify():\n    return 'always'\n")
    result = verify_certificate(root, certificate, require_clean=False, require_commit=False)
    assert not result.ok
    assert "AREA certification_control" in result.render()
    assert "MODIFIED: tools/certification/verifier.py" in result.render()


def test_a_modified_certification_workflow_invalidates_the_certificate(synthetic):
    root, certificate = synthetic
    fx.write(root, ".github/workflows/recertify-hardened-core.yml", "name: Recertify\n# gate removed\n")
    result = verify_certificate(root, certificate, require_clean=False, require_commit=False)
    assert not result.ok
    assert "MODIFIED: .github/workflows/recertify-hardened-core.yml" in result.render()


def test_a_new_certification_module_invalidates_the_certificate(synthetic):
    root, certificate = synthetic
    fx.write(root, "tools/certification/shortcut.py", "OK = True\n")
    result = verify_certificate(root, certificate, require_clean=False, require_commit=False)
    assert "ADDED: tools/certification/shortcut.py" in result.render()


def test_the_builder_refuses_a_control_file_without_a_reason(synthetic):
    root, _ = synthetic
    fx.write(root, "tools/certification/shortcut.py", "OK = True\n")
    fx.commit(root, "unexplained module")
    with pytest.raises(CertificationError, match="unexplained .*shortcut.py"):
        build_certificate(root, certification_id="SYNTHETIC")


def test_the_builder_refuses_a_reason_for_a_file_that_is_gone(synthetic, monkeypatch):
    root, _ = synthetic
    stale = tuple(
        ScopeArea(a.name, a.classification, a.patterns, a.why,
                  file_reasons=(*a.file_reasons, ("tools/certification/removed.py", "gone")))
        if a.name == "certification_control" else a
        for a in fx.SCOPE
    )
    monkeypatch.setattr(core_certificate, "SCOPE", stale)
    with pytest.raises(CertificationError, match="does not enumerate .*removed.py"):
        build_certificate(root, certification_id="SYNTHETIC")


def test_restoring_the_verifier_restores_verification(synthetic):
    root, certificate = synthetic
    target = root / "tools" / "certification" / "verifier.py"
    original = target.read_bytes()
    target.write_bytes(b"def verify():\n    return 1\n")
    assert not verify_certificate(root, certificate, require_commit=False).ok
    target.write_bytes(original)
    assert verify_certificate(root, certificate, require_commit=False).ok


# ---- scope currency ---------------------------------------------------------------------------------
def test_a_certificate_from_before_the_control_plane_is_refused(synthetic, monkeypatch):
    root, _ = synthetic
    narrower = tuple(a for a in fx.SCOPE if a.name != "certification_control")
    monkeypatch.setattr(core_certificate, "SCOPE", narrower)
    old = build_certificate(root, certification_id="SYNTHETIC")
    monkeypatch.setattr(core_certificate, "SCOPE", fx.SCOPE)

    # A verifier change is invisible to it -- which is the whole problem.
    fx.write(root, "tools/certification/verifier.py", "def verify():\n    return 'always'\n")
    fx.commit(root, "weaken the verifier")
    diagnosis = verify_certificate(root, old, require_commit=False, require_current_scope=False)
    assert diagnosis.ok, "the old certificate's own areas still agree"

    result = verify_certificate(root, old, require_commit=False)
    assert not result.ok
    assert any("missing areas ['certification_control']" in p for p in result.problems)


@pytest.mark.parametrize("section", ["manifest", "scope"])
def test_scope_is_compared_in_both_places_it_is_recorded(synthetic, section):
    _root, certificate = synthetic
    tampered = json.loads(json.dumps(certificate))
    if section == "manifest":
        tampered["manifest"]["areas"]["core"]["patterns"] = ["src/engcore/scientific/*.py"]
    else:
        tampered["scope"]["in"][0]["patterns"] = ["src/engcore/scientific/*.py"]
    problems = scope_problems(tampered)
    label = "manifest.areas" if section == "manifest" else "scope.in"
    assert any(label in p and "['core']" in p for p in problems), problems


def test_the_control_plane_identity_is_the_certified_area_digest(synthetic):
    root, certificate = synthetic
    identity = control_plane_identity(root)
    area = certificate["manifest"]["areas"]["certification_control"]
    assert identity == {"area": "certification_control", "digest": area["digest"], "file_count": area["file_count"]}


def test_an_executed_workflow_that_differs_from_the_source_is_refused(synthetic):
    root, _ = synthetic
    source = fx.git(root, "rev-parse", "HEAD")
    fx.write(root, "docs.md", "not certified\n")
    unrelated = fx.commit(root, "unrelated base change")
    assert executed_scope_problems(root, unrelated, source) == []

    fx.write(root, ".github/workflows/recertify-hardened-core.yml", "name: Recertify\non: push\n")
    moved = fx.commit(root, "base changed the workflow")
    problems = executed_scope_problems(root, moved, source)
    assert problems and ".github/workflows/recertify-hardened-core.yml" in problems[0]
