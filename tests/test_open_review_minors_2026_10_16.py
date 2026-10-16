"""Open review MINORs from the 2026-10-16 landing pass, each with a reproducer.

* An ``UncertaintyBudgetReport`` built directly could be empty (UNKNOWN read as zero) or carry an
  aggregate its own components do not reproduce.
* A claim whose applicability evaluator failed (NOT_ASSESSABLE) was reported as a missing capability.
* The certification ownership rule missed three hostile inventories: names escaping the root, a ``.git``
  file naming another repository, and a tracked file replaced by a directory.
"""

from __future__ import annotations

import os
import pathlib
import stat
import subprocess
import types
from dataclasses import replace

import pytest

from engcore.claims import (
    CapabilityRegistry,
    ExperimentAction,
    GapClass,
    analyze_gaps,
    assess_claim,
    recommend_next,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.models.definition import ValidityDomain
from engcore.uq.budget.aggregation import AggregatedUncertainty
from engcore.uq.budget.component import UncertaintyComponent
from engcore.uq.budget.correlation import Correlation
from engcore.uq.budget.report import UncertaintyBudgetReport
from engcore.uq.budget.serialization import budget_from_dict, budget_to_dict
from engcore.uq.budget.source import UncertaintySource
from tests.claims.test_claims_selection import _capability, _claim, _model
from tools.certification import mutation_workspace as mw
from tools.certification import ownership
from tools.certification.ownership import OwnershipError, owned_files, tracked_files


# --- uncertainty budget ------------------------------------------------------------------------------------


def _component(cid: str, u: float) -> UncertaintyComponent:
    return UncertaintyComponent(cid, UncertaintySource.MEASUREMENT, u)


def test_a_directly_built_empty_budget_is_refused_not_zero():
    with pytest.raises(ValueError, match="UNKNOWN"):
        UncertaintyBudgetReport((), (), AggregatedUncertainty(0.0, 0.0))


def test_a_directly_built_budget_cannot_understate_its_aggregate():
    with pytest.raises(ValueError, match="does not match"):
        UncertaintyBudgetReport((_component("a", 2.0),), (), AggregatedUncertainty(0.5, 0.25))


def test_a_directly_built_budget_cannot_drop_a_declared_correlation():
    a, b = _component("a", 1.0), _component("b", 1.0)
    correlated = UncertaintyBudgetReport.build((a, b), (Correlation("a", "b", 1.0),))
    with pytest.raises(ValueError, match="does not match"):
        UncertaintyBudgetReport((a, b), (Correlation("a", "b", 0.0),), correlated.aggregate)


def test_a_budget_aggregate_must_be_the_record_type():
    with pytest.raises(ValueError, match="does not match"):
        UncertaintyBudgetReport((_component("a", 2.0),), (), {"standard_uncertainty": 2.0, "variance": 4.0})


def test_build_and_round_trip_are_unchanged():
    report = UncertaintyBudgetReport.build([_component("a", 3.0), _component("b", 4.0)], [Correlation("a", "b", 0.0)])
    assert report.aggregate == AggregatedUncertainty(5.0, 25.0)
    assert isinstance(report.components, tuple) and isinstance(report.correlations, tuple)
    assert budget_from_dict(budget_to_dict(report)) == report


# --- NOT_ASSESSABLE applicability is not a missing capability ----------------------------------------------


def _evaluator_failure(monkeypatch):
    declaration = replace(_capability("syn.broken", _model("syn.beam")))

    def fail(*a, **k):
        raise InvalidScientificProblem("declared applicability evaluator failed")

    monkeypatch.setattr(ValidityDomain, "assess", fail)
    registry = CapabilityRegistry((declaration,))
    return assess_claim(_claim(), registry).to_dict(), registry


def test_an_unassessable_applicability_is_reported_as_unknown_applicability(monkeypatch):
    record, _ = _evaluator_failure(monkeypatch)
    analysis = analyze_gaps(record)
    assert analysis.complete, analysis.to_dict()
    unknown = analysis.of_kind(GapClass.MODEL_APPLICABILITY_UNKNOWN)
    assert [g.target for g in unknown] == ["syn.beam#*"]
    assert all(g.blocking for g in unknown)
    assert not analysis.of_kind(GapClass.CAPABILITY_MISSING)
    assert record["verdict"] == "insufficient_evidence"


def test_the_next_step_for_an_evaluator_failure_is_a_capability_repair_not_an_input(monkeypatch):
    record, registry = _evaluator_failure(monkeypatch)
    plan = recommend_next(record, registry)
    actions = {(r.action, r.target) for r in plan.recommendations}
    assert (ExperimentAction.EXTEND_CAPABILITY, "syn.beam#*") in actions
    assert not any(r.action in (ExperimentAction.PROVIDE_INPUT, ExperimentAction.ESTABLISH_APPLICABILITY)
                   for r in plan.recommendations)


def test_a_capability_that_produces_nothing_is_still_a_missing_capability():
    record = {
        "compilation": {"status": "unsupported_capability", "reasons": ["nothing produces q"]},
        "repair_actions": [{"kind": "extend_capability", "target": "q", "reason": "no capability",
                            "required_for": [], "detail": {}}],
    }
    analysis = analyze_gaps(record)
    assert [g.target for g in analysis.of_kind(GapClass.CAPABILITY_MISSING)] == ["q"]
    assert not analysis.of_kind(GapClass.MODEL_APPLICABILITY_UNKNOWN)


def test_every_predicted_gap_kind_has_an_explanation():
    # Reproducer: an APPLICABILITY_UNASSESSABLE prediction made assess_claim raise KeyError in explain().
    from engcore.claims.compiler import GapKind
    from engcore.claims.explanation import _GAP_KIND

    assert set(_GAP_KIND) == {kind.value for kind in GapKind}


# --- ownership: the inventory must be this checkout's ------------------------------------------------------


def _git(root, *args):
    subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args], cwd=root,
                   check=True, capture_output=True)


