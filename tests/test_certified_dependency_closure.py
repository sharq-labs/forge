"""BR-15: a certified module's meaning may not be decided by code the certificate does not measure.

The F2 closure starts at six verdict/authority roots. Certified modules outside that closure
(claims/falsification.py, claims/twin_evidence.py, sria/campaign/runner.py, system_runtime/executor.py)
imported uncertified modules that decide what their results mean:

* sria/decision/hypotheses.py defines the claim and content identity a falsification verdict binds to;
* sria/campaign/events.py supplies the Arbiter decisions, and their order, to the certified stop review;
* systems/twin_revision.py was exempt as an "answer" yet defines the evidence context and the CANDIDATE ban;
* scenarios/environment.py refuses to extrapolate a boundary condition the system runtime records;
* materials/properties.py keeps a missing material uncertainty UNKNOWN.

A committed hostile edit to any of them left the certificate verifying. These tests commit each edit
under the REAL scope table and require verification to fail, require the derived closure over every
certified file to be covered, and keep the declared exclusions out of reach of every verdict root.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

from tools.certification import core_certificate as cc

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The uncertified module, a committed hostile edit to it, and the authority it moves.
DEPENDENCY_EDITS = {
    # a refutation stops following its claim: a refuted claim re-registered under a new id survives
    "src/engcore/sria/decision/hypotheses.py": (
        'CLAIM_FIELDS = ("kind",', 'CLAIM_FIELDS = ("hypothesis_id", "kind",'),
    # the stop review never sees an INVALID Arbiter decision: STOP_REJECTED becomes STOP_APPROVED
    "src/engcore/sria/campaign/events.py": (
        "return iter(tuple(self._events))",
        "return iter(tuple(e for e in self._events if e.payload.get('verdict', 'valid') == 'valid'))"),
    # evidence produced for one geometry resolves against another (context identity)
    "src/engcore/systems/twin_revision.py": ('"geometry_digests": list(geometry), ', ""),
    # a missing boundary condition is extrapolated instead of being UNKNOWN
    "src/engcore/scenarios/environment.py": ("if not before or not after:", "if not before and not after:"),
    # a material datum with no stated uncertainty is reported with a zero one
    "src/engcore/materials/properties.py": (
        'Uncertainty.unknown(f"claim {d.claim.claim_id} states no uncertainty")',
        'Uncertainty.from_dict({"kind": "standard", "value": 0.0})'),
}

#: Declared non-authoritative: a committed edit is allowed not to move the certificate (positive control).
EXCLUDED_EDIT = ("src/engcore/design/history.py", "\n", "\nSEARCH_MEMORY_NOTE = 'reworded'\n")


def _git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
                          cwd=root, check=True, capture_output=True, text=True).stdout


def _placeholder(pattern: str) -> str:
    return pattern.replace("**/", "").replace("*", "x")


@pytest.fixture()
def committed(tmp_path):
    """A committed repository under the real SCOPE, with the real bytes of every dependency under test."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_bytes(b"[project]\nname='br15'\n")
    for area in cc.SCOPE:
        paths = [path for path, _ in area.file_reasons] if area.file_reasons else [_placeholder(p) for p in area.patterns]
        for relative in paths:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(b"# placeholder\n")
    (root / "tests" / "mutation_guards.py").write_bytes(b"MUTATIONS = ()\nTARGETS = ()\n")
    (root / "tests" / "mutation_population_v4.py").write_bytes(b"POPULATION_V4 = ()\n")
    for relative in (*DEPENDENCY_EDITS, EXCLUDED_EDIT[0]):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, root / relative)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "certified")
    return root, cc.build_certificate(root, certification_id="BR15")


def test_the_fixture_verifies_before_anything_changes(committed) -> None:
    root, certificate = committed
    result = cc.verify_certificate(root, certificate, require_commit=True)
    assert result.ok, result.render()


@pytest.mark.parametrize("relative", sorted(DEPENDENCY_EDITS))
def test_a_committed_edit_to_a_dependency_that_decides_certified_meaning_fails_verification(committed, relative) -> None:
    root, certificate = committed
    old, new = DEPENDENCY_EDITS[relative]
    text = (root / relative).read_bytes().decode("utf-8")
    assert text.count(old) == 1, relative
    (root / relative).write_bytes(text.replace(old, new, 1).encode("utf-8"))
    _git(root, "commit", "-q", "-am", f"hostile edit to {relative}")
    result = cc.verify_certificate(root, certificate, require_commit=False)
    assert not result.ok
    assert f"MODIFIED: {relative}" in result.render()


def test_positive_control_a_declared_non_authoritative_dependency_does_not_move_the_certificate(committed) -> None:
    root, certificate = committed
    relative, old, new = EXCLUDED_EDIT
    text = (root / relative).read_bytes().decode("utf-8")
    (root / relative).write_bytes(text.replace(old, new, 1).encode("utf-8"))
    _git(root, "commit", "-q", "-am", "edit design search memory")
    result = cc.verify_certificate(root, certificate, require_commit=False)
    assert result.ok, result.render()


# ---- the derived closure over every certified file -------------------------------------------------


def test_the_real_tree_covers_what_every_certified_module_imports() -> None:
    assert cc.certified_dependency_problems(ROOT) == []
    certified = {name for area in cc.SCOPE for name in cc.enumerate_area(ROOT, area)}
    assert set(DEPENDENCY_EDITS) <= certified
    assert "src/engcore/systems/__init__.py" in certified  # importing twin_revision runs it


