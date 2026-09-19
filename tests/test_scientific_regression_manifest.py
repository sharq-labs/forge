from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "scientific_regression" / "manifest.json"


def test_regression_manifest_is_large_enough_unique_and_points_to_real_tests():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["schema"] == "forge.scientific_regression/1"

    cases = data["cases"]
    assert len(cases) >= 30

    ids = [case["id"] for case in cases]
    nodeids = [case["nodeid"] for case in cases]
    assert len(ids) == len(set(ids))
    assert len(nodeids) == len(set(nodeids))

    for case in cases:
        assert case["tags"], case["id"]
        assert case["invariant"].strip(), case["id"]

        path_text, sep, function = case["nodeid"].partition("::")
        assert sep and function.startswith("test_"), case["nodeid"]

        path = ROOT / path_text
        assert path.is_file(), case["nodeid"]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert function in functions, case["nodeid"]


def test_regression_pack_covers_every_load_bearing_category():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tags = {tag for case in data["cases"] for tag in case["tags"]}
    required = {
        "verdict", "evidence", "vnv", "applicability", "compiler", "selection",
        "context", "uq", "policy", "external", "gaps", "challenge", "replay",
        "provenance", "diagnostics", "equation_ir",
    }
    assert required <= tags
