"""Big Rock I: Project Chrono adapter -- identity, translation plan and refusal (provider-free), plus a gated reference run."""

from __future__ import annotations

import math
import sys
import types

import pytest

from engcore.providers import Availability, ProviderRefusal, ProviderStatus, assess_health
from engcore.providers.health import ProviderHealth
from engcore.scientific.units.quantity import Quantity
from engcore.spatial.geometry import Transform
from engcore.systems.assembly import AssemblyRefusal, ConnectionPoint
from engcore.systems.multibody import GravityDeclaration, MassProperties, MultibodyModel, MultibodyRequest


def m(v):
    return Quantity(v, "m")


def pendulum(length=1.0, mass=2.0, amplitude_deg=5.0):
    from forge_chrono.routes import pendulum_model

    return pendulum_model(length, mass, amplitude_deg)


def request(model, **opts):
    return MultibodyRequest(model, Quantity(2.0, "s"), Quantity(1, "ms"), ("body:bob.position_x", "body:bob.position_z"),
                            opts or {"timestepper": "euler_implicit_linearized", "solver": "sparse_qr"})


def test_translation_plan_is_canonical_and_bound_to_the_model():
    from forge_chrono import translation_plan

    plan = translation_plan(request(pendulum()))
    assert plan == translation_plan(request(pendulum()))
    bob = next(b for b in plan["bodies"] if b["instance_id"] == "bob")
    assert bob["position_m"] == pytest.approx([math.sin(math.radians(5)), 0.0, -math.cos(math.radians(5))]) and bob["mass_kg"] == 2.0 and not bob["fixed"]
    hinge = plan["joints"][0]
    w, x, y, z = hinge["frame_quaternion"]
    # +z rotated onto +y: a rotation of -90 deg about x
    assert (w, x, y, z) == pytest.approx((math.sqrt(0.5), -math.sqrt(0.5), 0, 0))
    assert plan["steps"] == 2000 and plan["translation_status"] == "chrono10_translation_checked_only_by_its_declared_route"
    assert translation_plan(request(pendulum(length=1.5)))["model_digest"] != plan["model_digest"]
    with pytest.raises(ProviderRefusal, match="never used silently"):
        translation_plan(request(pendulum(), solver="x"))
    ts = "euler_implicit_linearized"
    with pytest.raises(ProviderRefusal, match="never used silently"):
        translation_plan(request(pendulum(), timestepper=ts))  # no solver declared: Chrono's PSOR default is never used
    with pytest.raises(ProviderRefusal, match="did not hold a bilateral joint"):
        translation_plan(request(pendulum(), timestepper=ts, solver="psor"))
    with pytest.raises(ProviderRefusal, match="never dropped silently"):
        translation_plan(request(pendulum(), timestepper=ts, solver="sparse_qr", max_iterations=50))
    with pytest.raises(ProviderRefusal, match="HHT is not translated"):
        translation_plan(request(pendulum(), timestepper="hht", solver="sparse_qr"))


