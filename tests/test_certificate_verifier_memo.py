"""What the certificate verifier may reuse between verifications, and what it must not (FAST regression, 2026-10-16).

PR #146 made one verify_certificate ~4x slower: the BR-15 dependency closure, the evidence-code walk and the authority
closure re-parsed the same files on every call, ``_spelled_on_disk`` listed the same directories ~220,000 times per
call, and the registry probe recompiled the interpreter's library into a fresh bytecode prefix every time. The fix
reuses three things, and each test below attacks one way that reuse could make a verification describe bytes other
than the ones on disk:

* the per-file analyses are memoized by the exact bytes read -- so a same-size, same-mtime edit is a new key -- and
  by the module's package; what the filesystem decides (a star import's submodules) is never memoized;
* directory listings live for one closure walk -- so a case-only rename between two calls is seen -- and a listing
  that failed is tried again;
* the probe keeps one private bytecode prefix per process -- created by the verifier, never another process's, never
  adopted once replaced, never inside the tree -- and a clean interpreter re-seeds it from the bytes on disk before
  every probe, so a planted or stale .pyc never runs in place of the source, whether it sits in the tree's
  __pycache__ or in the prefix itself, and nothing of the verifier's own process reaches the bytecode.
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

#: The tests of the per-process probe directory, which an interpreter whose mkdtemp is not private never makes.
needs_private_mkdtemp = pytest.mark.skipif(not cc._mkdtemp_is_private(),
                                           reason="this interpreter's mkdtemp is not private: every probe is one-shot")

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


def _os_with(**replaced) -> types.SimpleNamespace:
    """The os module as core_certificate sees it, with some functions replaced."""
    return types.SimpleNamespace(**{**{name: getattr(os, name) for name in dir(os) if not name.startswith("__")},
                                    **replaced})


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


def test_identical_bytes_in_two_packages_name_different_modules(tmp_path) -> None:
    """The memo keys a module's imports by its package as well as its bytes: `from . import x` depends on both."""
    root = _tree(tmp_path, {"src/engcore/one/__init__.py": b"", "src/engcore/one/m.py": b"from . import helper\n",
                            "src/engcore/two/__init__.py": b"", "src/engcore/two/m.py": b"from . import helper\n"})
    src = root / "src"
    assert cc._engcore_imports(src, src / "engcore" / "one" / "m.py") == {"engcore.one", "engcore.one.helper"}
    assert cc._engcore_imports(src, src / "engcore" / "two" / "m.py") == {"engcore.two", "engcore.two.helper"}


@pytest.mark.parametrize("closure", sorted(_CLOSURES))
def test_a_submodule_added_to_a_star_imported_package_between_verifications_is_seen(tmp_path, closure) -> None:
    """The importer's bytes stay the same; what `from pkg import *` reaches does not, so it is never memoized."""
    module = "src/engcore/certified/stop.py"
    root = _tree(tmp_path, {"src/engcore/certified/__init__.py": b"", module: b"from ..decider import *\n",
                            "src/engcore/decider/__init__.py": b""})
    observe = _CLOSURES[closure]
    assert "src/engcore/decider/rule.py" not in observe(root, module)
    (root / "src/engcore/decider/rule.py").write_bytes(b"def decide():\n    return 1\n")
    assert "src/engcore/decider/rule.py" in observe(root, module)


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


def test_a_directory_listing_that_fails_once_is_listed_again(tmp_path, monkeypatch) -> None:
    """Review I5: one transient listing error must not drop a whole directory from the rest of the walk."""
    module = "src/engcore/certified/stop.py"
    root = _tree(tmp_path, {"src/engcore/certified/__init__.py": b"", module: _IMPORTS_A_DECIDER, **_DECIDER})
    decider = os.fspath(root / "src" / "engcore" / "decider")
    failed: list[str] = []

    def listdir(path="."):
        if os.fspath(path) == decider and not failed:
            failed.append(os.fspath(path))
            raise OSError("a transient listing error")
        return os.listdir(path)

    monkeypatch.setattr(cc, "os", _os_with(listdir=listdir))
    (problem,) = cc.certified_dependency_problems(root, _SCOPE)
    assert failed and "src/engcore/decider/rule.py" in problem


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
            runs.append(types.SimpleNamespace(args=list(args), prefix=pathlib.Path(prefix),
                                              cwd=pathlib.Path(keywords["cwd"]), returncode=result.returncode))
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


