"""R11-D d23: the ledger half of round 10's 'a handed state its owner cannot write down refuses the account for good'.
The executor settles a charge in a form the ledger's owner cannot read back from its own written text (a tuple charge
id: from_dict(to_dict()) holds it, its JSON form is a list, which the owner's from_dict cannot hash), or leaves the
ledger in a state its owner refuses (a reservation above the total).  A verification is handed that state; the
execution side restores the pre-spend ledger; the executed action is dispatched again?  Run from a tree's root."""
import json

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


def spend_tuple_id(L, n):
    L.settle(charge_id=("run", n), action_id="simulate_pulse", iteration=n, family=ActionFamily.EXPLORE, realized=1.0)


def spend_then_overreserve(L, n):
    L.settle(charge_id=f"run-{n}", action_id="simulate_pulse", iteration=n, family=ActionFamily.EXPLORE, realized=1.0)
    L.reserved_validation_budget = L.total_budget + 1.0


for label, spend in (("tuple charge id", spend_tuple_id), ("reservation above total", spend_then_overreserve)):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auth)
    before = BudgetLedger.from_dict(json.loads(json.dumps(o.ledgers[lid].to_dict())))
    calls = []

    def executor(a):
        calls.append(1)
        spend(o.ledgers[lid], len(calls))

    gw = ExecutionDesk(auth, executor, accept_synthetic=True).gateway()
    gw.dispatch(r.admitted)
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
        seen = "read"
    except OwnerUnavailable as e:
        seen = "FOR GOOD" if "from then on" in str(e) else "this verification only"
    o.ledgers[lid] = before
    try:
        gw.dispatch(r.admitted)
        again = "DISPATCHED AGAIN"
    except DispatchRefused as e:
        again = "refused"
    print(f"[{label}] verification handed the spend: {seen}; after the restore: {again}; executor calls {len(calls)}")
