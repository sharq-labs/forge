"""Owner publication lifetime: synthetic authority controls, not physical validation."""
from unittest.mock import patch
import pytest
from engcore.mind.world import BudgetReader
from tests.mind.test_authority_review_r14 import _desk, _solver, _settle, _refused, ax
from engcore.sria.campaign.budget import BudgetLedger

@pytest.mark.parametrize("interruptions", [1, 2])
def test_pre_capture_restore_does_not_restore_authority(interruptions):
    o = ax.owned("battery")
    lid = _solver(o)
    calls = []
    def execute(authorization):
        calls.append(1)
        _settle(o.ledgers[lid], f"run.{len(calls)}")
    reader, _, gateway, admitted = _desk(o, lambda: (o.ledgers, o.experiments), execute)
    saved = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(admitted.admitted)
    original = BudgetReader._retain_handing
    remaining = [interruptions]
    def interrupted(value):
        if remaining[0]:
            remaining[0] -= 1
            raise KeyboardInterrupt()
        return original(value)
    with patch.object(BudgetReader, "_retain_handing", staticmethod(interrupted)):
        with pytest.raises(KeyboardInterrupt):
            reader.pinned()
    assert remaining == [0]
    o.ledgers[lid] = saved
    assert _refused(gateway, admitted.admitted), "restore erased spent authority"
    assert calls == [1]


from dataclasses import FrozenInstanceError
from threading import Event, Thread
from engcore.mind.world import OwnerKind, WorldRefused
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.owners import AccountPublication
K = OwnerKind.BUDGET_LEDGER


def _published():
    account = BudgetLedger(total_budget=100.)
    held = {"a": account}
    source = AccountPublication()
    def accounts():
        return source.publish(held, {})
    reader = BudgetReader.following(accounts)
    return source, held, account, reader


@pytest.mark.parametrize("spent", [False, True])
@pytest.mark.parametrize("phase", ["before_handoff", "after_publish", "capture", "reconcile"])
def test_interruption_lifetime_and_repeated_restore(spent, phase):
    source, held, account, reader = _published()
    saved = account.to_dict()
    if spent:
        _settle(account, "spent")
    original = reader._follow
    def interrupted():
        if phase == "after_publish":
            original()
        raise KeyboardInterrupt()
    if phase in ("before_handoff", "after_publish"):
        reader._follow = interrupted
        for _ in range(2):
            with pytest.raises(KeyboardInterrupt):
                reader.pinned()
        reader._follow = original
    else:
        method = "_retain_handing" if phase == "capture" else "_retained_entry"
        with patch.object(BudgetReader, method, side_effect=KeyboardInterrupt):
            if phase == "reconcile":
                # A detached checkpoint requires canonical entry reconciliation.
                held["a"] = BudgetLedger.from_dict(saved)
            try:
                reader.pinned()
            except (KeyboardInterrupt, OwnerUnavailable):
                pass
    for _ in range(3):
        held["a"] = BudgetLedger.from_dict(saved)
        if spent:
            with pytest.raises(OwnerUnavailable):
                reader.read(K, "a")
        else:
            assert reader.read(K, "a") is not None
            assert not reader._diverged
    if not spent:
        _settle(held["a"], "legitimate-progress")
        assert reader.read(K, "a").revision == str(held["a"].revision)


def test_earlier_success_does_not_retire_a_later_spend():
    source, held, account, reader = _published()
    saved = account.to_dict()
    for _ in range(3):
        assert reader.read(K, "a") is not None
    _settle(account, "later-spend")
    held["a"] = BudgetLedger.from_dict(saved)
    with pytest.raises(OwnerUnavailable):
        reader.read(K, "a")
    with pytest.raises(OwnerUnavailable):
        source.retire()
    assert len(source._generations) == 2


def test_publication_precedes_handoff_and_new_reader_recovers_prior_spend():
    source = AccountPublication()
    account = BudgetLedger(total_budget=100.)
    saved = account.to_dict()
    source.publish({"a": account})
    _settle(account, "spent")
    current = source.publish({"a": BudgetLedger.from_dict(saved)})
    reader = BudgetReader.following(lambda: current)
    with pytest.raises(OwnerUnavailable):
        reader.read(K, "a")


def test_publication_cannot_be_rewritten_through_returned_token():
    source, held, account, reader = _published()
    token = source.publish(held)
    with pytest.raises(FrozenInstanceError):
        token.bindings = None
    with pytest.raises(FrozenInstanceError):
        token.bindings.entries = ((), ())
    held.clear()
    assert token.bindings.entries[0][0][1] is account


def test_raw_callback_and_subclass_source_cannot_claim_publication_authority():
    with pytest.raises(WorldRefused):
        BudgetReader.following(lambda: ({"a": BudgetLedger(total_budget=100.)}, {}))
    class ForgedSource(AccountPublication):
        def _history(self, token):
            return (token,)
    source = ForgedSource()
    token = source.publish({"a": BudgetLedger(total_budget=100.)})
    with pytest.raises(WorldRefused):
        BudgetReader.following(lambda: token)


def test_retirement_waits_for_closed_pending_reader_and_stale_snapshot_refuses():
    source, held, account, reader = _published()
    stale = reader.pinned()
    entered, resume = Event(), Event()
    original = reader._follow
    result = []
    def paused():
        token = original()
        entered.set()
        assert resume.wait(5)
        return token
    reader._follow = paused
    def run():
        try:
            result.append(reader.read(K, "a"))
        except BaseException as exc:
            result.append(exc)
    thread = Thread(target=run)
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(OwnerUnavailable):
            source.retire()
        source.close()
        with pytest.raises(OwnerUnavailable):
            source.retire()
        assert source._generations
    finally:
        resume.set()
        thread.join(5)
    assert not thread.is_alive()
    assert len(result) == 1 and isinstance(result[0], OwnerUnavailable)
    source.retire()
    assert not source._generations
    for old in (reader, stale):
        with pytest.raises(OwnerUnavailable):
            old.read(K, "a")
    with pytest.raises(OwnerUnavailable):
        source.publish(held)


def test_missing_current_account_is_never_an_unspent_record():
    source, held, account, reader = _published()
    saved = account.to_dict()
    _settle(account, "spent")
    held.clear()
    assert reader.read(K, "a") is None
    held["a"] = BudgetLedger.from_dict(saved)
    with pytest.raises(OwnerUnavailable):
        reader.read(K, "a")


@pytest.mark.parametrize("phase", ["acquire", "release"])
def test_interrupted_lease_cleanup_has_explicit_quiescence(phase):
    source, held, account, reader = _published()
    name = "_" + phase
    original = getattr(source, name)
    def interrupted(lease):
        if phase == "acquire":
            original(lease)
        raise KeyboardInterrupt()
    with patch.object(source, name, interrupted):
        with pytest.raises(KeyboardInterrupt):
            reader.pinned()
    assert all(not lease.active for lease in source._leases)
    source.close()
    source.retire()
    assert not source._generations and not source._leases


@pytest.mark.parametrize("malformed", ["non_string", "wrong_type", "alias"])
def test_initial_publication_preserves_strict_constructor_contract(malformed):
    source = AccountPublication()
    account = BudgetLedger(total_budget=100.)
    maps = {1: account} if malformed == "non_string" else {"a": object()} if malformed == "wrong_type" else {"a": account, "b": account}
    token = source.publish(maps)
    with pytest.raises(WorldRefused):
        BudgetReader.following(lambda: token)
    source.close()
    source.retire()