def _bytecode_path(prefix: pathlib.Path, source: pathlib.Path) -> pathlib.Path:
    """Where an interpreter started like the probe keeps ``source``'s bytecode -- asked of such an interpreter."""
    run = subprocess.run([sys.executable, "-E", "-s", "-P", "-X", f"pycache_prefix={prefix}", "-c",
                          "import importlib.util, sys; print(importlib.util.cache_from_source(sys.argv[1]))",
                          os.fspath(source)], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr
    return pathlib.Path(run.stdout.strip())


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


@needs_private_mkdtemp
def test_a_source_edit_between_two_probes_that_keeps_size_and_mtime_is_seen(tmp_path, monkeypatch) -> None:
    """The prefix outlives a probe; what it holds for the tree is the compilation of the bytes on disk now."""
    root = _registry_tree(tmp_path / "tree")
    capabilities = root / cc.REGISTRY_ENTRY
    probes = _record_probes(monkeypatch)
    assert cc.production_registry_identity(root)["digest"] == "honest"
    prefix = probes[-1].prefix
    expected = _bytecode_path(prefix, capabilities.resolve())
    # the probe ran the bytecode that was seeded -- hash-based, checked, bound to the source bytes, at the path the
    # probe's own interpreter names -- and wrote none of its own for that module anywhere in the tree's part of it
    pyc = expected.read_bytes()
    assert int.from_bytes(pyc[4:8], "little") == 0b11
    assert pyc[8:16] == importlib.util.source_hash(capabilities.read_bytes())
    mirror = _bytecode_path(prefix, root.resolve() / "x.py").parent
    assert [p.resolve() for p in mirror.rglob(f"{capabilities.stem}.*")] == [expected.resolve()]
    _rewrite_keeping_size_and_mtime(capabilities, _CAPABILITIES % b"edited")
    assert cc.production_registry_identity(root)["digest"] == "edited"
    assert probes[-1].prefix == prefix and len(probes) == 2


@needs_private_mkdtemp
def test_a_source_edit_after_seeding_and_before_the_import_is_caught_by_the_probes_hash_check(tmp_path, monkeypatch) -> None:
    """Review I6a: between seeding and the probe's import, only the interpreter's check of a CHECKED_HASH .pyc stands."""
    root = _registry_tree(tmp_path / "tree")
    capabilities = root / cc.REGISTRY_ENTRY
    seeded: list[bool] = []
    real_seed = cc._seed_probe_bytecode

    def seed_then_edit(*args, **kwargs):
        seeded.append(real_seed(*args, **kwargs))
        _rewrite_keeping_size_and_mtime(capabilities, _CAPABILITIES % b"edited")
        return seeded[-1]

    monkeypatch.setattr(cc, "_seed_probe_bytecode", seed_then_edit)
    assert cc.production_registry_identity(root)["digest"] == "edited"
    assert seeded == [True]   # the seeded prefix was used, and its now-stale .pyc refused at import


@needs_private_mkdtemp
def test_bytecode_in_the_prefix_that_the_verifier_did_not_write_never_runs(tmp_path, monkeypatch) -> None:
    """A probe writes bytecode for what it compiles itself; the next seeding replaces or removes all of it."""
    root = _registry_tree(tmp_path / "tree")
    capabilities = root / cc.REGISTRY_ENTRY
    probes = _record_probes(monkeypatch)
    assert cc.production_registry_identity(root)["digest"] == "honest"
    prefix = probes[-1].prefix
    target = _bytecode_path(prefix, capabilities.resolve())
    target.write_bytes(_timestamp_pyc(capabilities, _CAPABILITIES % b"planted"))
    stray = target.parent / f"stray.{sys.implementation.cache_tag}.pyc"
    stray.write_bytes(b"stray bytecode")
    # review I4: tree code outside src/ (an editable install from the tree, say) is swept too
    outside = _bytecode_path(prefix, root.resolve() / "providers" / "adapter.py")
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"stale bytecode")
    assert cc.production_registry_identity(root)["digest"] == "honest"
    assert not stray.exists() and not outside.exists()
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
    assert cc.production_registry_identity(root)["digest"] == "evaluated-kept"     # seeded for the probe
    optimized = subprocess.run(   # a verifier process running under -O seeds the same bytecode
        [sys.executable, "-O", "-c", "import pathlib, sys\nfrom tools.certification import core_certificate as cc\n"
                                     "print(cc.production_registry_identity(pathlib.Path(sys.argv[1]))['digest'])",
         str(root)], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert optimized.returncode == 0, optimized.stderr
    assert optimized.stdout.strip().splitlines()[-1] == "evaluated-kept"


def test_the_verifiers_integer_digit_limit_does_not_reach_the_probe(tmp_path) -> None:
    """Review I3: the probe's interpreter refuses a 5000-digit literal, so this registry cannot be read -- even when
    the verifier's own process, with the limit lifted, would compile it."""
    root = _registry_tree(tmp_path / "tree")
    (root / "src/engcore/domains/big.py").write_bytes(b"N = " + b"7" * 5000 + b"\n")   # the probe imports every domain
    limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    try:
        with pytest.raises(cc.CertificationError, match="could not be read"):
            cc.production_registry_identity(root)
    finally:
        sys.set_int_max_str_digits(limit)


@needs_private_mkdtemp
def test_the_probe_prefix_is_created_by_this_process_and_reused_only_by_it(tmp_path, monkeypatch) -> None:
    root = _registry_tree(tmp_path / "tree")
    created: list[pathlib.Path] = []
    real_mkdtemp = tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        if kwargs.get("prefix") == "forge-registry-probe-":
            created.append(pathlib.Path(path).resolve())
        return path

    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp)
    probes = _record_probes(monkeypatch)
    try:
        first = cc.production_registry_identity(root)
        second = cc.production_registry_identity(root)
        assert first == second and [run.returncode for run in probes] == [0, 0]
        (base,) = created
        assert {run.prefix for run in probes} == {probes[0].prefix} and probes[0].prefix.parent == base
        # review I4: each probe works in a directory of its own, made inside the verifier's directory and removed
        assert len({run.cwd for run in probes}) == 2 and all(run.cwd.parent == base for run in probes)
        assert not any(run.cwd.exists() for run in probes)
        assert base.name.startswith("forge-registry-probe-")
        assert not base.is_relative_to(root.resolve())
        if os.name == "posix":
            assert not stat.S_IMODE(base.stat().st_mode) & 0o077   # no access for its group or anyone else
    finally:
        if workspace:
            cc._remove_probe_directory(os.getpid(), workspace["base"], workspace["identity"])
    assert created and not any(base.exists() for base in created)


