"""A narrow, auditable natural-language entrance to Forge.

This module does not choose physics.  It recognises declarations for the
existing electro-thermal boundary, reports every required declaration it could
not find, and only emits a runnable case when that boundary is complete.  The
recogniser is deliberately a controlled-language compiler, not an LLM hidden
inside the scientific runtime: every extracted value carries the text span and
rule that produced it, and no physical value is defaulted.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from .errors import MissingUnitError, ProblemPayloadError, WrongDimensionError
from .battery import build_battery_case
from .problem import build_electrothermal_system
from .systems import system
from ..scientific.errors import UnitCompatibilityError
from ..scientific.units.quantity import Quantity

__all__ = ["INTENT_SCHEMA", "compile_engineering_intent"]

INTENT_SCHEMA = "engineering_intent/1"


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫−", "0123456789.-")
_NUMBER = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

# Longest spellings first so ``watt/kelvin`` is not captured as ``watt``.
_UNIT = (
    r"(?:ampere[_\s-]*hour|amp(?:ere)?(?:s)?|أمبير\s*[- ]?\s*ساعة|امبير\s*[- ]?\s*ساعة|"
    r"أمبير|امبير|dimensionless|بلا\s+أبعاد|دون\s+أبعاد|"
    r"joule\s*/\s*kelvin|watt\s*/\s*kelvin|1\s*/\s*kelvin|"
    r"جول\s*/\s*(?:كلفن|كلفين)|وات\s*/\s*(?:كلفن|كلفين)|"
    r"لكل\s+(?:كلفن|كلفين)|per\s+kelvin|"
    r"volt(?:s)?|فولت|ohm(?:s)?|أوم|اوم|kelvin|كلفن|كلفين|"
    r"second(?:s)?|ثانية|ثوان(?:ي)?|joule|جول|watt|وات)"
)

_UNIT_CANONICAL = {
    "فولت": "volt",
    "أوم": "ohm",
    "اوم": "ohm",
    "كلفن": "kelvin",
    "كلفين": "kelvin",
    "ثانية": "second",
    "ثوان": "second",
    "ثواني": "second",
    "جول": "joule",
    "وات": "watt",
    "أمبير": "ampere",
    "امبير": "ampere",
    "أمبير ساعة": "ampere_hour",
    "امبير ساعة": "ampere_hour",
    "أمبير-ساعة": "ampere_hour",
    "امبير-ساعة": "ampere_hour",
    "بلا أبعاد": "dimensionless",
    "دون أبعاد": "dimensionless",
    "لكل كلفن": "1/kelvin",
    "لكل كلفين": "1/kelvin",
    "per kelvin": "1/kelvin",
    "جول/كلفن": "joule/kelvin",
    "جول/كلفين": "joule/kelvin",
    "وات/كلفن": "watt/kelvin",
    "وات/كلفين": "watt/kelvin",
    "ampere hour": "ampere_hour",
    "ampere-hour": "ampere_hour",
    "amp hours": "ampere_hour",
    "amps": "ampere",
}


@dataclass(frozen=True)
class _Rule:
    path: str
    names: tuple[str, ...]
    question_ar: str


_RULES = (
    _Rule("source_voltage", ("source voltage", "جهد المصدر"), "ما جهد المصدر؟"),
    _Rule(
        "stages[0].conductor.reference_resistance",
        ("reference resistance", "المقاومة المرجعية", "مقاومة مرجعية"),
        "ما المقاومة المرجعية للموصل؟",
    ),
    _Rule(
        "stages[0].conductor.temperature_coefficient",
        ("temperature coefficient", "temperature coefficient of resistance", "معامل الحرارة", "المعامل الحراري"),
        "ما معامل المقاومة الحراري؟",
    ),
    _Rule(
        "stages[0].conductor.reference_temperature",
        ("reference temperature", "درجة الحرارة المرجعية", "حرارة مرجعية"),
        "عند أي درجة حرارة عُرّفت المقاومة المرجعية؟",
    ),
    _Rule(
        "stages[0].body.heat_capacity",
        ("heat capacity", "thermal capacity", "السعة الحرارية", "سعة حرارية"),
        "ما السعة الحرارية للجسم؟",
    ),
    _Rule(
        "stages[0].body.ambient_conductance",
        ("ambient conductance", "thermal conductance to ambient", "التوصيل الحراري للمحيط", "موصلية حرارية للمحيط"),
        "ما التوصيل الحراري من الجسم إلى المحيط؟",
    ),
    _Rule(
        "stages[0].body.ambient_temperature",
        ("ambient temperature", "درجة حرارة المحيط", "حرارة المحيط", "درجة حرارة الجو", "حرارة الجو"),
        "ما درجة حرارة المحيط؟",
    ),
    _Rule(
        "stages[0].body.initial_temperature",
        ("initial temperature", "درجة الحرارة الابتدائية", "حرارة ابتدائية", "حرارة البداية"),
        "ما درجة حرارة الجسم الابتدائية؟",
    ),
    _Rule(
        "stages[0].body.duration",
        ("duration", "simulation time", "مدة المحاكاة", "المدة", "مدة"),
        "ما مدة المحاكاة؟",
    ),
)

_BATTERY_RULES = (
    _Rule(
        "cell.nominal_capacity",
        ("nominal capacity", "السعة الاسمية", "سعة البطارية"),
        "ما السعة الاسمية للخلية؟",
    ),
    _Rule(
        "cell.internal_resistance",
        ("internal resistance", "المقاومة الداخلية"),
        "ما المقاومة الداخلية للخلية؟",
    ),
    _Rule(
        "cell.open_circuit_voltage_at_full",
        ("full open circuit voltage", "open circuit voltage at full", "جهد الدائرة المفتوحة عند الامتلاء", "جهد الامتلاء"),
        "ما جهد الدائرة المفتوحة عند الامتلاء؟",
    ),
    _Rule(
        "cell.open_circuit_voltage_at_empty",
        ("empty open circuit voltage", "open circuit voltage at empty", "جهد الدائرة المفتوحة عند الفراغ", "جهد الفراغ"),
        "ما جهد الدائرة المفتوحة عند الفراغ؟",
    ),
    _Rule(
        "cell.coulombic_efficiency",
        ("coulombic efficiency", "الكفاءة الكولومية", "كفاءة كولومية"),
        "ما الكفاءة الكولومية؟",
    ),
    _Rule(
        "load.discharge_current",
        ("discharge current", "تيار التفريغ"),
        "ما تيار التفريغ؟",
    ),
    _Rule(
        "load.state_of_charge",
        ("state of charge", "حالة الشحن"),
        "ما حالة الشحن الابتدائية؟",
    ),
    _Rule(
        "load.cell_temperature",
        ("cell temperature", "درجة حرارة الخلية", "حرارة الخلية"),
        "ما درجة حرارة الخلية؟",
    ),
    _Rule(
        "load.duration",
        ("step duration", "load duration", "مدة الخطوة", "مدة الحمل"),
        "ما مدة خطوة التفريغ؟",
    ),
    _Rule(
        "thermal.heat_capacity",
        ("thermal heat capacity", "cell heat capacity", "السعة الحرارية للخلية", "سعة الخلية الحرارية"),
        "ما السعة الحرارية للخلية؟",
    ),
    _Rule(
        "thermal.ambient_temperature",
        ("thermal ambient temperature", "ambient temperature", "درجة حرارة المحيط", "حرارة المحيط"),
        "ما درجة حرارة المحيط الحراري؟",
    ),
    _Rule(
        "cell.limits.cell_thermal_conductance",
        ("cell thermal conductance", "thermal conductance", "التوصيل الحراري للخلية", "موصلية الخلية الحرارية"),
        "ما التوصيل الحراري بين الخلية والمحيط؟",
    ),
)


def _normalise_text(text: str) -> str:
    return text.translate(_DIGITS).replace("،", ",")


def _canonical_quantity(number: str, unit: str) -> str:
    compact = re.sub(r"\s*/\s*", "/", unit.strip().lower())
    canonical = _UNIT_CANONICAL.get(compact, compact)
    if canonical.endswith("s") and canonical in {"volts", "ohms", "seconds"}:
        canonical = canonical[:-1]
    return f"{number} {canonical}"


def _extract(text: str, rule: _Rule) -> tuple[str, dict[str, Any]] | None:
    alternatives = "|".join(re.escape(name) for name in rule.names)
    pattern = re.compile(
        rf"(?P<label>{alternatives})\s*(?:هي|هو|=|:)?\s*"
        rf"(?P<number>{_NUMBER})\s*(?P<unit>{_UNIT})",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if match is None:
        return None
    value = _canonical_quantity(match.group("number"), match.group("unit"))
    return value, {
        "path": rule.path,
        "value": value,
        "source": "controlled_natural_language",
        "rule": match.group("label"),
        "span": [match.start(), match.end()],
        "text": match.group(0),
    }


def _set_path(case: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node: Any = case
    for part in parts[:-1]:
        if part == "stages[0]":
            node.setdefault("stages", [{}])
            node = node["stages"][0]
        else:
            node = node.setdefault(part, {})
    node[parts[-1]] = value


def _validate_quantity_grounding(
    path: str,
    value: Any,
    description_record: Any,
) -> None:
    """Reject unparseable or dimensionally wrong quantities immediately.

    The full system builder remains the final authority on payload shape and
    scientific applicability.  This guard closes the earlier partial-intent
    hole where a bad unit was presented as a successful extraction until all
    other required fields happened to be supplied.
    """

    canonical_path = path.replace("stages[0]", "stages[]")
    try:
        field = description_record.field(canonical_path)
    except KeyError:
        return
    if field.kind not in {"quantity", "fraction"}:
        return
    if not isinstance(value, str):
        raise MissingUnitError(
            f"{path}: expected a unit-bearing quantity string, got {value!r}"
        )
    try:
        quantity = Quantity.parse(value)
    except (UnitCompatibilityError, TypeError, ValueError) as exc:
        raise MissingUnitError(
            f"{path}: could not parse a unit-bearing quantity from {value!r}"
        ) from exc
    expected = field.unit_exemplar
    if expected is not None and not quantity.is_compatible_with(expected):
        raise WrongDimensionError(
            f"{path}: got {quantity.units!r} [{quantity.dimensionality}], "
            f"expected {expected!r} [{field.dimension}]"
        )


def compile_engineering_intent(
    description: str,
    declarations: Mapping[str, Any] | None = None,
    *,
    system_name: str = "electrothermal",
) -> dict[str, Any]:
    """Compile a controlled Arabic/English description into a reviewed case.

    ``declarations`` is the deterministic correction channel: a UI or agent
    may answer the returned questions with exact dotted paths.  Unknown paths
    are refused rather than ignored.  Values still pass through the ordinary
    electro-thermal boundary, which remains the authority on units and shape.
    """
    if not isinstance(description, str) or not description.strip():
        raise ValueError("description must be a non-empty string")
    if declarations is not None and not isinstance(declarations, Mapping):
        raise TypeError("declarations must be a mapping of field path to value")

    try:
        boundary = system(system_name)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc

    text = _normalise_text(description)
    case: dict[str, Any] = (
        {"stages": [{"component_id": "R1"}]}
        if system_name == "electrothermal" else {}
    )
    extracted: list[dict[str, Any]] = []

    active_rules = (
        _RULES if system_name == "electrothermal" else _BATTERY_RULES
    )
    for rule in active_rules:
        found = _extract(text, rule)
        if found is not None:
            value, trace = found
            _set_path(case, rule.path, value)
            extracted.append(trace)

    description_record = boundary.description()
    accepted = {
        field.path.replace("stages[]", "stages[0]")
        for field in description_record.fields
    }
    if system_name == "electrothermal":
        accepted.update(
            {
                "stages[0].body.capacity_evidence.bulk_density",
                "stages[0].body.capacity_evidence.bulk_specific_heat",
                "stages[0].body.capacity_evidence.extra_heat_capacity",
            }
        )
    for path, value in (declarations or {}).items():
        if path not in accepted:
            raise ValueError(
                f"unknown declaration {path!r}; accepted paths are {sorted(accepted)}"
            )
        _set_path(case, path, value)
        extracted = [item for item in extracted if item["path"] != path]
        extracted.append({
            "path": path,
            "value": value,
            "source": "explicit_declaration",
            "rule": None,
            "span": None,
            "text": None,
        })

    grounding_diagnostics = []
    for item in extracted:
        try:
            _validate_quantity_grounding(
                item["path"], item["value"], description_record
            )
        except ProblemPayloadError as exc:
            grounding_diagnostics.append({
                "type": type(exc).__name__,
                "path": item["path"],
                "message": str(exc),
            })

    # A generated identifier carries no physical claim, but it is still made
    # visible instead of pretending the user supplied it.
    assumptions = []
    if system_name == "electrothermal" and not (
        declarations and "stages[0].component_id" in declarations
    ):
        assumptions = [{
            "path": "stages[0].component_id",
            "value": "R1",
            "kind": "generated_identifier",
            "affects_physics": False,
        }]
    elif system_name == "battery":
        generated = {
            "cell.cell_id": "C1",
            "load.load_id": "L1",
        }
        for path, value in generated.items():
            if declarations and path in declarations:
                continue
            _set_path(case, path, value)
            assumptions.append({
                "path": path,
                "value": value,
                "kind": "generated_identifier",
                "affects_physics": False,
            })

    present = {item["path"] for item in extracted}
    present.update(item["path"] for item in assumptions)
    rule_by_path = {rule.path: rule for rule in active_rules}
    questions = []
    for field in description_record.required:
        path = field.path.replace("stages[]", "stages[0]")
        if path in present:
            continue
        rule = rule_by_path.get(path)
        questions.append({
            "path": path,
            "question": (
                rule.question_ar if rule is not None
                else f"ما القيمة المطلوبة للحقل {path}؟"
            ),
            "dimension": field.dimension,
            "example_unit": field.unit_exemplar,
            "why": field.description,
        })

    resolved_conditions: set[str] = set()
    for field in description_record.optional:
        path = field.path.replace("stages[]", "stages[0]")
        if path in present:
            resolved_conditions.update(field.unlocks)
            resolved_conditions.update(field.group_unlocks)

    optional_declarations = []
    for field in description_record.optional:
        path = field.path.replace("stages[]", "stages[0]")
        if path in present:
            continue
        optional_declarations.append({
            "path": path,
            "dimension": field.dimension,
            "example_unit": field.unit_exemplar,
            "description": field.description,
            "unlocks_conditions": list(field.unlocks),
            "unresolved_conditions": [
                condition for condition in field.unlocks
                if condition not in resolved_conditions
            ],
            "alternative_to": [
                item.replace("stages[]", "stages[0]")
                for item in field.alternative_to
            ],
        })

    result: dict[str, Any] = {
        "schema": INTENT_SCHEMA,
        "system": system_name,
        "status": "needs_input" if questions else "ready",
        "original_description": description,
        "extracted": sorted(extracted, key=lambda item: item["path"]),
        "assumptions": assumptions,
        "questions": questions,
        "optional_declarations": optional_declarations,
        "unresolved_evidence_inputs": [
            item for item in optional_declarations
            if item["unresolved_conditions"]
        ],
        "case": None,
    }
    if grounding_diagnostics:
        result["status"] = "invalid"
        result["diagnostics"] = grounding_diagnostics
        return result
    if questions:
        return result

    # Shape, units and dimensions are checked by the same deterministic
    # boundary that checks a hand-authored case.  Nothing in this compiler can
    # make a malformed case runnable.
    try:
        if system_name == "electrothermal":
            build_electrothermal_system(case)
        elif system_name == "battery":
            build_battery_case(case)
        else:  # guarded by the registry lookup above
            raise AssertionError(f"no compiler validator for {system_name!r}")
    except ProblemPayloadError as exc:
        result["status"] = "invalid"
        result["diagnostics"] = [{
            "type": type(exc).__name__,
            "message": str(exc),
        }]
        return result
    result["case"] = case
    return result
