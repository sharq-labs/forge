"""Uncertainty must qualify the value it is attached to.

THE DEFECT
----------
``Uncertainty`` checks that an interval's two endpoints agree with EACH OTHER,
and nothing checked either against the value they qualify. So ``350 K +/- 5 V``
and ``350 K in [1 V, 9 V]`` both constructed, serialized, and round-tripped.

The error would surface downstream, deep inside an arithmetic the consumer did
not choose -- or not at all, if the consumer compared magnitudes and produced a
bound in the wrong physical dimension without noticing.

THE SEMANTICS, CLARIFIED BEFORE THE RULE WAS WRITTEN
----------------------------------------------------
``UncertaintyKind`` has three members and both quantified ones are **absolute**:
``STANDARD`` carries a standard uncertainty as a ``Quantity``, ``INTERVAL``
carries two ``Quantity`` endpoints. There is no relative or dimensionless FORM.

So the rule is unconditional -- every ``Quantity`` an uncertainty carries must
share the dimension of the value it qualifies -- and a dimensionless result
needs no special case, because its uncertainty is dimensionless by the same
rule rather than by an exemption.

WHERE IT LIVES
--------------
On ``ScientificResult``, which is the only record that holds both. An
``Uncertainty`` does not know which value it belongs to.
"""

from __future__ import annotations

import json

import pytest

from engcore.scientific.errors import (
    ScientificCoreError,
    UnitCompatibilityError,
)
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.results.provenance import (
    ExecutionBinding,
    ProvenanceRecord,
)
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.results.uncertainty import (
    Uncertainty,
    UncertaintyKind,
)
from engcore.scientific.serialization import to_json
from engcore.scientific.solvers.protocol import SolverIdentity
from engcore.scientific.units.quantity import Quantity


def _result(values, uncertainty):
    return ScientificResult(
        result_id="r",
        values=values,
        provenance=ProvenanceRecord(run_id="run"),
        uncertainty=uncertainty,
    )


def _standard(quantity):
    return Uncertainty(
        kind=UncertaintyKind.STANDARD,
        standard_uncertainty=quantity,
        method="a declared method",
    )


def _interval(lower, upper):
    return Uncertainty(
        kind=UncertaintyKind.INTERVAL,
        lower=lower,
        upper=upper,
        method="a declared method",
    )


# =============================================================== G: uncertainty


def test_a_standard_uncertainty_must_carry_the_results_dimension():
    """The reproduction: 350 K plus or minus 5 volts."""
    with pytest.raises(UnitCompatibilityError):
        _result(
            {"T": Quantity(350.0, "kelvin")},
            {"T": _standard(Quantity(5.0, "volt"))},
        )


def test_an_interval_must_carry_the_results_dimension():
    """`Uncertainty` checked the endpoints against each other, and only that.

    Both endpoints agree with one another perfectly here, which is exactly why
    the record constructed: the check that existed had nothing to say about the
    value being qualified.
    """
    with pytest.raises(UnitCompatibilityError):
        _result(
            {"T": Quantity(350.0, "kelvin")},
            {"T": _interval(Quantity(1.0, "volt"), Quantity(9.0, "volt"))},
        )


def test_a_matching_dimension_is_accepted():
    result = _result(
        {"T": Quantity(350.0, "kelvin")},
        {"T": _standard(Quantity(5.0, "kelvin"))},
    )
    assert result.uncertainty_of("T").standard_uncertainty == Quantity(5.0, "kelvin")


@pytest.mark.parametrize("unit", ["kelvin", "K", "millikelvin", "degR"])
def test_any_compatible_temperature_unit_is_accepted(unit):
    """Compatible dimensions, not one spelling.

    An uncertainty quoted in millikelvin against a result in kelvin is a
    perfectly ordinary thing to write, and a check keyed on the unit STRING
    would refuse it for a reason that has nothing to do with physics.
    """
    result = _result(
        {"T": Quantity(350.0, "kelvin")},
        {"T": _standard(Quantity(5.0, unit))},
    )
    assert result.uncertainty_of("T").is_quantified


