"""Phase 1 — inventory every shipped record that describes behaviour.

Read-only. This walks the shipped model definitions and writes down, for each
one, what it *claims*: the description, the validity narrative, the assumptions
and exclusions, which inputs it marks required, and — the part this round turns
on — every clause in a condition's description that promises something about
when the condition is UNKNOWN, or that describes a cross-check.

Nothing here decides whether a claim is true. That is Phase 2.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROUND = HERE.parent
REPO = ROUND.parent.parent
sys.path.insert(0, str(REPO / "src"))

DECLARING_MODULES = (
    "engcore.domains.thermal_models.lumped",
    "engcore.domains.thermal.conduction1d.problem",
    "engcore.domains.battery.models",
    "engcore.domains.electrical.dc.models",
    "engcore.domains.electrical.material",
    "engcore.domains.electrical.dc_applicability",
    "engcore.domains.kinetics.cstr.problem",
    "engcore.domains.kinetics.cstr.alternatives",
)

#: Where each system's derived quantities are actually assembled. This is the
#: implementation side of the comparison, named per system rather than guessed.
ASSEMBLERS = {
    "thermal.lumped": "engcore.domains.thermal_models.context",
    "electrical.material": "engcore.domains.electrical.material",
    "battery.cell": "engcore.domains.battery.context",
    "kinetics.cstr": "engcore.domains.kinetics.cstr.context",
    "electrical.dc": "engcore.domains.electrical.dc.models",
    "thermal.conduction1d": "engcore.domains.thermal.conduction1d.problem",
}

#: A description that promises UNKNOWN in a named circumstance. The two spellings
#: below are the ones the shipped records actually use.
UNKNOWN_CLAUSE = re.compile(
    r"(UNKNOWN\s+(?:unless|only\s+when|when|without)\b[^.]*\.)", re.IGNORECASE
)
#: A description that claims two routes were compared, or that one was enough.
CROSSCHECK_CLAUSE = re.compile(
    r"([^.]*\b(?:cross-check|two routes|both routes|one route|routes to one|"
    r"agreement|agree|compare[sd]?)\b[^.]*\.)",
    re.IGNORECASE,
)

#: Named declarations a clause may refer to. Extracted so Phase 2 can drop
#: exactly those and see what the runtime does.
IDENTIFIER = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b")


def system_of(model_id: str) -> str:
    return ".".join(model_id.split(".")[:2])


def record_file(model, module_name: str) -> str:
    try:
        return str(pathlib.Path(inspect.getfile(sys.modules[module_name])).relative_to(REPO))
    except Exception:
        return module_name


def clauses(description: str) -> dict:
    unknown = [c.strip() for c in UNKNOWN_CLAUSE.findall(description or "")]
    cross = [c.strip() for c in CROSSCHECK_CLAUSE.findall(description or "")]
    named: list[str] = []
    for clause in unknown:
        named.extend(IDENTIFIER.findall(clause))
    return {
        "unknown_clauses": unknown,
        "unknown_clause_named_declarations": sorted(set(named)),
        "crosscheck_clauses": cross,
    }


def collect() -> dict:
    from engcore.scientific.models.definition import ScientificModelDefinition

    found: dict[tuple[str, str], tuple[object, str]] = {}
    for module_name in DECLARING_MODULES:
        module = importlib.import_module(module_name)
        for attr in dir(module):
            value = getattr(module, attr)
            if isinstance(value, ScientificModelDefinition):
                found[(value.model_id, value.version)] = (value, module_name)

    models = []
    total_claims = 0
    for (model_id, version), (model, module_name) in sorted(found.items()):
        system = system_of(model_id)
        conditions = []
        for condition in model.validity.conditions:
            payload = condition.to_dict()
            payload.pop("schema", None)
            payload["condition_type"] = type(condition).__name__
            payload.update(clauses(payload.get("description", "")))
            conditions.append(payload)

        required = [i.name for i in model.inputs if i.required]
        optional = [i.name for i in model.inputs if not i.required]
        claim_count = (
            1  # the model description itself
            + 1  # the validity narrative
            + len(model.assumptions)
            + len(model.exclusions or ())
            + len(conditions)
            + len(model.inputs)
        )
        total_claims += claim_count
        models.append(
            {
                "system": system,
                "domain": model.domain,
                "model_id": model_id,
                "version": version,
                "name": model.name,
                "record_file": record_file(model, module_name),
                "implementation_file": str(
                    pathlib.Path(
                        importlib.import_module(ASSEMBLERS[system]).__file__
                    ).relative_to(REPO)
                ),
                "published_claim": model.description,
                "validity_claim": model.validity.description,
                "model_type": model.model_type.value,
                "validation_status": model.validation_status.value,
                "required_capabilities": sorted(model.required_capabilities),
                "required_inputs_per_record": required,
                "optional_inputs_per_record": optional,
                "declared_outputs": [o.metric for o in model.outputs],
                "assumptions": list(model.assumptions),
                "exclusions": list(model.exclusions) if model.exclusions else None,
                "derived_quantities": sorted(model.validity.derived_quantities),
                "conditions": conditions,
                "claims_counted": claim_count,
                "status": "UNREVIEWED",
            }
        )

    systems: dict[str, list[str]] = {}
    for entry in models:
        systems.setdefault(entry["system"], []).append(entry["model_id"])

    return {
        "schema": "contract_integrity_surface/1",
        "what_this_is": (
            "Every shipped model record that describes behaviour, and what it "
            "claims. Read-only inventory. No claim here has been checked yet; "
            "status is UNREVIEWED for all of them until Phase 2."
        ),
        "systems": {k: sorted(v) for k, v in sorted(systems.items())},
        "system_count": len(systems),
        "model_count": len(models),
        "claim_count": total_claims,
        "condition_count": sum(len(m["conditions"]) for m in models),
        "unknown_clause_count": sum(
            len(c["unknown_clauses"]) for m in models for c in m["conditions"]
        ),
        "crosscheck_clause_count": sum(
            len(c["crosscheck_clauses"]) for m in models for c in m["conditions"]
        ),
        "models": models,
    }


def main() -> int:
    payload = collect()
    out = ROUND / "CONTRACT_SURFACE.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    out.write_text(text, encoding="utf-8")
    print(
        f"systems={payload['system_count']} models={payload['model_count']} "
        f"conditions={payload['condition_count']} claims={payload['claim_count']}"
    )
    print(
        f"UNKNOWN-unless clauses={payload['unknown_clause_count']}  "
        f"cross-check clauses={payload['crosscheck_clause_count']}"
    )
    print("sha256:", hashlib.sha256(text.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
