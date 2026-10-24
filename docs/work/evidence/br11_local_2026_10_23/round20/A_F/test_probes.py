import pytest
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind, ExecutionDesk, FeasibleActionSpace, WorldRefused, DispatchRefused
from engcore.mind.world.owners import AccountPublication
from engcore.mind.world.authority import Authorities, OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _settle, _solver, SIM
K=OwnerKind.BUDGET_LEDGER

def setup():
    old=BudgetLedger(total_budget=100.)
    held={"a":old}; source=AccountPublication()
    reader=BudgetReader.following(lambda:source.publish(held))
    return old,held,source,reader

def test_cross_source_handoff_is_not_a_migration():
    old,held,source,reader=setup();saved=old.to_dict();_settle(old,"spent")
    replacement=AccountPublication(); token=replacement.publish({"a":BudgetLedger.from_dict(saved)})
    reader._follow=lambda:token
    with pytest.raises(OwnerUnavailable):reader.read(K,"a")
    reader._follow=lambda:source.publish(held)
    with pytest.raises(OwnerUnavailable):reader.read(K,"a")

def test_recreated_reader_of_same_source_remembers_unobserved_spend():
    old,held,source,reader=setup();saved=old.to_dict();_settle(old,"spent")
    held["a"]=BudgetLedger.from_dict(saved)
    next_reader=BudgetReader.following(lambda:source.publish(held))
    with pytest.raises(OwnerUnavailable):next_reader.read(K,"a")

def test_unknown_current_does_not_hide_old_authority():
    old,held,source,reader=setup();saved=old.to_dict();_settle(old,"spent")
    held.clear();assert reader.read(K,"a") is None
    held["a"]=BudgetLedger.from_dict(saved)
    with pytest.raises(OwnerUnavailable):reader.read(K,"a")

def test_eager_owner_pin_tracks_account_unbound_by_world():
    old,held,source,reader=setup();saved=old.to_dict();_settle(old,"spent")
    held["a"]=BudgetLedger.from_dict(saved)
    memo=Authorities.of(reader).memoized()
    with pytest.raises(OwnerUnavailable):memo.read(K,"a")

@pytest.mark.parametrize("attack",["raw","policy","missing_budget","faked_live"])
def test_dispatch_boundary(attack):
    o=ax.owned("battery");auth=o.authorities();calls=[]
    prop=o.propose("simulate_pulse",*SIM)
    normal=ExecutionDesk(auth,calls.append,accept_synthetic=True).gateway()
    admitted=normal.admit(FeasibleActionSpace.build(o.world),prop).admitted
    assert admitted is not None
    if attack=="faked_live":
        class Fake:
            owner_id="budget"; kinds=BudgetReader.kinds; live=True
        bad=Authorities.of(*(Fake() if type(r) is BudgetReader else r for r in auth.readers))
        with pytest.raises(WorldRefused):ExecutionDesk(bad,calls.append,accept_synthetic=True)
    else:
        use=Authorities.of(*(r for r in auth.readers if type(r) is not BudgetReader)) if attack=="missing_budget" else auth
        desk=ExecutionDesk(use,calls.append,accept_synthetic=True,suggestions_only=attack=="policy")
        with pytest.raises(DispatchRefused):desk.gateway().dispatch(prop if attack=="raw" else admitted)
    assert calls==[]
