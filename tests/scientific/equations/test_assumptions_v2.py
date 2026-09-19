from engcore.scientific.equations import (
    AssumptionSet, AssumptionStatus, CheckableAssumption, Constant,
    ExpressionConstraint, RelationOperator, Symbol,
)
from engcore.scientific.units.quantity import Quantity


def assumption():
    return CheckableAssumption(
        "positive-k",
        ExpressionConstraint(
            "k-positive",Symbol("k"),RelationOperator.GREATER_THAN,
            Constant(Quantity(0,"1 / second")),
        ),
        "decay coefficient is positive",
    )


def test_checkable_assumption_can_be_satisfied_violated_or_unknown():
    aset=AssumptionSet((assumption(),))
    aset.require_dimensions({"k":"1 / second"})
    assert aset.assess({"k":Quantity(0.1,"1 / second")})[0].status is AssumptionStatus.SATISFIED
    assert aset.assess({"k":Quantity(-0.1,"1 / second")})[0].status is AssumptionStatus.VIOLATED
    assert aset.assess({})[0].status is AssumptionStatus.UNKNOWN


def test_assumption_assessment_round_trip_revalidates_evaluation():
    result=AssumptionSet((assumption(),)).assess({"k":Quantity(0.1,"1 / second")})[0]
    assert type(result).from_dict(result.to_dict())==result