@needs_private_mkdtemp
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


@needs_private_mkdtemp
def test_a_forked_child_never_adopts_or_removes_its_parents_probe_directory(tmp_path, monkeypatch) -> None:
    root = _registry_tree(tmp_path / "tree")
    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    parent = cc._probe_workspace(root)[0]
    identity = workspace["identity"]
    real_pid = os.getpid()
    monkeypatch.setattr(cc, "os", _os_with(getpid=lambda: real_pid + 1))   # what a child forked after it sees
    child = None
    try:
        child = cc._probe_workspace(root)[0]
        cc._remove_probe_directory(real_pid, parent, identity)   # the parent's exit handler, run by the child
        assert child != parent and parent.is_dir() and child.is_dir()
    finally:
        monkeypatch.undo()
        for base in (parent, child):
            if base is not None:
                shutil.rmtree(base, ignore_errors=True)


@needs_private_mkdtemp
@pytest.mark.parametrize("replacement", ["directory", "private-directory", "symlink"])
def test_a_probe_directory_that_was_replaced_is_never_adopted_or_removed(tmp_path, monkeypatch, replacement) -> None:
    """Review I1: the directory can vanish while the process lives, and something else appear at its path."""
    root = _registry_tree(tmp_path / "tree")
    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    first = cc._probe_workspace(root)[0]
    identity = workspace["identity"]
    moved = first.with_name(first.name + "-moved")
    if replacement == "private-directory":   # review LOW-G: owner and mode match; only the identity differs
        first.rename(moved)
        first.mkdir()
        os.chmod(first, 0o700)
    else:
        shutil.rmtree(first)
    if replacement == "directory":
        first.mkdir()
        os.chmod(first, 0o755)
    elif replacement == "symlink":
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        try:
            first.symlink_to(elsewhere, target_is_directory=True)
        except OSError:
            pytest.skip("this platform cannot create symbolic links")
    (first / "kept").write_bytes(b"not the verifier's")
    second = cc._probe_workspace(root)[0]
    try:
        assert second != first and workspace["base"] == second
        cc._remove_probe_directory(os.getpid(), first, identity)   # the exit handler registered for the first
        assert (first / "kept").exists()
    finally:
        cc._remove_probe_directory(os.getpid(), second, workspace["identity"])
        if first.is_symlink():
            first.unlink()
        else:
            shutil.rmtree(first, ignore_errors=True)
        shutil.rmtree(moved, ignore_errors=True)


