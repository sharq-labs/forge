"""Generic product/assembly topology layered on :class:`~.topology.SystemDefinition`.

``SystemDefinition`` already owns the component hierarchy (``parent_id``),
component identity (definition id/version + Scientific Twin reference), ports
and connections.  This module adds what an engineered PRODUCT needs on top of
that hierarchy, without creating a second one:

* the composition level of every instance (system / subsystem / assembly /
  component / part) and the rule that levels deepen down the tree;
* placements (rigid transforms of each instance frame in its parent's frame);
* connection points and joint declarations (fixed, revolute, prismatic,
  spherical, compliant placeholder) -- the structural readiness for
  multibody dynamics, not a dynamics engine;
* physical interfaces (mechanical / thermal / electrical / fluid / signal);
* geometry, material and state ownership;
* replaceable slots, so a component can be swapped and the assembly obtains a
  new, traceable variant identity.

Nothing here is evidence.  A joint declaration says what a designer intends to
connect; it does not assert stiffness, friction, strength or that the joint
exists.  A compliant joint must name the record that will carry its
compliance model; there is no default stiffness.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import math
from typing import Any, Iterable, Mapping

from ..materials.identity import MaterialIdentity
from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.twins import TwinReference
from ..scientific.units.quantity import Quantity, dimensionality
from ..spatial.geometry import GeometryModel, Transform
from .topology import ComponentDefinition, ComponentInstance, SystemDefinition

ASSEMBLY_TOPOLOGY_SCHEMA = "engcore.systems.assembly_topology/1"
JOINT_SCHEMA = "engcore.systems.joint_declaration/1"


class AssemblyRefusal(InvalidScientificProblem):
    """An assembly declaration that cannot be honoured without inventing something."""


def _text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AssemblyRefusal(f"{label} must be non-empty")
    return text


class CompositionLevel(str, Enum):
    SYSTEM = "system"
    SUBSYSTEM = "subsystem"
    ASSEMBLY = "assembly"
    COMPONENT = "component"
    PART = "part"

    @property
    def depth(self) -> int:
        return _DEPTH[self]


_DEPTH = {CompositionLevel.SYSTEM: 0, CompositionLevel.SUBSYSTEM: 1, CompositionLevel.ASSEMBLY: 2,
          CompositionLevel.COMPONENT: 3, CompositionLevel.PART: 4}


@dataclass(frozen=True, order=True)
class InstanceLevel:
    instance_id: str
    level: CompositionLevel

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", _text(self.instance_id, "instance_id"))
        object.__setattr__(self, "level", CompositionLevel(self.level))

    def to_dict(self) -> dict[str, Any]:
        return {"instance_id": self.instance_id, "level": self.level.value}


@dataclass(frozen=True)
class Placement:
    """Pose of an instance's frame in its PARENT instance's frame (the root instance's frame is the product frame)."""

    instance_id: str
    transform: Transform

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", _text(self.instance_id, "placement instance_id"))
        if not isinstance(self.transform, Transform):
            raise AssemblyRefusal("placement requires a Transform")

    def to_dict(self) -> dict[str, Any]:
        return {"instance_id": self.instance_id, "transform": self.transform.to_dict()}


@dataclass(frozen=True)
class ConnectionPoint:
    """A named frame on an instance where something connects.  Optionally tied to a geometry entity."""

    point_id: str
    instance_id: str
    local: Transform = field(default_factory=Transform)
    geometry_entity: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "point_id", _text(self.point_id, "point_id"))
        object.__setattr__(self, "instance_id", _text(self.instance_id, "connection point instance"))
        object.__setattr__(self, "geometry_entity", str(self.geometry_entity or "").strip())

    def to_dict(self) -> dict[str, Any]:
        return {"point_id": self.point_id, "instance_id": self.instance_id, "local": self.local.to_dict(), "geometry_entity": self.geometry_entity}


class JointKind(str, Enum):
    FIXED = "fixed"
    REVOLUTE = "revolute"
    PRISMATIC = "prismatic"
    SPHERICAL = "spherical"
    COMPLIANT = "compliant"   # placeholder: an elastic connection whose model is named, never assumed


#: Relative degrees of freedom each ideal joint leaves.  COMPLIANT is None: it is not an ideal constraint.
JOINT_DOF: dict[JointKind, int | None] = {JointKind.FIXED: 0, JointKind.REVOLUTE: 1, JointKind.PRISMATIC: 1,
                                          JointKind.SPHERICAL: 3, JointKind.COMPLIANT: None}


