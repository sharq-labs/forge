"""R14-C probe 1: a handed state not read back is NOT recorded when a concurrently compared verification already
accepted a LONGER state; that longer state rewrote the unread one (restore + two other charges) and the executed
action is admitted and dispatched again.  Control: the same steps compared in the other order are refused."""
import sys, threading, time
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.projection import project_world
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
ORDER = sys.argv[1]          # "concurrent" (V2 compares first) or "sequential" (V1 compares first)


class SlowMovingNote:        # the interpreter's own mutation error (transient, 'may have moved'), slowly, on V1 only
    def __str__(self):
        if threading.current_thread().name == "V1":
            time.sleep(0.2)
        cache = {"a": 1}
        for k in cache:
            cache[k + "x"] = 2
        return "unreached"


o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
calls = []
v1_handed = threading.Event()


def accounts():
    m = (dict(o.ledgers), dict(o.experiments))
    if threading.current_thread().name == "V1":
        v1_handed.set()
    return m


def executor(authorization):
    calls.append(1)
    o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=len(calls),
                          family=ActionFamily.EXPLORE, realized=1.0, detail=SlowMovingNote())


reader = BudgetReader.following(accounts)
authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
assert r.admitted is not None
gateway = ExecutionDesk(authorities, executor, accept_synthetic=True).gateway()
s0 = BudgetLedger.from_dict(o.ledgers[lid].to_dict())          # the checkpoint before the spend
n0 = len(s0.charges)
gateway.dispatch(r.admitted)                                   # executes: run.1 settled (S1, n0+1)
print("after first dispatch: calls", len(calls), "charges", len(o.ledgers[lid].charges))

out = {}
def v1():
    try:
        out["v1"] = reader.read(OwnerKind.BUDGET_LEDGER, lid)
    except OwnerUnavailable as exc:
        out["v1"] = "refused: " + str(exc)[:160]

t1 = threading.Thread(target=v1, name="V1")
t1.start()
assert v1_handed.wait(10)                                      # V1 was handed S1 (object L1)
if ORDER == "sequential":
    t1.join(10)
# checkpoint restore (object replaced) and two other actions' charges: n0+2 entries, rewriting run.1
o.ledgers[lid] = BudgetLedger.from_dict(s0.to_dict())
o.ledgers[lid].settle(charge_id="other.1", action_id="other", iteration=2, family=ActionFamily.EXPLORE, realized=0.5)
o.ledgers[lid].settle(charge_id="other.2", action_id="other", iteration=3, family=ActionFamily.EXPLORE, realized=0.5)


def readmit():
    try:
        world = project_world(o.declaration, authorities)
    except OwnerUnavailable as exc:
        return "projection refused: " + str(exc)[:200]
    res = gateway.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world))
    if res.admitted is None:
        return "admission refused: " + ",".join(res.codes())
    try:
        gateway.dispatch(res.admitted)
        return "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        return "dispatch refused: " + str(exc)[:200]

v2 = readmit()
t1.join(10)
print("ORDER", ORDER)
print("V1:", out.get("v1"))
print("V2 (fresh world from the owners):", v2)
print("executor calls:", len(calls), " unread entries:", {k: len(v) for k, v in reader._unread_entries.items()},
      " diverged:", list(reader._diverged))
v3 = readmit()
print("V3 later:", v3, " executor calls:", len(calls))
