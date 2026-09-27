"""BIG 11 provider boundary: registry/discovery, no silent fallback, content identity, process safety.

Proof I (unavailable-provider refusal) and Proof J (stale/foreign output refusal)
live here; they need no heavy provider stack.  The "solver" in the process tests
is a real child Python process.
"""

from __future__ import annotations

import os
import sys

import pytest

from engcore.providers import (
    Availability, GeneratedFile, ProcessInvocation, ProcessWorkspace, ProviderCapability, ProviderExecutionIdentity,
    ProviderExecutionRecord, ProviderRefusal, ProviderRegistry, ProviderStatus, ProviderUnavailable, QuantitySeries,
    default_registry, executable_probe, minimal_environment, safe_relative,
)
from engcore.providers.catalog import KNOWN_ADAPTERS, _sha256_file
from engcore.scientific.units.quantity import Quantity

CAP = ProviderCapability("demo", "demo_family", "library", "demo-pkg", ("demo",))
PY = os.path.realpath(sys.executable)


def _available(version="1.0"):
    return lambda: ProviderStatus(CAP, Availability.AVAILABLE, version, "a" * 64, "/x")


# ---- registry / discovery / no fallback (Proof I) ------------------------------------


def test_proof_i_unavailable_provider_is_refused_and_nothing_is_substituted():
    reg = ProviderRegistry()
    reg.register(CAP, _available())
    other = ProviderCapability("absent", "demo_family", "process", "absent-exe", ("demo",))
    reg.register(other, executable_probe(other, "forge-no-such-solver-xyz", ("--version",), lambda s: s.strip()))
    status = reg.status("absent")
    assert status.availability is Availability.UNAVAILABLE and "not found" in status.reason
    with pytest.raises(ProviderUnavailable, match="no other provider is substituted"):
        reg.require("absent")  # a same-family provider IS available; it is not used
    with pytest.raises(ProviderUnavailable, match="does not match"):
        reg.require("demo", version="2.0")
    with pytest.raises(ProviderUnavailable, match="not registered"):
        reg.require("never-heard-of")
    assert [s.capability.provider_id for s in reg.discover()] == ["absent", "demo"]  # id order, no ranking
    assert reg.discover()[0].capability.to_dict()["classification"] == "descriptive_capability_not_applicability"


def test_default_registry_never_raises_for_missing_adapter_packages():
    reg = default_registry()
    statuses = {s.capability.provider_id: s for s in reg.discover()}
    assert set(statuses) >= {m.removeprefix("forge_") for m in KNOWN_ADAPTERS if m not in ("forge_fenicsx", "forge_precice")}
    for s in statuses.values():
        assert s.available or s.reason  # unavailable always says why


def test_the_calculix_descriptor_declares_exactly_its_measured_probe_exit_code(monkeypatch):
    """BIG 14 F3/F7: `ccx -v` exits 201 by design (CalculiX 2.23). The declaration is pinned, and the rule refuses nonsense."""
    import forge_calculix.descriptor as ccd

    seen = {}

    def spy(capability, executable, version_argv, parse_version, **kwargs):
        seen.update(executable=executable, argv=version_argv, **kwargs)
        return lambda: ProviderStatus(capability, Availability.UNAVAILABLE, reason="spy")
    monkeypatch.setattr(ccd, "executable_probe", spy)
    ccd.register(ProviderRegistry(), provider_envs="/nowhere")
    assert seen["executable"] == "ccx" and seen["argv"] == ("-v",) and seen["accepted_exit_codes"] == (201,)
    assert ccd._version("                This is Version 2.23\n") == "2.23"
    cap = ProviderCapability("x", "demo", "process", "x", ("demo",))
    for bad in ((), (-9,), (True,), ("0",)):
        with pytest.raises(Exception, match="accepted_exit_codes"):
            executable_probe(cap, "x", (), str, accepted_exit_codes=bad)


@pytest.mark.skipif(os.name != "posix", reason="a shell-script stand-in for icoFoam needs a POSIX host (CI is Linux)")
@pytest.mark.parametrize("exit_code, available", ((0, True), (1, False)))
def test_the_openfoam_probe_requires_exit_zero_whatever_its_output_says(tmp_path, exit_code, available):
    """BIG 14 F1: OpenFOAM does not go through executable_probe, so its own probe must refuse a failed run."""
    import json
    import stat

    import forge_openfoam.descriptor as ofd

    prefix = tmp_path / "openfoam"
    (prefix / "bin").mkdir(parents=True)
    (prefix / "conda-meta").mkdir()
    (prefix / "conda-meta" / "stub-1-0.json").write_text(json.dumps({"name": "stub", "version": "1", "build": "0", "sha256": "0" * 64}))
    exe = prefix / "bin" / "icoFoam"
    exe.write_text("\n".join(("#!/bin/sh", "echo 'Build  : OpenFOAM-v2412'", f"exit {exit_code}", "")))
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    reg = ProviderRegistry()
    ofd.register(reg, provider_envs=str(tmp_path))
    status = reg.status("openfoam")
    assert status.available is available, status.reason
    if available:
        assert status.version == "v2412" and status.digest
    else:
        assert not status.digest and "exited 1 (accepted [0])" in status.reason


