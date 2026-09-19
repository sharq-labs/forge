from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.equation_ir.generate_cases import build_cases
from engcore.scientific.equations import (
    DimensionVector,
    EquationDimensionError,
    decode_expression,
    infer_dimension,
)

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "benchmarks" / "equation_ir" / "cases.json"


def load_cases() -> list[dict]:
    return json.loads(CASES.read_text(encoding="utf-8"))


def test_corpus_contains_exactly_500_unique_cases():
    cases = load_cases()
    assert len(cases) == 500
    ids = [case["id"] for case in cases]
    assert len(set(ids)) == 500
    assert all(case["schema"] == "equation_ir_case/1" for case in cases)


def test_committed_corpus_is_exactly_reproducible_from_generator():
    assert load_cases() == build_cases()


def test_all_500_cases_match_the_real_dimension_engine():
    for payload in load_cases():
        expression = decode_expression(payload["expression"])
        units = {item["name"]: item["unit"] for item in payload["variables"]}
        expected = payload["expected"]
        if expected["status"] == "valid":
            inferred = infer_dimension(expression, units)
            assert inferred == DimensionVector.from_unit(expected["unit"]), payload["id"]
        else:
            with pytest.raises(EquationDimensionError) as caught:
                infer_dimension(expression, units)
            assert caught.value.code == expected["error"], payload["id"]
