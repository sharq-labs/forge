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
    # review I-2: a provider output with no stated uncertainty reports a zero one to the system runtime
    "src/engcore/providers/records.py": (
        "uncertainty: Uncertainty = field(default_factory=lambda: Uncertainty.unknown(",
        'uncertainty: Uncertainty = field(default_factory=lambda: Uncertainty.from_dict({"kind": "standard", "value": 0.0}) or Uncertainty.unknown('),
    # review I-2: the multi-timescale slow state the system runtime commits silently drops a degradation step
    "src/engcore/multiscale/runtime.py": ("            if step.applied:\n", "            if step.applied and False:\n"),
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
    for importer, imported, why in cc.CERTIFIED_DEPENDENCY_EXCLUSIONS:
        assert why and list(ROOT.glob(importer)) and list(ROOT.glob(imported)), (importer, imported)


def test_the_exemption_no_longer_covers_systems_as_a_whole() -> None:
    """systems/** was 'answers' and held an evidence-binding vocabulary; the F6 mechanism is not exempted either."""
    assert not cc._closure_exempt("src/engcore/systems/twin_revision.py")
    assert not cc._closure_exempt("src/engcore/systems/admissibility.py")
    assert not cc._closure_exempt("src/engcore/systems/new_vocabulary.py")
    assert cc._closure_exempt("src/engcore/systems/products/drone.py")


def _tree(root: pathlib.Path, files: dict[str, bytes]) -> None:
    for relative, data in {"src/engcore/__init__.py": b"", **files}.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(data)


#: A certified area holding one module that is not a verdict root; the package __init__ is control plane, as in SCOPE.
_SCOPE = [cc.ScopeArea("certified", "CORE_CERTIFIED", ("src/engcore/certified/**/*.py",), "test"),
          cc.ScopeArea("control", "CERTIFICATION_CONTROL", ("src/engcore/__init__.py",), "test")]


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


_DESIGN = {
    "src/engcore/claims/__init__.py": b"",
    "src/engcore/claims/design_memory.py": b"from ..design.history import DesignHistory\n",
    "src/engcore/design/__init__.py": b"",
    "src/engcore/design/history.py": b"class DesignHistory:\n    pass\n",
}
_CLAIMS = [cc.ScopeArea("claims", "CORE_CERTIFIED", ("src/engcore/__init__.py", "src/engcore/claims/**/*.py"), "t")]


def test_a_declared_edge_excuses_its_importer_and_only_its_importer(tmp_path) -> None:
    """Review I-1: an exclusion is an edge, not a package-wide blind spot."""
    _tree(tmp_path, _DESIGN)
    assert cc.certified_dependency_problems(tmp_path, _CLAIMS) == []
    _tree(tmp_path, {"src/engcore/claims/stop_rule.py": b"from ..design.history import DesignHistory\n"})
    (problem,) = cc.certified_dependency_problems(tmp_path, _CLAIMS)
    assert "src/engcore/design/history.py" in problem


def test_a_declared_edge_never_excuses_a_verdict_root(tmp_path) -> None:
    """The root closure does not read the table: a verdict that reaches design/** through design_memory fails."""
    _tree(tmp_path, {**_DESIGN, "src/engcore/claims/verdict.py": b"from .design_memory import DesignHistory\n"})
    assert cc.certified_dependency_problems(tmp_path, _CLAIMS) == []
    assert any("src/engcore/design/history.py" in p for p in cc.authority_closure_problems(tmp_path, _CLAIMS))


def test_an_uncertified_module_behind_an_exempt_one_is_reported(tmp_path) -> None:
    """Review I-3: traversal continues through an exempt answer module."""
    _tree(tmp_path, {
        "src/engcore/certified/__init__.py": b"",
        "src/engcore/certified/run.py": b"from ..domains.solver import solve\n",
        "src/engcore/domains/__init__.py": b"",
        "src/engcore/domains/solver.py": b"from ..decider.rule import decide\n",
        "src/engcore/decider/__init__.py": b"",
        "src/engcore/decider/rule.py": b"def decide():\n    return 'admissible'\n",
    })
    (problem,) = cc.certified_dependency_problems(tmp_path, _SCOPE)
    assert "src/engcore/decider/rule.py" in problem and "solver.py" not in problem


def test_a_pinned_control_plane_package_init_is_a_seed(tmp_path) -> None:
    """Review I-4: src/engcore/__init__.py runs on every engcore import, whatever its area's classification."""
    _tree(tmp_path, {
        "src/engcore/__init__.py": b"from . import product\n",
        "src/engcore/certified/__init__.py": b"",
        "src/engcore/product.py": b"VERDICT = 'supported'\n",
    })
    (problem,) = cc.certified_dependency_problems(tmp_path, _SCOPE)
    assert "src/engcore/product.py" in problem


@pytest.mark.parametrize("source", [
    b"import builtins\nbuiltins.exec(open('rule.py').read())\n",
    b"RULE = getattr(__import__('importlib'), 'import_module')('engcore.' + 'decider')\n",
    b"import builtins as b\nb.exec(open('rule.py').read())\n",
    b"from builtins import exec as run\nrun(open('rule.py').read())\n",
    b"import builtins\ngetattr(builtins, 'exec')(open('rule.py').read())\n",
    b"import importlib\nRULE = vars(importlib)['import_module']('engcore.' + 'decider')\n",
])
def test_review_i5_loaders_the_detector_missed_are_refused(tmp_path, source) -> None:
    _tree(tmp_path, {"src/engcore/certified/__init__.py": b"", "src/engcore/certified/stop.py": source})
    problems = cc.certified_dependency_problems(tmp_path, _SCOPE)
    assert any("DYNAMIC_REACH" in p for p in problems), problems


