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

from engcore.claims import ClaimLayerError, verify_assessment
from engcore.claims.analysis.diagnostics import diagnose_assessment
from engcore.claims.external_evidence import PRODUCTION_EXTERNAL_REGISTRY
from engcore.claims.replay.bundle import BUNDLE_SCHEMA, BundleStatus, verify_bundle
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


def _verified_record(payload: Any, registry: Any, *, source: str) -> Mapping[str, Any]:
    """Fail closed: diagnostics consume a re-derived assessment, never raw JSON."""
    if isinstance(payload, Mapping) and payload.get("schema") == BUNDLE_SCHEMA:
        check = verify_bundle(payload, registry)
        if check.status is not BundleStatus.VERIFIED:
            raise ValueError(f"{source}: replay bundle is {check.status.value}: {list(check.problems)}")
        record = payload.get("record")
        if not isinstance(record, Mapping):
            raise ValueError(f"{source}: verified bundle carries no assessment record")
        return record

    records = records_from_payload(payload, source=source)
    if len(records) != 1:
        raise ValueError("diagnosis requires exactly one assessment record")
    record = records[0]
    if record.get("external_trust_registry") != PRODUCTION_EXTERNAL_REGISTRY.digest:
        raise ValueError(
            "raw assessment uses a non-production trust registry; diagnose its replay bundle so the trust pins can be verified"
        )
    return verify_assessment(record, registry, trust=PRODUCTION_EXTERNAL_REGISTRY).to_dict()

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
        registry = production_registry()
        record = _verified_record(payload, registry, source=args.assessment)
        report = diagnose_assessment(
            record,
            registry,
            sensitivity=_optional_mapping(args.sensitivity, label="sensitivity"),
            robustness=_optional_mapping(args.robustness, label="robustness"),
        )
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError, ClaimLayerError) as exc:
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
