"""R10-D d16: an experiment whose metadata holds a cycle (a list that contains itself).  ceaf8cd: to_json refuses a
circular reference (OWNER_UNAVAILABLE).  c69e579: the exact-type walk _plain runs first and has no visited set.
Run with a time limit; a second thread's verification while the first is stuck shows the in-flight refusal."""
import sys, threading, time
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

o = ax.owned("battery")
eid = next(iter(o.experiments))
lid = next(k for k in o.ledgers if k.endswith(".solver"))
reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
cyc = []
cyc.append(cyc)
o.experiments[eid].metadata["cycle"] = cyc
out = {}


def first():
    t0 = time.time()
    try:
        reader.read(OwnerKind.EXPERIMENT, eid)
        out["first"] = "read"
    except OwnerUnavailable as e:
        out["first"] = "OWNER_UNAVAILABLE: " + str(e)[-60:]
    out["t"] = time.time() - t0


t = threading.Thread(target=first, daemon=True)
t.start()
t.join(5)
print("first verification finished within 5 s:", not t.is_alive(), out)
if t.is_alive():
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)                 # another verification, another account
        print("second verification (the ledger): read")
    except OwnerUnavailable as e:
        print("second verification (the ledger): OWNER_UNAVAILABLE:", str(e)[:110])
