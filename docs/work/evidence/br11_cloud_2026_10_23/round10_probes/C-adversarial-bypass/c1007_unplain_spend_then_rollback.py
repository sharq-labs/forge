"""R10-C c1007: round 9 refuses a ledger whose RAW serialization is not exactly plain JSON (owners.py:363-365), before the
owner's own read-back (BudgetLedger.from_dict, which normalizes e.g. a numpy iteration to int).  BudgetLedger.settle
coerces only `realized`; `iteration` and `predicted` are stored as passed.  If the executor settles a spend with a
numpy iteration (or predicted), the follower cannot observe that spend (refused, not recorded); after a rollback to the
pre-spend state, is the executed action dispatched again?  No concurrency.  Public paths only: the execution side's
accounts() callable (object-replacing restore, as sria.campaign restores) and the desk's gateway.

Each variant: dispatch once; the executor settles; a verification reads the spend (sequentially: it is handed it);
the execution side restores the pre-spend ledger; re-dispatch."""
import sys

import numpy as np

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, DispatchRefused, ExecutionDesk, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
VARIANTS = {
    "python ints/floats (control)": dict(iteration=1, predicted=2.0),
    "numpy iteration": dict(iteration=np.int64(1), predicted=2.0),
    "numpy predicted": dict(iteration=1, predicted=np.float64(2.0)),
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
    spent.settle(charge_id="run-1", action_id="simulate_pulse", family=ActionFamily.EXPLORE, realized=2.0, **kw)
    o.ledgers[lid] = spent
    try:
        owner_digest = spent.digest
    except Exception as exc:  # noqa: BLE001
        owner_digest = f"owner digest raises {type(exc).__name__}"
    try:
        seen = f"read revision {reader.read(OwnerKind.BUDGET_LEDGER, lid).revision}"
    except OwnerUnavailable as exc:
        seen = f"refused: {str(exc)[:90]}"
    try:
        gateway.dispatch(r.admitted)
        while_spent = "DISPATCHED"
    except DispatchRefused as exc:
        while_spent = "refused " + str(exc)[str(exc).find("("):][:60]
    o.ledgers[lid] = before                                     # the execution side restores the pre-spend ledger
    try:
        gateway.dispatch(r.admitted)
        after = "DISPATCHED AGAIN"
    except DispatchRefused as exc:
        after = "refused " + str(exc)[str(exc).find("("):][:60]
    print(f"{label:30s} | owner's own digest of the spend: {'ok' if len(str(owner_digest)) == 64 else owner_digest}"
          f" | follower on the spend: {seen}\n{'':30s} | re-dispatch while spent: {while_spent} | after the restore:"
          f" {after} | executor ran {len(calls)}")


for label, kw in VARIANTS.items():
    run(label, kw)
