import pytest
from engcore.uq.budget import *
from engcore.uq.budget.serialization import budget_from_dict,budget_to_dict

def test_budget_round_trip_recomputes_aggregate():
    r=UncertaintyBudgetReport.build((UncertaintyComponent("a",UncertaintySource.MEASUREMENT,2),))
    p=budget_to_dict(r);p["aggregate"]["variance"]=99
    with pytest.raises(ValueError,match="variance"):
        budget_from_dict(p)


@pytest.mark.parametrize("components", [None, [], ()])
def test_missing_or_empty_components_are_refused(components):
    report = UncertaintyBudgetReport.build((UncertaintyComponent("a", UncertaintySource.MEASUREMENT, 2),))
    payload = budget_to_dict(report)
    if components is None:
        payload.pop("components")
    else:
        payload["components"] = components
    # A caller cannot turn absent measurements into a declaration of perfect certainty.
    payload["aggregate"] = {"variance": 0, "standard_uncertainty": 0}
    with pytest.raises(ValueError, match="missing uncertainty is not zero"):
        budget_from_dict(payload)


def test_valid_budget_round_trip_preserves_its_serialized_identity():
    payload = budget_to_dict(UncertaintyBudgetReport.build((UncertaintyComponent("a", UncertaintySource.MEASUREMENT, 2),)))
    assert budget_to_dict(budget_from_dict(payload)) == payload