def test_a_missing_or_failing_adapter_is_registered_unavailable_with_its_error(monkeypatch):
    """BIG 14 re-review N8: with the adapters on the pytest path, the missing-package branch is tested on purpose."""
    import types

    import engcore.providers.catalog as catalog

    broken = types.ModuleType("forge_brokenadapter.descriptor")

    def register(registry, **_):
        raise NameError("simulated adapter defect")
    broken.register = register
    monkeypatch.setitem(sys.modules, "forge_brokenadapter", types.ModuleType("forge_brokenadapter"))
    monkeypatch.setitem(sys.modules, "forge_brokenadapter.descriptor", broken)
    monkeypatch.setattr(catalog, "KNOWN_ADAPTERS", ("forge_doesnotexist", "forge_brokenadapter"))
    statuses = {s.capability.provider_id: s for s in catalog.default_registry().discover()}
    assert set(statuses) == {"doesnotexist", "brokenadapter"}
    missing, failing = statuses["doesnotexist"], statuses["brokenadapter"]
    assert not missing.available and missing.reason.startswith("adapter package 'forge_doesnotexist' is not importable here (ModuleNotFoundError: ")
    assert not failing.available and failing.reason == "adapter 'forge_brokenadapter' failed to register: NameError: simulated adapter defect"


def test_executable_probe_binds_exact_path_version_and_digest():
    cap = ProviderCapability("python-proc", "demo", "process", "python", ("demo",))
    status = executable_probe(cap, os.path.basename(PY), ("--version",), lambda s: s.split()[-1] if "Python" in s else "",
                              search_path=os.path.dirname(PY))()
    assert status.available and status.version.startswith("3.") and status.digest == _sha256_file(PY) and status.location == PY


def test_a_failed_or_timed_out_version_probe_yields_no_identity():
    """BIG 14 14.1: exit code and timeout decide, not whether some text parses as a version."""
    cap = ProviderCapability("python-proc", "demo", "process", "python", ("demo",))
    parse = lambda s: s.split()[-1] if "Python" in s else ""  # noqa: E731
    exe, path = os.path.basename(PY), os.path.dirname(PY)
    lying = ("-c", "import sys; print('Python 3.99.1'); sys.exit(3)")  # prints a version, then fails
    failed = executable_probe(cap, exe, lying, parse, search_path=path)()
    assert not failed.available and not failed.digest and "exited 3 (accepted [0])" in failed.reason
    base = dict(adapter_id="demo-adapter", adapter_version="1", problem={"k": 1}, configuration="deck", output_request=("x",))
    with pytest.raises(Exception, match="AVAILABLE"):
        ProviderExecutionIdentity.from_content(failed, **base)
    # a tool whose version flag exits non-zero by design declares the measured code; nothing else is accepted
    declared = executable_probe(cap, exe, lying, parse, search_path=path, accepted_exit_codes=(3,))()
    assert declared.available and declared.version == "3.99.1" and declared.digest == _sha256_file(PY)
    clean = executable_probe(cap, exe, ("--version",), parse, search_path=path, accepted_exit_codes=(3,))()
    assert not clean.available and "exited 0 (accepted [3])" in clean.reason
    hung = executable_probe(cap, exe, ("-c", "import time; print('Python 3.99.1', flush=True); time.sleep(30)"), parse,
                            search_path=path, timeout=0.5)()
    assert not hung.available and not hung.digest and "TimeoutExpired" in hung.reason
    # the registry caches the failed answer as UNAVAILABLE; require() refuses it and no identity can be formed
    reg = ProviderRegistry()
    reg.register(cap, executable_probe(cap, exe, lying, parse, search_path=path))
    with pytest.raises(ProviderUnavailable, match="exited 3"):
        reg.require("python-proc")
    assert not reg.status("python-proc").available


# ---- content identity ---------------------------------------------------------------


