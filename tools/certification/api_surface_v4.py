"""The V4 deep API surface: the method signatures and enum member POSITIONS the digests could not see.

    python -m tools.certification.api_surface_v4 > certification/core_v4_api_surface.json

WHY A SECOND SURFACE
--------------------
The re-audit's finding 94 measured the gap by deleting two methods -- ``ScientificResult.record_values``
and ``ValidationReport.evidence_basis`` -- and watching the V1 and V2 frozen digests hold still.
``engcore.api_snapshot`` describes MODULE-LEVEL symbols: a class's kind, its signature, its dataclass
fields, its enum members. Not one method. So the object a consumer actually calls could lose a method
without moving any number the freeze policy quotes.

Finding 95 is the other half: 13 ``RouteReason`` members changed position with nothing detecting it.
The snapshot does record enum members as an ordered list, so a reorder does move its bytes -- but
nothing SAID that order was part of the contract, and a comparison written over sets would have been
accepted as equivalent. Here each member carries its position explicitly, so the claim is written
down rather than implied by a JSON array.

WHY NOT EXTEND ``engcore.api_snapshot``
---------------------------------------
Because it would move the V1 frozen digest, which Core Freeze V1, V2 and V3 all pin. Those manifests
are records of their own commits and are never rewritten, and a V4 that changed what the V1 number
MEANS would make three published contracts unverifiable to gain one check. So this is an ADDITIVE
surface in the certification control plane, with its own file and its own digest, and the V1 contract
keeps meaning exactly what it meant.

WHAT IS RECORDED
----------------
For every FROZEN symbol of the V1 canonical modules (the contract, not the experimental scaffolding):

* ``methods``: every public callable attribute defined on the class, by name, with its full parameter
  list -- name, kind, and whether it has a default -- and whether it is a classmethod, staticmethod or
  property. Inherited methods are recorded too, because a consumer calls what the object has;
* ``enum_members``: name, value and POSITION;
* ``dataclass_field_order``: the field names in order, which is what an additive-only comparator
  reads for a reorder.

Recorded by NAME and SIGNATURE. A method whose body changed is not visible here -- that is what the
575-mutation population and the suites are for -- and a private helper is not a promise.
"""

from __future__ import annotations

import dataclasses
import enum
import hashlib
import inspect
import json
from typing import Any

from engcore import api_snapshot

SCHEMA = "engcore.api_surface_v4/1"

#: A method whose name starts with one underscore is not a promise. The dunders below ARE part of
#: what a record is, so they are recorded by name: a dataclass that stops comparing by value, or a
#: record that stops hashing, changes what every consumer of it can do.
RECORDED_DUNDERS = ("__eq__", "__hash__", "__iter__", "__len__", "__contains__", "__getitem__")


def _parameters(value: Any) -> list[dict[str, Any]] | None:
    try:
        signature = inspect.signature(value)
    except (TypeError, ValueError):
        return None
    return [
        {"name": parameter.name, "kind": parameter.kind.name,
         "has_default": parameter.default is not inspect.Parameter.empty}
        for parameter in signature.parameters.values()
    ]


def _method_entry(owner: type, name: str) -> dict[str, Any] | None:
    raw = inspect.getattr_static(owner, name, None)
    if raw is None:
        return None
    if isinstance(raw, property):
        return {"role": "property", "parameters": []}
    role = "method"
    value = raw
    if isinstance(raw, classmethod):
        role, value = "classmethod", raw.__func__
    elif isinstance(raw, staticmethod):
        role, value = "staticmethod", raw.__func__
    if not callable(value):
        return None
    parameters = _parameters(value)
    if parameters is None:
        return None
    return {"role": role, "parameters": parameters}


def methods_of(value: Any) -> dict[str, dict[str, Any]] | None:
    """Every public callable a consumer of this class can call, with its signature."""
    if not inspect.isclass(value):
        return None
    found: dict[str, dict[str, Any]] = {}
    for name in dir(value):
        if name.startswith("_") and name not in RECORDED_DUNDERS:
            continue
        if isinstance(value, type) and issubclass(value, enum.Enum) and name in value.__members__:
            continue
        entry = _method_entry(value, name)
        if entry is not None:
            found[name] = entry
    return found


def build(*, modules: tuple[str, ...] = api_snapshot.CANONICAL_MODULES) -> dict[str, Any]:
    """The deep surface of the FROZEN symbols of ``modules``."""
    snapshot = api_snapshot.build(modules=modules)
    symbols: list[dict[str, Any]] = []
    for entry in snapshot["symbols"]:
        if entry["classification"] not in ("FREEZE", "DEPRECATED"):
            continue
        module = __import__(entry["module"], fromlist=[entry["name"]])
        value = getattr(module, entry["name"])
        described: dict[str, Any] = {
            "module": entry["module"], "name": entry["name"], "kind": entry["kind"],
        }
        methods = methods_of(value)
        if methods is not None:
            described["methods"] = methods
        if inspect.isclass(value) and issubclass(value, enum.Enum):
            described["enum_members"] = [
                {"name": member.name, "value": member.value, "position": position}
                for position, member in enumerate(value)
            ]
        if inspect.isclass(value) and dataclasses.is_dataclass(value):
            described["dataclass_field_order"] = [f.name for f in dataclasses.fields(value)]
        symbols.append(described)
    symbols.sort(key=lambda item: (item["module"], item["name"]))
    return {
        "schema": SCHEMA,
        "modules": list(modules),
        "symbol_count": len(symbols),
        "method_count": sum(len(item.get("methods", {})) for item in symbols),
        "symbols": symbols,
    }


def canonical_bytes(surface: dict[str, Any] | None = None) -> bytes:
    payload = build() if surface is None else surface
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def digest(surface: dict[str, Any] | None = None) -> str:
    return hashlib.sha256(canonical_bytes(surface)).hexdigest()


if __name__ == "__main__":  # pragma: no cover - a tool entry point
    import sys

    if "--digest" in sys.argv:
        print(digest())
    else:
        text = json.dumps(build(), indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        sys.stdout.buffer.write((text + chr(10)).encode("utf-8"))
