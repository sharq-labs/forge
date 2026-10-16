"""What the certificate verifier may reuse between verifications, and what it must not (FAST regression, 2026-10-16).

PR #146 made one verify_certificate ~4x slower: the BR-15 dependency closure, the evidence-code walk and the authority
closure re-parsed the same files on every call, ``_spelled_on_disk`` listed the same directories ~220,000 times per
call, and the registry probe recompiled the interpreter's library into a fresh bytecode prefix every time. The fix
reuses three things, and each test below attacks one way that reuse could make a verification describe bytes other
than the ones on disk:

* the per-file analyses are memoized by the exact bytes read -- so a same-size, same-mtime edit is a new key;
* directory listings live for one closure walk -- so a case-only rename between two calls is seen;
* the probe keeps one private bytecode prefix per process -- created by the verifier, never another process's,
  never inside the tree, and re-seeded from the bytes on disk before every probe, so a planted or stale .pyc never
  runs in place of the source, whether it sits in the tree's __pycache__ or in the prefix itself.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import marshal
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import uuid

import pytest

from tools.certification import core_certificate as cc

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: A certified area holding one module that is not a verdict root; the package __init__ is control plane, as in SCOPE.
_SCOPE = [cc.ScopeArea("certified", "CORE_CERTIFIED", ("src/engcore/certified/**/*.py",), "test"),
          cc.ScopeArea("control", "CERTIFICATION_CONTROL", ("src/engcore/__init__.py",), "test")]


def _tree(root: pathlib.Path, files: dict[str, bytes]) -> pathlib.Path:
    for relative, data in {"src/engcore/__init__.py": b"", **files}.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(data)
    return root


def _line(text: bytes, width: int = 64) -> bytes:
    """One line padded to ``width`` bytes, so two versions of a file can have exactly the same size."""
    assert len(text) <= width
    return text.ljust(width) + b"\n"


def _rewrite_keeping_size_and_mtime(path: pathlib.Path, data: bytes) -> None:
    """Change ``path``'s bytes while its size and modification time stay exactly what they were."""
    before = path.stat()
    assert len(data) == before.st_size and data != path.read_bytes()
    path.write_bytes(data)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = path.stat()
    assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns)


# ---- the per-file analyses: memoized by the exact bytes ------------------------------------------------------------
_HARMLESS = _line(b"from . import sibling as rule")
_IMPORTS_A_DECIDER = _line(b"from ..decider import rule")
_HARMLESS_NAME = _line(b"NAME = 'engcore.decider.rule'")
_LOADS_BY_NAME = _line(b"import importlib; RULE = importlib.import_module(NAME)")

_DECIDER = {"src/engcore/decider/__init__.py": b"", "src/engcore/decider/rule.py": b"def decide():\n    return 1\n"}


def _certified_dependencies(root: pathlib.Path, module: str) -> str:
    return "\n".join(cc.certified_dependency_problems(root, _SCOPE))


def _authority_closure(root: pathlib.Path, module: str) -> str:
    return "\n".join(cc.authority_import_closure(root, roots=(module,)))


def _evidence_code(root: pathlib.Path, module: str) -> str:
    try:
        return "\n".join(cc.evidence_code_digests(root, {"capabilities": {"c": {"executor": {"source": module}}}}))
    except cc.CertificationError as exc:
        return str(exc)


_CLOSURES = {"certified_dependency": _certified_dependencies, "authority": _authority_closure,
             "evidence_code": _evidence_code}


@pytest.mark.parametrize("closure", sorted(_CLOSURES))
def test_an_import_added_between_two_verifications_with_the_same_size_and_mtime_is_seen(tmp_path, closure) -> None:
    module = "src/engcore/certified/stop.py"
    root = _tree(tmp_path, {"src/engcore/certified/__init__.py": b"", module: _HARMLESS, **_DECIDER})
    observe = _CLOSURES[closure]
    assert "src/engcore/decider/rule.py" not in observe(root, module)
    _rewrite_keeping_size_and_mtime(root / module, _IMPORTS_A_DECIDER)
    assert "src/engcore/decider/rule.py" in observe(root, module)