def test_execution_identity_is_derived_from_content_not_labels():
    status = _available()()
    base = dict(adapter_id="demo-adapter", adapter_version="1", problem={"k": 1}, configuration="solver deck v1",
                inputs={"mesh": b"\x00\x01"}, output_request=("x",))
    a = ProviderExecutionIdentity.from_content(status, **base)
    assert a.digest == ProviderExecutionIdentity.from_content(status, **base).digest
    for change in ({"problem": {"k": 2}}, {"configuration": "solver deck v2"}, {"inputs": {"mesh": b"\x00\x02"}}, {"output_request": ("y",)}):
        assert ProviderExecutionIdentity.from_content(status, **{**base, **change}).digest != a.digest
    newer = ProviderStatus(CAP, Availability.AVAILABLE, "1.1", "b" * 64, "/x")
    assert ProviderExecutionIdentity.from_content(newer, **base).digest != a.digest
    with pytest.raises(Exception, match="AVAILABLE"):
        ProviderExecutionIdentity.from_content(ProviderStatus(CAP, Availability.UNAVAILABLE, reason="x"), **base)
    with pytest.raises(Exception, match="canonical"):
        ProviderExecutionIdentity.from_content(status, **{**base, "problem": {"k": float("nan")}})


def test_records_refuse_missing_or_non_finite_outputs_and_failed_records_expose_nothing():
    status = _available()()
    ident = ProviderExecutionIdentity.from_content(status, adapter_id="a", adapter_version="1", problem={}, configuration={},
                                                   output_request=("v",))
    with pytest.raises(ProviderRefusal, match="never a default"):
        ProviderExecutionRecord(ident, True, "", scalars={})
    with pytest.raises(ProviderRefusal, match="non-finite"):
        QuantitySeries("v", "V", (0.0, 1.0), (1.0, float("inf")))
    with pytest.raises(ProviderRefusal, match="exposes no outputs"):
        ProviderExecutionRecord(ident, False, "diverged", scalars={"v": Quantity(1, "V")})
    ok = ProviderExecutionRecord(ident, True, "", scalars={"v": Quantity(3.7, "V")})
    assert ok.to_dict()["classification"] == "provider_computation_not_evidence" and ok.uncertainty.kind.value == "unknown"


# ---- process boundary (Proof J) --------------------------------------------------------


SOLVER = b"import sys\nopen(sys.argv[2], 'wb').write(open(sys.argv[1], 'rb').read().upper())\n"


