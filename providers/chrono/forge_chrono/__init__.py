"""Project Chrono adapter: MultibodyModel -> canonical translation plan -> PyChrono system -> trajectories.

Two stages, kept apart on purpose:

1. :func:`translation_plan` turns a :class:`~engcore.systems.multibody.MultibodyModel`
   request into a provider-neutral, JSON-canonical plan (bodies at their
   centres of mass in the product frame, joint frames, gravity, actuator
   profiles, integration settings).  It needs no provider and is what replay
   and identity bind.
2. :class:`ChronoProvider.execute` builds a PyChrono system from that plan and
   integrates it.  It runs only when the registry status is AVAILABLE (which
   includes the API-identity check of :mod:`.descriptor`).

STATUS: stage 2 targets the Chrono 10 Python API (conda-forge ``pychrono``
10.0.0).  This adapter's declared reference route (:mod:`.routes`) checks
the translation on one point-mass pendulum; route runs and where they were
recorded are listed in ``docs/work/PROGRESS.md``.  A passed route run is
not a qualification by itself (see :mod:`engcore.providers.qualification`),
and an output is "provider computation, not evidence".

Every integration setting is declared.  Chrono's NSC default solver
(iterative PSOR) did not hold a bilateral revolute joint on the pendulum
reference (recorded in PROGRESS.md), so only the direct sparse solvers are
translated.  HHT is NOT translated: its alpha, Newton iteration limit,
tolerances and step control would be Chrono's defaults.

``ADAPTER_VERSION`` carries a digest of this adapter's source files: an edit
to the translation or to the route's measurement is a new adapter version,
so an earlier route run or qualification does not transfer to it.
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Any

from engcore.providers import ProviderExecutionIdentity, ProviderExecutionRecord, ProviderRefusal, ProviderStatus, QuantitySeries, failed
from engcore.providers.identity import content_digest
from engcore.scientific.units.quantity import Quantity
from engcore.systems.multibody import MultibodyRequest

ADAPTER_ID = "forge_chrono"


def _source_digest() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    h = hashlib.sha256()
    for name in ("__init__.py", "routes.py"):
        with open(os.path.join(here, name), "rb") as fh:
            h.update(name.encode() + b"\0" + fh.read() + b"\0")
    return h.hexdigest()


ADAPTER_VERSION = f"0.3.0+src.{_source_digest()[:16]}"
TRANSLATION_STATUS = "chrono10_translation_checked_only_by_its_declared_route"
REQUIRED_SOLVER_OPTIONS = ("timestepper", "solver")
SUPPORTED_TIMESTEPPERS = ("euler_implicit_linearized",)
SUPPORTED_SOLVERS = ("sparse_qr", "sparse_lu")


def _axis_to_quaternion(axis: tuple[float, float, float]) -> tuple[float, float, float, float]:
    """Quaternion (w, x, y, z) rotating +z onto ``axis`` (Chrono lock joints act along/about their frame's z)."""
    x, y, z = axis
    dot = max(-1.0, min(1.0, z))
    if dot > 1 - 1e-15:
        return (1.0, 0.0, 0.0, 0.0)
    if dot < -1 + 1e-15:
        return (0.0, 1.0, 0.0, 0.0)
    cx, cy, cz = -y, x, 0.0  # (0,0,1) x axis
    w = 1.0 + dot
    n = math.sqrt(w * w + cx * cx + cy * cy + cz * cz)
    return (w / n, cx / n, cy / n, cz / n)


def _rotation_to_quaternion(r) -> tuple[float, float, float, float]:
    """Unit quaternion (w, x, y, z) of a proper rotation matrix (Shepperd's method; sign fixed to w >= 0)."""
    m = [[float(v) for v in row] for row in r]
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0:
        s = 2.0 * math.sqrt(1.0 + tr)
        q = (0.25 * s, (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s)
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = 2.0 * math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2])
        q = ((m[2][1] - m[1][2]) / s, 0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s)
    elif m[1][1] > m[2][2]:
        s = 2.0 * math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2])
        q = ((m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s)
    else:
        s = 2.0 * math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1])
        q = ((m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s)
    n = math.sqrt(sum(c * c for c in q))
    q = tuple(c / n for c in q)
    return q if q[0] >= 0 else tuple(-c for c in q)


def translation_plan(request: MultibodyRequest) -> dict[str, Any]:
    """The canonical plan a Chrono run executes.  Refuses undeclared integration settings."""
    if not isinstance(request, MultibodyRequest):
        raise ProviderRefusal("translation needs a MultibodyRequest")
    opts = dict(request.solver_options)
    missing = [k for k in REQUIRED_SOLVER_OPTIONS if k not in opts]
    if missing:
        raise ProviderRefusal(f"solver options {missing} are required; the provider's defaults are never used silently")
    if opts["timestepper"] not in SUPPORTED_TIMESTEPPERS:
        raise ProviderRefusal(f"timestepper {opts['timestepper']!r} is not one of {SUPPORTED_TIMESTEPPERS} (HHT is not translated: "
                              "its parameters would be Chrono's defaults)")
    if opts["solver"] not in SUPPORTED_SOLVERS:
        raise ProviderRefusal(f"solver {opts['solver']!r} is not one of {SUPPORTED_SOLVERS} (iterative PSOR did not hold a "
                              "bilateral joint on the reference route)")
    unknown = sorted(set(opts) - set(REQUIRED_SOLVER_OPTIONS))
    if unknown:
        raise ProviderRefusal(f"solver options {unknown} are not translated by this adapter version; an option is never dropped silently")
    model = request.model
    asm = model.assembly
    mp = {m.instance_id: m for m in model.mass_properties}
    bodies = []
    for iid in sorted({model.ground, *model.moving_instances()}):
        pose = asm.world_transform(iid)
        entry: dict[str, Any] = {"instance_id": iid, "fixed": iid == model.ground, "rotation": [list(r) for r in pose.rotation],
                                 "quaternion": list(_rotation_to_quaternion(pose.rotation))}
        if iid in mp:
            c = mp[iid].canonical()
            entry.update(position_m=list(pose.apply(c["com_m"])), mass_kg=c["mass_kg"], inertia_kg_m2=c["inertia_kg_m2"])
        else:
            entry.update(position_m=list(pose.translation_m))
        bodies.append(entry)
    pmap = {p.point_id: p for p in asm.points}
    joints = []
    for j in asm.joints:
        if j.lower is not None or j.upper is not None:
            raise ProviderRefusal(f"joint {j.joint_id!r} declares limits; this adapter version does not translate joint limits, "
                                  "and a limited joint is never run as an unlimited one")
        frame = asm.point_world(j.parent_point)
        axis = frame.rotate(j.axis) if j.axis is not None else (0.0, 0.0, 1.0)
        joints.append({"joint_id": j.joint_id, "kind": j.kind.value, "parent": pmap[j.parent_point].instance_id,
                       "child": pmap[j.child_point].instance_id, "origin_m": list(frame.translation_m),
                       "frame_quaternion": list(_axis_to_quaternion(tuple(axis))),
                       "lower": None if j.lower is None else j.lower.magnitude, "upper": None if j.upper is None else j.upper.magnitude})
    if model.actuators:
        raise ProviderRefusal("actuated Chrono runs are not translated by this adapter version; passive dynamics only")
    jmap = {j.joint_id: j for j in asm.joints}
    actuators = [{"actuator_id": a.actuator_id, "joint_id": a.joint_id, "kind": a.kind.value, "profile": a.canonical(jmap[a.joint_id].kind)}
                 for a in model.actuators]
    end, dt = request.end_time.magnitude_in("s"), request.step.magnitude_in("s")
    return {"adapter": ADAPTER_ID, "adapter_version": ADAPTER_VERSION, "translation_status": TRANSLATION_STATUS,
            "model_digest": model.digest, "gravity_m_s2": list(model.gravity.components_m_s2), "bodies": bodies, "joints": joints,
            "actuators": actuators, "end_time_s": end, "step_s": dt, "steps": int(round(end / dt)), "outputs": sorted(request.outputs),
            "solver_options": dict(sorted(opts.items()))}


class ChronoProvider:
    def __init__(self, status: ProviderStatus) -> None:
        if not isinstance(status, ProviderStatus) or status.capability.provider_id != "chrono":
            raise ProviderRefusal("ChronoProvider needs the registry status of the 'chrono' provider")
        self.status = status

    def identity(self, request: MultibodyRequest) -> ProviderExecutionIdentity:
        plan = translation_plan(request)
        return ProviderExecutionIdentity.from_content(self.status, adapter_id=ADAPTER_ID, adapter_version=ADAPTER_VERSION,
                                                      problem=request.to_dict(), configuration=plan, output_request=tuple(request.outputs))

    def execute(self, request: MultibodyRequest) -> ProviderExecutionRecord:
        if not self.status.available:
            raise ProviderRefusal(f"Project Chrono is unavailable: {self.status.reason}; no trajectory is synthesized")
        from .descriptor import require_unchanged

        require_unchanged(self.status)
        import pychrono as chrono

        plan = translation_plan(request)
        ident = self.identity(request)
        try:
            series = _run(chrono, plan)
        except Exception as exc:  # noqa: BLE001 - a provider failure is a failed record, never partial outputs
            return failed(ident, f"Chrono run failed: {type(exc).__name__}: {exc}", artifacts={"plan.json": content_digest(plan)})
        return ProviderExecutionRecord(ident, True, f"integrated {plan['steps']} steps ({TRANSLATION_STATUS})", series=tuple(series),
                                       artifacts={"plan.json": content_digest(plan)}, metrics={"steps": plan["steps"]})


def _run(chrono, plan: dict[str, Any]) -> list[QuantitySeries]:  # pragma: no cover - requires Project Chrono
    system = chrono.ChSystemNSC()
    system.SetGravitationalAcceleration(chrono.ChVector3d(*plan["gravity_m_s2"]))
    system.SetTimestepperType({"euler_implicit_linearized": chrono.ChTimestepper.Type_EULER_IMPLICIT_LINEARIZED}[
        plan["solver_options"]["timestepper"]])
    system.SetSolverType({"sparse_qr": chrono.ChSolver.Type_SPARSE_QR, "sparse_lu": chrono.ChSolver.Type_SPARSE_LU}[plan["solver_options"]["solver"]])
    bodies = {}
    for b in plan["bodies"]:
        body = chrono.ChBody()
        body.SetFixed(bool(b["fixed"]))
        body.SetPos(chrono.ChVector3d(*b["position_m"]))
        body.SetRot(chrono.ChQuaterniond(*b["quaternion"]))
        if not b["fixed"]:
            body.SetMass(b["mass_kg"])
            j = b["inertia_kg_m2"]
            body.SetInertiaXX(chrono.ChVector3d(j[0][0], j[1][1], j[2][2]))
            body.SetInertiaXY(chrono.ChVector3d(j[0][1], j[0][2], j[1][2]))
        system.Add(body)
        bodies[b["instance_id"]] = body
    links = {}
    classes = {"fixed": chrono.ChLinkLockLock, "revolute": chrono.ChLinkLockRevolute, "prismatic": chrono.ChLinkLockPrismatic,
               "spherical": chrono.ChLinkLockSpherical}
    for j in plan["joints"]:
        link = classes[j["kind"]]()
        frame = chrono.ChFramed(chrono.ChVector3d(*j["origin_m"]), chrono.ChQuaterniond(*j["frame_quaternion"]))
        link.Initialize(bodies[j["child"]], bodies[j["parent"]], frame)
        system.Add(link)
        links[j["joint_id"]] = (link, j)
    out: dict[str, list[float]] = {o: [] for o in plan["outputs"]}
    times: list[float] = []
    dt = plan["step_s"]

    def sample(t: float) -> None:
        times.append(t)
        for o in plan["outputs"]:
            kind, _, rest = o.partition(":")
            ident, _, what = rest.rpartition(".")
            if kind == "body":
                quantity, _, comp = what.partition("_")
                v = bodies[ident].GetPos() if quantity == "position" else bodies[ident].GetPosDt()
                out[o].append(float(getattr(v, comp)))
            else:
                raise ProviderRefusal(f"output {o!r} is not translated in this adapter version")
    sample(0.0)
    for k in range(plan["steps"]):
        system.DoStepDynamics(dt)
        sample((k + 1) * dt)
    unit = {"position": "m", "velocity": "m/s"}
    return [QuantitySeries(o, unit[o.rpartition(".")[2].partition("_")[0]], tuple(times), tuple(v)) for o, v in out.items()]


def reference_pendulum_period(length: Quantity, gravity: Quantity, amplitude: Quantity | None = None) -> Quantity:
    """Period of a point-mass pendulum: 2*pi*sqrt(L/g), times the finite-amplitude series
    1 + a^2/16 + 11 a^4/3072 when ``amplitude`` is given (truncation < 1e-7 relative below 10 deg).
    The qualification route's analytic reference."""
    L, g = length.magnitude_in("m"), gravity.magnitude_in("m/s^2")
    if not (L > 0 and g > 0):
        raise ProviderRefusal("pendulum reference needs positive length and gravity")
    factor = 1.0
    if amplitude is not None:
        a = amplitude.magnitude_in("rad")
        if not 0 < abs(a) <= math.radians(10):
            raise ProviderRefusal("the series reference is used only for 0 < amplitude <= 10 deg")
        factor = 1 + a * a / 16 + 11 * a ** 4 / 3072
    return Quantity(2 * math.pi * math.sqrt(L / g) * factor, "s")


__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "ChronoProvider", "TRANSLATION_STATUS", "reference_pendulum_period", "translation_plan"]