def test_body_orientation_is_translated_as_a_unit_quaternion():
    from forge_chrono import _rotation_to_quaternion

    for axis, deg in (((0, 0, 1), 30.0), ((1, 0, 0), 179.0), ((0, 1, 0), -120.0), ((1, 1, 1), 250.0), ((0, 0, 1), 179.0)):
        t = Transform.from_quantities(axis=axis, angle=Quantity(deg, "degree"))
        w, x, y, z = _rotation_to_quaternion(t.rotation)
        # rebuild the matrix from the quaternion and compare
        r = ((1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
             (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
             (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)))
        assert w >= 0 and w * w + x * x + y * y + z * z == pytest.approx(1.0)
        for i in range(3):
            assert r[i] == pytest.approx(t.rotation[i], abs=1e-12)


def test_multibody_declarations_fail_closed():
    model = pendulum()
    with pytest.raises(AssemblyRefusal, match="never estimated"):
        MultibodyModel(model.assembly, "frame", (), model.gravity)
    with pytest.raises(AssemblyRefusal, match="source reference"):
        GravityDeclaration((Quantity(0, "m/s^2"),) * 3, "")
    with pytest.raises(AssemblyRefusal, match="not a physical inertia"):
        MassProperties("bob", Quantity(1, "kg"), (m(0),) * 3, ((Quantity(1, "kg*m^2"), Quantity(0, "kg*m^2"), Quantity(0, "kg*m^2")),
                                                               (Quantity(0, "kg*m^2"), Quantity(1, "kg*m^2"), Quantity(0, "kg*m^2")),
                                                               (Quantity(0, "kg*m^2"), Quantity(0, "kg*m^2"), Quantity(3, "kg*m^2"))), "src", ("bob", "1"))
    with pytest.raises(AssemblyRefusal, match="the ground does not move"):
        MultibodyModel(model.assembly, "bob", model.mass_properties, model.gravity)
    with pytest.raises(AssemblyRefusal, match="integer number of steps"):
        MultibodyRequest(model, Quantity(1.0, "s"), Quantity(0.3, "s"), ("body:bob.position_x",))
    with pytest.raises(AssemblyRefusal, match="unknown output"):
        MultibodyRequest(model, Quantity(1.0, "s"), Quantity(0.1, "s"), ("body:frame.position_x",))


def test_joint_points_limits_and_definition_binding_fail_closed():
    import dataclasses

    from forge_chrono import translation_plan

    model = pendulum()
    asm = model.assembly
    frame_pivot = next(p for p in asm.points if p.point_id == "frame.pivot")
    moved = dataclasses.replace(asm, points=(frame_pivot, ConnectionPoint("bob.pivot", "bob", Transform.from_quantities((m(0), m(0), m(0.5))))))
    with pytest.raises(AssemblyRefusal, match="never at one of them"):
        MultibodyModel(moved, "frame", model.mass_properties, model.gravity)
    limited = dataclasses.replace(asm, joints=(dataclasses.replace(asm.joints[0], lower=Quantity(-1, "rad"), upper=Quantity(1, "rad")),))
    with pytest.raises(ProviderRefusal, match="limits"):
        translation_plan(request(MultibodyModel(limited, "frame", model.mass_properties, model.gravity)))
    wrong = dataclasses.replace(model.mass_properties[0], definition=("bob", "2"))
    with pytest.raises(AssemblyRefusal, match="brings its own mass properties"):
        MultibodyModel(asm, "frame", (wrong,), model.gravity)


def test_a_same_named_package_is_not_project_chrono(monkeypatch):
    import forge_chrono.descriptor as d

    impostor = types.ModuleType("pychrono")
    impostor.Timer = object  # the PyPI 'pychrono' timing library exposes timing helpers, not ChSystemNSC
    assert "not Project Chrono" in d.identity_problem(impostor, "1.1.0")
    monkeypatch.setitem(sys.modules, "pychrono", impostor)
    monkeypatch.setattr(d, "conda_record", lambda prefix=None: None)  # a pip install: no conda record
    monkeypatch.setattr(d, "python_package_probe", lambda *a, **k: (lambda: ProviderStatus(
        d.CAPABILITY, Availability.AVAILABLE, "1.1.0", "e" * 64, "/site-packages/pychrono")))
    status = d.probe()
    assert not status.available and status.found_but_refused
    assert assess_health(status).health is ProviderHealth.BROKEN
    real_like = types.SimpleNamespace(**{s: object for s in d.IDENTITY_SYMBOLS})
    assert "outside the supported API major version" in d.identity_problem(real_like, "9.0.1")
    assert d.identity_problem(real_like, "10.0.0") == ""


def _fake_env(tmp_path, *, lib_bytes=b"libchrono-v10"):
    """A conda prefix with pychrono + chrono records whose paths_data hash the files on disk."""
    import hashlib
    import json

    prefix = tmp_path / "env"
    (prefix / "conda-meta").mkdir(parents=True)
    pkg = prefix / "lib" / "python3.12" / "site-packages" / "pychrono"
    pkg.mkdir(parents=True)
    files = {"lib/python3.12/site-packages/pychrono/__init__.py": b"", "lib/python3.12/site-packages/pychrono/_core.so": b"core-v10"}
    for rel, data in files.items():
        (prefix / rel).write_bytes(data)
    (prefix / "lib" / "libChrono_core.so").write_bytes(lib_bytes)

    def rec(name, fmap):
        return {"name": name, "version": "10.0.0", "build": "b0", "sha256": "f" * 64, "files": sorted(fmap),
                "paths_data": {"paths": [{"_path": k, "sha256": hashlib.sha256(v).hexdigest()} for k, v in sorted(fmap.items())]}}

    (prefix / "conda-meta" / "pychrono-10.0.0-b0.json").write_text(json.dumps(rec("pychrono", files)))
    (prefix / "conda-meta" / "chrono-10.0.0-b0.json").write_text(json.dumps(rec("chrono", {"lib/libChrono_core.so": lib_bytes})))
    return prefix, pkg


def _real_like():
    import forge_chrono.descriptor as d

    mod = types.ModuleType("pychrono")
    for s in d.IDENTITY_SYMBOLS:
        setattr(mod, s, object)
    return mod


def test_conda_identity_binds_record_bytes_and_location(tmp_path, monkeypatch):
    import importlib.machinery

    import forge_chrono.descriptor as d

    prefix, pkg = _fake_env(tmp_path)
    monkeypatch.setattr(d.importlib.machinery.PathFinder, "find_spec",
                        classmethod(lambda cls, name, *a: importlib.machinery.ModuleSpec("pychrono", None, origin=str(pkg / "__init__.py"))))
    version, digest, location, deps = d._conda_identity(d.conda_record(str(prefix)), str(prefix))
    assert version == "10.0.0" and deps[0][0] == d.CONDA_ENVIRONMENT and location == str(pkg)
    # an in-place change of a loaded shared library is refused, not re-labelled
    (prefix / "lib" / "libChrono_core.so").write_bytes(b"patched")
    with pytest.raises(d._Refused, match="does not have the bytes"):
        d._conda_identity(d.conda_record(str(prefix)), str(prefix))
    (prefix / "lib" / "libChrono_core.so").write_bytes(b"libchrono-v10")
    (pkg / "_core.so").write_bytes(b"pip-overwrite")
    with pytest.raises(d._Refused, match="does not have the bytes"):
        d._conda_identity(d.conda_record(str(prefix)), str(prefix))
    (pkg / "_core.so").write_bytes(b"core-v10")
    # a module on the path outside the record's files is not the recorded package
    elsewhere = tmp_path / "checkout" / "pychrono"
    elsewhere.mkdir(parents=True)
    (elsewhere / "__init__.py").write_text("")
    monkeypatch.setattr(d.importlib.machinery.PathFinder, "find_spec",
                        classmethod(lambda cls, name, *a: importlib.machinery.ModuleSpec("pychrono", None, origin=str(elsewhere / "__init__.py"))))
    with pytest.raises(d._Refused, match="is not a file of the conda package"):
        d._conda_identity(d.conda_record(str(prefix)), str(prefix))
    # two records naming pychrono: which one is installed would be a guess
    (prefix / "conda-meta" / "pychrono-10.0.1-b0.json").write_text((prefix / "conda-meta" / "pychrono-10.0.0-b0.json").read_text())
    with pytest.raises(d._Refused, match="would be a guess"):
        d.conda_record(str(prefix))


def test_the_loaded_build_is_pinned_at_discovery(tmp_path, monkeypatch):
    import forge_chrono.descriptor as d

    prefix, pkg = _fake_env(tmp_path)
    rec = d.conda_record(str(prefix))
    monkeypatch.setattr(d, "_LOADED_UNDER", [])
    monkeypatch.setattr(d, "_conda_identity", lambda r, p: ("10.0.0", "1" * 64, str(pkg), ()))
    # a pychrono already in memory before any discovery: which build it is, is not established
    monkeypatch.setitem(sys.modules, "pychrono", _real_like())
    early = d._conda_probe(rec, str(prefix))
    assert not early.available and "imported before discovery" in early.reason and early.found_but_refused
    # discovery imports and pins
    monkeypatch.delitem(sys.modules, "pychrono")
    mod = _real_like()
    mod.__file__ = str(pkg / "__init__.py")
    monkeypatch.setitem(sys.modules, "pychrono", mod)
    monkeypatch.setattr(d, "_LOADED_UNDER", [("10.0.0", "1" * 64)])
    assert d._conda_probe(rec, str(prefix)).available
    # the files on disk change to another build: this process still runs the first one, so it is refused
    monkeypatch.setattr(d, "_conda_identity", lambda r, p: ("10.0.0", "2" * 64, str(pkg), ()))
    changed = d._conda_probe(rec, str(prefix))
    assert not changed.available and "only a new process runs it" in changed.reason
    # the module in memory came from another place than the discovered location
    monkeypatch.setattr(d, "_conda_identity", lambda r, p: ("10.0.0", "1" * 64, str(tmp_path), ()))
    moved = d._conda_probe(rec, str(prefix))
    assert not moved.available and "was loaded from" in moved.reason


def test_execution_rediscovers_and_refuses_a_changed_identity(monkeypatch):
    import forge_chrono.descriptor as d
    from forge_chrono import ChronoProvider

    discovered = ProviderStatus(d.CAPABILITY, Availability.AVAILABLE, "10.0.0", "1" * 64, "/nowhere")
    monkeypatch.setattr(d, "probe", lambda: ProviderStatus(d.CAPABILITY, Availability.AVAILABLE, "10.0.0", "2" * 64, "/nowhere"))
    with pytest.raises(ProviderRefusal, match="changed since discovery"):
        ChronoProvider(discovered).execute(request(pendulum()))
    monkeypatch.setattr(d, "probe", lambda: ProviderStatus(d.CAPABILITY, Availability.UNAVAILABLE, reason="python module 'pychrono' is not installed"))
    with pytest.raises(ProviderRefusal, match="changed since discovery"):
        ChronoProvider(discovered).execute(request(pendulum()))


def test_the_adapter_version_binds_its_source_and_routes_bind_their_request():
    from forge_chrono import ADAPTER_VERSION
    from forge_chrono.routes import declared_routes, pendulum_request

    assert ADAPTER_VERSION.startswith("0.3.0+src.") and len(ADAPTER_VERSION) == len("0.3.0+src.") + 16
    routes = declared_routes()
    assert len({r.digest for r in routes}) == len(routes) == 2
    assert all(len(r.scope) == 1 and r.scope[0].endswith(r.route_id.rpartition(".")[2]) for r in routes)
    assert routes[0].relative_tolerance == 1e-5 and "budget" in routes[0].tolerance_basis
    from engcore.providers.identity import content_digest

    assert routes[0].problem_digest == content_digest(pendulum_request(solver="sparse_qr").to_dict())


def test_unavailable_chrono_refuses_rather_than_synthesizing():
    from forge_chrono import ChronoProvider
    from forge_chrono.descriptor import CAPABILITY

    provider = ChronoProvider(ProviderStatus(CAPABILITY, Availability.UNAVAILABLE, reason="python module 'pychrono' is not installed"))
    with pytest.raises(ProviderRefusal, match="no trajectory is synthesized"):
        provider.execute(request(pendulum()))


def _chrono_status():
    from engcore.providers import ProviderRegistry

    import forge_chrono.descriptor as d

    reg = ProviderRegistry()
    d.register(reg)
    return reg.status("chrono")


@pytest.mark.skipif(not _chrono_status().available, reason="Project Chrono unavailable")
@pytest.mark.parametrize("solver", ["sparse_qr", "sparse_lu"])
def test_pendulum_period_matches_the_analytic_reference(solver):  # pragma: no cover - needs Project Chrono
    """The adapter's declared reference ROUTE on the discovered build: a check of the translation, not validation.

    Also checks the revolute joint's length drift to 1e-6 m, which the route's period alone would not see."""
    import numpy as np

    from engcore.providers.qualification import RouteOutcome
    from forge_chrono import ChronoProvider
    from forge_chrono.routes import pendulum_request, run_pendulum_route

    status = _chrono_status()
    run = run_pendulum_route(status, solver)
    assert run.outcome is RouteOutcome.PASSED, run.to_dict()
    assert run.provider_version == status.version and run.provider_digest == status.digest
    rec = ChronoProvider(status).execute(pendulum_request(solver=solver))
    x = np.array(rec.series_for("body:bob.position_x").values)
    z = np.array(rec.series_for("body:bob.position_z").values)
    assert float(np.max(np.abs(np.hypot(x, z) - 1.0))) < 1e-6
