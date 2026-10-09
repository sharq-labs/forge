"""Big Rock T: the Scene IR presents records; it never becomes scientific authority."""

from __future__ import annotations

import pytest

from engcore.engineering.scene import EvidenceStatus, OverlayKind, SceneOverlay, SceneRefusal, scene_from_assembly
from engcore.scientific.units.quantity import Quantity
from engcore.systems.products import drone_template


def test_scene_mirrors_hierarchy_and_keeps_unknown_poses_unknown():
    bare = scene_from_assembly("drone-view", drone_template().assembly)
    d = bare.to_dict()
    assert d["authority"] == "presentation_only"
    poses = {n["node_id"]: n["pose_status"] for n in d["nodes"]}
    assert poses["drone"] == "known" and poses["arm_1"] == "unknown"
    placed = scene_from_assembly("drone-view", drone_template({"arm_length": (Quantity(0.25, "m"), "spec:frame-r2")}).assembly)
    assert {n.node_id: n.pose_status for n in placed.nodes}["arm_1"] == "known"
    assert placed.digest == scene_from_assembly("drone-view", drone_template({"arm_length": (Quantity(0.25, "m"), "spec:frame-r2")}).assembly).digest


def test_overlays_need_records_and_risk_needs_an_assessment():
    asm = drone_template().assembly
    src = "a" * 64
    ok = SceneOverlay("p", "motor_1", OverlayKind.SCALAR, EvidenceStatus.INSUFFICIENT_EVIDENCE, src, Quantity(42, "W"))
    scene = scene_from_assembly("v", asm, overlays=(ok,))
    assert scene.to_dict()["overlays"][0]["evidence_status"] == "insufficient_evidence"
    with pytest.raises(SceneRefusal, match="never infers risk"):
        SceneOverlay("r", "motor_1", OverlayKind.RISK, EvidenceStatus.UNASSESSED, src, text="winding hot")
    with pytest.raises(SceneRefusal, match="no source record"):
        SceneOverlay("p", "motor_1", OverlayKind.SCALAR, EvidenceStatus.UNASSESSED, "", Quantity(1, "W"))
    claimed = SceneOverlay("s", "motor_1", OverlayKind.STATUS, EvidenceStatus.SUPPORTED, src, text="SAFE")
    with pytest.raises(SceneRefusal, match="no supplied record states"):
        scene_from_assembly("v", asm, overlays=(claimed,))
    assert scene_from_assembly("v", asm, overlays=(claimed,), records={src: {"evidence_status": "supported"}})
    risk = SceneOverlay("r", "motor_1", OverlayKind.RISK, EvidenceStatus.UNASSESSED, src, text="near limit", assessment_ref="x")
    with pytest.raises(SceneRefusal, match="not supplied as an assessment"):
        scene_from_assembly("v", asm, overlays=(risk,))
    with pytest.raises(SceneRefusal, match="no source record"):
        SceneOverlay("p", "motor_1", OverlayKind.SCALAR, EvidenceStatus.UNASSESSED, "Z" * 64, Quantity(1, "W"))
    with pytest.raises(SceneRefusal, match="unknown node"):
        scene_from_assembly("v", asm, overlays=(SceneOverlay("p", "ghost", OverlayKind.SCALAR, EvidenceStatus.UNASSESSED, src, Quantity(1, "W")),))
