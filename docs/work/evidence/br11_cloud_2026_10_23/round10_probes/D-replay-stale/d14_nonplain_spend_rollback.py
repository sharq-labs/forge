"""R10-D d14: a spend whose ledger serialization is valid JSON but not 'plain' by exact type (BudgetLedger.settle
coerces `realized` to float but keeps `predicted` as given: here a numpy float64, a float subclass that json
serializes), then an object-replacing restore to the pre-spend state (plain, JSON checkpoint), then a re-dispatch of
the executed action.  Single-threaded, no concurrency.  Run from a tree's root to compare revisions."""
import json, sys
import numpy as np
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, FeasibleActionSpace, admit, ExecutionDesk, DispatchRefused, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
for label, kw in {"predicted=float": {"predicted": 1.5}, "predicted=np.float64": {"predicted": np.float64(1.5)}}.items():
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    a = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    r = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), a)
    checkpoint = json.dumps(o.ledgers[lid].to_dict())                    # the execution side's checkpoint (JSON)
    calls = []

    def executor(auth):
        calls.append(auth)
        o.ledgers[lid].settle(charge_id=f"run-{len(calls)}", action_id="simulate_pulse", iteration=len(calls),
                              family=ActionFamily.EXPLORE, realized=2.0, **kw)

    gw = ExecutionDesk(a, executor, accept_synthetic=True).gateway()
    gw.dispatch(r.admitted)                                              # executed once: the spend
    try:
        rec = reader.read(OwnerKind.BUDGET_LEDGER, lid)                  # a verification handed the spent ledger
        seen = f"read revision {rec.revision}"
    except OwnerUnavailable as e:
        seen = f"OWNER_UNAVAILABLE: {str(e)[:110]}"
    try:
        gw.dispatch(r.admitted); again = "DISPATCHED"                    # before the restore
    except DispatchRefused as e:
        again = f"refused ({str(e)[:60]})"
    o.ledgers[lid] = BudgetLedger.from_dict(json.loads(checkpoint))      # restore from the checkpoint (replaces)
    try:
        gw.dispatch(r.admitted); after = "DISPATCHED"
    except DispatchRefused as e:
        after = f"refused ({str(e)[:80]})"
    print(f"[{label}] verification after the spend: {seen}\n    re-dispatch before restore: {again}\n"
          f"    re-dispatch after restore: {after}; executor calls: {len(calls)}")
