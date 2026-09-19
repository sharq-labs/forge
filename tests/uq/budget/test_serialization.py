import pytest
from engcore.uq.budget import *
from engcore.uq.budget.serialization import budget_from_dict,budget_to_dict

def test_budget_round_trip_recomputes_aggregate():
    r=UncertaintyBudgetReport.build((UncertaintyComponent("a",UncertaintySource.MEASUREMENT,2),))
    p=budget_to_dict(r);p["aggregate"]["variance"]=99
    with pytest.raises(ValueError,match="variance"):
        budget_from_dict(p)
