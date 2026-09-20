from engcore.mcp.planning import PLAN_SCHEMA, plan_engineering_intent


def test_electrothermal_terms_select_electrothermal():
    plan = plan_engineering_intent(
        "احسب حرارة مقاومة موصلة مع جهد المصدر"
    )
    assert plan["schema"] == PLAN_SCHEMA
    assert plan["status"] == "selected"
    assert plan["selected_system"] == "electrothermal"
    assert plan["selection_authority"] == "deterministic_keyword_router"


def test_terms_from_both_systems_refuse_an_ambiguous_tie():
    plan = plan_engineering_intent("battery resistor")
    assert plan["status"] == "needs_system"
    assert plan["selected_system"] is None


def test_generic_engineering_prose_is_not_forced_into_a_known_system():
    # "excellent" contains the letters "cell" and "social" contains "soc";
    # substrings are not evidence that the user asked for a battery cell/SOC.
    plan = plan_engineering_intent(
        "optimise this excellent engineering design for social benefit"
    )
    assert plan["status"] == "needs_system"
    assert all(candidate["score"] == 0 for candidate in plan["candidates"])