def test_review_i5_a_star_import_from_a_package_reaches_its_submodules(tmp_path) -> None:
    _tree(tmp_path, {
        "src/engcore/certified/__init__.py": b"",
        "src/engcore/certified/stop.py": b"from ..decider import *\n",
        "src/engcore/decider/__init__.py": b"__all__ = ['rule']\n",
        "src/engcore/decider/rule.py": b"def decide():\n    return 'supported'\n",
    })
    (problem,) = cc.certified_dependency_problems(tmp_path, _SCOPE)
    assert "src/engcore/decider/rule.py" in problem


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


def test_a_declared_edge_does_not_excuse_lookalike_names(tmp_path) -> None:
    """Confirmation review: design_memory2.py is not design_memory.py, and designs/ is not design/."""
    _tree(tmp_path, {
        **_DESIGN,
        "src/engcore/claims/design_memory2.py": b"from ..designs.history import DesignHistory\n",
        "src/engcore/designs/__init__.py": b"",
        "src/engcore/designs/history.py": b"class DesignHistory:\n    pass\n",
        "src/engcore/claims/design_memoryx.py": b"from ..design.history import DesignHistory\n",
    })
    (problem,) = cc.certified_dependency_problems(tmp_path, _CLAIMS)
    assert "src/engcore/designs/history.py" in problem and "src/engcore/design/history.py" in problem


# ---- G0/A1 final review (2026-10-14) -------------------------------------------------------------------------------
@pytest.mark.parametrize("source", [
    b"RULE = __import__('engcore', fromlist=['decider']).decider\n",
    b"RULE = __import__('decider', globals(), None, ['rule'], 2)\n",
    b"import importlib\nL = {'k': importlib.import_module}\nRULE = L['k']('engcore.' + 'decider')\n",
    b"import importlib\nRULE = importlib.__dict__['import_module']('engcore.' + 'decider')\n",
])
def test_final_review_c1_loaders_reached_without_a_direct_call_are_refused(tmp_path, source) -> None:
    _tree(tmp_path, {"src/engcore/certified/__init__.py": b"", "src/engcore/certified/stop.py": source})
    problems = cc.certified_dependency_problems(tmp_path, _SCOPE)
    assert any("DYNAMIC_REACH" in p for p in problems), problems


def test_final_review_c2_an_exempt_module_on_the_path_is_checked_for_dynamic_loads(tmp_path) -> None:
    """Traversal continues through exempt answer modules (review I-3), so their computed-name loads count too."""
    _tree(tmp_path, {
        "src/engcore/certified/__init__.py": b"",
        "src/engcore/certified/run.py": b"from ..domains.solver import solve\n",
        "src/engcore/domains/__init__.py": b"",
        "src/engcore/domains/solver.py": b"import importlib\nRULE = importlib.import_module('engcore.' + 'decider')\n"
                                         b"def solve():\n    return 1\n",
    })
    problems = cc.certified_dependency_problems(tmp_path, _SCOPE)
    assert any("src/engcore/domains/solver.py" in p and "DYNAMIC_REACH" in p for p in problems), problems


def test_final_review_c2_a_declared_dynamic_reach_is_traversed(tmp_path, monkeypatch) -> None:
    """A declared computed-name load reaches its targets; what THEY import is followed like any other import."""
    _tree(tmp_path, {
        "src/engcore/certified/__init__.py": b"",
        "src/engcore/certified/load.py": b"import importlib, pkgutil\nimport engcore.domains as d\n"
                                         b"MODS = [importlib.import_module(m.name) for m in pkgutil.walk_packages(d.__path__)]\n",
        "src/engcore/domains/__init__.py": b"",
        "src/engcore/domains/pack.py": b"from ..decider.rule import decide\n",
        "src/engcore/decider/__init__.py": b"",
        "src/engcore/decider/rule.py": b"def decide():\n    return 'admissible'\n",
    })
    monkeypatch.setattr(cc, "DYNAMIC_REACH", (("src/engcore/certified/load.py", "src/engcore/domains/**", "test"),))
    problems = cc.certified_dependency_problems(tmp_path, _SCOPE)
    assert any("src/engcore/decider/rule.py" in p for p in problems), problems


@pytest.mark.parametrize("relative", [
    "src/engcore/certified/__pycache__/stop.cpython-312.pyc",
    "src/engcore/certified/stop.cpython-312-x86_64-linux-gnu.so",
    "src/engcore/certified/stop.pyd",
])
def test_final_review_c3_a_tracked_compiled_module_beside_certified_source_is_refused(tmp_path, relative) -> None:
    """CPython runs an unchecked-hash .pyc or an extension module instead of the pinned .py source."""
    _tree(tmp_path, {"src/engcore/certified/__init__.py": b"", "src/engcore/certified/stop.py": b"X = 1\n",
                     relative: b"\x00compiled"})
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-f", ".")
    problems = cc.source_form_problems(tmp_path)
    assert any(relative in p for p in problems), problems


def test_final_review_c3_the_real_tree_tracks_only_python_source_under_engcore() -> None:
    assert cc.source_form_problems(ROOT) == []
