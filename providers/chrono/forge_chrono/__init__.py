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

STATUS: the PyChrono calls in stage 2 follow the Chrono 9 Python API and have
NOT been executed in the environment that built this adapter (no Project
Chrono there).  Until the pendulum reference test in this distribution's
suite runs green against a real install, every output is
UNVERIFIED-TRANSLATION as well as "provider computation, not evidence".
"""

from __future__ import annotations

import math
from typing import Any

from engcore.providers import ProviderExecutionIdentity, ProviderExecutionRecord, ProviderRefusal, ProviderStatus, QuantitySeries, failed
from engcore.providers.identity import content_digest
from engcore.scientific.units.quantity import Quantity
from engcore.systems.multibody import MultibodyRequest

ADAPTER_ID = "forge_chrono"
ADAPTER_VERSION = "0.1.0"
TRANSLATION_STATUS = "unverified_against_running_provider"
REQUIRED_SOLVER_OPTIONS = ("timestepper",)
SUPPORTED_TIMESTEPPERS = ("euler_implicit_linearized", "hht")


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


def translation_plan(request: MultibodyRequest) -> dict[str, Any]:
    """The canonical plan a Chrono run executes.  Refuses undeclared integration settings."""
    if not isinstance(request, MultibodyRequest):
        raise ProviderRefusal("translation needs a MultibodyRequest")
    opts = dict(request.solver_options)
    missing = [k for k in REQUIRED_SOLVER_OPTIONS if k not in opts]
    if missing:
        raise ProviderRefusal(f"solver options {missing} are required; the provider's defaults are never used silently")
    if opts["timestepper"] not in SUPPORTED_TIMESTEPPERS:
        raise ProviderRefusal(f"timestepper {opts['timestepper']!r} is not one of {SUPPORTED_TIMESTEPPERS}")
    model = request.model
    asm = model.assembly
    mp = {m.instance_id: m for m in model.mass_properties}
    bodies = []
    for iid in sorted({model.ground, *model.moving_instances()}):
        pose = asm.world_transform(iid)
        entry: dict[str, Any] = {"instance_id": iid, "fixed": iid == model.ground, "rotation": [list(r) for r in pose.rotation]}
        if iid in mp:
            c = mp[iid].canonical()
            entry.update(position_m=list(pose.apply(c["com_m"])), mass_kg=c["mass_kg"], inertia_kg_m2=c["inertia_kg_m2"])
        else:
            entry.update(position_m=list(pose.translation_m))
        bodies.append(entry)
    pmap = {p.point_id: p for p in asm.points}
    joints = []
    for j in asm.joints:
        frame = asm.point_world(j.parent_point)
        axis = frame.rotate(j.axis) if j.axis is not None else (0.0, 0.0, 1.0)
        joints.append({"joint_id": j.joint_id, "kind": j.kind.value, "parent": pmap[j.parent_point].instance_id,
                       "child": pmap[j.child_point].instance_id, "origin_m": list(frame.translation_m),
                       "frame_quaternion": list(_axis_to_quaternion(tuple(axis))),
                       "lower": None if j.lower is None else j.lower.magnitude, "upper": None if j.upper is None else j.upper.magnitude})
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
        from engcore.providers import require_library_unchanged

        require_library_unchanged(self.status, "pychrono")
        import pychrono as chrono

        from .descriptor import identity_problem

        problem = identity_problem(chrono)
        if problem:
            raise ProviderRefusal(problem)
        plan = translation_plan(request)
        ident = self.identity(request)
        try:
            series = _run(chrono, plan)
        except Exception as exc:  # noqa: BLE001 - a provider failure is a failed record, never partial outputs
            return failed(ident, f"Chrono run failed: {type(exc).__name__}: {exc}", artifacts={"plan.json": content_digest(plan)})
        return ProviderExecutionRecord(ident, True, f"integrated {plan['steps']} steps ({TRANSLATION_STATUS})", series=tuple(series),
                                       artifacts={"plan.json": str(plan)}, metrics={"steps": plan["steps"]})


def _run(chrono, plan: dict[str, Any]) -> list[QuantitySeries]:  # pragma: no cover - requires Project Chrono
    system = chrono.ChSystemNSC()
    system.SetGravitationalAcceleration(chrono.ChVector3d(*plan["gravity_m_s2"]))
    if plan["solver_options"]["timestepper"] == "hht":
        system.SetTimestepperType(chrono.ChTimestepper.Type_HHT)
    else:
        system.SetTimestepperType(chrono.ChTimestepper.Type_EULER_IMPLICIT_LINEARIZED)
    bodies = {}
    for b in plan["bodies"]:
        body = chrono.ChBody()
        body.SetFixed(bool(b["fixed"]))
        body.SetPos(chrono.ChVector3d(*b["position_m"]))
        r = b["rotation"]
        m33 = chrono.ChMatrix33d()
        for i in range(3):
            for k in range(3):
                m33.SetItem(i, k, r[i][k])
        body.SetRot(m33.GetQuaternion())
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
    if plan["actuators"]:
        raise ProviderRefusal("actuated Chrono runs are not translated yet; passive dynamics only in this adapter version")
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


def reference_pendulum_period(length: Quantity, gravity: Quantity) -> Quantity:
    """Small-amplitude period of a point-mass pendulum, 2*pi*sqrt(L/g): the qualification route's analytic reference."""
    L, g = length.magnitude_in("m"), gravity.magnitude_in("m/s^2")
    if not (L > 0 and g > 0):
        raise ProviderRefusal("pendulum reference needs positive length and gravity")
    return Quantity(2 * math.pi * math.sqrt(L / g), "s")


__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "ChronoProvider", "TRANSLATION_STATUS", "reference_pendulum_period", "translation_plan"]
