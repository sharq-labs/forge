import json
import pytest
from engcore.mind.world.owners import AccountPublication,BudgetReader,FrozenReader,is_live,rederive
from engcore.mind.world import OwnerKind,WorldRefused
from engcore.mind.world.authority import OwnerUnavailable,OwnerRecord
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily
K=OwnerKind.BUDGET_LEDGER

def charge(a,cost=1,detail="spent"):
    a.settle(charge_id="one",action_id="probe",iteration=0,family=ActionFamily.EXPLORE,realized=cost,detail=detail)

def setup():
    source=AccountPublication();held={"a":BudgetLedger(total_budget=10.)}
    r=BudgetReader.following(lambda:source.publish(held))
    return source,held,r

@pytest.mark.parametrize("detail",["plain",{"tuple":(1,2),"nested":{"x":None}}])
def test_json_detached_equal_history_remains_equal(detail):
    source,held,r=setup();charge(held["a"],detail=detail)
    first=r.read(K,"a")
    held["a"]=BudgetLedger.from_dict(json.loads(json.dumps(held["a"].to_dict())))
    second=r.read(K,"a")
    assert first.record_digest==second.record_digest
    assert not r._diverged
    assert rederive(K,r.owner_id,"a",second.payload)==(second.revision,second.record_digest)

def test_new_reader_cannot_erase_conflicting_published_history():
    source,held,r=setup();old=held["a"];charge(old,1)
    held["a"]=BudgetLedger(total_budget=10.);charge(held["a"],2)
    token=source.publish(held)
    fresh=BudgetReader.following(lambda:token)
    for reader in (r,fresh):
        with pytest.raises(OwnerUnavailable): reader.read(K,"a")

def test_unknown_retained_entry_cannot_become_zero():
    source,held,r=setup()
    # Existing canonical ledger allows arbitrary detail, but unserializable
    # cyclic metadata cannot be silently discarded after its publication.
    cyclic={};cyclic["self"]=cyclic
    charge(held["a"],detail=cyclic)
    held["a"]=BudgetLedger(total_budget=10.)
    for _ in range(3):
        with pytest.raises(OwnerUnavailable): r.read(K,"a")

def test_foreign_source_token_refuses_instead_of_new_timeline():
    source,held,r=setup();charge(held["a"])
    foreign=AccountPublication();token=foreign.publish({"a":BudgetLedger(total_budget=10.)})
    r._follow=lambda:token
    with pytest.raises(OwnerUnavailable): r.read(K,"a")

def test_frozen_record_rederives_identity_without_liveness():
    source,held,r=setup();charge(held["a"])
    record=r.read(K,"a");f=FrozenReader(K,r.owner_id,{"a":(record,None)})
    assert not is_live(f) and f.read(K,"a").record_digest==record.record_digest
    source.close();source.retire()
    assert f.read(K,"a").revision=="1"  # historical replay survives, never live
    with pytest.raises(OwnerUnavailable):r.read(K,"a")

def test_forged_replay_derived_totals_refused():
    source,held,r=setup();charge(held["a"])
    record=r.read(K,"a");payload=json.loads(json.dumps(record.payload))
    payload["ledger"]["spent_total"]=0
    forged=OwnerRecord(K,r.owner_id,"a",record.revision,record.record_digest,payload)
    with pytest.raises(WorldRefused):FrozenReader(K,r.owner_id,{"a":(forged,None)})