def test_both_interval_endpoints_are_checked_against_the_result():
    """One good endpoint must not carry a bad one.

    A check that looked at `lower` alone would pass this, and the interval
    would still be half in the wrong dimension.
    """
    with pytest.raises(UnitCompatibilityError):
        _result(
            {"T": Quantity(350.0, "kelvin")},
            {"T": _interval(Quantity(340.0, "kelvin"), Quantity(9.0, "volt"))},
        )
    with pytest.raises(UnitCompatibilityError):
        _result(
            {"T": Quantity(350.0, "kelvin")},
            {"T": _interval(Quantity(1.0, "volt"), Quantity(360.0, "kelvin"))},
        )


def test_a_well_formed_interval_is_accepted_and_round_trips():
    result = _result(
        {"T": Quantity(350.0, "kelvin")},
        {"T": _interval(Quantity(348.0, "kelvin"), Quantity(352.0, "kelvin"))},
    )
    restored = ScientificResult.from_dict(json.loads(to_json(result)))
    assert restored.uncertainty_of("T").lower == Quantity(348.0, "kelvin")
    assert restored.uncertainty_of("T").upper == Quantity(352.0, "kelvin")


def test_the_rule_holds_for_every_value_in_a_multi_valued_result():
    """One correct pairing must not vouch for an incorrect neighbour."""
    values = {"T": Quantity(350.0, "kelvin"), "V": Quantity(12.0, "volt")}
    ok = _result(
        values,
        {
            "T": _standard(Quantity(5.0, "kelvin")),
            "V": _standard(Quantity(0.1, "volt")),
        },
    )
    assert len(ok.uncertainty) == 2

    # The two uncertainties swapped: each is a real dimension, and each is the
    # wrong one for the value it is filed under.
    with pytest.raises(UnitCompatibilityError):
        _result(
            values,
            {
                "T": _standard(Quantity(0.1, "volt")),
                "V": _standard(Quantity(5.0, "kelvin")),
            },
        )


def test_a_dimensionless_result_takes_a_dimensionless_uncertainty():
    """No special case is needed, and none is made.

    There is no relative or dimensionless uncertainty FORM in this vocabulary
    -- STANDARD and INTERVAL are both absolute and carry Quantities -- so a
    dimensionless result falls under the same unconditional rule.
    """
    ok = _result(
        {"ratio": Quantity(0.8, "dimensionless")},
        {"ratio": _standard(Quantity(0.01, "dimensionless"))},
    )
    assert ok.uncertainty_of("ratio").is_quantified

    with pytest.raises(UnitCompatibilityError):
        _result(
            {"ratio": Quantity(0.8, "dimensionless")},
            {"ratio": _standard(Quantity(0.01, "kelvin"))},
        )


def test_an_unknown_uncertainty_carries_no_dimension_to_check():
    """UNKNOWN is the honest default and must stay costless."""
    result = _result(
        {"T": Quantity(350.0, "kelvin")}, {"T": Uncertainty.unknown()}
    )
    assert result.uncertainty_of("T").is_quantified is False
    # And a value with no uncertainty entry at all is still fine.
    assert _result({"T": Quantity(350.0, "kelvin")}, {}).uncertainty == {}


def test_uncertainty_for_a_value_that_does_not_exist_is_refused():
    """The guard that already existed, kept exercised beside the new one."""
    with pytest.raises(ScientificCoreError):
        _result(
            {"T": Quantity(350.0, "kelvin")},
            {"pressure": _standard(Quantity(1.0, "pascal"))},
        )


def test_a_malformed_interval_is_still_refused_for_its_own_reason():
    """Upper below lower, and a missing endpoint. Different defects."""
    with pytest.raises(ScientificCoreError):
        _interval(Quantity(9.0, "kelvin"), Quantity(1.0, "kelvin"))
    with pytest.raises(ScientificCoreError):
        Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(1.0, "kelvin"),
            method="m",
        )
    with pytest.raises(ScientificCoreError):
        Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(-1.0, "kelvin"),
            method="m",
        )


def test_the_dimensional_rule_survives_the_wire():
    """A payload gets no exemption."""
    good = _result(
        {"T": Quantity(350.0, "kelvin")},
        {"T": _standard(Quantity(5.0, "kelvin"))},
    )
    payload = json.loads(to_json(good))
    assert ScientificResult.from_dict(payload).uncertainty_of("T").is_quantified

    payload["uncertainty"]["T"]["standard_uncertainty"] = Quantity(
        5.0, "volt"
    ).to_dict()
    with pytest.raises(UnitCompatibilityError):
        ScientificResult.from_dict(payload)