@dataclass(frozen=True)
class JointDeclaration:
    """A declared connection of a child point to a parent point.  Declaration, not a mechanical claim.

    ``axis`` (unit vector in the parent point's frame) is required for revolute
    and prismatic joints.  Limits are optional; when given they must be angles
    (revolute) or lengths (prismatic).  A compliant joint must name the record
    carrying its compliance model in ``compliance_ref``.
    """

    joint_id: str
    kind: JointKind
    parent_point: str
    child_point: str
    axis: tuple[float, float, float] | None = None
    lower: Quantity | None = None
    upper: Quantity | None = None
    compliance_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "joint_id", _text(self.joint_id, "joint_id"))
        kind = JointKind(self.kind)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "parent_point", _text(self.parent_point, "joint parent point"))
        object.__setattr__(self, "child_point", _text(self.child_point, "joint child point"))
        if self.parent_point == self.child_point:
            raise AssemblyRefusal(f"joint {self.joint_id!r} connects a point to itself")
        if kind in (JointKind.REVOLUTE, JointKind.PRISMATIC):
            if self.axis is None:
                raise AssemblyRefusal(f"{kind.value} joint {self.joint_id!r} needs an axis; none is assumed")
            ax = tuple(float(v) for v in self.axis)
            n = math.sqrt(sum(v * v for v in ax))
            if len(ax) != 3 or not math.isfinite(n) or abs(n - 1.0) > 1e-9:
                raise AssemblyRefusal(f"joint {self.joint_id!r} axis must be a unit 3-vector")
            object.__setattr__(self, "axis", ax)
        elif self.axis is not None:
            raise AssemblyRefusal(f"{kind.value} joint {self.joint_id!r} takes no axis")
        unit = {JointKind.REVOLUTE: "rad", JointKind.PRISMATIC: "m"}.get(kind)
        for label in ("lower", "upper"):
            q = getattr(self, label)
            if q is None:
                continue
            if unit is None:
                raise AssemblyRefusal(f"{kind.value} joint {self.joint_id!r} takes no {label} limit")
            if not isinstance(q, Quantity) or q.dimensionality != dimensionality(unit):
                raise AssemblyRefusal(f"joint {self.joint_id!r} {label} limit must be a Quantity of the joint coordinate ({unit})")
            object.__setattr__(self, label, q.to(unit))
        if self.lower is not None and self.upper is not None and not self.upper.magnitude > self.lower.magnitude:
            raise AssemblyRefusal(f"joint {self.joint_id!r} needs upper > lower")
        ref = str(self.compliance_ref or "").strip()
        if kind is JointKind.COMPLIANT and not ref:
            raise AssemblyRefusal(f"compliant joint {self.joint_id!r} names no compliance model; stiffness is never defaulted")
        if kind is not JointKind.COMPLIANT and ref:
            raise AssemblyRefusal(f"only a compliant joint carries a compliance_ref ({self.joint_id!r})")
        object.__setattr__(self, "compliance_ref", ref)

    @property
    def dof(self) -> int | None:
        return JOINT_DOF[self.kind]

    def to_dict(self) -> dict[str, Any]:
        return {"schema": JOINT_SCHEMA, "joint_id": self.joint_id, "kind": self.kind.value, "parent_point": self.parent_point, "child_point": self.child_point,
                "axis": None if self.axis is None else list(self.axis),
                "lower": None if self.lower is None else self.lower.to_dict(), "upper": None if self.upper is None else self.upper.to_dict(),
                "compliance_ref": self.compliance_ref}

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "JointDeclaration":
        if p.get("schema") != JOINT_SCHEMA:
            raise AssemblyRefusal("unsupported joint declaration schema")
        return cls(p["joint_id"], JointKind(p["kind"]), p["parent_point"], p["child_point"],
                   None if p.get("axis") is None else tuple(p["axis"]),
                   None if p.get("lower") is None else Quantity.from_dict(p["lower"]),
                   None if p.get("upper") is None else Quantity.from_dict(p["upper"]), p.get("compliance_ref", ""))


class InterfaceKind(str, Enum):
    MECHANICAL = "mechanical"
    THERMAL = "thermal"
    ELECTRICAL = "electrical"
    FLUID = "fluid"
    SIGNAL = "signal"


