"""Lens A r10: a BudgetLedger settled with a numpy `predicted` / `iteration` (settle() coerces only `realized`):
README §4 states the plain-data rule for experiments only; the code applies it to ledgers too (owners.py:363-365)."""
import numpy as np
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily
for label, kw in (("python floats", dict(iteration=1, predicted=1.0)),
                  ("numpy predicted", dict(iteration=1, predicted=np.float64(1.0))),
                  ("numpy iteration", dict(iteration=np.int64(1), predicted=1.0))):
    led = BudgetLedger(total_budget=10.0)
    led.settle(charge_id="c1", action_id="a", family=ActionFamily.EXPLORE, realized=1.0, **kw)
    for name, reader in (("static", BudgetReader({"L": led}, {})),
                         ("following", BudgetReader.following(lambda led=led: ({"L": led}, {})))):
        try:
            r = reader.read(OwnerKind.BUDGET_LEDGER, "L")
            print(label, name, "READ revision", r.revision)
        except Exception as exc:
            print(label, name, "REFUSED", type(exc).__name__, str(exc)[:110])
