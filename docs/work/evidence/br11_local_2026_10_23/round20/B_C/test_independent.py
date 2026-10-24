import inspect, sys, threading
import pytest
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.owners import AccountPublication
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from tests.mind.test_authority_review_r14 import _settle
K=OwnerKind.BUDGET_LEDGER

@pytest.mark.parametrize("construct",[False,True])
@pytest.mark.parametrize("effect",["spent_restore","equal_detached","close","conflict"])
def test_at_final_boundary(construct,effect):
    source=AccountPublication(); account=BudgetLedger(total_budget=100.); held={"a":account}
    _settle(account,"baseline")
    saved=account.to_dict()
    follow=lambda:source.publish(held)
    reader=None if construct else BudgetReader.following(follow)
    reached=threading.Event(); resume=threading.Event(); out=[]; errors=[]
    lines,start=inspect.getsourcelines(BudgetReader._reconcile_publication)
    line=start+next(i for i,s in enumerate(lines) if "newer = self._source._newer(token)" in s)
    def work():
        paused=False
        def trace(frame,event,arg):
            nonlocal paused
            if not paused and event=="line" and frame.f_code is BudgetReader._reconcile_publication.__code__ and frame.f_lineno==line:
                paused=True; reached.set(); assert resume.wait(8)
            return trace
        sys.settrace(trace)
        try:
            r=BudgetReader.following(follow) if construct else reader.pinned()
            out.append(r)
        except BaseException as e: errors.append(e)
        finally:sys.settrace(None)
    thread=threading.Thread(target=work);thread.start()
    try:
        assert reached.wait(8)
        if effect=="close":
            source.close()
            with pytest.raises(OwnerUnavailable):source.retire()
        else:
            replacement=BudgetLedger.from_dict(saved)
            if effect=="spent_restore":_settle(replacement,"hidden-spend")
            if effect=="conflict":
                replacement=BudgetLedger(total_budget=100.);_settle(replacement,"other-timeline")
            source.publish({"a":replacement})
            held["a"]=BudgetLedger.from_dict(saved)
            source.publish(held)
    finally:resume.set();thread.join(10)
    assert not thread.is_alive()
    if effect=="close":
        assert len(errors)==1 and isinstance(errors[0],OwnerUnavailable)
        source.retire();assert not source._generations
    else:
        assert not errors,errors
        assert len(out)==1
        if effect=="equal_detached":
            assert out[0].read(K,"a").revision=="1"
            _settle(held["a"],"progress")
            live=out[0] if construct else reader
            assert live.read(K,"a").revision=="2"
            assert not live._diverged
        else:
            with pytest.raises(OwnerUnavailable):out[0].read(K,"a")
            live=out[0] if construct else reader
            for _ in range(3):
                held["a"]=BudgetLedger.from_dict(saved)
                with pytest.raises(OwnerUnavailable):live.read(K,"a")

@pytest.mark.parametrize("interrupts",[1,2,3])
def test_multiple_readers_recover_unhanded_published_spend(interrupts):
    source=AccountPublication(); original=BudgetLedger(total_budget=100.); saved=original.to_dict();held={"a":original}
    follow=lambda:source.publish(held)
    readers=[BudgetReader.following(follow) for _ in range(3)]
    replacement=BudgetLedger.from_dict(saved);source.publish({"a":replacement});_settle(replacement,"spent")
    def interrupted():
        source.publish(held)
        raise KeyboardInterrupt()
    for r in readers:
        r._follow=interrupted
        for _ in range(interrupts):
            with pytest.raises(KeyboardInterrupt):r.pinned()
        r._follow=follow
    for r in readers:
        with pytest.raises(OwnerUnavailable):r.read(K,"a")
    source.close();source.retire();assert not source._generations
