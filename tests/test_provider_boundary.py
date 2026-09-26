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


def test_executable_probe_binds_exact_path_version_and_digest():
    cap = ProviderCapability("python-proc", "demo", "process", "python", ("demo",))
    status = executable_probe(cap, os.path.basename(PY), ("--version",), lambda s: s.split()[-1] if "Python" in s else "",
                              search_path=os.path.dirname(PY))()
    assert status.available and status.version.startswith("3.") and status.digest == _sha256_file(PY) and status.location == PY


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
    for name in ("pybamm", "cantera", "coolprop", "tespy", "calculix", "openfoam", "su2", "code_aster", "openmodelica"):
        monkeypatch.syspath_prepend(str(root / "providers" / name))
    monkeypatch.setenv("FORGE_PROVIDER_ENVS", str(root / "no-provider-envs-here"))
    reg = default_registry()
    by_id = {s.capability.provider_id: s for s in reg.discover()}
    for pid in ("pybamm", "cantera", "coolprop", "tespy", "calculix", "openfoam", "su2", "code_aster", "openmodelica"):
        assert pid in by_id, pid
        status = by_id[pid]
        if not status.available:  # this core venv has none of the heavy stacks
            assert status.reason
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
