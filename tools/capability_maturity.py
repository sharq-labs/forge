"""Capability completion ledger validation and matrix rendering."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "project" / "scientific_capability_completion.json"
MATRIX = ROOT / "docs" / "SCIENTIFIC_CAPABILITY_MATRIX.md"

SCHEMA = "forge.scientific_capability_completion/1"
STAGES = ("FOUNDATION", "FUNCTIONAL", "EVIDENCE_BACKED", "PRODUCTION_READY")
RANK = {name: i for i, name in enumerate(STAGES)}
STATUSES = {"PASS", "MISSING", "NOT_APPLICABLE"}

GATES = (
    "scientific_definition", "applicability", "implementation", "regression_tests",
    "execution", "verification", "failure_cases", "provenance_replay",
    "real_data", "calibration", "independent_validation", "measurement_uq",
    "benchmark_metrics", "parameter_uq", "numerical_uq", "model_discrepancy",
    "claims_integration", "domainpack_integration", "documentation",
)

REQUIREMENTS = {
    "FOUNDATION": (
        "scientific_definition", "applicability", "implementation", "regression_tests",
    ),
    "FUNCTIONAL": (
        "execution", "verification", "failure_cases", "provenance_replay",
    ),
    "EVIDENCE_BACKED": (
        "real_data", "calibration", "independent_validation", "measurement_uq",
        "benchmark_metrics",
    ),
    "PRODUCTION_READY": (
        "parameter_uq", "numerical_uq", "model_discrepancy",
        "claims_integration", "domainpack_integration", "documentation",
    ),
}


def load_ledger(path: Path = LEDGER) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise ValueError("unsupported capability completion schema")
    return data


def satisfied(gate: dict[str, Any]) -> bool:
    return gate["status"] in {"PASS", "NOT_APPLICABLE"}


def computed_stage(capability: dict[str, Any]) -> str | None:
    required: list[str] = []
    highest = None
    for stage in STAGES:
        required.extend(REQUIREMENTS[stage])
        if all(satisfied(capability["gates"][name]) for name in required):
            highest = stage
        else:
            break
    return highest


def missing_for_next_stage(capability: dict[str, Any]) -> tuple[str, ...]:
    current = computed_stage(capability)
    target_index = 0 if current is None else RANK[current] + 1
    if target_index >= len(STAGES):
        return ()
    required: list[str] = []
    for stage in STAGES[: target_index + 1]:
        required.extend(REQUIREMENTS[stage])
    return tuple(
        name for name in required if not satisfied(capability["gates"][name])
    )


def validate(data: dict[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        return ("capabilities must be a non-empty array",)

    ids = [str(cap.get("id", "")).strip() for cap in capabilities if isinstance(cap, dict)]
    if len(ids) != len(set(ids)):
        errors.append("capability ids must be unique")

    for cap in capabilities:
        if not isinstance(cap, dict):
            errors.append("every capability must be an object")
            continue
        cid = str(cap.get("id", "")).strip() or "<missing>"
        stage = cap.get("declared_stage")
        if stage not in STAGES:
            errors.append(f"{cid}: invalid declared_stage {stage!r}")
        gates = cap.get("gates")
        if not isinstance(gates, dict):
            errors.append(f"{cid}: gates must be an object")
            continue
        if set(gates) != set(GATES):
            errors.append(f"{cid}: gates must be exactly {list(GATES)}")
            continue

        for name in GATES:
            gate = gates[name]
            if not isinstance(gate, dict):
                errors.append(f"{cid}.{name}: gate must be an object")
                continue
            status = gate.get("status")
            if status not in STATUSES:
                errors.append(f"{cid}.{name}: invalid status {status!r}")
                continue
            evidence = gate.get("evidence", [])
            if not isinstance(evidence, list):
                errors.append(f"{cid}.{name}: evidence must be an array")
            if status == "PASS" and not evidence:
                errors.append(f"{cid}.{name}: PASS requires evidence")
            if status == "NOT_APPLICABLE" and not str(gate.get("rationale", "")).strip():
                errors.append(f"{cid}.{name}: NOT_APPLICABLE requires rationale")
            if status == "MISSING" and not str(gate.get("next_action", "")).strip():
                errors.append(f"{cid}.{name}: MISSING requires next_action")

        calculated = computed_stage(cap)
        if calculated is None:
            errors.append(f"{cid}: does not satisfy FOUNDATION")
        elif stage in RANK and RANK[stage] > RANK[calculated]:
            errors.append(f"{cid}: declares {stage} but gates support only {calculated}")

        actions = cap.get("next_actions")
        if not isinstance(actions, list):
            errors.append(f"{cid}: next_actions must be an array")
        elif calculated != "PRODUCTION_READY" and not actions:
            errors.append(f"{cid}: incomplete capability must have next_actions")

    active = data.get("active_epic")
    if active not in ids:
        errors.append("active_epic must identify a tracked capability")
    else:
        active_cap = next(cap for cap in capabilities if cap["id"] == active)
        if computed_stage(active_cap) == "PRODUCTION_READY":
            errors.append("active_epic is already PRODUCTION_READY; choose the next epic")

    policy = data.get("policy")
    if not isinstance(policy, dict) or policy.get("horizontal_expansion_paused") is not True:
        errors.append("horizontal_expansion_paused must be true while the active epic is incomplete")

    return tuple(errors)


def render(data: dict[str, Any]) -> str:
    errors = validate(data)
    if errors:
        raise ValueError("\n".join(errors))

    lines = [
        "# Scientific Capability Completion Matrix",
        "",
        "Generated from docs/project/scientific_capability_completion.json.",
        "A capability is not complete because a class or file exists.",
        "",
        f"Active completion epic: {data['active_epic']}",
        "",
        "Stages: FOUNDATION -> FUNCTIONAL -> EVIDENCE_BACKED -> PRODUCTION_READY.",
        "",
        "| Capability | Declared | Computed max | Real data | Validation | UQ closure | Claims | Domain Pack | Next blockers |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    icon = {"PASS": "YES", "MISSING": "NO", "NOT_APPLICABLE": "N/A"}

    for cap in data["capabilities"]:
        gates = cap["gates"]
        uq = all(
            gates[name]["status"] in {"PASS", "NOT_APPLICABLE"}
            for name in ("measurement_uq", "parameter_uq", "numerical_uq", "model_discrepancy")
        )
        blockers = ", ".join(missing_for_next_stage(cap)[:4]) or "-"
        lines.append(
            "| "
            + " | ".join(
                (
                    cap["id"],
                    cap["declared_stage"],
                    computed_stage(cap) or "INCOMPLETE",
                    icon[gates["real_data"]["status"]],
                    icon[gates["independent_validation"]["status"]],
                    "YES" if uq else "NO",
                    icon[gates["claims_integration"]["status"]],
                    icon[gates["domainpack_integration"]["status"]],
                    blockers,
                )
            )
            + " |"
        )

    lines += [
        "",
        "## Policy",
        "",
        "The active epic is finished only when its computed stage reaches PRODUCTION_READY.",
        "Until then, horizontal expansion into new capability foundations is paused unless an explicit exception is recorded.",
        "Every MISSING gate must carry a concrete next action. NOT_APPLICABLE requires a rationale.",
        "",
    ]
    return "\n".join(lines)


def check() -> tuple[str, ...]:
    data = load_ledger()
    errors = list(validate(data))
    if errors:
        return tuple(errors)
    expected = render(data).rstrip()
    if not MATRIX.exists() or MATRIX.read_text(encoding="utf-8").rstrip() != expected:
        errors.append("SCIENTIFIC_CAPABILITY_MATRIX.md is stale; run tools.capability_maturity --write")
    return tuple(errors)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    data = load_ledger()
    errors = validate(data)
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1
    if args.write:
        MATRIX.write_text(render(data) + "\n", encoding="utf-8")
        return 0
    errors = check()
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1
    print("Capability completion ledger is coherent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
