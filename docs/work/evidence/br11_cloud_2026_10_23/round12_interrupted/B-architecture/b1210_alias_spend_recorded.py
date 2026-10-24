"""R12-B b1210: 'one object handed under two ids is observed under both and refused to that verification': a spend
on the bound solver ledger while the execution side hands it under a second id too; then a restore handed under one
id; re-dispatch.  Refused iff the aliased state's history was recorded (run on HEAD and on the alias_not_recorded2
mutant)."""
import copy

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
state = {"alias": False}


def accounts():
    ledgers = dict(o.ledgers)
    if state["alias"]:
        ledgers["mirror.of.solver"] = ledgers[lid]
    return ledgers, dict(o.experiments)


reader = BudgetReader.following(accounts)
auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auth)
calls = []
before = BudgetLedger.from_dict(copy.deepcopy(o.ledgers[lid].to_dict()))


def executor(a):
    calls.append(1)
    o.ledgers[lid].settle(charge_id=f"run.{len(calls)}", action_id="simulate_pulse", iteration=1,
                          family=ActionFamily.EXPLORE, realized=1.0)
    state["alias"] = True


gw = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
gw.dispatch(r.admitted)
try:
    reader.pinned().read(OwnerKind.BUDGET_LEDGER, lid)
    seen = "served"
except OwnerUnavailable as e:
    seen = "refused: " + str(e)[:60]
o.ledgers[lid] = before
state["alias"] = False
try:
    gw.dispatch(r.admitted)
    again = "DISPATCHED AGAIN"
except DispatchRefused:
    again = "refused"
print(f"verification handed the aliased spend: {seen}; after the restore: {again}; executor ran {len(calls)}")