#: Where each closure reports an undeclared computed-name load: the module edited, and the report read.
_DYNAMIC_REPORTS = {
    "certified_dependency": ("src/engcore/certified/stop.py",
                             lambda root: "\n".join(cc.certified_dependency_problems(root, _SCOPE))),
    "authority": ("src/engcore/claims/verdict.py",   # a verdict root
                  lambda root: "\n".join(cc.authority_closure_problems(root, _SCOPE))),
    "evidence_code": ("src/engcore/certified/stop.py",
                      lambda root: _evidence_code(root, "src/engcore/certified/stop.py")),
}


@pytest.mark.parametrize("closure", sorted(_DYNAMIC_REPORTS))
def test_a_dynamic_load_added_between_two_verifications_with_the_same_size_and_mtime_is_seen(tmp_path, closure) -> None:
    module, report = _DYNAMIC_REPORTS[closure]
    root = _tree(tmp_path, {"src/engcore/certified/__init__.py": b"", "src/engcore/claims/__init__.py": b"",
                            module: _HARMLESS_NAME, **_DECIDER})
    before = report(root)
    assert "DYNAMIC_REACH" not in before and "computed name" not in before
    _rewrite_keeping_size_and_mtime(root / module, _LOADS_BY_NAME)
    after = report(root)
    assert ("DYNAMIC_REACH" in after or "computed name" in after) and module in after, after


def test_the_same_bytes_are_parsed_once_and_changed_bytes_again(tmp_path, monkeypatch) -> None:
    """The memo is what makes a repeated verification cheap; its key is the bytes, not the path."""
    marker = uuid.uuid4().hex
    parsed: list[object] = []
    real_parse = ast.parse
    monkeypatch.setattr(cc.ast, "parse", lambda source, *a, **k: parsed.append(source) or real_parse(source, *a, **k))
    path = tmp_path / "m.py"
    path.write_bytes(_line(b"import importlib; R = importlib.import_module(NAME)  # " + marker.encode(), 96))

    def parses() -> int:
        return sum(isinstance(source, str) and marker in source for source in parsed)

    assert cc.dynamic_imports(path) == [1] and cc.dynamic_imports(path) == [1]
    assert parses() == 1
    _rewrite_keeping_size_and_mtime(path, path.read_bytes().replace(b"(NAME)", b"('ab')"))
    assert cc.dynamic_imports(path) == []
    assert parses() == 2


# ---- directory listings: one closure walk, never longer -------------------------------------------------------------
@pytest.mark.parametrize("closure", sorted(_CLOSURES))
def test_a_case_only_rename_between_two_verifications_is_seen(tmp_path, closure) -> None:
    """`from ..decider import Rule` names a symbol while the file is rule.py, and a module once it is Rule.py.

    A listing memo that outlived the first call would keep the old spelling: on a case-insensitive filesystem the
    closure would then report rule.py, a file that no longer exists with that name, and on a case-sensitive one it
    would miss Rule.py entirely.
    """
    module = "src/engcore/certified/__init__.py"
    root = _tree(tmp_path, {module: b"from ..decider import Rule\n",
                            "src/engcore/decider/__init__.py": b"from .rule import Rule\n",
                            "src/engcore/decider/rule.py": b"class Rule:\n    pass\n"})
    observe = _CLOSURES[closure]
    before = observe(root, module)
    assert "src/engcore/decider/rule.py" in before and "src/engcore/decider/Rule.py" not in before
    os.rename(root / "src/engcore/decider/rule.py", root / "src/engcore/decider/Rule.py")
    assert sorted(os.listdir(root / "src/engcore/decider")) == ["Rule.py", "__init__.py"]
    after = observe(root, module)
    assert "src/engcore/decider/Rule.py" in after and "src/engcore/decider/rule.py" not in after, after


