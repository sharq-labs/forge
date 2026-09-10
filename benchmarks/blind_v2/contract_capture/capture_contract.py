"""Capture the DECLARED contract surface of the shipped scientific models.

This is the ONE place in Blind Challenge v2 that imports ``engcore``, and it
runs exactly once, before the challenge is generated. It reads *declarations*
-- model identity, declared inputs and their units, declared outputs, and the
declared validity conditions with their bounds -- and writes them to JSON.

It does not read, and cannot read, how a verdict is decided: a condition's
``to_dict()`` is the record the model publishes about itself, not the code
that evaluates it.

Everything downstream of this script -- generator, oracles, truth, shadows --
reads the JSON and never imports engcore. ``challenge/audit.py`` enforces that
mechanically, and this file is deliberately outside the package it audits.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

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

#: model_id prefix -> system id. Six systems; the split is the model_id's own
#: first two segments, which is how the shipped records name themselves.
def system_of(model_id: str) -> str:
    return ".".join(model_id.split(".")[:2])


def capture() -> dict:
    from engcore.scientific.models.definition import ScientificModelDefinition

    found: dict[tuple[str, str], object] = {}
    for module_name in DECLARING_MODULES:
        module = importlib.import_module(module_name)
        for attr in dir(module):
            value = getattr(module, attr)
            if isinstance(value, ScientificModelDefinition):
                found[(value.model_id, value.version)] = value

    models = []
    for (model_id, version), model in sorted(found.items()):
        conditions = []
        for condition in model.validity.conditions:
            payload = condition.to_dict()
            payload.pop("schema", None)
            payload["condition_type"] = type(condition).__name__
            conditions.append(payload)
        models.append(
            {
                "model_id": model_id,
                "version": version,
                "system": system_of(model_id),
                "domain": model.domain,
                "model_type": model.model_type.value,
                "validation_status": model.validation_status.value,
                "name": model.name,
                "required_capabilities": sorted(model.required_capabilities),
                "inputs": [
                    {
                        "name": spec.name,
                        "source_kind": spec.source_kind.value,
                        "unit_exemplar": spec.unit_exemplar,
                        "value_kind": spec.value_kind.value if spec.value_kind else None,
                        "role": spec.role.value if spec.role else None,
                        "required": bool(spec.required),
                        "varies_with": spec.varies_with,
                    }
                    for spec in model.inputs
                ],
                "outputs": [
                    {"metric": out.metric, "unit_exemplar": out.unit_exemplar}
                    for out in model.outputs
                ],
                "assumptions": list(model.assumptions),
                "exclusions": list(model.exclusions or ()) if model.exclusions else None,
                "validity_description": model.validity.description,
                "derived_quantities": sorted(model.validity.derived_quantities),
                "conditions": conditions,
            }
        )

    systems: dict[str, list[str]] = {}
    for entry in models:
        systems.setdefault(entry["system"], []).append(entry["model_id"])

    return {
        "schema": "blind_v2_contract_capture/1",
        "what_this_is": (
            "Declared model records as the shipped Core publishes them. "
            "Declarations only: no verdict, validation, consensus or reason "
            "implementation was read to produce this file."
        ),
        "systems": {k: sorted(v) for k, v in sorted(systems.items())},
        "system_count": len(systems),
        "model_count": len(models),
        "models": models,
    }


def main() -> int:
    payload = capture()
    out = HERE.parent / "CONTRACT_SURFACE.json"
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    out.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(f"systems={payload['system_count']} models={payload['model_count']}")
    print(f"wrote {out.relative_to(ROOT)}  sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
