"""Provider-neutral Scene IR: a presentation contract over authoritative Forge records.

A :class:`Scene` is what a viewer (Three.js, Babylon.js, ParaView/VTK, WebGPU)
renders.  It is built FROM records -- an assembly topology, geometry models,
materials, computed fields, results, evidence status -- and carries their
digests, never copies of their authority:

* nodes mirror the assembly hierarchy; a node whose pose is UNKNOWN (no
  placement) is emitted with ``pose = None`` and ``pose_status = "unknown"``,
  never at its parent's origin;
* geometry is referenced by geometry digest + body ids (+ primitive dims);
* overlays bind a value (with unit) or a field digest to a node, and always
  carry an evidence status; a RISK overlay must name the assessment record
  that supports it -- colour never implies failure, burnout or safety;
* time states are explicit (time, node poses) frames.

``authority`` is always ``presentation_only``.  Rendering a scene proves
nothing about the product.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from ..scenarios.timeline import canonical_digest
from ..scientific.errors import InvalidScientificProblem
from ..scientific.units.quantity import Quantity
from ..spatial.geometry import GeometryModel
from ..systems.assembly import AssemblyRefusal, AssemblyTopology

SCENE_SCHEMA = "engcore.engineering.scene/1"


class SceneRefusal(InvalidScientificProblem):
    """A scene element that would present something no record supports."""


class OverlayKind(str, Enum):
    SCALAR = "scalar"        # one value with unit on a node
    FIELD = "field"          # a computed/resolved field, by digest
    STATUS = "status"        # verdict / evidence-stop text
    RISK = "risk"            # a limit/margin statement -- requires an assessment record


class EvidenceStatus(str, Enum):
    UNASSESSED = "unassessed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    VERIFIED_NUMERICS_ONLY = "verified_numerics_only"
    SUPPORTED = "supported"           # a credibility-layer verdict, quoted, not computed here
    REFUSED = "refused"


@dataclass(frozen=True)
class SceneNode:
    node_id: str
    parent: str
    level: str
    pose: tuple[tuple[float, ...], ...] | None
    geometry: Mapping[str, Any] = field(default_factory=dict)
    material: Mapping[str, Any] = field(default_factory=dict)

    @property
    def pose_status(self) -> str:
        return "known" if self.pose is not None else "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "parent": self.parent, "level": self.level, "pose_status": self.pose_status,
                "pose": None if self.pose is None else [list(r) for r in self.pose], "geometry": dict(self.geometry),
                "material": dict(self.material)}


@dataclass(frozen=True)
class SceneOverlay:
    overlay_id: str
    node_id: str
    kind: OverlayKind
    evidence_status: EvidenceStatus
    source_digest: str
    value: Quantity | None = None
    field_digest: str = ""
    text: str = ""
    assessment_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", OverlayKind(self.kind))
        object.__setattr__(self, "evidence_status", EvidenceStatus(self.evidence_status))
        if len(str(self.source_digest)) != 64:
            raise SceneRefusal(f"overlay {self.overlay_id!r} names no source record digest; a value with no record is not shown")
        if self.kind is OverlayKind.SCALAR and not isinstance(self.value, Quantity):
            raise SceneRefusal(f"scalar overlay {self.overlay_id!r} needs a Quantity (value and unit)")
        if self.kind is OverlayKind.FIELD and len(self.field_digest) != 64:
            raise SceneRefusal(f"field overlay {self.overlay_id!r} needs the field digest")
        if self.kind is OverlayKind.RISK and not self.assessment_ref.strip():
            raise SceneRefusal(f"risk overlay {self.overlay_id!r} names no assessment record; a viewer never infers risk from colour")

    def to_dict(self) -> dict[str, Any]:
        return {"overlay_id": self.overlay_id, "node_id": self.node_id, "kind": self.kind.value, "evidence_status": self.evidence_status.value,
                "source_digest": self.source_digest, "value": None if self.value is None else self.value.to_dict(),
                "field_digest": self.field_digest, "text": self.text, "assessment_ref": self.assessment_ref}


@dataclass(frozen=True)
class TimeState:
    time_s: float
    poses: Mapping[str, tuple[tuple[float, ...], ...]]
    source_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {"time_s": self.time_s, "poses": {k: [list(r) for r in v] for k, v in sorted(self.poses.items())}, "source_digest": self.source_digest}


@dataclass(frozen=True)
class Scene:
    scene_id: str
    assembly_digest: str
    nodes: tuple[SceneNode, ...]
    overlays: tuple[SceneOverlay, ...] = ()
    time_states: tuple[TimeState, ...] = ()

    def __post_init__(self) -> None:
        ids = {n.node_id for n in self.nodes}
        if len(ids) != len(self.nodes):
            raise SceneRefusal("scene node ids must be unique")
        for o in self.overlays:
            if o.node_id not in ids:
                raise SceneRefusal(f"overlay {o.overlay_id!r} targets unknown node {o.node_id!r}")
        for t in self.time_states:
            if set(t.poses) - ids:
                raise SceneRefusal(f"time state at {t.time_s} s poses unknown nodes")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCENE_SCHEMA, "authority": "presentation_only", "scene_id": self.scene_id, "assembly_digest": self.assembly_digest,
                "nodes": [n.to_dict() for n in self.nodes], "overlays": [o.to_dict() for o in self.overlays],
                "time_states": [t.to_dict() for t in self.time_states]}

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())


def _matrix(t) -> tuple[tuple[float, ...], ...]:
    r, p = t.rotation, t.translation_m
    return tuple(tuple(r[i]) + (p[i],) for i in range(3)) + ((0.0, 0.0, 0.0, 1.0),)


def scene_from_assembly(scene_id: str, assembly: AssemblyTopology, *, geometry: Iterable[GeometryModel] = (),
                        overlays: Iterable[SceneOverlay] = (), time_states: Iterable[TimeState] = ()) -> Scene:
    """Nodes from the assembly; geometry/material annotations from the owned geometry; UNKNOWN poses stay unknown."""
    models = {g.digest: g for g in geometry}
    owned = {g.instance_id: g for g in assembly.geometry}
    mats = {m.instance_id: m.material for m in assembly.materials}
    nodes = []
    for inst in assembly.system.instances:
        try:
            pose = _matrix(assembly.world_transform(inst.instance_id))
        except AssemblyRefusal:
            pose = None
        geo: dict[str, Any] = {}
        if inst.instance_id in owned:
            g = owned[inst.instance_id]
            model = models.get(g.geometry_digest)
            geo = {"geometry_digest": g.geometry_digest, "bodies": list(g.body_ids)}
            if model is not None:
                geo["shapes"] = {b: model.body(b).shape.to_dict() for b in g.body_ids}
        mat = {"material_digest": mats[inst.instance_id].digest, "family": mats[inst.instance_id].family} if inst.instance_id in mats else {}
        nodes.append(SceneNode(inst.instance_id, inst.parent_id, assembly.level(inst.instance_id).value, pose, geo, mat))
    return Scene(scene_id, assembly.digest, tuple(nodes), tuple(overlays), tuple(time_states))
