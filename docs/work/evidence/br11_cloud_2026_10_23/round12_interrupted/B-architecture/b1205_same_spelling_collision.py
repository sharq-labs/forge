"""R12-B b1205: round 11 reads a str-subclass id as the plain str it spells (owners.py _handed and the strict
constructor).  Two handed entries whose keys are distinct dict keys but spell the same id (a str subclass that hashes
by identity) collapse into one: the later entry silently replaces the earlier in the snapshot (no refusal, no 'two
accounts under one id'), and the strict constructor, which refused such ids before round 11, now accepts the set and
drops one account.  Shows (1) which object the reader serves, (2) the constructor, (3) a spend on the dropped
account never observed and a restore re-dispatching."""
import copy

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


class Tag(str):                              # a tagged id: equal only to itself (identity hash)
    __hash__ = object.__hash__

    def __eq__(self, other):
        return self is other


a = BudgetLedger(total_budget=10.0, cost_unit="hour")
b = BudgetLedger(total_budget=99.0, cost_unit="hour")
handed = {Tag("L"): a, Tag("L"): b}
print("(1) handed entries:", len(handed))
try:
    strict = BudgetReader(handed, {})
    print("(2) strict constructor accepted; ledgers held:", {k: v.total_budget for k, v in strict._ledgers.items()})
except Exception as e:  # noqa: BLE001
    print("(2) strict constructor refused:", e)
f = BudgetReader.following(lambda: (handed, {}))
rec = f.pinned().read(OwnerKind.BUDGET_LEDGER, "L")
print("(1) following reader serves ledger 'L' with total", rec.payload["ledger"]["total_budget"])

# (3) the bound solver ledger is also handed, after the spend, under a second key spelling its id
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
state = {"spent": False}
stale = BudgetLedger.from_dict(copy.deepcopy(o.ledgers[lid].to_dict()))


def accounts():
    ledgers = {Tag(k): v for k, v in o.ledgers.items()}
    if state["spent"]:
        ledgers[Tag(lid)] = stale                  # a second entry spelling the same id (a stale cache entry)
    return ledgers, dict(o.experiments)


reader = BudgetReader.following(accounts)
auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
space = FeasibleActionSpace.build(o.world)
r = admit(space, o.propose("simulate_pulse", *SIM), auth)
calls = []


def executor(x):
    calls.append(1)
    o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=1,
                          family=ActionFamily.EXPLORE, realized=1.0)
    state["spent"] = True


gw = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
gw.dispatch(r.admitted)
seen = []
for _ in range(2):
    try:
        seen.append("served %d charges" % len(reader.read(OwnerKind.BUDGET_LEDGER, lid).payload["ledger"]["charges"]))
    except OwnerUnavailable as e:
        seen.append("refused " + str(e)[:60])
o.ledgers[lid] = stale                            # restore
state["spent"] = False
try:
    gw.dispatch(r.admitted)
    again = "DISPATCHED AGAIN"
except DispatchRefused:
    again = "refused"
print(f"(3) verifications after the spend: {seen}; history recorded {len(reader._seen[('ledger', lid)])}; after the "
      f"restore: {again}; executor ran {len(calls)}")
