"""Deterministically generate the 500-case Equation IR dimensional corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CASE_SCHEMA = "equation_ir_case/1"
SYMBOL_SCHEMA = "equation_symbol/1"
BINARY_SCHEMA = "equation_binary/1"
POWER_SCHEMA = "equation_power/1"
FUNCTION_SCHEMA = "equation_function/1"

VALID_UNITS = (
    "meter", "second", "kilogram", "ampere", "kelvin",
    "mole", "candela", "volt", "ohm", "watt",
)
BASE_UNITS = ("meter", "second", "kilogram", "ampere", "kelvin", "mole", "candela")
FUNCTIONS = ("exp", "log", "sin", "cos", "tan")
POWERS = (2, 3, -1, 4, 0)


def symbol(name: str) -> dict[str, Any]:
    return {"schema": SYMBOL_SCHEMA, "name": name}


def binary(operator: str) -> dict[str, Any]:
    return {
        "schema": BINARY_SCHEMA,
        "operator": operator,
        "left": symbol("x"),
        "right": symbol("y"),
    }


def case(
    case_id: str,
    variables: list[dict[str, str]],
    expression: dict[str, Any],
    expected: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema": CASE_SCHEMA,
        "id": case_id,
        "variables": variables,
        "expression": expression,
        "expected": expected,
    }


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    for index in range(100):
        unit = VALID_UNITS[index % len(VALID_UNITS)]
        cases.append(case(
            f"add-valid-{index + 1:03d}",
            [{"name": "x", "unit": unit}, {"name": "y", "unit": unit}],
            binary("add"),
            {"status": "valid", "unit": unit},
        ))

    for index in range(100):
        left = BASE_UNITS[index % len(BASE_UNITS)]
        right = BASE_UNITS[(index + 1) % len(BASE_UNITS)]
        cases.append(case(
            f"add-invalid-{index + 1:03d}",
            [{"name": "x", "unit": left}, {"name": "y", "unit": right}],
            binary("add"),
            {"status": "invalid", "error": "dimension_mismatch"},
        ))

    for index in range(100):
        left = VALID_UNITS[index % len(VALID_UNITS)]
        right = VALID_UNITS[(index * 3 + 1) % len(VALID_UNITS)]
        cases.append(case(
            f"multiply-{index + 1:03d}",
            [{"name": "x", "unit": left}, {"name": "y", "unit": right}],
            binary("multiply"),
            {"status": "valid", "unit": f"{left} * {right}"},
        ))

    for index in range(100):
        left = VALID_UNITS[index % len(VALID_UNITS)]
        right = VALID_UNITS[(index * 7 + 3) % len(VALID_UNITS)]
        cases.append(case(
            f"divide-{index + 1:03d}",
            [{"name": "x", "unit": left}, {"name": "y", "unit": right}],
            binary("divide"),
            {"status": "valid", "unit": f"{left} / {right}"},
        ))

    for index in range(50):
        unit = BASE_UNITS[index % len(BASE_UNITS)]
        exponent = POWERS[index % len(POWERS)]
        cases.append(case(
            f"power-{index + 1:03d}",
            [{"name": "x", "unit": unit}],
            {
                "schema": POWER_SCHEMA,
                "base": symbol("x"),
                "numerator": exponent,
                "denominator": 1,
            },
            {
                "status": "valid",
                "unit": "dimensionless" if exponent == 0 else f"{unit} ** {exponent}",
            },
        ))

    for index in range(25):
        function = FUNCTIONS[index % len(FUNCTIONS)]
        cases.append(case(
            f"function-valid-{index + 1:03d}",
            [{"name": "x", "unit": "dimensionless"}],
            {
                "schema": FUNCTION_SCHEMA,
                "function": function,
                "argument": symbol("x"),
            },
            {"status": "valid", "unit": "dimensionless"},
        ))

    for index in range(25):
        function = FUNCTIONS[index % len(FUNCTIONS)]
        unit = BASE_UNITS[index % len(BASE_UNITS)]
        cases.append(case(
            f"function-invalid-{index + 1:03d}",
            [{"name": "x", "unit": unit}],
            {
                "schema": FUNCTION_SCHEMA,
                "function": function,
                "argument": symbol("x"),
            },
            {"status": "invalid", "error": "dimensionless_required"},
        ))

    assert len(cases) == 500
    return cases


def write_cases(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(build_cases(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "cases.json",
    )
    args = parser.parse_args()
    write_cases(args.out)
    print(f"wrote one deterministic 500-case Equation IR corpus to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
