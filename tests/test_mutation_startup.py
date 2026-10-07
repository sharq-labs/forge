"""Hostile specifications of the sealed mutation child startup (Pass 7; executed since Pass 8)."""
from __future__ import annotations

import ast
import pathlib
import subprocess

import pytest

from tools.certification import mutation_startup as startup
from tools.certification import mutation_workspace as mw
from tools.certification import mutation_v4_runner as v4


def test_environment_snapshot_is_independent_of_parent_and_each_child(tmp_path):
    executable = tmp_path / "python"
    executable.write_bytes(b"interpreter")
    executable.chmod(0o700)
    inherited = {"PATH": "controlled", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "0",
                 "PYTHONPYCACHEPREFIX": "/old/mutant/cache"}
    inputs = startup.StartupInputs.capture(executable=executable, inherited=inherited)
    inherited["PATH"] = "changed"
    with pytest.raises(TypeError):
        inputs.environment["PATH"] = "child mutation"
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir(); second.mkdir()
    one = mw.mutation_environment(first, inputs.environment)
    one["PATH"] = "mutated child environment"
    two = mw.mutation_environment(second, inputs.environment)
    assert two["PATH"] == "controlled"
    assert two["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert two["PYTHONDONTWRITEBYTECODE"] == "1"
    assert "PYTHONPYCACHEPREFIX" not in two
    assert two["TMPDIR"] != one["TMPDIR"]


def test_interpreter_replacement_is_refused_with_same_size(tmp_path):
    path = tmp_path / "python"
    path.write_bytes(b"original")
    path.chmod(0o700)
    inputs = startup.StartupInputs.capture(executable=path, inherited={})
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"modified")
    replacement.chmod(0o700)
    replacement.replace(path)
    with pytest.raises(RuntimeError, match="identity changed"):
        inputs.check()


def test_venv_interpreter_symlink_spelling_is_preserved(tmp_path):
    binary = tmp_path / "binary"
    binary.write_bytes(b"python")
    binary.chmod(0o700)
    link = tmp_path / "venv-python"
    link.symlink_to(binary)
    inputs = startup.StartupInputs.capture(executable=link, inherited={})
    assert inputs.executable == str(link)
    inputs.check()


def test_startup_module_imports_no_project_test_or_pytest_state():
    tree = ast.parse(pathlib.Path(startup.__file__).read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert not any(name.startswith(("engcore", "crafty", "tests", "pytest", "numpy")) for name in imports)


def test_v4_command_preserves_exact_parametrized_target_and_report(monkeypatch, tmp_path):
    from types import SimpleNamespace
    inputs = startup.StartupInputs.capture(inherited={})
    seen = []
    owned = SimpleNamespace(work=tmp_path / "worker", artifacts=tmp_path / "artifacts",
                            startup=inputs, artifact_path=lambda *parts: tmp_path.joinpath(*parts))
    def captured(argv, **kwargs):
        seen.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(v4, "run_captured", captured)
    target = "tests/test_guard.py::test_guard[value-with-space]"
    v4._pytest(owned.work, [target], owned.artifacts, "first", workspace=owned)
    v4._pytest(owned.work, [target], owned.artifacts, "second", workspace=owned)
    assert len(seen) == 2  # Each attempt calls the fresh child launcher.
    assert all(argv[-1] == target for argv, _ in seen)
    assert seen[0][0] != seen[1][0]  # Independent output paths.
    assert all("--runxfail" in argv and "--continue-on-collection-errors" not in argv for argv, _ in seen)
    assert all(kwargs["inherited"] is inputs.environment for _, kwargs in seen)


def test_malformed_junit_cannot_supply_named_credit():
    assert v4.verdict_from_junit(b"<truncated", "tests/test_guard.py::test_guard") != "KILLED"


@pytest.mark.parametrize("variable,value", [("PYTHONOPTIMIZE", "2"), ("PYTHONWARNINGS", "error"),
                                           ("PYTHONINSPECT", "1"), ("PYTHONSAFEPATH", "1")])
def test_host_python_startup_switches_cannot_change_guard_semantics(tmp_path, variable, value):
    env = mw.mutation_environment(tmp_path, {variable: value})
    assert variable not in env
    assert env["PYTHONNOUSERSITE"] == env["PYTHONDONTWRITEBYTECODE"] == "1"


def test_formal_copy_excludes_legacy_bytecode(tmp_path, monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(pathlib.Path(__file__).resolve().parent))
    import mutation_guards as mg
    source = tmp_path / "repo"
    (source / "src").mkdir(parents=True)
    (source / "src/guard.py").write_text("assert True")
    (source / "src/guard.pyc").write_bytes(b"stale bytecode")
    (source / "src/__pycache__").mkdir()
    (source / "src/__pycache__/guard.pyc").write_bytes(b"stale cache")
    monkeypatch.setattr(mg, "_COPIED", ("src",))
    target = tmp_path / "copy"
    mg._copy_tree(source, target)
    assert (target / "src/guard.py").exists()
    assert not list(target.rglob("*.pyc"))


@pytest.mark.parametrize("report", [
    b'<garbage><testcase classname="tests.test_guard" name="test_guard"><failure/></testcase></garbage>',
    b'<testsuites><testcase classname="tests.test_guard" name="test_guard"><failure/></testcase></testsuites>',
    b'<testsuite><testcase classname="tests.test_guard" name="test_guard"><failure>\xff</failure></testcase></testsuite>',
])
def test_non_junit_and_invalid_encoding_never_earn_credit(report):
    assert v4.verdict_from_junit(report, "tests/test_guard.py::test_guard").startswith("REPORT_UNREADABLE")