def _write(root, relative, text="x = 1\n"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


@pytest.fixture()
def checkout(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _write(root, "src/pkg/__init__.py", "")
    _write(root, "src/pkg/model.py")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "repo")
    return root


@pytest.mark.parametrize("name", ["../outside.py", "/etc/passwd", "src/../../x.py", "C:/x.py", "src\\x.py", "a//b.py"])
def test_an_inventory_name_escaping_the_root_is_refused(checkout, monkeypatch, name):
    real = subprocess.run

    def poisoned(args, **kwargs):
        if "ls-files" in args:
            return subprocess.CompletedProcess(args, 0, stdout=b"src/pkg/model.py\0" + name.encode() + b"\0", stderr=b"")
        return real(args, **kwargs)

    monkeypatch.setattr(ownership.subprocess, "run", poisoned)
    with pytest.raises(OwnershipError, match="outside the repository root"):
        tracked_files(checkout)


def test_a_reported_top_level_elsewhere_is_refused(checkout, tmp_path, monkeypatch):
    real = subprocess.run

    def elsewhere(args, **kwargs):
        if "--show-toplevel" in args:
            return subprocess.CompletedProcess(args, 0, stdout=str(tmp_path).encode() + b"\n", stderr=b"")
        return real(args, **kwargs)

    monkeypatch.setattr(ownership.subprocess, "run", elsewhere)
    with pytest.raises(OwnershipError, match="another repository"):
        tracked_files(checkout)


def test_a_git_file_naming_another_repository_is_refused(checkout, tmp_path):
    impostor = tmp_path / "impostor"
    _write(impostor, "src/pkg/__init__.py", "")
    _write(impostor, ".git", f"gitdir: {(checkout / '.git').as_posix()}\n")
    with pytest.raises(OwnershipError, match="does not name this checkout back"):
        tracked_files(impostor)


def test_a_linked_worktree_is_still_its_own_checkout(checkout, tmp_path):
    linked = tmp_path / "linked"
    _git(checkout, "worktree", "add", "-q", "--detach", str(linked))
    assert (linked / ".git").is_file()
    assert tracked_files(linked) == frozenset({"src/pkg/__init__.py", "src/pkg/model.py"})


def test_a_separated_git_directory_with_its_worktree_declared_is_accepted(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    _write(root, "a.py")
    _git(root, "init", "-q", "--separate-git-dir", str(tmp_path / "store.git"))
    _git(root, "config", "core.worktree", str(root))
    _git(root, "add", "-A")
    assert tracked_files(root) == frozenset({"a.py"})


def test_a_tracked_file_replaced_by_a_directory_is_refused_not_dropped(checkout):
    source = checkout / "src/pkg/model.py"
    source.unlink()
    source.mkdir()
    _write(checkout, "src/pkg/model.py/inner.py", "VALUE = 3\n")
    owned = owned_files(checkout)
    assert "src/pkg/model.py" in owned.refused
    assert not any(name.startswith("src/pkg/model.py") for name in owned.files)


def test_a_deleted_tracked_file_is_absent_not_refused(checkout):
    (checkout / "src/pkg/model.py").unlink()
    owned = owned_files(checkout)
    assert "src/pkg/model.py" not in owned.files
    assert not owned.refused


def test_this_repository_checkout_is_still_owned():
    root = pathlib.Path(__file__).resolve().parents[1]
    tracked = tracked_files(root)
    assert tracked is not None and "tools/certification/ownership.py" in tracked


# --- review I-1, I-4, I-6: linked .git, foreign worktree gitdir, relative back-reference, case variants ------


def _directory_link(link: pathlib.Path, target: pathlib.Path) -> None:
    """A directory link that needs no privilege: a junction on Windows, a symlink elsewhere."""
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_a_linked_git_directory_is_refused(checkout, tmp_path):
    impostor = tmp_path / "impostor"
    _write(impostor, "build/kept.py", "KEPT = 1\n")
    _directory_link(impostor / ".git", checkout / ".git")
    assert ownership.is_link(impostor / ".git")
    with pytest.raises(OwnershipError, match="is a link"):
        tracked_files(impostor)
    with pytest.raises(OwnershipError):
        owned_files(impostor)


def test_a_git_file_naming_another_worktrees_git_directory_is_refused(checkout, tmp_path):
    other = tmp_path / "other"
    _git(checkout, "worktree", "add", "-q", "--detach", str(other))
    foreign = (other / ".git").read_text(encoding="utf-8").split(":", 1)[1].strip()
    impostor = tmp_path / "impostor"
    _write(impostor, "src/pkg/__init__.py", "")
    _write(impostor, ".git", f"gitdir: {foreign}\n")
    with pytest.raises(OwnershipError, match="does not name this checkout back"):
        tracked_files(impostor)


def test_a_relative_worktree_back_reference_is_read_against_the_git_directory(checkout, tmp_path):
    linked = tmp_path / "linked"
    _git(checkout, "worktree", "add", "-q", "--detach", str(linked))
    git_dir = pathlib.Path((linked / ".git").read_text(encoding="utf-8").split(":", 1)[1].strip())
    back = git_dir / "gitdir"
    back.write_bytes((os.path.relpath(linked / ".git", git_dir).replace(os.sep, "/") + "\n").encode("utf-8"))
    assert tracked_files(linked) == frozenset({"src/pkg/__init__.py", "src/pkg/model.py"})


def test_a_case_variant_directory_replacing_a_tracked_file_is_never_walked_as_owned(tmp_path):
    root = tmp_path / "repo"
    _write(root, "src/Model.py")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "repo")
    (root / "src/Model.py").unlink()
    (root / "src/model.py").mkdir()
    _write(root, "src/model.py/inner.py", "VALUE = 3\n")
    owned = owned_files(root)
    case_insensitive = (root / "src/MODEL.PY").exists()
    if case_insensitive:
        # The tracked spelling now names a directory: refused, and nothing under it is read as owned.
        assert "src/Model.py" in owned.refused
        assert not any(name.casefold().startswith("src/model.py/") for name in owned.files)
    else:
        # Different names on a case-sensitive filesystem: the tracked file is deleted, the directory is new source.
        assert "src/Model.py" not in owned.files and not owned.refused
        assert "src/model.py/inner.py" in owned.files


# --- review I-2, I-3: the certified snapshot reads link counts and junctions from the filesystem -----------


class _Entry:
    """A scandir entry as Windows reports it: st_nlink 0 in its cached stat."""

    def __init__(self, real, *, junction=None, info=None):
        self._real, self._junction, self._info = real, junction, info
        self.name, self.path = real.name, real.path
        if junction is not None:
            self.is_junction = lambda: junction

    def stat(self, follow_symlinks=True):
        if self._info is not None:
            return self._info
        real = self._real.stat(follow_symlinks=follow_symlinks)
        fields = list(real)
        fields[3] = 0  # st_nlink
        return os.stat_result(fields)


class _Scan:
    def __init__(self, entries):
        self._entries = entries

    def __enter__(self):
        return iter(self._entries)

    def __exit__(self, *exc):
        return False


def _windows_scandir(monkeypatch, wrap=lambda real: _Entry(real)):
    real_scandir = os.scandir

    def scandir(path):
        with real_scandir(path) as handle:
            return _Scan([wrap(entry) for entry in handle])

    monkeypatch.setattr(mw.os, "scandir", scandir)


def test_a_zero_link_count_from_scandir_is_reread_and_a_hard_link_still_refuses_the_seed(tmp_path, monkeypatch):
    seed = tmp_path / "seed"
    _write(seed, "a.py")
    _windows_scandir(monkeypatch)
    calls = []
    real_lstat = os.lstat
    monkeypatch.setattr(mw.os, "lstat", lambda p, *a, **k: calls.append(p) or real_lstat(p, *a, **k))
    entries = mw.snapshot(seed)
    assert entries["a.py"].links == 1 and calls
    mw.PristineIndex.build(seed)
    os.link(seed / "a.py", seed / "b.py")
    assert mw.snapshot(seed)["a.py"].links == 2
    with pytest.raises(mw.WorkspaceError, match="links or special files"):
        mw.PristineIndex.build(seed)


def test_a_junction_is_recorded_as_special_and_never_walked(tmp_path, monkeypatch):
    seed = tmp_path / "seed"
    _write(seed, "a.py")
    _write(seed, "linked/inner.py")
    _windows_scandir(monkeypatch, lambda real: _Entry(real, junction=real.name == "linked"))
    entries = mw.snapshot(seed)
    assert entries["linked"].kind == "special"
    assert "linked/inner.py" not in entries
    with pytest.raises(mw.WorkspaceError, match="links or special files"):
        mw.PristineIndex.build(seed)


def test_a_junction_is_recognised_from_its_reparse_tag_without_is_junction(tmp_path, monkeypatch):
    seed = tmp_path / "seed"
    _write(seed, "linked/inner.py")
    tagged = types.SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_nlink=1, st_size=0,
                                   st_reparse_tag=mw._IO_REPARSE_TAG_MOUNT_POINT)
    _windows_scandir(monkeypatch, lambda real: _Entry(real, info=tagged if real.name == "linked" else None))
    entries = mw.snapshot(seed)
    assert entries["linked"].kind == "special" and "linked/inner.py" not in entries
