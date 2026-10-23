"""R10-C c1004: the ticket rule with an execution-side accounts() that BLOCKS or RAISES, through the public gateway.

(a) one verification's accounts() blocks (ticket 1 in flight); while it blocks, re-dispatches of an executed action
    after a rollback, and fresh admissions, are refused ('earlier verification ... in flight'), never dispatched;
    after it returns, the spend it carried is compared and the rollback is behind.
(b) the blocked verification is handed the ROLLED-BACK mapping (it took its mapping after the restore) while a later
    one is handed the spend and compares first (refused, but recorded): the blocked one then reads the rollback: behind.
(c) accounts() raises on one verification: its ticket leaves the in-flight set; the next verification decides.
(d) accounts() blocks forever: every later verification of that reader is refused for as long as it blocks
    (fail closed; the reader is unusable until then)."""
import threading
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def setup(accounts_factory):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    accounts, ctl = accounts_factory(o)
    reader = BudgetReader.following(accounts)
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    spent = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    spent.settle(charge_id="run-1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE, realized=2.0)
    o.ledgers[lid] = spent
    return o, lid, reader, gateway, r, calls, before, ctl


def try_dispatch(gateway, admitted):
    try:
        gateway.dispatch(admitted)
        return "DISPATCHED"
    except DispatchRefused as exc:
        return "refused: " + str(exc)[str(exc).find("("):][:70]


def blocking_factory(o):
    ctl = {"block_on": None, "entered": threading.Event(), "go": threading.Event(), "map_first": True}

    def accounts():
        if threading.current_thread().name == ctl["block_on"] and not ctl["go"].is_set():
            mapping = (dict(o.ledgers), dict(o.experiments)) if ctl["map_first"] else None
            ctl["entered"].set()
            ctl["go"].wait(30)
            return mapping if mapping is not None else (dict(o.ledgers), dict(o.experiments))
        return dict(o.ledgers), dict(o.experiments)
    return accounts, ctl


# (a)
o, lid, reader, gateway, r, calls, before, ctl = setup(blocking_factory)
ctl["block_on"] = "B"
tb = threading.Thread(target=reader.pinned, name="B", daemon=True)
tb.start()
assert ctl["entered"].wait(10)                     # B was handed the spend; blocks inside accounts()
o.ledgers[lid] = before                            # rollback
print("(a) while B blocks: re-dispatch", try_dispatch(gateway, r.admitted))
print("(a) while B blocks: fresh admission",
      gateway.admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM)).codes())
ctl["go"].set()
tb.join(10)
print("(a) after B compared the spend: re-dispatch", try_dispatch(gateway, r.admitted), "| executor ran", len(calls))

# (b)
o, lid, reader, gateway, r, calls, before, ctl = setup(blocking_factory)
ctl["block_on"], ctl["map_first"] = "B", False
tb = threading.Thread(target=reader.pinned, name="B", daemon=True)
tb.start()
assert ctl["entered"].wait(10)                     # B (ticket earlier) holds no mapping yet
try:
    reader.pinned()                                # a later verification handed the spend: refused, but recorded
    print("(b) later verification: decided")
except Exception as exc:  # noqa: BLE001
    print("(b) later verification:", type(exc).__name__)
o.ledgers[lid] = before                            # rollback, then B maps it
out = {}
td = threading.Thread(target=lambda: out.setdefault("d", try_dispatch(gateway, r.admitted)), name="D", daemon=True)
td.start()
td.join(10)
print("(b) re-dispatch while B in flight:", out.get("d"))
ctl["go"].set()
tb.join(10)
print("(b) after B read the rollback: re-dispatch", try_dispatch(gateway, r.admitted), "| executor ran", len(calls))


# (c)
def raising_factory(o):
    ctl = {"raise_on": None}

    def accounts():
        if threading.current_thread().name == ctl["raise_on"]:
            raise RuntimeError("execution side busy")
        return dict(o.ledgers), dict(o.experiments)
    return accounts, ctl


o, lid, reader, gateway, r, calls, before, ctl = setup(raising_factory)
ctl["raise_on"] = "E"
te = threading.Thread(target=lambda: (lambda: reader.pinned())() if False else None, name="E")
res = {}


def raising_pin():
    try:
        reader.pinned()
    except OwnerUnavailable as exc:
        res["E"] = "OwnerUnavailable: " + str(exc)[:60]


te = threading.Thread(target=raising_pin, name="E")
te.start()
te.join()
print("(c) E:", res.get("E"), "| in flight after:", sorted(reader._in_flight), "| next verification reads ledger rev",
      reader.read(OwnerKind.BUDGET_LEDGER, lid).revision)

# (d)
o, lid, reader, gateway, r, calls, before, ctl = setup(blocking_factory)
ctl["block_on"] = "F"
tf = threading.Thread(target=reader.pinned, name="F", daemon=True)
tf.start()
assert ctl["entered"].wait(10)
refusals = 0
t0 = time.time()
for _ in range(20):
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
    except OwnerUnavailable as exc:
        refusals += "still in flight" in str(exc)
print(f"(d) while F blocks: {refusals}/20 later verifications refused 'earlier ... in flight' ({time.time() - t0:.2f}s)")
ctl["go"].set()
tf.join(10)
print("(d) after F returns: ledger rev", reader.read(OwnerKind.BUDGET_LEDGER, lid).revision)