@needs_private_mkdtemp
def test_a_relative_temporary_directory_still_gives_the_probe_an_absolute_prefix(tmp_path, monkeypatch) -> None:
    """Review I2: before 3.12, mkdtemp under a relative temp directory returns a path the probe resolves elsewhere."""
    root = _registry_tree(tmp_path / "tree")
    work = tmp_path / "work"
    (work / "relative-temp").mkdir(parents=True)
    monkeypatch.chdir(work)
    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    monkeypatch.setattr(tempfile, "tempdir", "relative-temp")
    probes = _record_probes(monkeypatch)
    try:
        assert cc.production_registry_identity(root)["digest"] == "honest"
        _rewrite_keeping_size_and_mtime(root / cc.REGISTRY_ENTRY, _CAPABILITIES % b"edited")
        assert cc.production_registry_identity(root)["digest"] == "edited"
        assert workspace["base"].is_absolute()
        assert all(run.prefix.is_absolute() and run.cwd.is_absolute() for run in probes)
    finally:
        if workspace:
            cc._remove_probe_directory(os.getpid(), workspace["base"], workspace["identity"])


@needs_private_mkdtemp
def test_the_probe_never_leaves_a_directory_inside_the_tree_it_certifies(tmp_path, monkeypatch) -> None:
    """With the temporary directory inside the tree, a persistent prefix would make the tree dirty: one-shot instead."""
    root = _registry_tree(tmp_path / "tree")
    other = _registry_tree(tmp_path / "other")
    inside = root / "scratch"
    inside.mkdir()
    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    monkeypatch.setattr(tempfile, "tempdir", str(inside))
    probes = _record_probes(monkeypatch)
    for _ in range(2):
        assert cc.production_registry_identity(root)["digest"] == "honest"
    assert list(inside.iterdir()) == [] and workspace == {}
    assert len({run.prefix for run in probes}) == 2   # a fresh prefix per probe, as before the per-process prefix
    # a prefix created for another tree, which this tree turns out to contain, is not used for it either
    assert cc.production_registry_identity(other)["digest"] == "honest"
    assert workspace and workspace["base"].is_relative_to(inside.resolve())
    assert cc.production_registry_identity(root)["digest"] == "honest"
    assert list(inside.iterdir()) == [] and workspace == {}


# ---- second review (LOW-1..LOW-3) -------------------------------------------------------------------------------------
def _checked_pyc(source: pathlib.Path, planted: bytes) -> bytes:
    """A CHECKED_HASH .pyc of ``planted`` that carries ``source``'s own hash: the import's check accepts it."""
    code = compile(planted, str(source), "exec", dont_inherit=True)
    return (importlib.util.MAGIC_NUMBER + (0b11).to_bytes(4, "little")
            + importlib.util.source_hash(source.read_bytes()) + marshal.dumps(code))


