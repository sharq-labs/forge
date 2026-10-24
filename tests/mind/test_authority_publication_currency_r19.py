"""R19 publication currency: synthetic execution controls, not scientific validation."""
from threading import Event,Thread,current_thread
from unittest.mock import patch
import pytest
from tests.mind.test_authority_review_r14 import ax,_solver,_settle,_refused,SIM
from engcore.mind.world import BudgetReader,ExecutionDesk,FeasibleActionSpace,admit
from engcore.mind.world.owners import AccountPublication
from engcore.sria.campaign.budget import BudgetLedger

@pytest.mark.parametrize("prepublish",[False,True])
def test_completed_spend_published_before_comparison_refuses_dispatch(prepublish):
    o=ax.owned("battery");lid=_solver(o);initial=o.ledgers[lid];saved=initial.to_dict();source=AccountPublication()
    handed,commit=Event(),Event();read,resume=Event(),Event()
    def follow():
        maps=dict(o.ledgers),dict(o.experiments)
        if current_thread().name=="late-publication":handed.set();assert commit.wait(5)
        return source.publish(*maps)
    r1=BudgetReader.following(follow);r2=BudgetReader.following(follow)
    def authorities(r):return type(o.authorities()).of(*(r if type(x) is BudgetReader else x for x in o.authorities().readers))
    calls=[]
    def execute(auth):
        calls.append(current_thread().name)
        o.ledgers[lid]=BudgetLedger.from_dict(saved)
        _settle(o.ledgers[lid],f"run.{len(calls)}")
        if prepublish:source.publish(o.ledgers,o.experiments)
    a1,a2=authorities(r1),authorities(r2)
    g1=ExecutionDesk(a1,execute,accept_synthetic=True).gateway();g2=ExecutionDesk(a2,execute,accept_synthetic=True).gateway()
    admitted=admit(FeasibleActionSpace.build(o.world),o.propose("simulate_pulse",*SIM),a1).admitted
    g1.dispatch(admitted);assert len(calls)==1
    spent=o.ledgers[lid]
    assert any(any(account is spent for _,account in token.bindings.entries[0]) for token in source._generations) is prepublish
    out2=[]
    t2=Thread(target=lambda:out2.append(_refused(g2,admitted)),name="late-publication");t2.start();assert handed.wait(5)
    o.ledgers[lid]=initial
    original=BudgetReader._read_back;out1=[]
    def paused(self):
        result=original(self)
        if current_thread().name=="late-dispatch":read.set();assert resume.wait(5)
        return result
    with patch.object(BudgetReader,"_read_back",paused):
        t1=Thread(target=lambda:out1.append(_refused(g1,admitted)),name="late-dispatch");t1.start();assert read.wait(5)
        commit.set();t2.join(5);assert not t2.is_alive() and out2==[True]
        resume.set();t1.join(5);assert not t1.is_alive()
    print("prepublish",prepublish,"calls",calls,"second_refused",out1)
    assert out1==[True] and len(calls)==1
    assert _refused(g1,admitted) and _refused(g2,admitted)


from engcore.mind.world import OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments import EvaluationStatus, ScientificEvaluation


@pytest.mark.parametrize("construct", [False, True])
@pytest.mark.parametrize("kind", ["ledger", "experiment"])
@pytest.mark.parametrize("change", ["identical", "forward"])
def test_new_generation_is_reconciled_without_rejecting_honest_progress(construct, kind, change):
    source = AccountPublication()
    held = {"a": BudgetLedger(total_budget=100.)}
    experiments = dict(ax.gen1_pool().experiments) if kind == "experiment" else {}
    eid = next(iter(experiments), None)
    follow = lambda: source.publish(held, experiments)
    reader = None if construct else BudgetReader.following(follow)
    original = BudgetReader._read_back
    calls = []
    def publication_during_readback(snapshot):
        result = original(snapshot)
        calls.append(1)
        if len(calls) == 1:
            if change == "forward":
                if kind == "ledger":
                    _settle(held["a"], "forward")
                else:
                    experiments[eid].record(ScientificEvaluation("forward", {}, status=EvaluationStatus.NOT_CONVERGED))
            # A distinct benign binding forces a publication without replacing
            # the account being read; forward owner history must be read again.
            held["extra"] = BudgetLedger(total_budget=1.)
            follow()
        return result
    with patch.object(BudgetReader, "_read_back", publication_during_readback):
        if construct:
            reader = BudgetReader.following(follow)
        else:
            snapshot = reader.pinned()
    assert len(calls) == 2
    key = (kind, "a" if kind == "ledger" else eid)
    expected = 1 if change == "forward" else 0
    assert len(reader._seen[key]) == expected
    record = reader.read(OwnerKind.BUDGET_LEDGER if kind == "ledger" else OwnerKind.EXPERIMENT, key[1])
    assert record.revision == str(expected)


@pytest.mark.parametrize("boundary", ["interrupt", "close", "churn"])
def test_reconciliation_retry_is_bounded_and_retains_lifetime(boundary):
    source = AccountPublication()
    held = {"a": BudgetLedger(total_budget=100.)}
    follow = lambda: source.publish(held)
    reader = BudgetReader.following(follow)
    original = BudgetReader._read_back
    calls = []
    def change(snapshot):
        result = original(snapshot)
        calls.append(1)
        if len(calls) == 1 or boundary == "churn":
            held["extra"] = BudgetLedger(total_budget=1.)
            follow()
        elif boundary == "interrupt":
            raise KeyboardInterrupt()
        elif boundary == "close":
            source.close()
            with pytest.raises(OwnerUnavailable):
                source.retire()
        return result
    with patch.object(BudgetReader, "_read_back", change):
        with pytest.raises(KeyboardInterrupt if boundary == "interrupt" else OwnerUnavailable):
            reader.pinned()
    assert len(calls) == (3 if boundary == "churn" else 2)
    assert not reader._in_flight
    assert all(not lease.active for lease in source._leases)
    if boundary != "close":
        assert reader.read(OwnerKind.BUDGET_LEDGER, "a") is not None
        source.close()
    source.retire()
    assert not source._generations
