"""Metamorphic shadows: the same physical state, said differently.

A shadow is not a new case and carries no independent truth. It is an
*invariance probe*: it names a parent case and a transformation that a correct
system must not notice. Where the transformation is genuinely semantics-free
the shadow's semantic outcome must equal its parent's; where it is not -- an
affine unit standing in for a span is the one that is not -- the shadow says so
and the difference is the finding.

Exact serialization bytes are never required to match. 25 degC and 298.15 K are
the same state and need not print the same.
"""

from __future__ import annotations

import json
import random

from . import units

TRANSFORMATIONS = (
    "equivalent_units",
    "declaration_order",
    "serialization_round_trip",
    "integer_spelling",
    "provenance_metadata",
    "affine_span_probe",
)


def _alternative_unit(current: str, options: tuple[str, ...], rng) -> str | None:
    """Another spelling of the same dimension, on a ratio scale."""
    alternatives = [
        u
        for u in options
        if u != current
        and units.dimension(u) == units.dimension(current)
        and units.is_ratio_scale(u) == units.is_ratio_scale(current)
    ]
    return rng.choice(sorted(alternatives)) if alternatives else None


def equivalent_units(case: dict, spec, rng) -> dict | None:
    declaration = dict(case["declaration"])
    changed: list[str] = []
    for name, entry in sorted(declaration.items()):
        options = spec.units.get(name)
        if not options:
            continue
        if name in spec.span_fields:
            options = tuple(u for u in options if units.is_ratio_scale(u))
        alternative = _alternative_unit(entry["unit"], options, rng)
        if alternative is None:
            continue
        si = units.to_si(entry["value"], entry["unit"])
        spec_alt = units.parse(alternative)
        declaration[name] = {
            "value": (si - spec_alt.offset) / spec_alt.factor,
            "unit": alternative,
        }
        changed.append(name)
    if not changed:
        return None
    return {"declaration": declaration, "detail": {"fields_respelled": changed}}


def declaration_order(case: dict, spec, rng) -> dict | None:
    items = list(case["declaration"].items())
    if len(items) < 2:
        return None
    rng.shuffle(items)
    if [k for k, _ in items] == list(case["declaration"]):
        return None
    return {"declaration": dict(items), "detail": {"reordered": True}}


def serialization_round_trip(case: dict, spec, rng) -> dict | None:
    """Through JSON and back. A state that does not survive its own wire is not one."""
    recovered = json.loads(json.dumps(case["declaration"], sort_keys=True))
    return {"declaration": recovered, "detail": {"via": "json round trip, sorted keys"}}


def integer_spelling(case: dict, spec, rng) -> dict | None:
    """1.0 and 1 are the same number. A record that disagrees has a type leak."""
    declaration = dict(case["declaration"])
    changed = []
    for name, entry in sorted(declaration.items()):
        value = entry["value"]
        if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
            declaration[name] = {"value": int(value), "unit": entry["unit"]}
            changed.append(name)
    if not changed:
        return None
    return {"declaration": declaration, "detail": {"fields_as_integers": changed}}


def provenance_metadata(case: dict, spec, rng) -> dict | None:
    """A label nothing scientific reads. Changing it must change nothing."""
    return {
        "declaration": dict(case["declaration"]),
        "detail": {
            "metadata": {
                "operator": "blind-v2",
                "note": "a provenance label carries no scientific content",
                "nonce": rng.randrange(10**9),
            }
        },
    }


def affine_span_probe(case: dict, spec, rng) -> dict | None:
    """The one transformation that is *not* semantics-free, and says so.

    A span restated on an affine scale -- 40 K becoming 40 degC -- is ambiguous
    by construction. Paired with its ratio-scale parent it separates the two
    readings a system might take: a system that refuses agrees with the parent
    on nothing and is right to; one that reads 40 degC as a 40 K span agrees
    with the parent exactly; one that reads it as 313.15 K disagrees and has
    silently confused a state with a difference.
    """
    spans = sorted(spec.span_fields & set(case["declaration"]))
    if not spans:
        return None
    field_name = rng.choice(spans)
    declaration = dict(case["declaration"])
    entry = declaration[field_name]
    kelvin_span = units.si_span(entry["value"], entry["unit"])
    declaration[field_name] = {"value": kelvin_span, "unit": "degC"}
    return {
        "declaration": declaration,
        "detail": {
            "field": field_name,
            "kelvin_span": kelvin_span,
            "state_reading_kelvin": kelvin_span + 273.15,
            "invariance_expected": False,
            "adjudication": (
                "refusal agrees with the challenge; a span reading is a "
                "defensible policy difference; a state reading is a silent "
                "confusion of a difference with an absolute temperature"
            ),
        },
    }


BUILDERS = {
    "equivalent_units": equivalent_units,
    "declaration_order": declaration_order,
    "serialization_round_trip": serialization_round_trip,
    "integer_spelling": integer_spelling,
    "provenance_metadata": provenance_metadata,
    "affine_span_probe": affine_span_probe,
}


def build_for_system(spec, cases: list[dict], seed: str) -> list[dict]:
    """At least one shadow for a spread of this system's cases."""
    rng = random.Random(f"{seed}:shadow:{spec.system_id}")
    out: list[dict] = []
    eligible = [c for c in cases if c["family"] != "boundary_refusal"]
    index = 1
    for transformation in TRANSFORMATIONS:
        builder = BUILDERS[transformation]
        pool = list(eligible)
        rng.shuffle(pool)
        made = 0
        for parent in pool:
            if made >= 7:
                break
            built = builder(parent, spec, rng)
            if built is None:
                continue
            out.append(
                {
                    "shadow_id": f"{parent['case_id']}-S{index:03d}",
                    "parent_case_id": parent["case_id"],
                    "system": spec.system_id,
                    "model_id": parent["model_id"],
                    "transformation": transformation,
                    "semantics_preserving": transformation != "affine_span_probe",
                    "declaration": built["declaration"],
                    "extras": parent.get("extras") or {},
                    "detail": built["detail"],
                }
            )
            index += 1
            made += 1
    return out
