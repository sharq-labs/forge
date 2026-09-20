"""The controlled-language entrance to the existing scientific boundary."""

from __future__ import annotations

import pytest

from engcore.mcp.intent import INTENT_SCHEMA, compile_engineering_intent


ARABIC_CASE = """
جهد المصدر 5 فولت. المقاومة المرجعية 10 أوم.
معامل الحرارة 0.00393 لكل كلفن.
درجة الحرارة المرجعية 293.15 كلفن.
السعة الحرارية 2.5 جول/كلفن.
التوصيل الحراري للمحيط 0.05 وات/كلفن.
درجة حرارة المحيط 300 كلفن. درجة الحرارة الابتدائية 300 كلفن.
مدة المحاكاة 120 ثانية.
"""

ARABIC_BATTERY_CASE = """
بطارية: السعة الاسمية 2.5 أمبير ساعة. المقاومة الداخلية 0.03 أوم.
جهد الامتلاء 4.2 فولت. جهد الفراغ 3.0 فولت.
الكفاءة الكولومية 0.99 بلا أبعاد. تيار التفريغ 1.5 أمبير.
حالة الشحن 0.9 بلا أبعاد. درجة حرارة الخلية 298.15 كلفن.
مدة الخطوة 60 ثانية. السعة الحرارية للخلية 60 جول/كلفن.
درجة حرارة المحيط 298.15 كلفن.
التوصيل الحراري للخلية 0.4 وات/كلفن.
"""


def test_incomplete_prose_asks_instead_of_inventing_physics():
    intent = compile_engineering_intent("جهد المصدر 5 فولت")

    assert intent["schema"] == INTENT_SCHEMA
    assert intent["status"] == "needs_input"
    assert intent["case"] is None
    assert intent["extracted"][0]["path"] == "source_voltage"
    assert intent["extracted"][0]["value"] == "5 volt"
    assert intent["extracted"][0]["span"]
    assert {q["path"] for q in intent["questions"]} == {
        "stages[0].conductor.reference_resistance",
        "stages[0].conductor.temperature_coefficient",
        "stages[0].conductor.reference_temperature",
        "stages[0].body.heat_capacity",
        "stages[0].body.ambient_conductance",
        "stages[0].body.ambient_temperature",
        "stages[0].body.initial_temperature",
        "stages[0].body.duration",
    }
    assert intent["assumptions"] == [{
        "path": "stages[0].component_id",
        "value": "R1",
        "kind": "generated_identifier",
        "affects_physics": False,
    }]
    assert intent["unresolved_evidence_inputs"]
    assert all(
        item["unlocks_conditions"]
        for item in intent["unresolved_evidence_inputs"]
    )


def test_complete_arabic_prose_compiles_through_the_real_boundary():
    intent = compile_engineering_intent(ARABIC_CASE)

    assert intent["status"] == "ready"
    assert intent["questions"] == []
    assert intent["case"]["source_voltage"] == "5 volt"
    stage = intent["case"]["stages"][0]
    assert stage["conductor"]["reference_resistance"] == "10 ohm"
    assert stage["body"]["heat_capacity"] == "2.5 joule/kelvin"
    assert stage["body"]["duration"] == "120 second"


def test_explicit_answers_override_an_extraction_and_are_attributed():
    intent = compile_engineering_intent(
        ARABIC_CASE,
        {"source_voltage": "12 volt", "stages[0].component_id": "heater"},
    )

    assert intent["status"] == "ready"
    assert intent["case"]["source_voltage"] == "12 volt"
    assert intent["case"]["stages"][0]["component_id"] == "heater"
    assert intent["assumptions"] == []
    source = next(i for i in intent["extracted"] if i["path"] == "source_voltage")
    assert source["source"] == "explicit_declaration"


def test_unknown_answer_path_is_refused_not_ignored():
    with pytest.raises(ValueError, match="unknown declaration"):
        compile_engineering_intent(
            "جهد المصدر 5 فولت", {"stages[0].body.magic": "10 watt"}
        )


def test_registry_declared_optional_evidence_is_accepted():
    intent = compile_engineering_intent(
        ARABIC_CASE,
        {
            "stages[0].conductor.limits.maximum_operating_temperature":
                "400 kelvin",
            "stages[0].conductor.ratings.rated_power": "5 watt",
            "coupling.max_iterations": 75,
        },
    )

    assert intent["status"] == "ready"
    assert intent["case"]["stages"][0]["conductor"]["limits"][
        "maximum_operating_temperature"
    ] == "400 kelvin"
    assert intent["case"]["coupling"]["max_iterations"] == 75
    assert {
        item["path"] for item in intent["unresolved_evidence_inputs"]
    }.isdisjoint({
        "stages[0].conductor.limits.maximum_operating_temperature",
        "stages[0].conductor.ratings.rated_power",
    })


def test_arabic_digits_are_normalised_before_extraction():
    intent = compile_engineering_intent("جهد المصدر ٥٫٥ فولت")
    assert intent["extracted"][0]["value"] == "5.5 volt"


def test_a_dimensionally_wrong_extraction_never_becomes_runnable():
    intent = compile_engineering_intent(
        ARABIC_CASE,
        {"stages[0].body.duration": "120 kelvin"},
    )
    assert intent["status"] == "invalid"
    assert intent["case"] is None
    assert intent["diagnostics"][0]["type"] == "WrongDimensionError"


def test_complete_arabic_battery_prose_compiles_without_payload_scaffolding():
    intent = compile_engineering_intent(
        ARABIC_BATTERY_CASE, system_name="battery"
    )

    assert intent["status"] == "ready"
    assert intent["questions"] == []
    assert intent["case"]["cell"]["cell_id"] == "C1"
    assert intent["case"]["load"]["load_id"] == "L1"
    assert intent["case"]["cell"]["nominal_capacity"] == "2.5 ampere_hour"
    assert intent["case"]["load"]["discharge_current"] == "1.5 ampere"
    assert intent["case"]["cell"]["limits"][
        "cell_thermal_conductance"
    ] == "0.4 watt/kelvin"