# ---- the registry probe's private bytecode prefix -------------------------------------------------------------------
_CAPABILITIES = b'''DIGEST = "%s"


class _Declaration:
    capability_id = "c"
    digest = DIGEST
    executor = None
    case_builder = None
    routes = ()


class _Registry:
    digest = DIGEST
    declarations = (_Declaration(),)


def production_registry():
    return _Registry()
'''


def _registry_tree(root: pathlib.Path) -> pathlib.Path:
    """The smallest tree the real registry probe can read: a registry whose digest is a word in its source."""
    return _tree(root, {
        "src/engcore/product/__init__.py": b"",
        cc.REGISTRY_ENTRY: _CAPABILITIES % b"honest",
        "src/engcore/scientific/__init__.py": b"",
        "src/engcore/scientific/models/__init__.py": b"",
        "src/engcore/scientific/models/definition.py": b"class ScientificModelDefinition:\n    pass\n",
        "src/engcore/domains/__init__.py": b"",
    })


def _timestamp_pyc(source: pathlib.Path, planted: bytes) -> bytes:
    """A timestamp .pyc of ``planted`` whose header matches ``source``'s mtime and size: it runs instead of the source."""
    before = source.stat()
    code = compile(planted, str(source), "exec", dont_inherit=True)
    return (importlib.util.MAGIC_NUMBER + (0).to_bytes(4, "little")
            + (int(before.st_mtime) & 0xFFFFFFFF).to_bytes(4, "little")
            + (before.st_size & 0xFFFFFFFF).to_bytes(4, "little") + marshal.dumps(code))


def _record_probes(monkeypatch) -> list[types.SimpleNamespace]:
    """Pass every subprocess.run through unchanged, recording the registry probe's runs."""
    runs: list[types.SimpleNamespace] = []
    real_run = subprocess.run

    def recording(args, *positional, **keywords):
        result = real_run(args, *positional, **keywords)
        if cc._REGISTRY_PROBE in list(args):
            prefix = next(a.split("=", 1)[1] for a in args if str(a).startswith("pycache_prefix="))
            runs.append(types.SimpleNamespace(args=list(args), prefix=pathlib.Path(prefix), cwd=keywords.get("cwd"),
                                              returncode=result.returncode))
        return result

    monkeypatch.setattr(cc.subprocess, "run", recording)
    return runs