def _probe_with_prefix(root: pathlib.Path, prefix: pathlib.Path, cwd: pathlib.Path) -> dict:
    """The registry probe exactly as the verifier runs it, reading ``prefix`` with no seeding first."""
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(("PYTHON", "FORGE"))}
    run = subprocess.run([sys.executable, "-E", "-s", "-P", "-X", f"pycache_prefix={prefix}", "-c", cc._REGISTRY_PROBE,
                          str(root / "src")], cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout.strip().splitlines()[-1])


@needs_private_mkdtemp
def test_a_forged_checked_hash_pyc_in_the_prefix_never_runs(tmp_path, monkeypatch) -> None:
    """Review LOW-1a: the import compares only the header's hash with the source's, so a .pyc carrying the right hash
    and other code passes it. Only the seeding's record of the bytes it wrote replaces it."""
    root = _registry_tree(tmp_path / "tree")
    capabilities = root / cc.REGISTRY_ENTRY
    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    probes = _record_probes(monkeypatch)
    try:
        assert cc.production_registry_identity(root)["digest"] == "honest"
        prefix = probes[-1].prefix
        _bytecode_path(prefix, capabilities.resolve()).write_bytes(_checked_pyc(capabilities, _CAPABILITIES % b"planted"))
        elsewhere = tmp_path / "cwd"
        elsewhere.mkdir()
        assert _probe_with_prefix(root, prefix, elsewhere)["digest"] == "planted"   # positive control: it passes
        assert cc.production_registry_identity(root)["digest"] == "honest"
    finally:
        if workspace:
            cc._remove_probe_directory(os.getpid(), workspace["base"], workspace["identity"])


@needs_private_mkdtemp
@pytest.mark.parametrize("seeder", [
    # a record that would be accepted, from a run that then fails: only the exit status refuses it
    "print('{\"kept\": {}, \"errors\": []}'); raise SystemExit(1)",
    "print('{\"kept\": {}, \"errors\": [\"a directory could not be listed\"]}')",
])
def test_a_seeding_that_fails_gives_the_probe_a_fresh_prefix(tmp_path, monkeypatch, seeder) -> None:
    """Review LOW-1b: a prefix whose seeding did not complete is never handed to the probe."""
    root = _registry_tree(tmp_path / "tree")
    capabilities = root / cc.REGISTRY_ENTRY
    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    probes = _record_probes(monkeypatch)
    try:
        assert cc.production_registry_identity(root)["digest"] == "honest"
        reused = probes[-1].prefix
        _bytecode_path(reused, capabilities.resolve()).write_bytes(_checked_pyc(capabilities, _CAPABILITIES % b"planted"))
        monkeypatch.setattr(cc, "_SEED_PROBE_BYTECODE", seeder)
        assert cc.production_registry_identity(root)["digest"] == "honest"
        assert probes[-1].prefix != reused and not probes[-1].prefix.exists()   # one-shot, removed after the probe
    finally:
        if workspace:
            cc._remove_probe_directory(os.getpid(), workspace["base"], workspace["identity"])


def test_the_analysis_memo_is_keyed_by_the_parsers_integer_digit_limit(tmp_path) -> None:
    """Review LOW-2: whether a file with a long literal parses at all depends on the limit, so the memo does too."""
    path = tmp_path / "big.py"
    path.write_bytes(b"N = " + b"7" * 5000 + b"  # " + uuid.uuid4().hex.encode() + b"\n")
    limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    try:
        assert cc.dynamic_imports(path) == []
    finally:
        sys.set_int_max_str_digits(limit)
    with pytest.raises(SyntaxError, match="digits"):
        cc.dynamic_imports(path)


def _link_directory(link: pathlib.Path, target: pathlib.Path) -> None:
    """A directory link at ``link``: a symbolic link, or on Windows without that privilege a junction."""
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        pass
    if os.name != "nt":
        pytest.skip("this platform cannot create a directory link")
    import _winapi

    try:
        _winapi.CreateJunction(str(target), str(link))
    except OSError:
        pytest.skip("this platform cannot create a directory link")


