"""verify-1-scope: ledger analogue. Which settle() inputs make the follower unable to read the spend back, at this tree?
Then the restore + re-dispatch sequence of R10-C c1007."""
import decimal
import numpy as np
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
VARIANTS = {
    "control": dict(iteration=1, predicted=2.0),
    "numpy iteration": dict(iteration=np.int64(1), predicted=2.0),
    "numpy predicted": dict(iteration=1, predicted=np.float64(2.0)),
    "Decimal predicted": dict(iteration=1, predicted=decimal.Decimal("2.0")),
    "nan predicted": dict(iteration=1, predicted=float("nan")),
    "inf predicted": dict(iteration=1, predicted=float("inf")),
    "str iteration": dict(iteration="1", predicted=2.0),
    "float iteration": dict(iteration=1.0, predicted=2.0),
    "bool iteration": dict(iteration=True, predicted=2.0),
}


def run(label, kw):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), authorities)
    calls = []
    gateway = ExecutionDesk(authorities, calls.append, accept_synthetic=True).gateway()
    before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    gateway.dispatch(r.admitted)
    spent = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
    try:
        spent.settle(charge_id="run-1", action_id="simulate_pulse", family=ActionFamily.EXPLORE, realized=2.0, **kw)
    except Exception as exc:  # noqa: BLE001
        print(f"{label:20s} | settle refused: {type(exc).__name__}: {str(exc)[:60]}")
        return
    o.ledgers[lid] = spent
    try:
        seen = f"read revision {reader.read(OwnerKind.BUDGET_LEDGER, lid).revision}"
    except OwnerUnavailable as exc:
        seen = f"refused: {str(exc)[70:150]}"
    o.ledgers[lid] = before
    try:
        gateway.dispatch(r.admitted)
        after = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        after = "refused " + str(exc)[str(exc).find("("):][:50]
    print(f"{label:20s} | follower: {seen} | after restore: {after} | ran {len(calls)}")


for label, kw in VARIANTS.items():
    run(label, kw)
