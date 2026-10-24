"""Skeptic re-run of R15-C-F1, written independently.  Modes:
  concurrent  - V1 passes pinned()'s _sealed check, then V2 seals (MappingProxyType handing), restore, V1 compares.
  sequential  - same steps, V1 starts after the seal.
  noseal      - same as concurrent but V2 hands plain dicts (so S1 IS observed): control that the restore is refused
                when observed.
  restore_only- no V2 at all: does a restore of S1 (unobserved by anyone since dispatch) re-admit anyway?  If so, the
                seal is irrelevant (the documented residual: a spend+rollback between two verifications)."""
import sys, threading, types
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

MODE = sys.argv[1]
SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
st = {"proxy": False, "log": []}
go1, v1_asking = threading.Event(), threading.Event()

def accounts():
    name = threading.current_thread().name
    if name == "V1":
        v1_asking.set(); go1.wait(10)
    ledgers = dict(o.ledgers)
    st["log"].append((name, [c.charge_id for c in o.ledgers[lid].charges]))
    return (types.MappingProxyType(ledgers) if st["proxy"] else ledgers), dict(o.experiments)

calls = []
def executor(a):
    calls.append(1)
    o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=len(calls),
                          family=ActionFamily.EXPLORE, realized=1.0)

reader = BudgetReader.following(accounts)
auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auth)
assert r.admitted is not None
gw = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
s0 = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
gw.dispatch(r.admitted)
print("first dispatch: calls", len(calls), "charges", [c.charge_id for c in o.ledgers[lid].charges])
print("reader _seen len for ledger:", len(reader._seen.get(("ledger", lid), ())))

# sanity: an immediate second dispatch (no restore) must be refused
out = {}
def v1():
    try:
        gw.dispatch(r.admitted); out["v1"] = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        out["v1"] = "refused: " + str(exc)[:200]
t1 = threading.Thread(target=v1, name="V1")
if MODE in ("concurrent", "noseal", "restore_only"):
    t1.start(); assert v1_asking.wait(10)
if MODE != "restore_only":
    st["proxy"] = MODE != "noseal"
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid); print("V2: served")
    except OwnerUnavailable as exc:
        print("V2 refused:", str(exc)[:120])
    st["proxy"] = False
print("sealed:", reader._sealed is not None)
o.ledgers[lid] = BudgetLedger.from_dict(s0.to_dict())
if MODE == "sequential":
    t1.start()
go1.set(); t1.join(20)
print(f"MODE {MODE} | V1: {out.get('v1')} | executor calls: {len(calls)}")
print("charges now:", [c.charge_id for c in o.ledgers[lid].charges])
print("accounts() log:", st["log"])