@needs_private_mkdtemp
def test_a_src_that_resolves_outside_the_tree_is_swept_too(tmp_path, monkeypatch) -> None:
    """Review LOW-3: the probe imports from the resolved src/, so that part of the prefix is swept even when it is not
    under the tree's part -- or bytecode for what the seeding does not compile would carry into the next probe."""
    elsewhere = _registry_tree(tmp_path / "elsewhere")
    root = tmp_path / "tree"
    root.mkdir()
    _link_directory(root / "src", elsewhere / "src")
    try:
        assert not (root / "src").resolve().is_relative_to(root.resolve())
        probes = _record_probes(monkeypatch)
        assert cc.production_registry_identity(root)["digest"] == "honest"
        stray = _bytecode_path(probes[-1].prefix, (root / "src").resolve() / "engcore" / "stray.py")
        stray.write_bytes(b"stray bytecode")
        assert cc.production_registry_identity(root)["digest"] == "honest"
        assert not stray.exists()
    finally:
        if (root / "src").is_symlink():
            (root / "src").unlink()
        else:
            os.rmdir(root / "src")   # a junction: removes the link, never what it points at


@needs_private_mkdtemp
@pytest.mark.parametrize("mode", [0o750, 0o705])   # group access, other access
def test_a_probe_directory_that_is_not_private_from_the_start_is_never_used(tmp_path, monkeypatch, mode) -> None:
    """Second review O3: a temporary root that grants others access (setgid, a default ACL) is caught right after
    mkdtemp; the probe then gets a one-shot prefix instead of a directory its own exit handler would refuse to remove."""
    root = _registry_tree(tmp_path / "tree")
    created: list[pathlib.Path] = []
    real_mkdtemp = tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        if kwargs.get("prefix") == "forge-registry-probe-":
            created.append(pathlib.Path(path))
            if os.name == "posix":
                os.chmod(path, mode)
        return path

    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp)
    if os.name != "posix":   # Windows has no mode bits to check: make the directory fail the identity check instead
        monkeypatch.setattr(cc, "_directory_identity", lambda path: (-1, -1))
    probes = _record_probes(monkeypatch)
    assert cc.production_registry_identity(root)["digest"] == "honest"
    assert created and not any(path.exists() for path in created) and workspace == {}
    assert not probes[-1].prefix.exists()   # the one-shot prefix, removed after the probe


# ---- third review (LOW-A..LOW-C, Ob-1) --------------------------------------------------------------------------------
@pytest.mark.skipif(os.name != "posix", reason="setgid and mode bits are POSIX")
def test_posix_a_setgid_probe_directory_is_private_and_is_used_reused_and_removed(tmp_path, monkeypatch) -> None:
    """Review LOW-C: under a setgid temporary root mkdtemp makes mode 2700 -- private, so the per-process directory is
    used, reused by the next probe and removed at exit, not refused for a bit that grants nobody access."""
    root = _registry_tree(tmp_path / "tree")
    real_mkdtemp = tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        if kwargs.get("prefix") == "forge-registry-probe-":
            os.chmod(path, 0o2700)
        return path

    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp)
    probes = _record_probes(monkeypatch)
    assert cc.production_registry_identity(root)["digest"] == "honest"
    assert cc.production_registry_identity(root)["digest"] == "honest"
    base = workspace["base"]
    assert stat.S_IMODE(base.stat().st_mode) == 0o2700
    assert {run.prefix for run in probes} == {probes[0].prefix} and probes[0].prefix.parent == base
    cc._remove_probe_directory(os.getpid(), base, workspace["identity"])
    assert not base.exists()