def _invocation(expected=("out.txt",), args=("solver.py", "in.txt", "out.txt"), timeout=60.0, extra_inputs=()):
    return ProcessInvocation(PY, _sha256_file(PY), sys.version.split()[0], args,
                             (GeneratedFile("solver.py", SOLVER), GeneratedFile("in.txt", b"forge deck\n")) + tuple(extra_inputs),
                             minimal_environment(PY, {"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}), timeout, expected)


def _fake_conda_env(root, packages=(("numpy", "2.5.3"), ("ccx", "2.23"))):
    import json

    meta = root / "conda-meta"
    meta.mkdir(parents=True)
    for name, version in packages:
        (meta / f"{name}-{version}-0.json").write_text(json.dumps({"name": name, "version": version, "build": "0", "sha256": "1" * 64}))
    return str(root)


def test_a_conda_environment_changed_after_discovery_is_refused_at_launch(tmp_path):
    """BIG 14 review F2: the executable was re-hashed at launch; the environment it loads from was not."""
    from engcore.providers.catalog import conda_environment_digest

    prefix = _fake_conda_env(tmp_path / "env")
    discovered, _ = conda_environment_digest(prefix)
    inv = _invocation()
    checked = ProcessInvocation(inv.executable, inv.executable_digest, inv.version, inv.args, inv.inputs, inv.environment,
                                inv.timeout_s, inv.expected_outputs, conda_environment=(prefix, discovered))
    assert checked.digest == inv.digest  # an operational check: the identity already binds the environment digest
    (tmp_path / "ok").mkdir()
    (tmp_path / "changed").mkdir()
    assert ProcessWorkspace(str(tmp_path / "ok")).run(checked).completed
    (tmp_path / "env" / "conda-meta" / "ccx-2.23-0.json").write_text('{"name": "ccx", "version": "2.24", "build": "0", "sha256": "2"}')
    with pytest.raises(ProviderRefusal, match="changed since discovery"):
        ProcessWorkspace(str(tmp_path / "changed")).run(checked)
    with pytest.raises(ProviderRefusal, match="absolute prefix"):
        ProcessInvocation(inv.executable, inv.executable_digest, inv.version, inv.args, inv.inputs, inv.environment,
                          inv.timeout_s, inv.expected_outputs, conda_environment=("relative", discovered))


def test_a_sequence_refused_at_a_later_step_leaves_a_spent_workspace(tmp_path):
    """Review L4: step 1 ran, step 2's launch check refused; the workspace must not be runnable again."""
    from engcore.providers.catalog import conda_environment_digest

    prefix = _fake_conda_env(tmp_path / "env")
    good, _ = conda_environment_digest(prefix)
    inv = _invocation()
    stale = ProcessInvocation(inv.executable, inv.executable_digest, inv.version, inv.args, inv.inputs, inv.environment,
                              inv.timeout_s, inv.expected_outputs, conda_environment=(prefix, "f" * 64))
    (tmp_path / "ws").mkdir()
    ws = ProcessWorkspace(str(tmp_path / "ws"))
    with pytest.raises(ProviderRefusal, match="changed since discovery"):
        ws.run_sequence((inv, stale))
    with pytest.raises(ProviderRefusal, match="exactly once"):
        ws.run(inv)
    assert good != "f" * 64


def test_conda_environment_of_reads_only_what_discovery_bound(tmp_path):
    from engcore.providers import conda_environment_of

    cap = ProviderCapability("ccx", "fem", "process", "ccx", ("demo",))
    prefix = _fake_conda_env(tmp_path / "env")
    exe = os.path.join(prefix, "bin", "ccx")
    bound = ProviderStatus(cap, Availability.AVAILABLE, "2.23", "a" * 64, exe, dependencies=(("conda-environment", "2 packages", "b" * 64),))
    assert conda_environment_of(bound) == (prefix, "b" * 64)
    assert conda_environment_of(ProviderStatus(cap, Availability.AVAILABLE, "2.23", "a" * 64, exe)) == ()
    elsewhere = ProviderStatus(cap, Availability.AVAILABLE, "2.23", "a" * 64, str(tmp_path / "plain" / "bin" / "ccx"),
                               dependencies=(("conda-environment", "2 packages", "b" * 64),))
    with pytest.raises(ProviderRefusal, match="is not one"):
        conda_environment_of(elsewhere)


def test_a_refresh_drops_the_per_process_discovery_caches():
    import engcore.providers.catalog as catalog

    catalog.python_environment_digest()
    catalog._located("pytest")
    assert catalog._PY_ENV and "pytest" in catalog._LOCATED
    cap = ProviderCapability("pytest-lib", "demo", "library", "pytest", ("demo",))
    reg = ProviderRegistry()
    reg.register(cap, catalog.python_package_probe(cap, "pytest", ("pytest",)))
    reg.status("pytest-lib", refresh=True)
    assert "pytest" not in catalog._LOCATED  # re-located on the next check, not reused
    assert catalog._PY_ENV  # re-read by the refreshed probe itself


def test_found_but_refused_separates_a_defect_from_an_absent_provider():
    cap = ProviderCapability("x", "demo", "process", "x", ("demo",))
    for reason in ("adapter 'forge_x' failed to register: NameError: y", "version probe of /e/bin/x exited 0 (accepted [201])",
                   "could not establish the version of /e/bin/x", "could not establish the OpenFOAM version"):
        assert ProviderStatus(cap, Availability.UNAVAILABLE, reason=reason).found_but_refused, reason
    for reason in ("executable 'x' not found", "python module 'x' is not installed", "OpenFOAM icoFoam not found under the provider prefix"):
        assert not ProviderStatus(cap, Availability.UNAVAILABLE, reason=reason).found_but_refused, reason
    assert not ProviderStatus(cap, Availability.AVAILABLE, "1", "a" * 64).found_but_refused
    assert "found_but_refused" not in ProviderStatus(cap, Availability.UNAVAILABLE, reason="adapter x").to_dict()


def test_a_library_changed_after_discovery_is_refused_at_execution(monkeypatch):
    """BIG 14 re-review N1: library providers import at execution; the library must still be the one discovery bound."""
    import engcore.providers.catalog as catalog
    from engcore.providers import python_package_probe, require_library_unchanged

    # a per-process pin: each test starts from its own empty table
    monkeypatch.setattr(catalog, "_IMPORTED_UNDER", {})
    cap = ProviderCapability("pytest-lib", "demo", "library", "pytest", ("demo",))
    status = python_package_probe(cap, "pytest", ("pytest",), dependencies=("pluggy",))()
    assert status.available, status.reason
    require_library_unchanged(status, "pytest")  # unchanged: passes
    real_digest = catalog._record_digest_of
    with monkeypatch.context() as m:
        m.setattr(catalog, "_record_digest_of", lambda d, n: "0" * 64 if n == "pluggy" else real_digest(d, n))
        with pytest.raises(ProviderRefusal, match="changed since discovery"):
            require_library_unchanged(status, "pytest")  # a dependency's files changed

    class Upgraded:  # what a located distribution reads like after pip replaced it with a newer one
        version, files = "99.0", ()

        @staticmethod
        def read_text(name):
            return "pytest/__init__.py,sha256=new,1\n" if name == "RECORD" else None
    with monkeypatch.context() as m:
        m.setitem(catalog._LOCATED, "pytest", Upgraded())
        with pytest.raises(ProviderRefusal, match="now 99.0"):
            require_library_unchanged(status, "pytest")  # the provider itself was upgraded

    class Removed:  # its dist-info directory is gone
        version, files = None, ()
    with monkeypatch.context() as m:
        m.setitem(catalog._LOCATED, "pytest", Removed())
        with pytest.raises(ProviderRefusal, match="no longer installed"):
            require_library_unchanged(status, "pytest")
    require_library_unchanged(status, "pytest")  # unchanged again once the stand-ins are gone
    with pytest.raises(ProviderRefusal, match="not an available library provider"):
        require_library_unchanged(ProviderStatus(ProviderCapability("x", "demo", "process", "x", ("d",)), Availability.AVAILABLE, "1", "a" * 64), "x")


def test_a_library_module_in_memory_must_be_the_one_discovery_bound(monkeypatch):
    """BIG 14 re-review M2: the check covers the imported module, not only the files on disk."""
    import types

    import engcore.providers.catalog as catalog
    from engcore.providers import python_package_probe, require_library_unchanged

    # a per-process pin: each test starts from its own empty table
    monkeypatch.setattr(catalog, "_IMPORTED_UNDER", {})
    cap = ProviderCapability("pytest-lib", "demo", "library", "pytest", ("demo",))
    status = python_package_probe(cap, "pytest", ("pytest",))()
    assert status.available, status.reason
    require_library_unchanged(status, "pytest")
    with pytest.raises(ProviderRefusal, match="not the library 'cantera'"):
        require_library_unchanged(status, "cantera")  # the status is not trusted to say which library runs
    real = sys.modules["pytest"]
    with monkeypatch.context() as m:
        shadow = types.ModuleType("pytest")
        shadow.__file__ = os.path.join(os.path.dirname(os.path.dirname(real.__file__)), "elsewhere", "pytest", "__init__.py")
        m.setitem(sys.modules, "pytest", shadow)
        with pytest.raises(ProviderRefusal, match="was loaded from"):
            require_library_unchanged(status, "pytest")
    with monkeypatch.context() as m:
        older = types.ModuleType("pytest")
        older.__file__, older.__version__ = real.__file__, "0.1"
        m.setitem(sys.modules, "pytest", older)
        with pytest.raises(ProviderRefusal, match="in memory is version 0.1"):
            require_library_unchanged(status, "pytest")
    with monkeypatch.context() as m:
        m.setitem(catalog._IMPORTED_UNDER, "pytest", ("0.1", "0" * 64))  # first used under an older discovery
        with pytest.raises(ProviderRefusal, match="first used in this process as 0.1"):
            require_library_unchanged(status, "pytest")
    # a declared DEPENDENCY counts too (re-review of d0294654): its module in memory and its per-process pin
    with_dep = python_package_probe(ProviderCapability("pytest-dep", "demo", "library", "pytest", ("d",)), "pytest", ("pytest",),
                                    dependencies=("pluggy",))()
    require_library_unchanged(with_dep, "pytest")
    with monkeypatch.context() as m:
        stale = types.ModuleType("pluggy")
        stale.__version__ = "0.0.1"
        m.setitem(sys.modules, "pluggy", stale)
        with pytest.raises(ProviderRefusal, match="'pluggy' in memory is version 0.0.1"):
            require_library_unchanged(with_dep, "pytest")
    with monkeypatch.context() as m:
        m.setitem(catalog._IMPORTED_UNDER, "pluggy", ("0.0.1", "0" * 64))
        with pytest.raises(ProviderRefusal, match="'pluggy' was first used in this process as 0.0.1"):
            require_library_unchanged(with_dep, "pytest")
    # discovery refuses a module that is not a file of the distribution it would bind (shadowing / editable)
    shadowed = python_package_probe(ProviderCapability("mis", "demo", "library", "pytest", ("d",)), "pytest", ("pluggy",))()
    assert not shadowed.available and shadowed.found_but_refused and "is not a file of the installed pluggy" in shadowed.reason


def test_every_library_adapter_checks_its_library_where_it_forms_an_identity():
    """BIG 14 M1: every function that forms an execution identity in a library adapter calls the check itself,
    naming its package. Itself, not an enclosing function: a closure such as the coupling path's per-window
    ``advance`` runs long after its constructor's check, which then says nothing about the window."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "providers"
    packages = {"cantera": "cantera", "coolprop": "CoolProp", "pybamm": "pybamm", "tespy": "tespy"}

    def own_nodes(fn):  # the function's body without the bodies of functions nested in it
        stack, out = list(fn.body), []
        while stack:
            node = stack.pop()
            out.append(node)
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                stack.extend(ast.iter_child_nodes(node))
        return out

    missing, seen = [], 0
    for name, package in packages.items():
        for path in sorted((root / name / f"forge_{name}").glob("*.py")):
            for fn in ast.walk(ast.parse(path.read_bytes().decode("utf-8"))):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                calls = [n for n in own_nodes(fn) if isinstance(n, ast.Call)]
                if not any(getattr(c.func, "attr", None) == "from_content" for c in calls):
                    continue
                seen += 1
                if not any(getattr(c.func, "id", None) == "require_library_unchanged" and len(c.args) == 2
                           and isinstance(c.args[1], ast.Constant) and c.args[1].value == package for c in calls):
                    missing.append(f"{path.relative_to(root).as_posix()}:{fn.name}")
    assert seen >= 5 and missing == [], (seen, missing)


def test_every_adapter_process_invocation_declares_its_environment_check():
    """Static: an adapter that builds a ProcessInvocation without the check would launch unverified (BIG 14 F2)."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "providers"
    calls = []
    for path in sorted(root.glob("*/forge_*/*.py")):
        for node in ast.walk(ast.parse(path.read_bytes().decode("utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "ProcessInvocation":
                value = next((k.value for k in node.keywords if k.arg == "conda_environment"), None)
                derived = (isinstance(value, ast.Call) and getattr(value.func, "id", None) == "conda_environment_of") or (
                    isinstance(value, ast.Name) and value.id == "checked_environment")
                calls.append((path.relative_to(root).as_posix(), node.lineno, derived))
    assert len(calls) >= 9, calls
    assert [c for c in calls if not c[2]] == [], calls


def test_process_outputs_are_digest_bound_and_only_this_executions_files_are_admitted(tmp_path):
    ws = ProcessWorkspace(str(tmp_path))
    rec = ws.run(_invocation())
    assert rec.completed and rec.exit_code == 0 and [o[0] for o in rec.outputs] == ["out.txt"]
    assert ws.read_output("out.txt") == b"FORGE DECK\n"
    assert rec.to_dict()["classification"] == "process_execution_not_evidence"
    # identity is content: the same invocation in another workspace has the same digest
    assert ProcessWorkspace(str(tmp_path)).run(_invocation()).invocation_digest == rec.invocation_digest


def test_proof_j_stale_and_foreign_result_files_are_refused(tmp_path):
    # a stale result left from an earlier execution is present BEFORE the run and never rewritten
    stale = ProcessWorkspace(str(tmp_path), preexisting={"result.dat": b"old answer 42\n"})
    rec = stale.run(_invocation())
    assert "result.dat" in rec.stale_inputs_untouched
    with pytest.raises(ProviderRefusal, match="stale"):
        stale.read_output("result.dat")
    # the run did not produce its expected output: missing, never a default
    missing = ProcessWorkspace(str(tmp_path), preexisting={"result.dat": b"old answer 42\n"})
    rec2 = missing.run(_invocation(expected=("result.dat",)))
    assert not rec2.completed and rec2.missing_outputs == ("result.dat",)
    # an output edited after the execution recorded it is foreign content
    fresh = ProcessWorkspace(str(tmp_path))
    fresh.run(_invocation())
    with open(os.path.join(fresh.path, "out.txt"), "wb") as fh:
        fh.write(b"tampered\n")
    with pytest.raises(ProviderRefusal, match="foreign"):
        fresh.read_output("out.txt")
    with pytest.raises(ProviderRefusal, match="not produced"):
        fresh.read_output("in.txt")  # an input is never an output


def test_process_safety_argv_names_timeout_and_exit_code(tmp_path):
    for bad in ("../escape.txt", "/abs.txt", "a;rm -rf x", "a b.txt", ""):
        with pytest.raises(ProviderRefusal):
            safe_relative(bad)
    with pytest.raises(ProviderRefusal, match="absolute"):
        ProcessInvocation("python", "0" * 64, "3", (), (), (), 1.0, ())
    # the argument is data, never shell: a ';' is passed through literally and fails as a file name
    ws = ProcessWorkspace(str(tmp_path))
    rec = ws.run(_invocation(args=("solver.py", "in.txt; echo pwned > pwned.txt", "out.txt")))
    assert rec.exit_code != 0 and not rec.completed and not os.path.exists(os.path.join(ws.path, "pwned.txt"))
    slow = ProcessWorkspace(str(tmp_path))
    rec = slow.run(_invocation(args=("-c", "import time; time.sleep(30)"), timeout=1.0, expected=()))
    assert rec.timed_out and rec.exit_code is None and not rec.completed
    with pytest.raises(ProviderRefusal, match="exactly once"):
        slow.run(_invocation())


# ---- optional dependencies: adapters are safe to import without their scientific stacks --------


def test_every_adapter_is_unavailable_not_an_import_error_without_its_stack(monkeypatch):
    import importlib
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    # the adapter roots are on the pytest path (pyproject pythonpath), so every adapter must IMPORT here
    monkeypatch.setenv("FORGE_PROVIDER_ENVS", str(root / "no-provider-envs-here"))
    reg = default_registry()
    by_id = {s.capability.provider_id: s for s in reg.discover()}
    for pid in ("pybamm", "cantera", "coolprop", "tespy", "calculix", "openfoam", "su2", "code_aster", "openmodelica"):
        assert pid in by_id, pid
        status = by_id[pid]
        if not status.available:  # this core venv has none of the heavy stacks
            assert status.reason
            # an adapter that fails to import or register is a defect, not a missing stack (BIG 14 round-3 L1)
            assert not status.reason.startswith("adapter "), status.reason
            with pytest.raises(ProviderUnavailable):
                reg.require(pid)
    adapters = {"forge_pybamm": "PyBaMMProvider", "forge_cantera": "CanteraProvider", "forge_coolprop": "CoolPropProvider",
                "forge_tespy": "TESPyProvider", "forge_calculix": "CalculixProvider", "forge_openfoam": "OpenFOAMProvider",
                "forge_su2": "SU2Provider", "forge_code_aster": "CodeAsterProvider", "forge_openmodelica": "OpenModelicaProvider"}
    for module, cls in adapters.items():
        provider_cls = getattr(importlib.import_module(module), cls)  # importing never needs the scientific stack
        pid = module.removeprefix("forge_")
        if not by_id[pid].available:
            with pytest.raises(ProviderUnavailable):
                provider_cls(reg)


def test_discovery_cli_lists_without_ranking(capsys):
    from engcore.providers.__main__ import main
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "not applicability" in out and "ranked" in out


# ---- review fixes: comparison is bound to real records; process identity holds at launch ----------------------


def _record(provider_id, outputs, dependencies=None, version="1.0"):
    import hashlib

    if dependencies is None:  # its own (distinct) environment
        dependencies = (("python-environment", "1", hashlib.sha256(provider_id.encode()).hexdigest()),)
    cap = ProviderCapability(provider_id, "demo_family", "library", provider_id, ("demo",))
    st = ProviderStatus(cap, Availability.AVAILABLE, version, "c" * 64, "/x", dependencies=dependencies)
    ident = ProviderExecutionIdentity.from_content(st, adapter_id="a", adapter_version="1", problem={"p": 1}, configuration={},
                                                   output_request=tuple(outputs))
    return ProviderExecutionRecord(ident, True, "", scalars=dict(outputs))


def test_comparison_takes_units_from_records_and_refuses_stand_ins_same_provider_and_shared_dependencies():
    from engcore.providers import ComparisonDeclaration, OutputSelection, compare_providers
    from engcore.scientific.errors import InvalidScientificProblem

    decl = ComparisonDeclaration("cell voltage", "V", "identity", Quantity(1e-3, "V"), 0.0, "demo")
    a = _record("alpha", {"v": Quantity(3.7, "V")})
    b = _record("beta", {"v_mv": Quantity(3700.4, "mV")})
    cmp = compare_providers(decl, a, "v", b, "v_mv")  # values AND units come from the records (mV here)
    assert cmp.within_tolerance and abs(cmp.max_absolute - 4e-4) < 1e-9
    assert cmp.to_dict()["classification"] == "solver_corroboration_not_validation" and len(cmp.values_digest) == 64

    class StandIn:
        succeeded, execution_identity = True, "d" * 64
    with pytest.raises(InvalidScientificProblem, match="stand-ins are not compared"):
        compare_providers(decl, StandIn(), "v", b, "v_mv")
    with pytest.raises(InvalidScientificProblem, match="not one provider twice"):
        compare_providers(decl, a, "v", _record("alpha", {"v": Quantity(3.7, "V")}, version="2.0"), "v")
    with pytest.raises(InvalidScientificProblem, match="outputs the records produced"):
        compare_providers(decl, a, "current", b, "v_mv")
    with pytest.raises(InvalidScientificProblem, match="does not fit"):
        compare_providers(decl, a, "v", b, "v_mv", b_select=OutputSelection(rows=(3,)))
    # a provider that declares no dependency set cannot be shown independent: refused, not assumed
    with pytest.raises(InvalidScientificProblem, match="independence UNKNOWN"):
        compare_providers(decl, a, "v", _record("bare", {"v": Quantity(3.7, "V")}, dependencies=()), "v")
    # a TESPy-like path that DEPENDS on the CoolProp-like provider is not an independent corroboration
    net = _record("tespy", {"v": Quantity(3.7, "V")}, dependencies=(("CoolProp", "8.0.0", "e" * 64),))
    with pytest.raises(InvalidScientificProblem, match="not independent"):
        compare_providers(decl, net, "v", _record("coolprop", {"v": Quantity(3.7, "V")}), "v")
    numpy_dep = (("numpy", "2.0", "f" * 64),)
    with pytest.raises(InvalidScientificProblem, match="not independent"):
        compare_providers(decl, _record("gamma", {"v": Quantity(3.7, "V")}, dependencies=numpy_dep), "v",
                          _record("delta", {"v": Quantity(3.7, "V")}, dependencies=numpy_dep), "v")
    same_env = (("python-environment", "1", "9" * 64),)
    with pytest.raises(InvalidScientificProblem, match="identical provider environment"):
        compare_providers(decl, _record("eps", {"v": Quantity(3.7, "V")}, dependencies=same_env), "v",
                          _record("zeta", {"v": Quantity(3.7, "V")}, dependencies=same_env), "v")


def test_comparison_tolerance_is_a_spread_and_relative_tolerance_needs_a_ratio_scale():
    from engcore.providers import ComparisonDeclaration, compare_providers
    from engcore.scientific.errors import InvalidScientificProblem

    decl = ComparisonDeclaration("temperature", "degC", "identity", Quantity(0.5, "degC"), 0.0, "demo")
    a = _record("alpha", {"t": Quantity(300.0, "K")})
    b = _record("beta", {"t": Quantity(300.4, "K")})
    assert compare_providers(decl, a, "t", b, "t").within_tolerance  # 0.5 degC is a 0.5 K spread
    assert not compare_providers(decl, a, "t", _record("gamma", {"t": Quantity(300.6, "K")}), "t").within_tolerance  # never 273.65 K
    with pytest.raises(InvalidScientificProblem, match="offset scale"):
        ComparisonDeclaration("temperature", "degC", "identity", Quantity(0.5, "K"), 0.01, "demo")
    post = ComparisonDeclaration("temperature", "K", "identity", Quantity(0.5, "K"), 0.0, "region picked after looking", post_hoc=True)
    assert compare_providers(post, a, "t", b, "t").classification == "post_hoc_solver_corroboration_not_validation"


def test_executable_changed_since_discovery_is_refused_at_launch(tmp_path):
    inv = _invocation()
    forged = ProcessInvocation(inv.executable, "0" * 64, inv.version, inv.args, inv.inputs, inv.environment, inv.timeout_s,
                               inv.expected_outputs)
    ws = ProcessWorkspace(str(tmp_path))
    try:
        with pytest.raises(ProviderRefusal, match="changed since discovery"):
            ws.run(forged)
    finally:
        ws.cleanup()


def test_a_symlinked_output_is_never_admitted(tmp_path):
    link_solver = b"import os, sys\nos.symlink(os.path.abspath(sys.argv[1]), sys.argv[2])\n"
    inv = ProcessInvocation(PY, _sha256_file(PY), sys.version.split()[0], ("solver.py", "in.txt", "out.txt"),
                            (GeneratedFile("solver.py", link_solver), GeneratedFile("in.txt", b"forge deck\n")),
                            minimal_environment(PY, {"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}), 60.0, ("out.txt",))
    ws = ProcessWorkspace(str(tmp_path))
    try:
        rec = ws.run(inv)
        if rec.exit_code != 0:
            pytest.skip("this platform does not let an unprivileged process create a symlink")
        assert not rec.completed and "out.txt" in rec.missing_outputs
        with pytest.raises(ProviderRefusal):
            ws.read_output("out.txt")
    finally:
        ws.cleanup()
