"""F10 f01: the round-9 ticket rule orders verifications by when they START (ticket), not by when the execution side's
accounts() HANDS them a state.  A re-dispatch D that took its ticket first, but whose accounts() returns after a
restore, decides on the restored account while a later-ticket verification T2, which was HANDED the spent account
before the restore, has not compared yet.  The executed action is dispatched again.

Deterministic: only the execution side's accounts() callable is timed by events (no reader internals patched):
  D's accounts() is entered (ticket taken) and waits until the restore; T2's accounts() hands the spent mapping and
  pauses before returning (a thread switch anywhere between taking the mapping and the compare opens this window).
Mirrors tests/mind/test_authority_review_r9.py::test_a_rollback_read_while_an_earlier_verification_holds_the_spend_never_redispatches
with the two tickets in the other order."""
import sys
import threading

import engcore
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, admit
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

print("engcore from", engcore.__file__)
mode = sys.argv[1] if len(sys.argv) > 1 else "replace"     # replace | inplace
SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))

d_entered, restored = threading.Event(), threading.Event()
t2_handed, t2_resume = threading.Event(), threading.Event()


def accounts():
    name = threading.current_thread().name
    if name == "D":
        d_entered.set()                       # D's ticket is already taken (pinned() takes it before accounts())
        restored.wait(10)
    mapping = (dict(o.ledgers), dict(o.experiments))
    if name == "T2":
        t2_handed.set()
        t2_resume.wait(10)                    # handed the spent mapping; returns later
    return mapping


reader = BudgetReader.following(accounts)
authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
print("admitted:", r.admitted is not None)
calls = []
gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
gateway.dispatch(r.admitted)                                             # executes once
if mode == "replace":
    spent = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    spent.settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE, realized=2.0)
    o.ledgers[lid] = spent                                               # the executor spends (object replaced)
else:
    o.ledgers[lid].settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                          realized=2.0)                                  # the executor spends in place
print("spent revision", o.ledgers[lid].revision, "before revision", before.revision)

out = {}


def redispatch():
    try:
        gateway.dispatch(r.admitted)
        out["D"] = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        out["D"] = f"refused: {str(exc)[:160]}"


def t2_verify():
    try:
        p = reader.pinned()
        out["T2"] = f"pinned; serves revision {p.read(__import__('engcore.mind.world', fromlist=['OwnerKind']).OwnerKind.BUDGET_LEDGER, lid).revision}"
    except Exception as exc:  # noqa: BLE001
        out["T2"] = f"{type(exc).__name__}: {str(exc)[:120]}"


d = threading.Thread(target=redispatch, name="D", daemon=True)
d.start()
assert d_entered.wait(10)                    # D started first (earlier ticket), its accounts() not yet answered
t2 = threading.Thread(target=t2_verify, name="T2", daemon=True)
t2.start()
assert t2_handed.wait(10)                    # T2 (later ticket) was HANDED the spent ledger
print("T2 handed spent ledger:", True)
if mode == "replace":
    o.ledgers[lid] = before                  # the execution side restores (replaces the object)
else:
    o.ledgers[lid] = before                  # in-place spend, restore by replacement of the mapping entry
restored.set()
d.join(10)
print("D (re-dispatch, ticket earlier, read after the restore):", out.get("D"), "| executor calls:", len(calls))
t2_resume.set()
t2.join(10)
print("T2:", out.get("T2"))
try:
    gateway.dispatch(r.admitted)
    print("a later re-dispatch: DISPATCHED; executor calls:", len(calls))
except DispatchRefused as exc:
    print("a later re-dispatch: refused:", str(exc)[:140], "| executor calls:", len(calls))
# part 2 (K9-F1's second consequence): the restored account's continuation (the second execution settles on it)
o.ledgers[lid].settle(charge_id="run-1-again", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE,
                      realized=2.0)
from engcore.mind.world import OwnerKind
for i in range(2):
    try:
        print("after the restored account moves on, verification", i, "reads revision",
              reader.read(OwnerKind.BUDGET_LEDGER, lid).revision)
    except Exception as exc:  # noqa: BLE001
        print("after the restored account moves on, verification", i, "->", type(exc).__name__, str(exc)[:150])