@needs_private_mkdtemp
@pytest.mark.parametrize("swap", ["per-process", "per-process and one-shot"])
def test_a_link_put_where_the_new_directory_was_is_never_followed(tmp_path, monkeypatch, swap) -> None:
    """Reviews LOW-A and LOW-D: on a temporary root others can write to, a directory mkdtemp just made can be swapped
    for a link to a private directory of this user before it is checked. Nothing is then written there and nothing in
    it is removed: the per-process directory is refused for a one-shot one, and a swapped one-shot one fails the probe."""
    root = _registry_tree(tmp_path / "tree")
    victim = tmp_path / "victim"
    victim.mkdir()
    os.chmod(victim, 0o700)
    (victim / "sentinel").write_bytes(b"this user's own file")
    swapped: list[pathlib.Path] = []
    real_mkdtemp = tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        per_process = kwargs.get("prefix") == "forge-registry-probe-"
        one_shot = args[1:2] == ("forge-registry-probe-",)   # TemporaryDirectory passes (suffix, prefix, dir)
        if per_process or (one_shot and "one-shot" in swap):
            os.rmdir(path)
            _link_directory(pathlib.Path(path), victim)
            swapped.append(pathlib.Path(path))
        return path

    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp)
    probes = _record_probes(monkeypatch)
    try:
        if "one-shot" in swap:
            with pytest.raises(cc.CertificationError, match="replaced by a link"):
                cc.production_registry_identity(root)
            assert len(swapped) == 2 and probes == []
        else:
            assert cc.production_registry_identity(root)["digest"] == "honest"
            assert len(swapped) == 1
            assert not probes[-1].prefix.resolve().is_relative_to(victim.resolve())
        assert workspace == {}
        assert sorted(path.name for path in victim.iterdir()) == ["sentinel"]
    finally:
        for link in swapped:
            if link.is_symlink():
                link.unlink()
            elif link.exists():
                os.rmdir(link)   # a junction: removes the link, never what it points at


def test_without_a_private_mkdtemp_the_probe_gets_a_one_shot_prefix(tmp_path, monkeypatch) -> None:
    """Review LOW-B: on a Windows CPython older than 3.12.4 mkdtemp's directory is not private to this user, so no
    directory outlives a probe there."""
    root = _registry_tree(tmp_path / "tree")
    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    monkeypatch.setattr(cc, "_mkdtemp_is_private", lambda: False)
    probes = _record_probes(monkeypatch)
    for _ in range(2):
        assert cc.production_registry_identity(root)["digest"] == "honest"
    assert workspace == {} and len({run.prefix for run in probes}) == 2
    assert not any(run.prefix.exists() for run in probes)


@needs_private_mkdtemp
@pytest.mark.parametrize("where", ["below the mirror", "at the mirror"])
def test_the_seeding_never_walks_writes_or_deletes_through_a_link_in_the_prefix(tmp_path, monkeypatch, where) -> None:
    """Reviews Ob-1 and LOW-F: os.walk enters a Windows junction, and a link at the walk's top is entered on every
    platform, so a link planted in the tree's part of the prefix would turn the seeding into writing and deleting this
    user's files elsewhere. The seeding refuses instead, and the probe gets a fresh prefix."""
    root = _registry_tree(tmp_path / "tree")
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / f"stray.{sys.implementation.cache_tag}.pyc").write_bytes(b"this user's own file")
    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    probes = _record_probes(monkeypatch)
    planted = None
    try:
        assert cc.production_registry_identity(root)["digest"] == "honest"
        reused = probes[-1].prefix
        mirror = _bytecode_path(reused, root.resolve() / "x.py").parent
        if where == "at the mirror":
            shutil.rmtree(mirror)
            planted = mirror
        else:
            planted = mirror / "planted"
        _link_directory(planted, victim)
        assert cc.production_registry_identity(root)["digest"] == "honest"
        assert [path.name for path in victim.iterdir()] == [f"stray.{sys.implementation.cache_tag}.pyc"]
        assert probes[-1].prefix != reused   # a fresh prefix: the seeded one could not be trusted
    finally:
        if planted is not None and planted.is_symlink():
            planted.unlink()
        elif planted is not None and planted.exists():
            os.rmdir(planted)   # a junction: removes the link, never what it points at
        if workspace:
            cc._remove_probe_directory(os.getpid(), workspace["base"], workspace["identity"])


