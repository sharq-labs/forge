"""Produce a derived Scientific Diagnostic report from an assessment JSON.

The diagnostic does not execute physics, mutate the assessment, or strengthen
its verdict. Optional sensitivity/robustness artifacts may refine hypotheses.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from engcore.claims.analysis.diagnostics import diagnose_assessment
from engcore.mcp.capabilities import production_registry
from tools.forge_impact import records_from_payload


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _optional_mapping(path: str | None, *, label: str) -> Mapping[str, Any] | None:
    if path is None:
        return None
    payload = _load(path)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assessment", help="assessment JSON or replay bundle containing one assessment")
    parser.add_argument("--sensitivity", help="optional SensitivityReport JSON")
    parser.add_argument("--robustness", help="optional RobustnessEnvelope JSON")
    parser.add_argument("--output", help="write the diagnostic JSON to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = _load(args.assessment)
        records = records_from_payload(payload, source=args.assessment)
        if len(records) != 1:
            raise ValueError("diagnosis requires exactly one assessment record")
        report = diagnose_assessment(
            records[0],
            production_registry(),
            sensitivity=_optional_mapping(args.sensitivity, label="sensitivity"),
            robustness=_optional_mapping(args.robustness, label="robustness"),
        )
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"forge-diagnose: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report.to_dict(), sort_keys=True, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
