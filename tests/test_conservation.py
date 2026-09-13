"""Conservation/balance checks are dimensional, deterministic and conservative."""

from __future__ import annotations

import pytest

from engcore.scientific.conservation import BalanceTerm, ConservationBalance
from engcore.scientific.errors import ScientificValidationError
from engcore.scientific.results.validation import ValidationOutcome
from engcore.scientific.units.quantity import Quantity


def test_mass_balance_passes_when_inflow_equals_outflow_plus_accumulation():
    balance = ConservationBalance(
        balance_id="mass",
        left=(
            BalanceTerm("feed", Quantity(10.0, "kilogram / second"), "flowmeter:A"),
        ),
        right=(
            BalanceTerm("product", Quantity(9.5, "kilogram / second"), "flowmeter:B"),
            BalanceTerm("accumulation", Quantity(0.5, "kilogram / second"), "state:dMdt"),
        ),
        tolerance=Quantity(0.01, "kilogram / second"),
        reference="mass conservation",
    )
    check = balance.to_check()
    assert balance.closed
    assert balance.absolute_residual == pytest.approx(0.0)
    assert check.outcome is ValidationOutcome.PASS
    assert check.establishes is None
    assert "balance:mass" in check.evidence


def test_energy_balance_accepts_compatible_unit_conversions():
    balance = ConservationBalance(
        balance_id="energy_rate",
        left=(BalanceTerm("heater", Quantity(1.0, "kilowatt")),),
        right=(BalanceTerm("losses", Quantity(995.0, "watt")),),
        tolerance=Quantity(10.0, "watt"),
    )
    assert balance.closed
    assert balance.absolute_residual == pytest.approx(0.005)
    assert balance.unit == "kilowatt"
    assert balance.to_check().outcome is ValidationOutcome.PASS


def test_balance_outside_tolerance_fails_and_awards_no_level():
    balance = ConservationBalance(
        balance_id="charge",
        left=(BalanceTerm("in", Quantity(5.0, "ampere")),),
        right=(BalanceTerm("out", Quantity(4.0, "ampere")),),
        tolerance=Quantity(0.1, "ampere"),
    )
    check = balance.to_check()
    assert not balance.closed
    assert check.outcome is ValidationOutcome.FAIL
    assert check.establishes is None
    assert check.residual == pytest.approx(10.0)
    assert check.tolerance == 1.0


def test_zero_tolerance_requires_exact_closure():
    exact = ConservationBalance(
        balance_id="exact",
        left=(BalanceTerm("a", Quantity(1.0, "mole")),),
        right=(BalanceTerm("b", Quantity(1.0, "mole")),),
        tolerance=Quantity(0.0, "mole"),
    )
    miss = ConservationBalance(
        balance_id="miss",
        left=(BalanceTerm("a", Quantity(1.0, "mole")),),
        right=(BalanceTerm("b", Quantity(0.9, "mole")),),
        tolerance=Quantity(0.0, "mole"),
    )
    assert exact.closed
    assert exact.normalized_residual == 0.0
    assert not miss.closed
    assert miss.normalized_residual == float("inf")
    assert miss.to_check().residual == 2.0


def test_mixed_physical_dimensions_are_refused_at_construction():
    with pytest.raises(Exception):
        ConservationBalance(
            balance_id="nonsense",
            left=(BalanceTerm("mass", Quantity(1.0, "kilogram")),),
            right=(BalanceTerm("energy", Quantity(1.0, "joule")),),
            tolerance=Quantity(0.1, "kilogram"),
        )


def test_tolerance_must_share_the_balance_dimension():
    with pytest.raises(Exception):
        ConservationBalance(
            balance_id="bad_tolerance",
            left=(BalanceTerm("a", Quantity(1.0, "watt")),),
            right=(BalanceTerm("b", Quantity(1.0, "watt")),),
            tolerance=Quantity(1.0, "volt"),
        )


def test_duplicate_term_names_are_refused_for_traceability():
    with pytest.raises(ScientificValidationError, match="unique"):
        ConservationBalance(
            balance_id="duplicate",
            left=(BalanceTerm("flow", Quantity(2.0, "kilogram / second")),),
            right=(BalanceTerm("flow", Quantity(2.0, "kilogram / second")),),
            tolerance=Quantity(0.1, "kilogram / second"),
        )


def test_empty_balance_is_not_evidence():
    with pytest.raises(ScientificValidationError, match="no terms"):
        ConservationBalance(
            balance_id="empty",
            left=(),
            right=(),
            tolerance=Quantity(0.0, "joule"),
        )


def test_balance_round_trip_preserves_terms_tolerance_and_evidence():
    balance = ConservationBalance(
        balance_id="species_A",
        left=(BalanceTerm("generation", Quantity(2.0, "mole / second"), "rxn:R1"),),
        right=(BalanceTerm("removal", Quantity(2.0, "mole / second"), "outlet"),),
        tolerance=Quantity(1e-6, "mole / second"),
        description="steady-state species balance",
        reference="reactor-balance-v1",
    )
    restored = ConservationBalance.from_dict(balance.to_dict())
    assert restored == balance
    assert restored.to_check().evidence == balance.to_check().evidence
