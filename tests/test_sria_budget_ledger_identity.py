"""GEN2-BR1.1: the budget ledger's read-only identity (``BudgetLedger.digest`` and ``revision``).

The ledger is the canonical current budget account of a campaign run.  BR1 found it had no identity a record could
cite, so a world's budget copy could not be verified.  The addition is read-only: no field, schema or wire shape
changes, and the digest follows the package's own convention (``sria.decision.replay.canonical_digest`` over
``to_dict``, as ``CampaignCheckpoint.digest`` and ``BudgetDeclaration.digest`` already do), taken in the form
``from_dict`` reads it back, so a ledger and its own round trip (a checkpoint restore) are one identity.
"""

from __future__ import annotations

from engcore.sria.campaign.budget import BudgetCharge, BudgetLedger
from engcore.sria.decision import ActionFamily
from engcore.sria.decision.replay import canonical_digest


def _ledger() -> BudgetLedger:
    ledger = BudgetLedger(total_budget=10.0, reserved_validation_budget=2.0, cost_unit="hour")
    ledger.settle(charge_id="c1", action_id="a", iteration=0, family=ActionFamily.EXPLORE, realized=1.5)
    return ledger


def test_the_digest_is_the_package_rule_over_the_ledger_payload():
    ledger = _ledger()
    assert ledger.digest == canonical_digest(BudgetLedger.from_dict(ledger.to_dict()).to_dict())
    assert ledger.digest == canonical_digest(ledger.to_dict()) and len(ledger.digest) == 64   # a float-amount ledger
    assert ledger.revision == 1


def test_the_payload_and_wire_shape_are_unchanged():
    payload = _ledger().to_dict()
    assert "digest" not in payload and "revision" not in payload
    assert BudgetLedger.from_dict(payload).to_dict() == payload


def test_any_settled_charge_or_declaration_change_moves_the_digest_and_a_repeat_settle_does_not():
    ledger = _ledger()
    before = (ledger.digest, ledger.revision)
    ledger.settle(charge_id="c1", action_id="a", iteration=0, family=ActionFamily.EXPLORE, realized=1.5)
    assert (ledger.digest, ledger.revision) == before                     # idempotent by charge id
    ledger.settle(charge_id="c2", action_id="b", iteration=1, family=ActionFamily.VALIDATE, realized=0.5)
    assert ledger.revision == before[1] + 1 and ledger.digest != before[0]
    moved = ledger.digest
    ledger.total_budget = 12.0                                            # a reassigned declaration is visible too
    assert ledger.digest != moved


def test_a_round_trip_keeps_the_identity():
    ledger = _ledger()
    again = BudgetLedger.from_dict(ledger.to_dict())
    assert (again.digest, again.revision) == (ledger.digest, ledger.revision)


def test_a_ledger_with_integer_amounts_keeps_its_identity_through_the_owners_round_trip():
    """GEN2-BR1.1 review round 3 (R3-B-07): a legal charge may carry integer amounts, which ``from_dict`` reads back as
    floats; the digest is taken in the read-back form, so a restore of an unchanged account is not a change."""
    charge = BudgetCharge("c1", "a", 0, ActionFamily.EXPLORE, realized=2, from_general_pool=2)
    ledger = BudgetLedger(total_budget=10.0, cost_unit="hour", charges=(charge,))
    again = BudgetLedger.from_dict(ledger.to_dict())
    assert canonical_digest(again.to_dict()) != canonical_digest(ledger.to_dict())   # the raw payloads differ ...
    assert (again.digest, again.revision) == (ledger.digest, ledger.revision)       # ... the identity does not
