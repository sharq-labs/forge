from __future__ import annotations

from pathlib import Path

import pytest

from engcore.design import (
    DesignCandidate,
    DesignCandidateReference,
    DesignSpace,
    FidelityLadder,
    FidelityRung,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.ir.values import BooleanValue, CategoricalValue, IntegerValue
from engcore.scientific.ir.variables import ScientificVariable, VariableKind
from engcore.scientific.twins.definition import TwinReference
from engcore.scientific.units.quantity import Quantity


def _space() -> DesignSpace:
    return DesignSpace(
        space_id="general-demo",
        version="0.1.0",
        variables=(
            ScientificVariable(
                name="length",
                unit="m",
                kind=VariableKind.CONTINUOUS,
                lower=Quantity(1.0, "m"),
                upper=Quantity(3.0, "m"),
            ),
            ScientificVariable(
                name="count",
                unit="dimensionless",
                kind=VariableKind.INTEGER,
                lower=Quantity(1, "dimensionless"),
                upper=Quantity(8, "dimensionless"),
            ),
            ScientificVariable(
                name="variant",
                unit="dimensionless",
                kind=VariableKind.CATEGORICAL,
                categories=("alpha", "beta"),
            ),
            ScientificVariable(
                name="enabled",
                unit="dimensionless",
                kind=VariableKind.BOOLEAN,
            ),
        ),
        constraint_refs=("system:compatibility/v1",),
    )


def _assignments():
    return {
        "length": Quantity(250, "cm"),
        "count": IntegerValue(4),
        "variant": CategoricalValue("beta"),
        "enabled": BooleanValue(True),
    }


def test_design_space_represents_and_validates_all_four_variable_kinds():
    space = _space()
    validated = space.validate_assignments(_assignments())
    assert tuple(validated) == ("length", "count", "variant", "enabled")
    assert space.reference.key == ("general-demo", "0.1.0")
    assert DesignSpace.from_dict(space.to_dict()) == space


def test_design_space_fails_closed_on_missing_extra_wrong_bounds_and_category():
    space = _space()

    missing = _assignments()
    missing.pop("enabled")
    with pytest.raises(InvalidScientificProblem, match="missing variables"):
        space.validate_assignments(missing)

    extra = _assignments()
    extra["undeclared"] = BooleanValue(False)
    with pytest.raises(InvalidScientificProblem, match="undeclared variables"):
        space.validate_assignments(extra)

    wrong_type = _assignments()
    wrong_type["count"] = Quantity(4, "dimensionless")
    with pytest.raises(InvalidScientificProblem, match="requires IntegerValue"):
        space.validate_assignments(wrong_type)

    out_of_bounds = _assignments()
    out_of_bounds["count"] = IntegerValue(9)
    with pytest.raises(InvalidScientificProblem, match="above upper bound"):
        space.validate_assignments(out_of_bounds)

    bad_category = _assignments()
    bad_category["variant"] = CategoricalValue("gamma")
    with pytest.raises(InvalidScientificProblem, match="is not allowed"):
        space.validate_assignments(bad_category)


def test_candidate_binds_exact_twin_and_round_trips_with_lineage():
    space = _space()
    root = DesignCandidate(
        candidate_id="candidate-0001",
        design_space=space.reference,
        twin=TwinReference("system-twin-0001", "1"),
        assignments=_assignments(),
    ).validate_against(space)

    child = DesignCandidate(
        candidate_id="candidate-0002",
        design_space=space.reference,
        twin=TwinReference("system-twin-0002", "1"),
        assignments={**_assignments(), "count": IntegerValue(5)},
        generation=1,
        parents=(DesignCandidateReference(root.candidate_id),),
        operator="recombine",
    ).validate_against(space)

    assert child.twin.key == ("system-twin-0002", "1")
    assert child.parents == (root.reference,)
    assert DesignCandidate.from_dict(child.to_dict()) == child


def test_candidate_lineage_fails_closed():
    space = _space()
    with pytest.raises(InvalidScientificProblem, match="generation-zero"):
        DesignCandidate(
            candidate_id="bad",
            design_space=space.reference,
            twin=TwinReference("twin", "1"),
            assignments=_assignments(),
            parents=(DesignCandidateReference("parent"),),
        )

    with pytest.raises(InvalidScientificProblem, match="derived generation"):
        DesignCandidate(
            candidate_id="bad",
            design_space=space.reference,
            twin=TwinReference("twin", "1"),
            assignments=_assignments(),
            generation=1,
        )


def test_fidelity_ladder_is_generic_ordered_and_round_trips():
    ladder = FidelityLadder(
        ladder_id="generic-study",
        version="0.1.0",
        rungs=(
            FidelityRung("rung-b", 20, frozenset({"capability:b"})),
            FidelityRung("rung-a", 10, frozenset({"capability:a"})),
        ),
    )
    assert [r.rung_id for r in ladder.rungs] == ["rung-a", "rung-b"]
    assert ladder.next_after("rung-a").rung_id == "rung-b"
    assert ladder.next_after("rung-b") is None
    assert FidelityLadder.from_dict(ladder.to_dict()) == ladder


def test_design_package_has_no_product_or_domain_specific_imports():
    root = Path(__file__).resolve().parents[1] / "src" / "engcore" / "design"
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = (
        "engcore.domains",
        "..domains",
        "engcore.systems",
        "..systems",
        "drone",
        "hvac",
        "aircraft",
        "cstr",
    )
    lowered = text.lower()
    for token in forbidden:
        assert token.lower() not in lowered