def _probe_without_a_prefix(root: pathlib.Path, cwd: pathlib.Path) -> dict:
    """The registry probe exactly as the verifier runs it, minus -X pycache_prefix: the tree's __pycache__ is read."""
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(("PYTHON", "FORGE"))}
    run = subprocess.run([sys.executable, "-E", "-s", "-P", "-c", cc._REGISTRY_PROBE, str(root / "src")],
                         cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_a_planted_timestamp_pyc_in_the_trees_pycache_is_never_executed(tmp_path, monkeypatch) -> None:
    root = _registry_tree(tmp_path / "tree")
    capabilities = root / cc.REGISTRY_ENTRY
    planted = capabilities.parent / "__pycache__" / f"{capabilities.stem}.{sys.implementation.cache_tag}.pyc"
    planted.parent.mkdir()
    planted.write_bytes(_timestamp_pyc(capabilities, _CAPABILITIES % b"planted"))
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    # positive control: an interpreter that reads the tree's __pycache__ runs the planted bytecode, not the source
    assert _probe_without_a_prefix(root, elsewhere)["digest"] == "planted"
    probes = _record_probes(monkeypatch)
    for _ in range(2):   # a first and a second probe: the second reuses this process's prefix
        assert cc.production_registry_identity(root)["digest"] == "honest"
    assert [run.returncode for run in probes] == [0, 0]
    assert all(not run.prefix.resolve().is_relative_to(root.resolve()) for run in probes)


def test_a_source_edit_between_two_probes_that_keeps_size_and_mtime_is_seen(tmp_path, monkeypatch) -> None:
    """The prefix outlives a probe; what it holds for the tree is the compilation of the bytes on disk now."""
    root = _registry_tree(tmp_path / "tree")
    capabilities = root / cc.REGISTRY_ENTRY
    probes = _record_probes(monkeypatch)
    assert cc.production_registry_identity(root)["digest"] == "honest"
    prefix = probes[-1].prefix
    expected = pathlib.Path(cc._probe_bytecode_path(os.fspath(prefix), os.fspath(capabilities.resolve())))
    # the probe ran the bytecode this process compiled -- hash-based, checked, bound to the source bytes -- and
    # wrote none of its own for that module anywhere in the prefix
    pyc = expected.read_bytes()
    assert int.from_bytes(pyc[4:8], "little") == 0b11
    assert pyc[8:16] == importlib.util.source_hash(capabilities.read_bytes())
    mirror = pathlib.Path(cc._probe_bytecode_path(os.fspath(prefix), os.fspath((root / "src").resolve() / "x.py"))).parent
    assert [p.resolve() for p in mirror.rglob(f"{capabilities.stem}.*")] == [expected.resolve()]
    _rewrite_keeping_size_and_mtime(capabilities, _CAPABILITIES % b"edited")
    assert cc.production_registry_identity(root)["digest"] == "edited"
    assert probes[-1].prefix == prefix and len(probes) == 2


def test_bytecode_in_the_prefix_that_the_verifier_did_not_write_never_runs(tmp_path, monkeypatch) -> None:
    """A probe writes bytecode for what it compiles itself; the next seeding replaces or removes all of it."""
    root = _registry_tree(tmp_path / "tree")
    capabilities = root / cc.REGISTRY_ENTRY
    probes = _record_probes(monkeypatch)
    assert cc.production_registry_identity(root)["digest"] == "honest"
    target = pathlib.Path(cc._probe_bytecode_path(os.fspath(probes[-1].prefix), os.fspath(capabilities.resolve())))
    target.write_bytes(_timestamp_pyc(capabilities, _CAPABILITIES % b"planted"))
    stray = target.parent / f"stray.{sys.implementation.cache_tag}.pyc"
    stray.write_bytes(_timestamp_pyc(capabilities, _CAPABILITIES % b"stray"))
    assert cc.production_registry_identity(root)["digest"] == "honest"
    assert not stray.exists()
    assert target.read_bytes()[4:8] == (0b11).to_bytes(4, "little")


#: A registry whose digest says how its own module was compiled: whether annotations were evaluated (a
#: ``from __future__ import annotations`` leaking from the verifier into compile() stringifies them) and whether
#: asserts survived (a verifier running under -O must not strip them from code the probe runs without -O).
_COMPILE_SENSITIVE = b'''def _f(x: int):
    pass


try:
    assert False
    _ASSERTS = "stripped"
except AssertionError:
    _ASSERTS = "kept"

''' + _CAPABILITIES.replace(b'DIGEST = "%s"', b"""DIGEST = ("evaluated" if _f.__annotations__["x"] is int else "stringified") + "-" + _ASSERTS""")


def test_the_bytecode_seeded_for_the_probe_is_what_the_interpreter_compiles_itself(tmp_path) -> None:
    root = _registry_tree(tmp_path / "tree")
    (root / cc.REGISTRY_ENTRY).write_bytes(_COMPILE_SENSITIVE)
    elsewhere = tmp_path / "cwd"
    elsewhere.mkdir()
    assert _probe_without_a_prefix(root, elsewhere)["digest"] == "evaluated-kept"   # compiled by the interpreter
    assert cc.production_registry_identity(root)["digest"] == "evaluated-kept"     # seeded by this process
    optimized = subprocess.run(   # a verifier process running under -O seeds the same bytecode
        [sys.executable, "-O", "-c", "import pathlib, sys\nfrom tools.certification import core_certificate as cc\n"
                                     "print(cc.production_registry_identity(pathlib.Path(sys.argv[1]))['digest'])",
         str(root)], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert optimized.returncode == 0, optimized.stderr
    assert optimized.stdout.strip().splitlines()[-1] == "evaluated-kept"


def test_the_probe_prefix_is_created_by_this_process_and_reused_only_by_it(tmp_path, monkeypatch) -> None:
    root = _registry_tree(tmp_path / "tree")
    created: list[pathlib.Path] = []
    real_mkdtemp = tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created.append(pathlib.Path(path))
        return path

    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", {})
    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp)
    probes = _record_probes(monkeypatch)
    try:
        first = cc.production_registry_identity(root)
        second = cc.production_registry_identity(root)
        assert first == second and [run.returncode for run in probes] == [0, 0]
        (base,) = created
        assert {run.prefix for run in probes} == {probes[0].prefix} and probes[0].prefix.parent == base
        assert {pathlib.Path(run.cwd) for run in probes} == {base}
        assert base.name.startswith("forge-registry-probe-")
        assert not base.resolve().is_relative_to(root.resolve())
        if os.name == "posix":
            assert stat.S_IMODE(base.stat().st_mode) == 0o700
    finally:
        for base in created:
            cc._remove_probe_directory(os.getpid(), base)
    assert created and not any(base.exists() for base in created)


def test_another_process_creates_its_own_probe_directory_and_removes_it_at_exit(tmp_path) -> None:
    root = _registry_tree(tmp_path / "tree")
    ours = cc._probe_workspace(root)[0]
    child = subprocess.run(
        [sys.executable, "-c", "import pathlib, sys\nfrom tools.certification import core_certificate as cc\n"
                               "print(cc._probe_workspace(pathlib.Path(sys.argv[1]))[0])", str(root)],
        cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert child.returncode == 0, child.stderr
    theirs = pathlib.Path(child.stdout.strip().splitlines()[-1])
    assert theirs.name.startswith("forge-registry-probe-") and theirs != ours
    assert not theirs.exists()   # removed when that process exited
    assert ours.is_dir()


def test_a_forked_child_never_adopts_or_removes_its_parents_probe_directory(tmp_path, monkeypatch) -> None:
    root = _registry_tree(tmp_path / "tree")
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", {})
    parent = cc._probe_workspace(root)[0]
    child_os = types.SimpleNamespace(**{name: getattr(os, name) for name in dir(os) if not name.startswith("__")})
    child_os.getpid = lambda: os.getpid() + 1   # what a child forked after the parent's first probe sees
    monkeypatch.setattr(cc, "os", child_os)
    child = None
    try:
        child = cc._probe_workspace(root)[0]
        cc._remove_probe_directory(os.getpid(), parent)   # the parent's exit handler, inherited and run by the child
        assert child != parent and parent.is_dir() and child.is_dir()
    finally:
        monkeypatch.undo()
        for base in (parent, child):
            if base is not None:
                shutil.rmtree(base, ignore_errors=True)


def test_the_probe_never_leaves_a_directory_inside_the_tree_it_certifies(tmp_path, monkeypatch) -> None:
    """With the temporary directory inside the tree, a persistent prefix would make the tree dirty: one-shot instead."""
    root = _registry_tree(tmp_path / "tree")
    other = _registry_tree(tmp_path / "other")
    inside = root / "scratch"
    inside.mkdir()
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", {})
    monkeypatch.setattr(tempfile, "tempdir", str(inside))
    probes = _record_probes(monkeypatch)
    for _ in range(2):
        assert cc.production_registry_identity(root)["digest"] == "honest"
    assert list(inside.iterdir()) == [] and cc._PROBE_WORKSPACE == {}
    assert len({run.prefix for run in probes}) == 2   # a fresh prefix per probe, as before the per-process prefix
    # a prefix created for another tree, which this tree turns out to contain, is not used for it either
    assert cc.production_registry_identity(other)["digest"] == "honest"
    assert cc._PROBE_WORKSPACE and cc._PROBE_WORKSPACE["base"].resolve().is_relative_to(inside.resolve())
    assert cc.production_registry_identity(root)["digest"] == "honest"
    assert list(inside.iterdir()) == [] and cc._PROBE_WORKSPACE == {}