@dataclass(frozen=True)
class InterfaceDeclaration:
    """A physical interface between two connection points.  Its physics lives in a domain model, not here."""

    interface_id: str
    kind: InterfaceKind
    point_a: str
    point_b: str
    geometry_entity: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "interface_id", _text(self.interface_id, "interface_id"))
        object.__setattr__(self, "kind", InterfaceKind(self.kind))
        a, b = sorted((_text(self.point_a, "interface point"), _text(self.point_b, "interface point")))
        if a == b:
            raise AssemblyRefusal(f"interface {self.interface_id!r} joins a point to itself")
        object.__setattr__(self, "point_a", a)
        object.__setattr__(self, "point_b", b)

    def to_dict(self) -> dict[str, Any]:
        return {"interface_id": self.interface_id, "kind": self.kind.value, "point_a": self.point_a, "point_b": self.point_b,
                "geometry_entity": self.geometry_entity}


@dataclass(frozen=True)
class GeometryOwnership:
    """Which bodies of which exact geometry an instance owns."""

    instance_id: str
    geometry_digest: str
    body_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", _text(self.instance_id, "geometry owner"))
        object.__setattr__(self, "geometry_digest", _text(self.geometry_digest, "geometry digest"))
        b = tuple(sorted(_text(x, "owned body") for x in self.body_ids))
        if not b or len(set(b)) != len(b):
            raise AssemblyRefusal(f"instance {self.instance_id!r} must own unique bodies")
        object.__setattr__(self, "body_ids", b)

    def to_dict(self) -> dict[str, Any]:
        return {"instance_id": self.instance_id, "geometry_digest": self.geometry_digest, "body_ids": list(self.body_ids)}


@dataclass(frozen=True)
class MaterialOwnership:
    instance_id: str
    material: MaterialIdentity

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", _text(self.instance_id, "material owner"))
        if not isinstance(self.material, MaterialIdentity):
            raise AssemblyRefusal("material ownership names an exact MaterialIdentity")

    def to_dict(self) -> dict[str, Any]:
        return {"instance_id": self.instance_id, "material_digest": self.material.digest, "material": self.material.to_dict()}


@dataclass(frozen=True, order=True)
class StateOwnership:
    """Exactly one instance owns each state variable (one authority per state)."""

    state_id: str
    instance_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "state_id", _text(self.state_id, "state_id"))
        object.__setattr__(self, "instance_id", _text(self.instance_id, "state owner"))

    def to_dict(self) -> dict[str, Any]:
        return {"state_id": self.state_id, "instance_id": self.instance_id}


@dataclass(frozen=True)
class ReplaceableSlot:
    """An instance that may be swapped for another declared definition with the same connection contract."""

    slot_id: str
    instance_id: str
    allowed_definitions: tuple[tuple[str, str], ...]
    required_points: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "slot_id", _text(self.slot_id, "slot_id"))
        object.__setattr__(self, "instance_id", _text(self.instance_id, "slot instance"))
        allowed = tuple(sorted({(str(a), str(b)) for a, b in self.allowed_definitions}))
        if not allowed:
            raise AssemblyRefusal(f"slot {self.slot_id!r} allows no definition")
        object.__setattr__(self, "allowed_definitions", allowed)
        object.__setattr__(self, "required_points", tuple(sorted(set(self.required_points))))

    def to_dict(self) -> dict[str, Any]:
        return {"slot_id": self.slot_id, "instance_id": self.instance_id, "allowed_definitions": [list(x) for x in self.allowed_definitions],
                "required_points": list(self.required_points)}


def _uniq(label: str, values: Iterable[Any], typ: type, key) -> tuple[Any, ...]:
    items = tuple(values)
    if any(not isinstance(x, typ) for x in items):
        raise AssemblyRefusal(f"{label} must be {typ.__name__} records")
    if len({key(x) for x in items}) != len(items):
        raise AssemblyRefusal(f"{label} identities must be unique")
    return tuple(sorted(items, key=key))


