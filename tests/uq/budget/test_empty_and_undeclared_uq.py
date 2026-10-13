"""Hostile review (empty-UQ authority): nothing quantified is never zero, and silence is never independence.

Two budgets carry uncertainty totals: the UQ budget (engcore.uq.budget) and the SRIA channel budget
(engcore.sria.assurance.uncertainty_budget). The first aggregated an empty tuple to 0.0 and read an
undeclared pair as independent; the second already refused both, and these tests pin that it still does.
"""

from __future__ import annotations

import pytest

from engcore.scientific.results.uncertainty import UncertaintySource as Source
from engcore.sria.assurance.uncertainty_budget import BudgetError
from engcore.sria.uncertainty import UncertaintyChannel
from engcore.uq.budget import Correlation, UncertaintyBudgetReport, UncertaintyComponent, UncertaintySource
from engcore.uq.budget.serialization import budget_from_dict, budget_to_dict
from tests.test_core_scientific_audit_batch54 import _budget, _entry, _standard


def test_a_stored_budget_that_relied_on_silent_independence_no_longer_reads_back() -> None:
    payload = budget_to_dict(UncertaintyBudgetReport.build(
        (UncertaintyComponent("a", UncertaintySource.MEASUREMENT, 3), UncertaintyComponent("b", UncertaintySource.NUMERICAL, 4)),
        (Correlation("a", "b", 0.0),)))
    assert budget_from_dict(payload).aggregate.standard_uncertainty == pytest.approx(5)
    payload["correlations"] = []
    with pytest.raises(ValueError, match="undeclared"):
        budget_from_dict(payload)


def test_the_sria_budget_refuses_an_empty_aggregate() -> None:
    with pytest.raises(BudgetError, match="at least one channel"):
        _budget(_entry(UncertaintyChannel.NUMERICAL, _standard(source_kind=Source.NUMERICAL))).aggregate([])


def test_the_sria_budget_reads_a_never_declared_channel_as_unknown_not_zero() -> None:
    budget = _budget(_entry(UncertaintyChannel.NUMERICAL, _standard(source_kind=Source.NUMERICAL)))
    with pytest.raises(BudgetError, match="UNKNOWN channel is not zero"):
        budget.aggregate([UncertaintyChannel.NUMERICAL, UncertaintyChannel.ALEATORIC],
                         assumptions=("independent",), allow_cross_kind=True)


def test_the_sria_budget_never_combines_channels_without_a_stated_independence() -> None:
    budget = _budget(_entry(UncertaintyChannel.NUMERICAL, _standard(source_kind=Source.NUMERICAL)),
                     _entry(UncertaintyChannel.ALEATORIC, _standard(0.25, source_kind=Source.MEASUREMENT)))
    channels = [UncertaintyChannel.NUMERICAL, UncertaintyChannel.ALEATORIC]
    with pytest.raises(BudgetError, match="allow_cross_kind"):
        budget.aggregate(channels, assumptions=("channels are independent",))
    with pytest.raises(BudgetError, match="independence assumption to be stated"):
        budget.aggregate(channels, allow_cross_kind=True)
