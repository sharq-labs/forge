"""BR-MIND-REPSEM-01 pins: the gap map's inputs, the fixtures' construction truth, and the recorded ablation."""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib

import pytest

from benchmarks.mind_repsem_v1 import fixtures as fx, gap_map
from engcore.mind.repsem import CLAIM_TYPES, ClaimState, Disposition, ScopedClaim

HERE = pathlib.Path(__file__).resolve().parents[1]
V1 = HERE.parent / "battery_rediscovery_v1"


def test_gap_map_reads_no_truth_field():
    assert gap_map.EVALUATION_FIELDS_READ == ("class", "mind_answer", "mind_outcome")
    src = (HERE / "gap_map.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    literals = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "truth" not in literals and "careful_answer" not in literals


def test_gap_map_is_reproducible_and_complete():
    built = gap_map.build()
    stored = json.loads((HERE / "results" / "GAP_MAP.json").read_bytes())
    assert built == stored
    assert stored["failed"] == 8
    assert stored["tally"]["REPRESENTATION_MISSING"] == 5 and stored["tally"]["SEMANTIC_ROLE_ERROR"] == 2
    assert stored["tally"]["MULTIPLE_CAUSES"] == 1 and stored["tally"]["UNKNOWN"] == 0


def test_battery_v1_frozen_artifacts_are_untouched():
    plan = json.loads((V1 / "PLAN.json").read_bytes())
    for rel, sha in plan["frozen_files"].items():
        path = HERE.parents[1] / rel
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha, rel


@pytest.mark.parametrize("protocol", fx.PROTOCOLS)
@pytest.mark.parametrize("kind", fx.FIXTURES)
def test_every_truth_label_follows_from_construction(kind, protocol):
    audit = fx.construction_audit(kind, protocol)
    bad = {a: c for a, c in audit["checks"].items() if not c["follows_from_construction"]}
    assert not bad, (kind, protocol, bad, audit["facts"])


def test_every_previously_not_representable_class_is_expressible():
    gm = json.loads((HERE / "results" / "GAP_MAP.json").read_bytes())
    for instance in gm["not_representable_failures"]:
        axis = instance.split("/")[1]
        ctype = CLAIM_TYPES[axis]
        for disposition, state in ((Disposition.SUPPORTED, ctype.positive), (Disposition.NOT_SUPPORTED, ctype.negative)):
            claim = ScopedClaim(axis, disposition, state=state, evidence=("sha256:x",), reason="expressible")
            assert ScopedClaim.from_dict(claim.to_dict()) == claim


def test_recorded_ablation_meets_the_success_criteria():
    result = json.loads((HERE / "results" / "ABLATION.json").read_bytes())
    arms = result["summary"]["by_arm"]
    old, new = arms["OLD_MIND"], arms["REPRESENTATION_PLUS_ROLES"]
    assert new["FALSE_REFUSE"] < old["FALSE_REFUSE"]
    assert new["FALSE_SUPPORT"] <= old["FALSE_SUPPORT"]
    assert result["replay"]["OTHER"] == 0
    reached = result["summary"]["reached"]["REPRESENTATION_PLUS_ROLES"]
    for axis in ("IDENTIFIABILITY", "MODEL_ADEQUACY", "MODEL_DISCREPANCY"):
        assert {"SUPPORTED", "NOT_SUPPORTED"} <= set(reached[axis]), axis
    assert "NOT_SUPPORTED" in reached["CROSS_CELL_TRANSFER"]
    assert ClaimState.MODEL_DISCREPANCY_UNRESOLVED.value != "MODEL_DISCREPANCY_ABSENT"
