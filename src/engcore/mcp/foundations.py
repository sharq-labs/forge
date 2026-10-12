"""MCP transport for the Big Rocks foundations: describe -> plan -> run (bounded screening).

Transport only.  Every answer is read off the authoritative records
(geometry shape table, parameter kinds, fidelity ladder, product templates,
provider registry); nothing here decides science.  Inputs supplied through
MCP are caller assertions: a declared input must carry a ``source_ref`` and
is recorded as such -- it is not evidence.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..design.multifidelity import standard_ladder
from ..providers import default_registry
from ..providers.health import assess_health
from ..scientific.units.quantity import Quantity
from ..spatial.geometry import IMPORT_FORMATS, SHAPE_TABLE
from ..spatial.parametric import ParameterKind
from ..systems.products import IN_REPOSITORY, TEMPLATES, TemplateRefusal, capability_report, coupled_hover_screening, hover_screening

FOUNDATIONS_SCHEMA = "mcp_engineering_foundations/1"
PRODUCT_PLAN_SCHEMA = "mcp_product_plan/1"
PRODUCT_SCREENING_SCHEMA = "mcp_product_screening/1"

#: Bounded executable screening paths per product (the first is the default).  A product absent here has none, and says so.
SCREENINGS = {"drone": {"hover_screening": hover_screening, "coupled_hover": coupled_hover_screening}}


def _q(q: Quantity) -> dict[str, Any]:
    return {"magnitude": q.magnitude, "unit": str(q.units)}


def describe_engineering_platform() -> dict[str, Any]:
    """Geometry primitives, parameter kinds, fidelity ladder, product templates and provider health -- all read off records."""
    registry = default_registry()
    providers = []
    for status in registry.discover():
        report = assess_health(status)
        providers.append({"provider_id": status.capability.provider_id, "family": status.capability.family,
                          "health": report.health.value, "reason": report.reason})
    return {
        "schema": FOUNDATIONS_SCHEMA,
        "geometry": {"shapes": [{"kind": k.value, "dimensions": list(dims), "dimension": d, "features": list(f)}
                                for k, (dims, d, f) in SHAPE_TABLE.items()],
                     "import_formats": list(IMPORT_FORMATS), "length_unit": "meter (canonical); every input needs a unit",
                     "rule": "provider tags never become Forge identity; imported geometry needs a declared, checked unit"},
        "parameter_kinds": [k.value for k in ParameterKind],
        "fidelity_ladder": standard_ladder().to_dict(),
        "products": [{"product": name, "inputs": [i.to_dict() for i in t.inputs],
                      "participants": [p.to_dict() for p in t.participants], "screenings": list(SCREENINGS.get(name, {}))}
                     for name, t in ((n, f()) for n, f in sorted(TEMPLATES.items()))],
        "providers": providers,
        "authority": ("available is not qualified; supported is not validated; search results are not evidence; "
                      "an MCP-declared input is a caller assertion with its source_ref, never evidence"),
    }


def _declared(raw: Mapping[str, Any] | None) -> dict[str, tuple[Quantity, str]]:
    out = {}
    for key, spec in dict(raw or {}).items():
        if not isinstance(spec, Mapping) or set(spec) != {"magnitude", "unit", "source_ref"}:
            raise TemplateRefusal(f"input {key!r} must be {{magnitude, unit, source_ref}}; a value without a unit and a source is refused")
        out[str(key)] = (Quantity(spec["magnitude"], str(spec["unit"])), str(spec["source_ref"]))
    return out


def _template(product: str, inputs: Mapping[str, Any] | None):
    if product not in TEMPLATES:
        raise TemplateRefusal(f"unknown product {product!r}; known: {sorted(TEMPLATES)}")
    declared = _declared(inputs)
    if product == "drone":  # the drone's structure is built FROM its declared inputs (one source of truth)
        return TEMPLATES[product](declared)
    return TEMPLATES[product]().with_inputs(declared)


def plan_product(product: str, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    """The product's structure, which inputs are still UNKNOWN, and per-participant capability here."""
    try:
        t = _template(product, inputs)
    except Exception as exc:  # noqa: BLE001 - every refusal is returned, typed
        return {"schema": PRODUCT_PLAN_SCHEMA, "status": "refused", "error": type(exc).__name__, "message": str(exc)}
    report = capability_report(t, default_registry(), in_repository=IN_REPOSITORY)
    return {"schema": PRODUCT_PLAN_SCHEMA, "status": "planned", "product": product, "template_digest": t.digest,
            "assembly_digest": t.assembly.digest,
            "instances": [{"instance_id": i.instance_id, "parent": i.parent_id, "level": t.assembly.level(i.instance_id).value}
                          for i in t.assembly.system.instances],
            "unknown_inputs": list(t.unknown_inputs()), "inputs": [i.to_dict() for i in t.inputs],
            "capability": [c.to_dict() for c in report], "couplings": [c.to_dict() for c in t.couplings],
            "screenings": list(SCREENINGS.get(product, {})),
            "note": "a plan is a capability statement; READY means runnable here, not qualified and not validated"}


def run_product_screening(product: str, inputs: dict[str, Any] | None = None, screening: str | None = None) -> dict[str, Any]:
    """Run one of the product's bounded screening paths from declared inputs; refused while any needed input is UNKNOWN."""
    try:
        t = _template(product, inputs)
        if product not in SCREENINGS:
            raise TemplateRefusal(f"{product!r} has no executable screening path yet; its capability gaps are in plan_product")
        name = screening or next(iter(SCREENINGS[product]))
        if name not in SCREENINGS[product]:
            raise TemplateRefusal(f"{product!r} has no screening {name!r}; known: {list(SCREENINGS[product])}")
        result = SCREENINGS[product][name](t)
    except Exception as exc:  # noqa: BLE001
        return {"schema": PRODUCT_SCREENING_SCHEMA, "status": "refused", "error": type(exc).__name__, "message": str(exc)}
    return {"schema": PRODUCT_SCREENING_SCHEMA, "status": "computed", "product": product, "screening": name,
            "result": {k: (_q(v) if isinstance(v, Quantity) else list(v) if isinstance(v, tuple) else v) for k, v in result.items()},
            "verdict": "insufficient_evidence", "template_digest": t.digest}
