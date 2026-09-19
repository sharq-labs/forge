"""Query and detect reassessment impact from stored Forge assessment records.

Examples:

    python tools/forge_impact.py query assessment.json --kind model --key thermal.model
    python tools/forge_impact.py detect archive/*.json

This tool never edits historical decisions and never upgrades scientific
standing. It only reads identities already recorded by the assessment layer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence

from engcore.claims.analysis.impact import (
    Change,
    ChangeKind,
    DecisionGraph,
    detect_changes,
    impact_of,
)


def _as_record(value: Any, *, source: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{source}: assessment record must be a JSON object")
    return value


def records_from_payload(payload: Any, *, source: str = "<memory>") -> list[Mapping[str, Any]]:
    """Accept one record, a list of records, a bundle, or {"records": [...]}."""

    if isinstance(payload, list):
        return [_as_record(item, source=source) for item in payload]

    mapping = _as_record(payload, source=source)
    if isinstance(mapping.get("records"), list):
        return [_as_record(item, source=source) for item in mapping["records"]]

    # Assessment replay bundles carry the authoritative assessment under
    # "record". Do not treat bundle metadata as assessment fields.
    if isinstance(mapping.get("record"), Mapping):
        return [_as_record(mapping["record"], source=source)]

    return [mapping]


def load_records(paths: Iterable[str | Path]) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for raw in paths:
        path = Path(raw)
        payload = json.loads(path.read_text(encoding="utf-8"))
        records.extend(records_from_payload(payload, source=str(path)))
    if not records:
        raise ValueError("at least one assessment record is required")
    return records


def report_for_change(
    records: Sequence[Mapping[str, Any]],
    *,
    kind: ChangeKind,
    key: str,
    detail: str = "",
) -> dict[str, Any]:
    graph = DecisionGraph(records)
    return impact_of(graph, (Change(kind, key, detail),)).to_dict()


def detect_current(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare stored identities with the repository's current production registries."""

    from engcore.claims.external_evidence import PRODUCTION_EXTERNAL_REGISTRY
    from engcore.mcp.capabilities import production_registry

    registry = production_registry()
    changes = detect_changes(
        records,
        registry,
        trust_registry=PRODUCTION_EXTERNAL_REGISTRY,
    )
    return impact_of(DecisionGraph(records), changes).to_dict()


def _write(payload: Mapping[str, Any], output: str | None) -> None:
    text = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    query = sub.add_parser("query", help="show assessments depending on one identity")
    query.add_argument("records", nargs="+", help="assessment JSON, list JSON, or replay bundle")
    query.add_argument("--kind", required=True, choices=[kind.value for kind in ChangeKind])
    query.add_argument("--key", required=True, help="identity/prefix used by the recorded dependency graph")
    query.add_argument("--detail", default="", help="human-readable change description")
    query.add_argument("--output", help="write JSON report to this file")

    detect = sub.add_parser("detect", help="detect drift against current production registries")
    detect.add_argument("records", nargs="+", help="assessment JSON, list JSON, or replay bundle")
    detect.add_argument("--output", help="write JSON report to this file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        records = load_records(args.records)
        if args.command == "query":
            payload = report_for_change(
                records,
                kind=ChangeKind(args.kind),
                key=args.key,
                detail=args.detail,
            )
        else:
            payload = detect_current(records)
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"forge-impact: {exc}", file=sys.stderr)
        return 2

    _write(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
