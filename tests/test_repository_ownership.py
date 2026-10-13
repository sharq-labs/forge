"""Hostile review (BLOCKER): assurance traversals of a checkout must not read environment trees as source.

``.forge/venvs/3.11`` and ``.forge/venvs/3.12`` are created INSIDE the checkout by
the local assurance runner. A whole-tree walk parsed their site-packages as
first-party code. Ownership decides instead: tracked files always count, wherever
they live; untracked files count unless they lie under an environment root; a
symlink is never followed.
"""

from __future__ import annotations

import os
import pathlib
import subprocess

import pytest

from tools import test_impact
from tools.certification.mutation_workspace import WorkspaceError, environment_trees, owned_snapshot, snapshot
from tools.certification.ownership import OwnershipError, copy_ignore, is_environment_dir, owned_files, tracked_files

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _git(root, *args):
    subprocess.run(["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args], cwd=root, check=True,
                   capture_output=True)


def _write(root, relative, text="x = 1\n"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


@pytest.fixture()
def checkout(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _write(root, "pyproject.toml", "[tool.pytest.ini_options]\npythonpath = [\"src\", \".\"]\n")
    _write(root, "src/pkg/__init__.py", "")
    _write(root, "src/pkg/model.py", "from .solver import solve\n")
    _write(root, "src/pkg/solver.py", "def solve():\n    return 1\n")
    _write(root, "tests/test_model.py", "from pkg.model import solve\n")
    _write(root, ".forge/policy.json", "{}\n")                       # legitimate repository metadata, tracked
    _write(root, "odd/venv/model.py", "VALUE = 2\n")                 # tracked source under an unusual name
    _write(root, "build/generator.py", "GEN = 1\n")                  # a tracked directory named build
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "repo")
    # what the toolchain and caches leave behind, untracked
    _write(root, ".forge/venvs/3.12/pyvenv.cfg", "home = /usr/bin\n")
    _write(root, ".forge/venvs/3.12/lib/python3.12/site-packages/foreign.py", "this is not = python\n")
    _write(root, ".venv/pyvenv.cfg", "home = /usr/bin\n")
    _write(root, ".venv/lib/site.py", "foreign = 1\n")
    _write(root, "tools/env/conda-meta/history", "\n")
    _write(root, "tools/env/lib/pkg.py", "foreign = 1\n")
    _write(root, "node_modules/left-pad/index.py", "foreign = 1\n")
    _write(root, "src/pkg/__pycache__/model.cpython-312.pyc", "\0")
    _write(root, "dist/crafty-0.whl.py", "foreign = 1\n")
    _write(root, "src/pkg/new_module.py", "NEW = 1\n")               # untracked first-party source someone just wrote
    return root


def test_environment_trees_are_not_repository_source(checkout) -> None:
    files = set(owned_files(checkout).files)
    assert not [f for f in files if f.startswith((".forge/venvs/", ".venv/", "tools/env/", "node_modules/", "dist/"))]
    assert not [f for f in files if "__pycache__" in f]


def test_tracked_files_are_visible_wherever_they_live(checkout) -> None:
    files = set(owned_files(checkout).files)
    assert {"src/pkg/model.py", ".forge/policy.json", "odd/venv/model.py", "build/generator.py"} <= files


def test_a_tracked_file_inside_an_environment_root_is_still_seen(checkout) -> None:
    _write(checkout, ".forge/venvs/3.12/forced.py", "TRACKED = 1\n")
    _git(checkout, "add", "-f", ".forge/venvs/3.12/forced.py")
    _git(checkout, "commit", "-q", "-m", "forced")
    files = set(owned_files(checkout).files)
    assert ".forge/venvs/3.12/forced.py" in files
    assert ".forge/venvs/3.12/lib/python3.12/site-packages/foreign.py" not in files


def test_untracked_first_party_source_is_still_seen(checkout) -> None:
    assert "src/pkg/new_module.py" in owned_files(checkout).files


def test_a_symlink_is_refused_never_followed(checkout, tmp_path) -> None:
    outside = _write(tmp_path, "outside/secret.py", "SECRET = 1\n")
    os.symlink(outside, checkout / "src" / "pkg" / "escape.py")
    owned = owned_files(checkout)
    assert "src/pkg/escape.py" in owned.refused and "src/pkg/escape.py" not in owned.files
    with pytest.raises(WorkspaceError, match="symlinks"):
        owned_snapshot(checkout)
    graph = test_impact.build_graph(checkout)
    assert "src/pkg/escape.py" in graph.unparseable  # never read, so nothing narrows past it


def test_reproduce_the_scanner_finding_before_and_after(checkout) -> None:
    """The hostile probe: a raw walk of the checkout reads the environment; an owned snapshot does not."""
    foreign = ".forge/venvs/3.12/lib/python3.12/site-packages/foreign.py"
    assert foreign in snapshot(checkout)            # integrity snapshot: complete by design (seeds and workers)
    owned = owned_snapshot(checkout)
    assert foreign not in owned and "src/pkg/model.py" in owned and ".forge/policy.json" in owned


def test_a_seed_that_carries_an_environment_is_refused(checkout) -> None:
    assert ".forge/venvs" in environment_trees(checkout) and ".venv" in environment_trees(checkout)
    clean = checkout.parent / "clean"
    import shutil

    for item in ("src", "tests", "odd", "build"):
        shutil.copytree(checkout / item, clean / item, ignore=copy_ignore(checkout, "__pycache__", "*.pyc"))
    assert environment_trees(clean) == []
    assert (clean / "src" / "pkg" / "new_module.py").exists()
    assert not (clean / "src" / "pkg" / "__pycache__").exists()


def test_the_impact_graph_reads_only_owned_source(checkout) -> None:
    graph = test_impact.build_graph(checkout)
    assert not [f for f in graph.deps if f.startswith((".forge/venvs/", ".venv/", "tools/env/", "node_modules/"))]
    assert not [f for f in graph.unparseable if "site-packages" in f]
    assert "src/pkg/new_module.py" in graph.deps


def test_the_real_checkout_graph_never_contains_an_environment() -> None:
    """The Phase 0 baseline failure: joblib's test files under .forge/venvs were 'unparseable repository modules'."""
    graph = test_impact.build_graph(ROOT)
    assert not [f for f in graph.deps if f.startswith(".forge/")]
    assert not [f for f in graph.unparseable if f.startswith(".forge/")]


# ---- third review C1-C6: the scanner fails closed -----------------------------------------------------


def test_c1_a_checkout_whose_listing_fails_raises_instead_of_hiding_tracked_files(checkout, monkeypatch) -> None:
    (checkout / ".git" / "index").write_bytes(b"not an index")  # git ls-files now fails in this checkout
    with pytest.raises(OwnershipError, match="could not be listed"):
        tracked_files(checkout)
    with pytest.raises(OwnershipError):
        owned_files(checkout)


def test_c2_inherited_git_variables_cannot_point_the_listing_at_another_repository(checkout, tmp_path, monkeypatch) -> None:
    other = tmp_path / "other"
    other.mkdir()
    _write(other, "unrelated.py")
    _git(other, "init", "-q")
    _git(other, "add", "-A")
    _git(other, "commit", "-q", "-m", "other")
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    listed = tracked_files(checkout)
    assert "build/generator.py" in listed and "unrelated.py" not in listed


@pytest.mark.parametrize("marker", ["site-packages/x.py", "foreign-1.0.dist-info/METADATA"])
def test_c3_an_installed_package_tree_is_an_environment(checkout, marker) -> None:
    _write(checkout, f"vendor/target/{marker}", "foreign = 1\n")
    _write(checkout, "vendor/target/foreign/__init__.py", "foreign = 1\n")
    assert is_environment_dir(checkout / "vendor" / "target")
    names = owned_files(checkout).files
    assert not any(name.startswith("vendor/target/") for name in names)
    _write(checkout, "__pypackages__/3.12/lib/foreign.py")
    assert not any(name.startswith("__pypackages__/") for name in owned_files(checkout).files)


def test_c4_a_nested_repository_is_refused_not_walked(checkout) -> None:
    nested = checkout / "third_party" / "lib"
    _write(nested, "code.py")
    _git(nested, "init", "-q")
    owned = owned_files(checkout)
    assert "third_party/lib" in owned.refused
    assert not any(name.startswith("third_party/lib/") for name in owned.files)


def test_c5_an_environment_marker_inside_tracked_source_is_refused_and_does_not_hide_it(checkout) -> None:
    _write(checkout, "src/pkg/pyvenv.cfg", "home = /usr/bin\n")
    _write(checkout, "src/pkg/fresh.py", "NEW = 1\n")              # untracked first-party source below the marker
    owned = owned_files(checkout)
    assert "src/pkg" in owned.refused
    assert "src/pkg/fresh.py" in owned.files and "src/pkg/model.py" in owned.files


def test_c6_a_tracked_file_reached_under_another_case_is_listed_once(checkout, monkeypatch) -> None:
    from tools.certification import ownership

    real = ownership.tracked_files

    def upper(root):
        listed = real(root)
        return frozenset(("SRC/pkg/model.py" if name == "src/pkg/model.py" else name) for name in listed)

    probe = checkout / "src" / "PKG_CASE_PROBE"
    probe.write_bytes(b"")
    insensitive = (checkout / "SRC" / "pkg" / "model.py").exists()
    probe.unlink()
    if not insensitive:
        pytest.skip("case-sensitive filesystem: two spellings are two files here")
    monkeypatch.setattr(ownership, "tracked_files", upper)
    files = owned_files(checkout).files
    assert ("SRC/pkg/model.py" in files) != ("src/pkg/model.py" in files)