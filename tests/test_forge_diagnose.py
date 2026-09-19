from __future__ import annotations

import json

from tools import forge_diagnose


def test_optional_mapping_refuses_non_object(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    try:
        forge_diagnose._optional_mapping(str(path), label="sensitivity")
    except ValueError as exc:
        assert "sensitivity must be a JSON object" in str(exc)
    else:
        raise AssertionError("non-object sensitivity must be refused")


def test_parser_accepts_optional_diagnostic_artifacts():
    args = forge_diagnose.build_parser().parse_args(
        ["assessment.json", "--sensitivity", "s.json", "--robustness", "r.json"]
    )
    assert args.assessment == "assessment.json"
    assert args.sensitivity == "s.json"
    assert args.robustness == "r.json"
