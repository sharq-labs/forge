"""Repository ownership must bound impact scans without hiding owned science."""
from __future__ import annotations

import pathlib
import subprocess

import pytest

from tools import test_impact


def write(root, name, text="VALUE = 1\n"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")
    return path


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    write(tmp_path, "pyproject.toml", '[tool.pytest.ini_options]\npythonpath = ["src", "."]\n')
    write(tmp_path, ".gitignore", "/.forge/\n.venv/\nvenv/\n__pycache__/\nbuild/\ndist/\n")
    write(tmp_path, "src/pkg/model.py")
    git(tmp_path, "add", "pyproject.toml", ".gitignore", "src/pkg/model.py")
    return tmp_path


def test_prepared_assurance_environments_do_not_poison_the_repository_graph(repo):
    write(repo, ".forge/venvs/3.11/lib/site-packages/bad.py", "not Python!\n")
    write(repo, ".forge/venvs/3.12/lib/site-packages/bad.py", "not Python!\n")
    graph = test_impact.build_graph(repo)
    assert not graph.unparseable
    assert "src/pkg/model.py" in graph.deps
    assert not any(name.startswith(".forge/venvs/") for name in graph.deps)


@pytest.mark.parametrize("directory", [".venv", "venv", "__pycache__", ".pytest_cache", "build", "dist", "node_modules"])
def test_unowned_environment_build_and_cache_files_are_not_repository_inputs(repo, directory):
    write(repo, directory + "/bad.py", "not Python!\n")
    assert not test_impact.build_graph(repo).unparseable


def test_tracked_files_win_over_runtime_names_including_legitimate_forge_locations(repo):
    write(repo, ".forge/checks/owned.py")
    write(repo, "build/owned_science.py")
    git(repo, "add", "-f", ".forge/checks/owned.py", "build/owned_science.py")
    graph = test_impact.build_graph(repo)
    assert {"src/pkg/model.py", ".forge/checks/owned.py", "build/owned_science.py"} <= graph.deps.keys()


def test_unknown_repository_owned_paths_are_scanned_and_bad_syntax_remains_visible(repo):
    write(repo, "new_science/model.py", "not Python!\n")
    assert "new_science/model.py" in test_impact.build_graph(repo).unparseable


def test_non_git_synthetic_trees_exclude_only_the_forge_environment_subtree(tmp_path):
    write(tmp_path, "pyproject.toml", '[tool.pytest.ini_options]\npythonpath = ["."]\n')
    write(tmp_path, ".forge/venvs/bad.py", "not Python!\n")
    write(tmp_path, ".forge/science/model.py")
    graph = test_impact.build_graph(tmp_path)
    assert not graph.unparseable
    assert ".forge/science/model.py" in graph.deps


def test_git_ownership_failure_is_not_an_empty_successful_scan(repo, monkeypatch):
    def refuse(*args, **kwargs):
        raise subprocess.CalledProcessError(128, args[0])
    monkeypatch.setattr(subprocess, "run", refuse)
    with pytest.raises((subprocess.CalledProcessError, RuntimeError)):
        test_impact.build_graph(repo)


def test_a_repository_python_symlink_is_refused_before_reading_its_target(repo, monkeypatch):
    source = repo / "src/pkg/model.py"
    original = pathlib.Path.is_symlink
    monkeypatch.setattr(pathlib.Path, "is_symlink", lambda p: p == source or original(p))
    with pytest.raises(ValueError, match="link"):
        test_impact.build_graph(repo)


def test_an_inventory_cannot_escape_the_repository_root(repo, monkeypatch):
    def poisoned(args, **kwargs):
        payload = str(repo).encode() + b"\n" if "rev-parse" in args else b"../outside.py\0"
        return subprocess.CompletedProcess(args, 0, stdout=payload, stderr=b"")
    monkeypatch.setattr(subprocess, "run", poisoned)
    with pytest.raises(ValueError, match="outside"):
        test_impact.build_graph(repo)


def test_worktree_metadata_cannot_substitute_another_repository(repo, tmp_path, monkeypatch):
    def substituted(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=str(tmp_path.parent).encode(), stderr=b"")
    monkeypatch.setattr(subprocess, "run", substituted)
    with pytest.raises(ValueError, match="ownership"):
        test_impact.build_graph(repo)


def test_a_tracked_python_file_replaced_by_a_directory_is_refused(repo):
    source = repo / "src/pkg/model.py"
    source.unlink()
    source.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        test_impact.build_graph(repo)


def test_a_dangling_git_directory_pointer_does_not_become_an_archive_scan(tmp_path):
    write(tmp_path, "pyproject.toml", '[tool.pytest.ini_options]\npythonpath = ["."]\n')
    write(tmp_path, ".git", "gitdir: missing-repository\n")
    write(tmp_path, "owned.py")
    with pytest.raises(subprocess.CalledProcessError):
        test_impact.build_graph(tmp_path)


def test_an_actual_outside_directory_link_is_refused(repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside-impact")
    write(outside, "model.py")
    alias = repo / "alias"
    try:
        alias.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink creation unavailable: {exc}")
    with pytest.raises(ValueError, match="link|outside"):
        test_impact.build_graph(repo)
