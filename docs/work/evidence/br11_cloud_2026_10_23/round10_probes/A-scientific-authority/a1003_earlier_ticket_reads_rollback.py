"""Lens A r10 (Q4/Q7, the ticket rule): the r9 control pauses the LATER verification after it was handed the spend.
Here the re-dispatch takes its ticket FIRST, but its accounts() reads the mapping only after a later-started
verification (T1) was handed the spend and the execution side restored the ledger (object-replacing restore, as in
the r9 control).  Does the earlier-ticket re-dispatch decide on the rollback and run the executor again?"""
import threading
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit, OwnerKind
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
t2_entered, go2 = threading.Event(), threading.Event()
handed1, resume1 = threading.Event(), threading.Event()


def accounts():
    name = threading.current_thread().name
    if name == "T2" and not go2.is_set():
        t2_entered.set()                 # T2 holds its ticket; it reads the mapping only when told to
        go2.wait(10)
    mapping = (dict(o.ledgers), dict(o.experiments))
    if name == "T1" and not resume1.is_set():
        handed1.set()                    # T1 was handed the spent ledger
        resume1.wait(10)
    return mapping


reader = BudgetReader.following(accounts)
authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
calls = []
gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
gateway.dispatch(r.admitted)
print("first dispatch: executor calls", len(calls))
spent = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
spent.settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE, realized=2.0)
o.ledgers[lid] = spent                                           # the executor spends (object replaced)
out = {}


def redispatch():
    try:
        gateway.dispatch(r.admitted)
        out["T2"] = "DISPATCHED"
    except DispatchRefused as exc:
        out["T2"] = f"refused: {str(exc)[:160]}"


def other_verification():
    try:
        out["T1"] = reader.pinned().read(OwnerKind.BUDGET_LEDGER, lid).revision
    except Exception as exc:
        out["T1"] = f"{type(exc).__name__}: {str(exc)[:120]}"


t2 = threading.Thread(target=redispatch, name="T2", daemon=True)
t2.start()
assert t2_entered.wait(10)                                       # T2 took the earlier ticket
t1 = threading.Thread(target=other_verification, name="T1", daemon=True)
t1.start()
assert handed1.wait(10)                                          # T1 (later ticket) was handed the spend
o.ledgers[lid] = before                                          # the execution side restores (replaces)
go2.set()
t2.join(10)
resume1.set()
t1.join(10)
print("T2 (earlier ticket, reads the restore):", out.get("T2"))
print("T1 (later ticket, handed the spend):", out.get("T1"))
print("executor calls:", len(calls))
try:
    print("next verification:", reader.pinned().read(OwnerKind.BUDGET_LEDGER, lid).revision)
except Exception as exc:
    print("next verification:", type(exc).__name__, str(exc)[:140])