def test_no_declared_exclusion_is_reachable_from_a_verdict_or_authority_root() -> None:
    closure = cc.authority_import_closure(ROOT)
    reached = [name for name in closure if cc._dependency_excluded(name)]
    assert reached == []
    for pattern, why in cc.CERTIFIED_DEPENDENCY_EXCLUSIONS:
        assert why and any(cc._dependency_excluded(p.relative_to(ROOT).as_posix()) for p in ROOT.glob(pattern)), pattern


def _tree(root: pathlib.Path, files: dict[str, bytes]) -> None:
    for relative, data in {"src/engcore/__init__.py": b"", **files}.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(data)


#: A certified area holding one module that is not a verdict root.
_SCOPE = [cc.ScopeArea("certified", "CORE_CERTIFIED", ("src/engcore/__init__.py", "src/engcore/certified/**/*.py"), "test")]


def test_a_certified_non_root_module_importing_an_uncertified_decider_is_refused(tmp_path) -> None:
    _tree(tmp_path, {
        "src/engcore/certified/__init__.py": b"",
        "src/engcore/certified/stop.py": b"from ..decider.rule import decide\n",
        "src/engcore/decider/__init__.py": b"",
        "src/engcore/decider/rule.py": b"def decide():\n    return 'stop_approved'\n",
    })
    (problem,) = cc.certified_dependency_problems(tmp_path, _SCOPE)
    assert "src/engcore/decider/rule.py" in problem and "src/engcore/decider/__init__.py" in problem
    with pytest.raises(cc.CertificationError, match="certified module"):
        cc.build_manifest(tmp_path, _SCOPE)


def test_a_dependency_missing_today_is_refused_the_day_it_appears(tmp_path) -> None:
    _tree(tmp_path, {
        "src/engcore/certified/__init__.py": b"",
        "src/engcore/certified/stop.py": b"try:\n    from ..later import rule\nexcept ImportError:\n    rule = None\n",
    })
    assert cc.certified_dependency_problems(tmp_path, _SCOPE) == []  # nothing to load, so nothing loaded
    _tree(tmp_path, {"src/engcore/later/__init__.py": b"", "src/engcore/later/rule.py": b"X = 1\n"})
    (problem,) = cc.certified_dependency_problems(tmp_path, _SCOPE)
    assert "src/engcore/later/rule.py" in problem


@pytest.mark.parametrize("source", [
    b"import importlib\nNAME = 'engcore.decider.rule'\nRULE = importlib.import_module(NAME)\n",
    b"from importlib import import_module as load\nRULE = load('engcore.' + 'decider')\n",
])
def test_a_dynamic_import_substitution_in_a_certified_module_is_refused(tmp_path, source) -> None:
    _tree(tmp_path, {"src/engcore/certified/__init__.py": b"", "src/engcore/certified/stop.py": source})
    problems = cc.certified_dependency_problems(tmp_path, _SCOPE)
    assert any("DYNAMIC_REACH" in p and "src/engcore/certified/stop.py" in p for p in problems), problems


def test_an_exempt_answer_package_stays_exempt_but_its_init_does_not(tmp_path) -> None:
    _tree(tmp_path, {
        "src/engcore/certified/__init__.py": b"",
        "src/engcore/certified/run.py": b"from ..domains.solver import solve\n",
        "src/engcore/domains/__init__.py": b"",
        "src/engcore/domains/solver.py": b"def solve():\n    return 1.0\n",
    })
    (problem,) = cc.certified_dependency_problems(tmp_path, _SCOPE)
    assert "src/engcore/domains/__init__.py" in problem and "solver.py" not in problem


def test_a_declared_exclusion_never_excuses_a_verdict_root(tmp_path) -> None:
    """An exclusion only says a certified NON-authority module reads it; the root closure ignores it."""
    _tree(tmp_path, {
        "src/engcore/claims/__init__.py": b"",
        "src/engcore/claims/verdict.py": b"from ..design.history import DesignHistory\n",
        "src/engcore/design/__init__.py": b"",
        "src/engcore/design/history.py": b"class DesignHistory:\n    pass\n",
    })
    scope = [cc.ScopeArea("claims", "CORE_CERTIFIED", ("src/engcore/__init__.py", "src/engcore/claims/**/*.py"), "t")]
    assert cc.certified_dependency_problems(tmp_path, scope) == []  # design/** is a declared exclusion here...
    assert any("src/engcore/design/history.py" in p for p in cc.authority_closure_problems(tmp_path, scope))  # ...not for a verdict


def test_the_closure_names_files_with_their_on_disk_spelling(tmp_path) -> None:
    """`from .results import Uncertainty` is a symbol, not a module, even where the filesystem ignores case."""
    _tree(tmp_path, {
        "src/engcore/certified/__init__.py": b"from .results import Uncertainty\n",
        "src/engcore/certified/results/__init__.py": b"from .uncertainty import Uncertainty\n",
        "src/engcore/certified/results/uncertainty.py": b"class Uncertainty:\n    pass\n",
    })
    closure = cc.authority_import_closure(tmp_path, roots=("src/engcore/certified/__init__.py",))
    assert "src/engcore/certified/results/uncertainty.py" in closure
    assert all((tmp_path / name).name in {p.name for p in (tmp_path / name).parent.iterdir()} for name in closure)
    assert cc.certified_dependency_problems(tmp_path, _SCOPE) == []
