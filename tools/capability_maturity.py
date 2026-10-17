"""Capability completion ledger validation and matrix rendering.

Schema /2 (OD-6, 2026-10-18): besides ``capabilities`` (maturity stages, 19 gates) the ledger holds
``research_programs`` -- entries with their OWN gate vocabulary and NO stage -- and ``active_epic`` may name
either.  A research program result never promotes a capability: programs never enter ``computed_stage``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "project" / "scientific_capability_completion.json"
MATRIX = ROOT / "docs" / "SCIENTIFIC_CAPABILITY_MATRIX.md"

SCHEMA = "forge.scientific_capability_completion/2"
PREVIOUS_SCHEMA = "forge.scientific_capability_completion/1"
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

PROGRAM_FIELDS = frozenset({
    "id", "kind", "title", "contract", "owner", "allowed_scope", "prohibited", "planned_capabilities", "gates", "exit",
})
PROGRAM_GATE_FIELDS = frozenset({"id", "title", "requires", "status", "evidence", "next_action"})
PROGRAM_STATUSES = frozenset({"PASS", "FAIL", "MISSING", "BLOCKED_WITH_EVIDENCE", "DEFERRED_BY_OWNER"})
#: a program gate outcome that decides the gate (MISSING and DEFERRED_BY_OWNER decide nothing)
DECIDED = frozenset({"PASS", "FAIL", "BLOCKED_WITH_EVIDENCE"})

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
    if data.get("schema") == PREVIOUS_SCHEMA:
        raise ValueError(f"capability completion schema {PREVIOUS_SCHEMA} is superseded: migrate the ledger to {SCHEMA}")
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


def _evidence_problems(owner: str, evidence: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(evidence, list):
        return [f"{owner}: evidence must be an array"]
    for reference in evidence:
        if not isinstance(reference, str) or not reference.strip():
            problems.append(f"{owner}: evidence entries must be non-empty paths")
            continue
        path_text = reference.split("::", 1)[0]
        if not (ROOT / path_text).exists():
            problems.append(f"{owner}: evidence path does not exist: {path_text}")
    return problems


def validate_programs(programs: Any) -> list[str]:
    """Research programs: gates with their own vocabulary, never a maturity stage (OD-6)."""
    errors: list[str] = []
    if not isinstance(programs, list):
        return ["research_programs must be an array"]
    for program in programs:
        if not isinstance(program, dict):
            errors.append("every research program must be an object")
            continue
        pid = str(program.get("id", "")).strip() or "<missing>"
        forbidden = sorted(({"declared_stage"} | set(GATES)) & set(program))
        if forbidden:
            errors.append(f"{pid}: a research program carries no maturity vocabulary ({forbidden})")
        if set(program) != PROGRAM_FIELDS:
            errors.append(f"{pid}: research program fields must be exactly {sorted(PROGRAM_FIELDS)}")
        if program.get("kind") != "research_program":
            errors.append(f"{pid}: kind must be research_program")
        for field_name in ("title", "contract", "owner", "exit"):
            if not str(program.get(field_name, "")).strip():
                errors.append(f"{pid}: {field_name} must be non-empty")
        for field_name in ("contract", "owner"):
            path_text = str(program.get(field_name, "")).strip()
            if path_text and not (ROOT / path_text).exists():
                errors.append(f"{pid}: {field_name} path does not exist: {path_text}")
        for field_name in ("allowed_scope", "prohibited", "gates"):
            value = program.get(field_name)
            if not isinstance(value, list) or not value:
                errors.append(f"{pid}: {field_name} must be a non-empty array")
        planned = program.get("planned_capabilities", [])
        if not isinstance(planned, list):
            errors.append(f"{pid}: planned_capabilities must be an array")
        gates = program.get("gates")
        if not isinstance(gates, list):
            continue
        seen: dict[str, str] = {}
        for gate in gates:
            if not isinstance(gate, dict):
                errors.append(f"{pid}: every gate must be an object")
                continue
            gid = str(gate.get("id", "")).strip() or "<missing>"
            where = f"{pid}.{gid}"
            if set(gate) != PROGRAM_GATE_FIELDS:
                errors.append(f"{where}: gate fields must be exactly {sorted(PROGRAM_GATE_FIELDS)}")
            if gid in GATES or gid in RANK:
                errors.append(f"{where}: a program gate may not reuse maturity vocabulary")
            if gid in seen:
                errors.append(f"{pid}: gate ids must be unique ({gid})")
            status = gate.get("status")
            if status not in PROGRAM_STATUSES:
                errors.append(f"{where}: invalid status {status!r}")
                seen[gid] = "MISSING"
                continue
            requires = gate.get("requires")
            if not isinstance(requires, list):
                errors.append(f"{where}: requires must be an array")
                requires = []
            for required in requires:
                if required not in seen:
                    errors.append(f"{where}: requires {required!r}, which is not an EARLIER gate")
                elif status in DECIDED and seen[required] != "PASS":
                    errors.append(f"{where}: {status} needs {required!r} PASS first (it is {seen[required]})")
            evidence = gate.get("evidence", [])
            errors += _evidence_problems(where, evidence)
            if status in ("PASS", "FAIL") and not evidence:
                errors.append(f"{where}: {status} requires evidence")
            if status in ("MISSING", "BLOCKED_WITH_EVIDENCE") and not str(gate.get("next_action", "")).strip():
                errors.append(f"{where}: {status} requires next_action")
            seen[gid] = status
    return errors


def _program_decided(program: dict[str, Any]) -> bool:
    gates = program.get("gates") or []
    return bool(gates) and all(isinstance(g, dict) and g.get("status") in DECIDED for g in gates)


def validate(data: dict[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        return ("capabilities must be a non-empty array",)

    ids = [str(cap.get("id", "")).strip() for cap in capabilities if isinstance(cap, dict)]
    if len(ids) != len(set(ids)):
        errors.append("capability ids must be unique")
    programs = data.get("research_programs", [])
    errors += validate_programs(programs)
    program_ids = [str(p.get("id", "")).strip() for p in programs if isinstance(p, dict)] if isinstance(programs, list) else []
    if len(program_ids) != len(set(program_ids)):
        errors.append("research program ids must be unique")
    if set(program_ids) & set(ids):
        errors.append(f"ids must be unique across capabilities and research programs: {sorted(set(program_ids) & set(ids))}")

    for cap in capabilities:
        if not isinstance(cap, dict):
            errors.append("every capability must be an object")
            continue
        expected_fields = {
            "id", "kind", "title", "owner", "declared_stage",
            "summary", "next_actions", "gates",
        }
        cid = str(cap.get("id", "")).strip() or "<missing>"
        if set(cap) != expected_fields:
            errors.append(
                f"{cid}: capability fields must be exactly {sorted(expected_fields)}"
            )
        for field_name in ("kind", "title", "owner", "summary"):
            if not str(cap.get(field_name, "")).strip():
                errors.append(f"{cid}: {field_name} must be non-empty")
        owner = str(cap.get("owner", "")).strip()
        if owner and not (ROOT / owner).exists():
            errors.append(f"{cid}: owner path does not exist: {owner}")
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
            if status == "PASS" and isinstance(evidence, list):
                for reference in evidence:
                    if not isinstance(reference, str) or not reference.strip():
                        continue
                    path_text = reference.split("::", 1)[0]
                    if not (ROOT / path_text).exists():
                        errors.append(
                            f"{cid}.{name}: evidence path does not exist: {path_text}"
                        )
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
    if active in ids and active not in program_ids:
        active_cap = next(cap for cap in capabilities if cap["id"] == active)
        if computed_stage(active_cap) == "PRODUCTION_READY":
            errors.append("active_epic is already PRODUCTION_READY; choose the next epic")
    elif active in program_ids and active not in ids:
        active_program = next(p for p in programs if isinstance(p, dict) and p.get("id") == active)
        if _program_decided(active_program):
            errors.append("active_epic is a research program whose every gate is decided; the owner names the next epic")
    else:
        errors.append("active_epic must identify a tracked capability or research program")

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
        f"Active completion epic: {data['active_epic']} ({_epic_kind(data)})",
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

    programs = data.get("research_programs", [])
    if programs:
        lines += [
            "",
            "## Research programs",
            "",
            "| Program | Gate | Status | Requires | Next action |",
            "|---|---|---|---|---|",
        ]
        for program in programs:
            for gate in program["gates"]:
                lines.append("| " + " | ".join((
                    program["id"], gate["id"], gate["status"], ", ".join(gate["requires"]) or "-",
                    gate.get("next_action", "") or "-",
                )) + " |")

    lines += [
        "",
        "## Policy",
        "",
        "A capability epic is finished only when its computed stage reaches PRODUCTION_READY; a research-program epic when every program gate is decided.",
        "Until then, horizontal expansion into new capability foundations outside the epic's scope is paused unless an explicit exception is recorded.",
        "A research program has gates, not maturity stages. A research result never promotes a capability.",
        "Every MISSING gate must carry a concrete next action. NOT_APPLICABLE requires a rationale.",
        "",
    ]
    return "\n".join(lines)


def _epic_kind(data: dict[str, Any]) -> str:
    programs = {p["id"] for p in data.get("research_programs", [])}
    return "research program" if data["active_epic"] in programs else "capability"


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