@dataclass(frozen=True)
class AssemblyTopology:
    """A product structure: the system hierarchy plus placement, joints, interfaces, ownership and slots."""

    system: SystemDefinition
    levels: tuple[InstanceLevel, ...]
    placements: tuple[Placement, ...] = ()
    points: tuple[ConnectionPoint, ...] = ()
    joints: tuple[JointDeclaration, ...] = ()
    interfaces: tuple[InterfaceDeclaration, ...] = ()
    geometry: tuple[GeometryOwnership, ...] = ()
    materials: tuple[MaterialOwnership, ...] = ()
    states: tuple[StateOwnership, ...] = ()
    slots: tuple[ReplaceableSlot, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.system, SystemDefinition):
            raise AssemblyRefusal("an assembly topology is layered on a SystemDefinition")
        inst = {i.instance_id: i for i in self.system.instances}
        levels = _uniq("levels", self.levels, InstanceLevel, lambda x: x.instance_id)
        lmap = {x.instance_id: x.level for x in levels}
        if set(lmap) != set(inst):
            raise AssemblyRefusal(f"every instance needs exactly one composition level; missing {sorted(set(inst) - set(lmap))}, "
                                  f"unknown {sorted(set(lmap) - set(inst))}")
        roots = [i for i in inst.values() if not i.parent_id]
        if len(roots) != 1:
            raise AssemblyRefusal(f"a product has exactly one root instance; found {sorted(i.instance_id for i in roots)}")
        if lmap[roots[0].instance_id] is not CompositionLevel.SYSTEM:
            raise AssemblyRefusal("the root instance is the SYSTEM level")
        for i in inst.values():
            if i.parent_id:
                if lmap[i.instance_id].depth <= lmap[i.parent_id].depth:
                    raise AssemblyRefusal(f"{i.instance_id!r} ({lmap[i.instance_id].value}) cannot sit under "
                                          f"{i.parent_id!r} ({lmap[i.parent_id].value}); levels deepen down the tree")
                if lmap[i.parent_id] is CompositionLevel.PART:
                    raise AssemblyRefusal(f"part {i.parent_id!r} cannot have children")
        placements = _uniq("placements", self.placements, Placement, lambda x: x.instance_id)
        for p in placements:
            if p.instance_id not in inst:
                raise AssemblyRefusal(f"placement of unknown instance {p.instance_id!r}")
            if not inst[p.instance_id].parent_id and not p.transform.is_identity:
                raise AssemblyRefusal("the root instance defines the product frame; its placement is identity")
        points = _uniq("connection points", self.points, ConnectionPoint, lambda x: x.point_id)
        pmap = {p.point_id: p for p in points}
        for p in points:
            if p.instance_id not in inst:
                raise AssemblyRefusal(f"connection point {p.point_id!r} on unknown instance {p.instance_id!r}")
        joints = _uniq("joints", self.joints, JointDeclaration, lambda x: x.joint_id)
        child_of: dict[str, str] = {}
        for j in joints:
            for pt in (j.parent_point, j.child_point):
                if pt not in pmap:
                    raise AssemblyRefusal(f"joint {j.joint_id!r} names unknown connection point {pt!r}")
            a, b = pmap[j.parent_point].instance_id, pmap[j.child_point].instance_id
            if a == b:
                raise AssemblyRefusal(f"joint {j.joint_id!r} connects instance {a!r} to itself")
            if b in child_of:
                raise AssemblyRefusal(f"instance {b!r} is the child of joints {child_of[b]!r} and {j.joint_id!r}; "
                                      "closed kinematic loops are not represented by this foundation")
            child_of[b] = j.joint_id
        parent_of = {pmap[j.child_point].instance_id: pmap[j.parent_point].instance_id for j in joints}
        for start in parent_of:  # one parent per child is not enough: A->B, B->A is a loop too
            seen, node = {start}, start
            while node in parent_of:
                node = parent_of[node]
                if node in seen:
                    raise AssemblyRefusal(f"the joints form a closed kinematic loop through {node!r}; closed loops are not "
                                          "represented by this foundation")
                seen.add(node)
        interfaces = _uniq("interfaces", self.interfaces, InterfaceDeclaration, lambda x: x.interface_id)
        for itf in interfaces:
            for pt in (itf.point_a, itf.point_b):
                if pt not in pmap:
                    raise AssemblyRefusal(f"interface {itf.interface_id!r} names unknown connection point {pt!r}")
            if pmap[itf.point_a].instance_id == pmap[itf.point_b].instance_id:
                raise AssemblyRefusal(f"interface {itf.interface_id!r} must join two instances")
        geometry = _uniq("geometry ownership", self.geometry, GeometryOwnership, lambda x: x.instance_id)
        owned: dict[tuple[str, str], str] = {}
        for g in geometry:
            if g.instance_id not in inst:
                raise AssemblyRefusal(f"geometry owned by unknown instance {g.instance_id!r}")
            for b in g.body_ids:
                key = (g.geometry_digest, b)
                if key in owned:
                    raise AssemblyRefusal(f"body {b!r} is owned by both {owned[key]!r} and {g.instance_id!r}")
                owned[key] = g.instance_id
        materials = _uniq("material ownership", self.materials, MaterialOwnership, lambda x: x.instance_id)
        states = _uniq("state ownership", self.states, StateOwnership, lambda x: x.state_id)
        slots = _uniq("slots", self.slots, ReplaceableSlot, lambda x: x.slot_id)
        for x in (*materials, *states):
            if x.instance_id not in inst:
                raise AssemblyRefusal(f"ownership names unknown instance {x.instance_id!r}")
        if len({s.instance_id for s in slots}) != len(slots):
            raise AssemblyRefusal("an instance belongs to at most one replaceable slot")
        for s in slots:
            if s.instance_id not in inst:
                raise AssemblyRefusal(f"slot {s.slot_id!r} names unknown instance")
            if inst[s.instance_id].definition_key not in s.allowed_definitions:
                raise AssemblyRefusal(f"slot {s.slot_id!r}: the current definition is not among its allowed definitions")
            have = {p.point_id for p in points if p.instance_id == s.instance_id}
            if set(s.required_points) - have:
                raise AssemblyRefusal(f"slot {s.slot_id!r} requires points {sorted(set(s.required_points) - have)} its instance lacks")
        for name, val in (("levels", levels), ("placements", placements), ("points", points), ("joints", joints),
                          ("interfaces", interfaces), ("geometry", geometry), ("materials", materials), ("states", states), ("slots", slots)):
            object.__setattr__(self, name, val)

    # ---- structure ----------------------------------------------------------
    @property
    def root(self) -> str:
        return next(i.instance_id for i in self.system.instances if not i.parent_id)

    def instance(self, instance_id: str) -> ComponentInstance:
        for i in self.system.instances:
            if i.instance_id == instance_id:
                return i
        raise AssemblyRefusal(f"no instance {instance_id!r}")

    def level(self, instance_id: str) -> CompositionLevel:
        return next(x.level for x in self.levels if x.instance_id == instance_id)

    def children(self, instance_id: str) -> tuple[str, ...]:
        return tuple(sorted(i.instance_id for i in self.system.instances if i.parent_id == instance_id))

    def path(self, instance_id: str) -> tuple[str, ...]:
        out = [instance_id]
        cur = self.instance(instance_id)
        while cur.parent_id:
            out.append(cur.parent_id)
            cur = self.instance(cur.parent_id)
        return tuple(reversed(out))

    def world_transform(self, instance_id: str) -> Transform:
        """Pose of an instance in the product frame.  A missing placement on the path is refused (UNKNOWN pose)."""
        pmap = {p.instance_id: p.transform for p in self.placements}
        out = Transform()
        for iid in self.path(instance_id)[1:]:
            if iid not in pmap:
                raise AssemblyRefusal(f"instance {iid!r} has no placement; its pose is UNKNOWN, not the parent's origin")
            out = out.compose(pmap[iid])
        return out

    def point_world(self, point_id: str) -> Transform:
        p = next((x for x in self.points if x.point_id == point_id), None)
        if p is None:
            raise AssemblyRefusal(f"no connection point {point_id!r}")
        return self.world_transform(p.instance_id).compose(p.local)

    def kinematic_dof(self) -> int | None:
        """Sum of declared ideal-joint DOF; None (UNKNOWN) as soon as one joint is compliant."""
        total = 0
        for j in self.joints:
            if j.dof is None:
                return None
            total += j.dof
        return total

    def owner_of_state(self, state_id: str) -> str:
        for s in self.states:
            if s.state_id == state_id:
                return s.instance_id
        raise AssemblyRefusal(f"state {state_id!r} has no owner")

    def validate_geometry(self, models: Mapping[str, GeometryModel]) -> None:
        """Owned bodies exist in the exact geometry; a body's geometry material agrees with its owner's material."""
        mats = {m.instance_id: m.material for m in self.materials}
        for g in self.geometry:
            model = models.get(g.geometry_digest)
            if model is None or model.digest != g.geometry_digest:
                raise AssemblyRefusal(f"geometry {g.geometry_digest[:12]} owned by {g.instance_id!r} was not supplied")
            for b in g.body_ids:
                model.body(b)
                bound = model.material_of_body(b)
                if g.instance_id in mats and bound is not None and bound.material != mats[g.instance_id]:
                    raise AssemblyRefusal(f"body {b!r} is bound to {bound.material.family} in the geometry but its owner "
                                          f"{g.instance_id!r} declares {mats[g.instance_id].family}")

    # ---- variants -----------------------------------------------------------
    def replace(self, slot_id: str, definition: ComponentDefinition, twin: TwinReference, *,
                geometry: GeometryOwnership | None = None, material: MaterialOwnership | None = None) -> "AssemblyTopology":
        """Swap a slot's component for another allowed definition; returns a NEW variant (this one is unchanged).

        Ports used by connections must still exist (SystemDefinition validation
        refuses otherwise); connection points, joints and interfaces stay bound
        to the instance id, so the slot contract carries over.  Geometry and
        material ownership of the old component are dropped unless replaced:
        the old component's geometry is not silently inherited.
        """
        slot = next((s for s in self.slots if s.slot_id == slot_id), None)
        if slot is None:
            raise AssemblyRefusal(f"no replaceable slot {slot_id!r}")
        if definition.key not in slot.allowed_definitions:
            raise AssemblyRefusal(f"definition {definition.key} is not allowed in slot {slot_id!r}")
        old = self.instance(slot.instance_id)
        new_inst = replace(old, definition_id=definition.component_id, definition_version=definition.version, twin=twin)
        defs = {d.key: d for d in self.system.definitions}
        defs[definition.key] = definition
        used = {i.definition_key for i in self.system.instances if i.instance_id != old.instance_id} | {definition.key}
        system = SystemDefinition(
            self.system.system_id, self.system.version, tuple(d for k, d in defs.items() if k in used),
            tuple(new_inst if i.instance_id == old.instance_id else i for i in self.system.instances),
            self.system.connections, self.system.parameter_bindings, self.system.state_bindings,
            self.system.constraint_bindings, self.system.constraints)
        geo = tuple(g for g in self.geometry if g.instance_id != old.instance_id) + ((geometry,) if geometry else ())
        mat = tuple(m for m in self.materials if m.instance_id != old.instance_id) + ((material,) if material else ())
        return replace(self, system=system, geometry=geo, materials=mat)

    # ---- identity -------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"schema": ASSEMBLY_TOPOLOGY_SCHEMA, "system": self.system.to_dict(), "system_digest": self.system.digest,
                "levels": [x.to_dict() for x in self.levels], "placements": [x.to_dict() for x in self.placements],
                "points": [x.to_dict() for x in self.points], "joints": [x.to_dict() for x in self.joints],
                "interfaces": [x.to_dict() for x in self.interfaces], "geometry": [x.to_dict() for x in self.geometry],
                "materials": [x.to_dict() for x in self.materials], "states": [x.to_dict() for x in self.states],
                "slots": [x.to_dict() for x in self.slots]}

    @property
    def digest(self) -> str:
        """The product variant identity: any swap, placement, joint or ownership change is a new identity."""
        return canonical_digest(self.to_dict())

    @classmethod
    def from_dict(cls, p: Mapping[str, Any]) -> "AssemblyTopology":
        if p.get("schema") != ASSEMBLY_TOPOLOGY_SCHEMA:
            raise AssemblyRefusal("unsupported assembly topology schema")
        system = SystemDefinition.from_dict(p["system"])
        if system.digest != p["system_digest"]:
            raise AssemblyRefusal("serialized system does not match its digest")
        out = cls(
            system, tuple(InstanceLevel(x["instance_id"], x["level"]) for x in p["levels"]),
            tuple(Placement(x["instance_id"], Transform.from_dict(x["transform"])) for x in p["placements"]),
            tuple(ConnectionPoint(x["point_id"], x["instance_id"], Transform.from_dict(x["local"]), x.get("geometry_entity", "")) for x in p["points"]),
            tuple(JointDeclaration.from_dict(x) for x in p["joints"]),
            tuple(InterfaceDeclaration(x["interface_id"], x["kind"], x["point_a"], x["point_b"], x.get("geometry_entity", "")) for x in p["interfaces"]),
            tuple(GeometryOwnership(x["instance_id"], x["geometry_digest"], tuple(x["body_ids"])) for x in p["geometry"]),
            tuple(MaterialOwnership(x["instance_id"], MaterialIdentity.from_dict(x["material"])) for x in p["materials"]),
            tuple(StateOwnership(x["state_id"], x["instance_id"]) for x in p["states"]),
            tuple(ReplaceableSlot(x["slot_id"], x["instance_id"], tuple(tuple(a) for a in x["allowed_definitions"]), tuple(x["required_points"]))
                  for x in p["slots"]),
        )
        if "digest" in p and p["digest"] != out.digest:
            raise AssemblyRefusal("serialized assembly does not match its digest")
        return out
