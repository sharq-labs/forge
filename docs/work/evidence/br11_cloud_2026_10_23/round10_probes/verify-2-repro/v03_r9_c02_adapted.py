"""R9-C c02: round 8 locks read-back + compare (B8-m1), but accounts() is still called with no lock held.  With the
execution side's normal restore (it REPLACES the account object, as sria.campaign does), a verification T2 that was
HANDED the spent ledger by accounts() before a rollback, but has not yet taken the lock, protects nothing: the
re-dispatch T1 reads the rolled-back object first, and the executed action is dispatched again.  Deterministic
interleaving: T2 pauses between accounts() and the locked read-back (a window any thread switch can open).
Mirrors tests/mind/test_authority_review_r8.py::test_a_spend_one_verification_read_is_observed_before_a_rollback_can_be_read
but pauses one step earlier."""
import threading

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
calls = []
gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
gateway.dispatch(r.admitted)
o.ledgers[lid].settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                      realized=2.0)                                   # the executor spends
handed, resume = threading.Event(), threading.Event()
real = BudgetReader._observe_all


def paused(self, snapshot, *a):
    if threading.current_thread().name == "T2":
        if isinstance(snapshot, BudgetReader):
            print("T2 was handed the ledger at revision", snapshot._ledgers[lid].revision, "(spent:",
                  snapshot._ledgers[lid] is not before, ")")
        handed.set()
        resume.wait(10)                                              # not yet read back under the lock
    return real(self, snapshot, *a)


BudgetReader._observe_all = paused
t2 = threading.Thread(target=lambda: reader.pinned(), name="T2", daemon=True)
t2.start()
assert handed.wait(10)
o.ledgers[lid] = before                                              # the execution side restores (replaces the object)
outcome = {}
try:
    gateway.dispatch(r.admitted)
    outcome["T1"] = "DISPATCHED AGAIN"
except DispatchRefused as exc:
    outcome["T1"] = f"refused: {str(exc)[:120]}"
resume.set()
t2.join(10)
print("re-dispatch after the rollback:", outcome["T1"], "| executor ran", len(calls), "times")
try:
    gateway.dispatch(r.admitted)
    print("a later re-dispatch: DISPATCHED")
except DispatchRefused as exc:
    print("a later re-dispatch: refused:", str(exc)[:100])