@pytest.mark.parametrize("name, implementation, version, private", [
    ("nt", "cpython", (3, 11, 9, "final", 0), False),
    ("nt", "cpython", (3, 12, 3, "final", 0), False),
    ("nt", "cpython", (3, 12, 4, "final", 0), True),
    ("nt", "cpython", (3, 13, 0, "alpha", 6), False),
    ("nt", "cpython", (3, 13, 0, "beta", 1), True),
    ("nt", "cpython", (3, 14, 2, "final", 0), True),
    ("nt", "pypy", (3, 14, 2, "final", 0), False),
    ("posix", "cpython", (3, 11, 0, "final", 0), True),
])
def test_review_low_e_mkdtemp_is_private_only_where_cpython_restricts_it(monkeypatch, name, implementation, version,
                                                                          private) -> None:
    """Review LOW-E: on Windows mkdtemp's directory is private to this user only in CPython 3.12.4+ and 3.13.0b1+
    (CVE-2024-4030); everywhere else the probe is one-shot."""
    monkeypatch.setattr(cc, "os", _os_with(name=name))
    monkeypatch.setattr(cc, "sys", types.SimpleNamespace(version_info=version,
                                                         implementation=types.SimpleNamespace(name=implementation)))
    assert cc._mkdtemp_is_private() is private


@needs_private_mkdtemp
def test_review_ob6_a_file_link_in_the_prefix_fails_the_seeding(tmp_path, monkeypatch) -> None:
    """Review Ob-6: a file link in the tree's part of the prefix is refused like a directory link."""
    root = _registry_tree(tmp_path / "tree")
    victim = tmp_path / "victim.pyc"
    victim.write_bytes(b"this user's own file")
    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    probes = _record_probes(monkeypatch)
    link = None
    try:
        assert cc.production_registry_identity(root)["digest"] == "honest"
        reused = probes[-1].prefix
        link = _bytecode_path(reused, root.resolve() / "src" / "engcore" / "linked.py")
        try:
            link.symlink_to(victim)
        except OSError:
            link = None
            pytest.skip("this platform cannot create symbolic links")
        assert cc.production_registry_identity(root)["digest"] == "honest"
        assert probes[-1].prefix != reused and victim.read_bytes() == b"this user's own file"
    finally:
        if link is not None and link.is_symlink():
            link.unlink()
        if workspace:
            cc._remove_probe_directory(os.getpid(), workspace["base"], workspace["identity"])


@needs_private_mkdtemp
def test_review_low_f_the_seeding_interpreter_writes_no_bytecode_of_its_own(tmp_path, monkeypatch) -> None:
    """Review LOW-F: the seeding checks the prefix for links before writing, but an interpreter writes the bytecode of
    its own imports before its first line runs; it runs with -B, so all it ever writes is the tree's seeded bytecode."""
    root = _registry_tree(tmp_path / "tree")
    workspace: dict = {}
    monkeypatch.setattr(cc, "_PROBE_WORKSPACE", workspace)
    real_run = subprocess.run
    seen: dict = {}

    def run(args, *positional, **keywords):
        if cc._REGISTRY_PROBE in list(args):
            seen["prefix"] = pathlib.Path(next(a.split("=", 1)[1] for a in args if str(a).startswith("pycache_prefix=")))
            raise RuntimeError("stopped before the probe")
        return real_run(args, *positional, **keywords)

    monkeypatch.setattr(cc.subprocess, "run", run)
    try:
        with pytest.raises(RuntimeError, match="stopped before the probe"):
            cc.production_registry_identity(root)
        written = [path for path in seen["prefix"].rglob("*") if path.is_file()]   # before anything else runs there
        mirror = _bytecode_path(seen["prefix"], root.resolve() / "x.py").parent
        assert written and all(path.is_relative_to(mirror) for path in written), \
            [str(path) for path in written if not path.is_relative_to(mirror)][:5]
    finally:
        if workspace:
            cc._remove_probe_directory(os.getpid(), workspace["base"], workspace["identity"])
