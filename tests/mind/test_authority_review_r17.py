"""R17 owner JSON readback parity controls; bounded software evidence only."""
from tests.mind.publication_support import following
import json

import pytest

from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific import ScientificCoreError, to_json
from engcore.scientific.experiments.experiment import ScientificExperiment
from engcore.scientific.experiments.evaluation import ScientificEvaluation, EvaluationStatus
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import ax
from tests.mind.test_authority_review_r16 import _interrupt_handing


class _Text:
    def __str__(self):
        return "owner default=str"


class _Iteration:
    def __int__(self):
        return 1

    def __str__(self):
        return "not an integer until owner normalization"


def _fixture(kind):
    if kind == "ledger":
        account = BudgetLedger(total_budget=100.)
        owner_kind = OwnerKind.BUDGET_LEDGER
        follow = lambda: ({"a": held[0]}, {})
    else:
        account = next(iter(ax.owned("battery").experiments.values()))
        owner_kind = OwnerKind.EXPERIMENT
        follow = lambda: ({}, {"a": held[0]})
    held = [account]
    return account, held, follow, following(follow), owner_kind


def _append(account, kind, value, iteration=1):
    if kind == "ledger":
        account.settle(charge_id="new", action_id="new", iteration=iteration,
                       family="explore", realized=1., detail={"nested": value})
    else:
        account.record(ScientificEvaluation("new", {}, status=EvaluationStatus.NOT_CONVERGED,
                                            metadata={"nested": value}))


def _checkpoint(account, kind):
    if kind == "ledger":
        return BudgetLedger.from_dict(json.loads(json.dumps(
            BudgetLedger.from_dict(account.to_dict()).to_dict(), sort_keys=True,
            separators=(",", ":"), default=str)))
    return ScientificExperiment.from_dict(json.loads(to_json(account)))


@pytest.mark.parametrize("kind", ["ledger", "experiment"])
@pytest.mark.parametrize("value", [{2: "a", 10: "b"}, {"2": "a", "10": "b"}, (1, 2)])
def test_owner_json_equivalent_detached_history_recovers(kind, value):
    account, held, follow, reader, owner_kind = _fixture(kind)
    _append(account, kind, value)
    _interrupt_handing(reader)
    held[0] = _checkpoint(account, kind)
    fresh = following(follow)
    expected = fresh.read(owner_kind, "a")
    for _ in range(2):
        assert reader.read(owner_kind, "a") == expected
    assert not reader._diverged and not reader._unread_entries


@pytest.mark.parametrize("value", [_Text(), float("nan")])
def test_ledger_retains_its_default_string_and_nonfinite_rules(value):
    account, held, follow, reader, owner_kind = _fixture("ledger")
    _append(account, "ledger", value, iteration=_Iteration())
    _interrupt_handing(reader)
    held[0] = _checkpoint(account, "ledger")
    assert reader.read(owner_kind, "a") == following(follow).read(owner_kind, "a")
    assert not reader._diverged


@pytest.mark.parametrize("kind", ["ledger", "experiment"])
@pytest.mark.parametrize("change", ["rollback", "rewrite"])
def test_owner_json_true_history_difference_refuses(kind, change):
    account, held, _, reader, owner_kind = _fixture(kind)
    old = _checkpoint(account, kind)
    _append(account, kind, {2: "a", 10: "b"})
    _interrupt_handing(reader)
    if change == "rewrite":
        _append(old, kind, {2: "CHANGED", 10: "b"})
    held[0] = _checkpoint(old, kind)
    for _ in range(2):
        with pytest.raises(OwnerUnavailable):
            reader.read(owner_kind, "a")


@pytest.mark.parametrize("kind,value", [
    ("experiment", _Text()), ("experiment", float("nan")),
    ("experiment", {2: "a", "10": "b"}), ("ledger", {2: "a", "10": "b"}),
])
def test_owner_unserializable_retained_entry_stays_unresolved(kind, value):
    account, held, _, reader, owner_kind = _fixture(kind)
    old = _checkpoint(account, kind)
    _append(account, kind, value)
    with pytest.raises((TypeError, ValueError, ScientificCoreError)):
        _checkpoint(account, kind)
    _interrupt_handing(reader)
    held[0] = old
    for _ in range(2):
        with pytest.raises(OwnerUnavailable):
            reader.read(owner_kind, "a")
    assert reader._unread_entries
    assert not reader._diverged
