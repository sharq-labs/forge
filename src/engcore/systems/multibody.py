"""Provider-neutral multibody declaration derived from an :class:`~.assembly.AssemblyTopology`.

Bodies, joints and frames come from the assembly (one mechanical hierarchy);
this module adds only what dynamics needs and the assembly does not declare:

* mass properties per moving instance (mass, centre of mass, inertia tensor),
  each with a source reference -- never estimated from geometry silently;
* a gravity declaration -- there is no default 9.81 m/s^2;
* actuators on declared joints with piecewise-constant input profiles;
* the ground instance (the fixed reference body).

A :class:`MultibodyModel` is a declaration a provider (Project Chrono, or any
other) translates.  Its digest binds the assembly digest, so a component swap
is a different model.  Running it produces a numerical trajectory of THIS
declaration; it is not evidence of how the physical product moves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping

from ..scenarios.timeline import canonical_digest
from ..scientific.units.quantity import Quantity, dimensionality
from .assembly import AssemblyRefusal, AssemblyTopology, JointKind

MULTIBODY_MODEL_SCHEMA = "engcore.systems.multibody_model/1"


def _q(value: Quantity, unit: str, label: str) -> float:
    if not isinstance(value, Quantity) or value.dimensionality != dimensionality(unit):
        raise AssemblyRefusal(f"{label} must be a Quantity in a unit of {unit}")
    v = value.magnitude_in(unit)
    if not math.isfinite(v):
        raise AssemblyRefusal(f"{label} must be finite")
    return v


def _ref(value: str, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AssemblyRefusal(f"{label} needs a source reference; an unsourced value is never admitted")
    return text


@dataclass(frozen=True)
class MassProperties:
    """Mass, centre of mass (instance frame) and inertia about the centre of mass (instance axes).

    Bound to the component DEFINITION (id, version) it was sourced for: after a
    slot swap the old component's mass properties do not describe the new one.
    """

    instance_id: str
    mass: Quantity
    center_of_mass: tuple[Quantity, Quantity, Quantity]
    inertia: tuple[tuple[Quantity, ...], ...]
    source_ref: str
    definition: tuple[str, str]

    def __post_init__(self) -> None:
        if not str(self.instance_id).strip():
            raise AssemblyRefusal("mass properties name an instance")
        m = _q(self.mass, "kg", f"{self.instance_id} mass")
        if not m > 0:
            raise AssemblyRefusal(f"{self.instance_id}: mass must be > 0 kg")
        if len(self.center_of_mass) != 3:
            raise AssemblyRefusal("centre of mass has three length components")
        com = tuple(_q(c, "m", "centre of mass") for c in self.center_of_mass)
        rows = tuple(tuple(self.inertia))
        if len(rows) != 3 or any(len(r) != 3 for r in rows):
            raise AssemblyRefusal("inertia is a 3x3 tensor of kg*m^2 Quantities")
        j = tuple(tuple(_q(v, "kg*m^2", "inertia") for v in r) for r in rows)
        if any(abs(j[a][b] - j[b][a]) > 1e-12 * max(1.0, abs(j[a][b])) for a in range(3) for b in range(3)):
            raise AssemblyRefusal(f"{self.instance_id}: inertia tensor is not symmetric")
        d = (j[0][0], j[1][1], j[2][2])
        if any(v <= 0 for v in d) or d[0] + d[1] < d[2] or d[1] + d[2] < d[0] or d[0] + d[2] < d[1]:
            raise AssemblyRefusal(f"{self.instance_id}: principal moments violate positivity/triangle inequality; not a physical inertia")
        object.__setattr__(self, "source_ref", _ref(self.source_ref, f"{self.instance_id} mass properties"))
        d = tuple(str(x).strip() for x in self.definition)
        if len(d) != 2 or not all(d):
            raise AssemblyRefusal(f"{self.instance_id}: mass properties name the component definition (id, version) they describe")
        object.__setattr__(self, "definition", d)
        object.__setattr__(self, "_canonical", {"mass_kg": m, "com_m": list(com), "inertia_kg_m2": [list(r) for r in j]})

    def canonical(self) -> dict[str, Any]:
        return dict(self._canonical)  # type: ignore[attr-defined]

    def to_dict(self) -> dict[str, Any]:
        return {"instance_id": self.instance_id, "definition": list(self.definition), **self.canonical(), "source_ref": self.source_ref}


@dataclass(frozen=True)
class GravityDeclaration:
    """The body-force field.  Declared with its source (a scenario/environment record), never defaulted."""

    vector: tuple[Quantity, Quantity, Quantity]
    source_ref: str

    def __post_init__(self) -> None:
        if len(self.vector) != 3:
            raise AssemblyRefusal("gravity has three acceleration components")
        object.__setattr__(self, "_g", tuple(_q(v, "m/s^2", "gravity") for v in self.vector))
        object.__setattr__(self, "source_ref", _ref(self.source_ref, "gravity"))

    @property
    def components_m_s2(self) -> tuple[float, float, float]:
        return self._g  # type: ignore[attr-defined]

    def to_dict(self) -> dict[str, Any]:
        return {"vector_m_s2": list(self.components_m_s2), "source_ref": self.source_ref}


class ActuationKind(str, Enum):
    TORQUE = "torque"     # revolute joint, N*m
    FORCE = "force"       # prismatic joint, N
    SPEED = "speed"       # revolute rad/s or prismatic m/s
    POSITION = "position" # revolute rad or prismatic m


_ACT_UNIT = {(ActuationKind.TORQUE, JointKind.REVOLUTE): "N*m", (ActuationKind.FORCE, JointKind.PRISMATIC): "N",
             (ActuationKind.SPEED, JointKind.REVOLUTE): "rad/s", (ActuationKind.SPEED, JointKind.PRISMATIC): "m/s",
             (ActuationKind.POSITION, JointKind.REVOLUTE): "rad", (ActuationKind.POSITION, JointKind.PRISMATIC): "m"}


@dataclass(frozen=True)
class ActuatorDeclaration:
    """A joint actuator with a piecewise-constant input profile ``((t_start, value), ...)``."""

    actuator_id: str
    joint_id: str
    kind: ActuationKind
    profile: tuple[tuple[Quantity, Quantity], ...]
    source_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ActuationKind(self.kind))
        if not self.profile:
            raise AssemblyRefusal(f"actuator {self.actuator_id!r} has no input profile; an input is never assumed")
        times = [_q(t, "s", "actuator time") for t, _ in self.profile]
        if times[0] != 0.0 or any(b <= a for a, b in zip(times, times[1:])):
            raise AssemblyRefusal(f"actuator {self.actuator_id!r} profile must start at t=0 and increase strictly")
        object.__setattr__(self, "source_ref", _ref(self.source_ref, f"actuator {self.actuator_id}"))

    def canonical(self, joint_kind: JointKind) -> list[list[float]]:
        unit = _ACT_UNIT.get((self.kind, joint_kind))
        if unit is None:
            raise AssemblyRefusal(f"actuator {self.actuator_id!r}: {self.kind.value} actuation is not defined on a {joint_kind.value} joint")
        return [[_q(t, "s", "time"), _q(v, unit, f"actuator {self.actuator_id} input")] for t, v in self.profile]

    def to_dict(self) -> dict[str, Any]:
        return {"actuator_id": self.actuator_id, "joint_id": self.joint_id, "kind": self.kind.value, "source_ref": self.source_ref,
                "profile": [[t.to_dict(), v.to_dict()] for t, v in self.profile]}


BODY_OUTPUTS = tuple(f"{q}_{c}" for q in ("position", "velocity") for c in "xyz")
SUPPORTED_JOINTS = (JointKind.FIXED, JointKind.REVOLUTE, JointKind.PRISMATIC, JointKind.SPHERICAL)


@dataclass(frozen=True)
class MultibodyModel:
    """Rigid-multibody declaration over one exact assembly variant."""

    assembly: AssemblyTopology
    ground: str
    mass_properties: tuple[MassProperties, ...]
    gravity: GravityDeclaration
    actuators: tuple[ActuatorDeclaration, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.assembly, AssemblyTopology) or not isinstance(self.gravity, GravityDeclaration):
            raise AssemblyRefusal("a multibody model needs an AssemblyTopology and a GravityDeclaration")
        pmap = {p.point_id: p for p in self.assembly.points}
        self.assembly.instance(self.ground)
        moving = {pmap[j.child_point].instance_id for j in self.assembly.joints}
        parents = {pmap[j.parent_point].instance_id for j in self.assembly.joints}
        if not self.assembly.joints:
            raise AssemblyRefusal("a multibody model needs at least one declared joint")
        if self.ground in moving:
            raise AssemblyRefusal(f"ground {self.ground!r} is the child of a joint; the ground does not move")
        for j in self.assembly.joints:
            if j.kind not in SUPPORTED_JOINTS:
                raise AssemblyRefusal(f"joint {j.joint_id!r} is {j.kind.value}; compliant connections need a declared compliance "
                                      "model, which this rigid-multibody foundation does not translate")
        mp = {}
        for m in self.mass_properties:
            if not isinstance(m, MassProperties) or m.instance_id in mp:
                raise AssemblyRefusal("mass properties must be unique MassProperties records")
            inst = self.assembly.instance(m.instance_id)
            if inst.definition_key != m.definition:
                raise AssemblyRefusal(f"mass properties of {m.instance_id!r} describe {m.definition}, but the instance is now "
                                      f"{inst.definition_key}; a swapped component brings its own mass properties")
            mp[m.instance_id] = m
        missing = sorted(moving - set(mp))
        if missing:
            raise AssemblyRefusal(f"moving bodies {missing} have no mass properties; mass is never estimated or defaulted")
        for j in self.assembly.joints:
            a, b = self.assembly.point_world(j.parent_point), self.assembly.point_world(j.child_point)
            gap = max(abs(x - y) for x, y in zip(a.translation_m, b.translation_m))
            if gap > 1e-9 * max(1.0, max(abs(v) for v in a.translation_m)):
                raise AssemblyRefusal(f"joint {j.joint_id!r}: parent and child points are {gap:.3e} m apart in the assembled pose; "
                                      "a joint is placed where both its points coincide, never at one of them")
            if j.kind is JointKind.FIXED and any(abs(x - y) > 1e-9 for ra, rb in zip(a.rotation, b.rotation) for x, y in zip(ra, rb)):
                raise AssemblyRefusal(f"fixed joint {j.joint_id!r}: point frames are not aligned in the assembled pose")
            if j.axis is not None:
                aa, ab = a.rotate(j.axis), b.rotate(j.axis)
                if max(abs(x - y) for x, y in zip(aa, ab)) > 1e-9:
                    raise AssemblyRefusal(f"joint {j.joint_id!r}: its axis differs between the parent and child point frames")
        roots = parents - moving
        if roots - {self.ground}:
            raise AssemblyRefusal(f"kinematic chain roots {sorted(roots - {self.ground})} are not the ground; floating bases are not declared")
        jmap = {j.joint_id: j for j in self.assembly.joints}
        seen = set()
        for a in self.actuators:
            if a.joint_id not in jmap:
                raise AssemblyRefusal(f"actuator {a.actuator_id!r} drives unknown joint {a.joint_id!r}")
            if a.joint_id in seen:
                raise AssemblyRefusal(f"joint {a.joint_id!r} is driven by two actuators")
            seen.add(a.joint_id)
            a.canonical(jmap[a.joint_id].kind)
        object.__setattr__(self, "mass_properties", tuple(sorted(mp.values(), key=lambda m: m.instance_id)))
        object.__setattr__(self, "actuators", tuple(sorted(self.actuators, key=lambda a: a.actuator_id)))

    def moving_instances(self) -> tuple[str, ...]:
        pmap = {p.point_id: p for p in self.assembly.points}
        return tuple(sorted({pmap[j.child_point].instance_id for j in self.assembly.joints}))

    def to_dict(self) -> dict[str, Any]:
        jmap = {j.joint_id: j for j in self.assembly.joints}
        return {"schema": MULTIBODY_MODEL_SCHEMA, "assembly_digest": self.assembly.digest, "ground": self.ground,
                "mass_properties": [m.to_dict() for m in self.mass_properties], "gravity": self.gravity.to_dict(),
                "actuators": [dict(a.to_dict(), canonical=a.canonical(jmap[a.joint_id].kind)) for a in self.actuators]}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


@dataclass(frozen=True)
class MultibodyRequest:
    """Time window, fixed step and requested outputs.

    Output ids are scalar components in the product frame:
    ``body:<id>.position_x|_y|_z``, ``body:<id>.velocity_x|_y|_z`` and
    ``joint:<id>.coordinate`` (angle in rad / displacement in m).
    """

    model: MultibodyModel
    end_time: Quantity
    step: Quantity
    outputs: tuple[str, ...]
    solver_options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        end, dt = _q(self.end_time, "s", "end time"), _q(self.step, "s", "step")
        if not (end > 0 and dt > 0 and dt <= end):
            raise AssemblyRefusal("a multibody run needs 0 < step <= end_time")
        if abs(round(end / dt) * dt - end) > 1e-9 * end:
            raise AssemblyRefusal("end_time must be an integer number of steps; a partial last step would be invented")
        if not self.outputs:
            raise AssemblyRefusal("a run states which outputs it requests")
        moving = set(self.model.moving_instances())
        joints = {j.joint_id for j in self.model.assembly.joints}
        for o in self.outputs:
            kind, _, rest = o.partition(":")
            ident, _, what = rest.rpartition(".")
            ok = (kind == "body" and ident in moving and what in BODY_OUTPUTS) or \
                 (kind == "joint" and ident in joints and what in ("coordinate", "reaction_force"))
            if not ok:
                raise AssemblyRefusal(f"unsupported or unknown output {o!r}")

    def to_dict(self) -> dict[str, Any]:
        return {"model_digest": self.model.digest, "end_time_s": _q(self.end_time, "s", "end"), "step_s": _q(self.step, "s", "step"),
                "outputs": sorted(self.outputs), "solver_options": dict(sorted(self.solver_options.items()))}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())
