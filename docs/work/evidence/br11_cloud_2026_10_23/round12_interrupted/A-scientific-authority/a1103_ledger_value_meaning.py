"""Lens A r11: what the owner-rule ledger read-back does to values the owner holds.  For each ledger: the reader's
outcome, whether its record digest is the owner's own BudgetLedger.digest, the Python type of each charge field in the
record payload, and whether the decision fields (pools, cost_unit) and the owner's affordable() agree between the live
owner object and the record."""
import uuid
from decimal import Decimal
import numpy as np
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.sria.campaign.budget import BudgetLedger, BudgetCharge
from engcore.sria.decision import ActionFamily


def settled(**kw):
    led = BudgetLedger(total_budget=10.0, cost_unit="dimensionless")
    led.settle(**{"charge_id": "c1", "action_id": "a", "iteration": 1, "family": ActionFamily.EXPLORE,
                  "realized": 2.0, **kw})
    return led


def direct(**kw):
    ch = BudgetCharge(**{"charge_id": "c1", "action_id": "a", "iteration": 1, "family": ActionFamily.EXPLORE,
                         "realized": 2.0, "from_general_pool": 2.0, **kw})
    return BudgetLedger(total_budget=10.0, cost_unit="dimensionless", charges=(ch,))


cases = {
    "plain": settled(),
    "predicted Decimal": settled(predicted=Decimal("1.5")),
    "predicted np.float32": settled(predicted=np.float32(1.5)),
    "predicted np.float64": settled(predicted=np.float64(1.5)),
    "iteration np.int64": settled(iteration=np.int64(3)),
    "charge_id uuid": settled(charge_id=uuid.UUID(int=7)),
    "detail dict": settled(detail={"host": "a"}),
    "detail set": settled(detail={1, 2}),
    "pools np.float32 (direct charge)": direct(realized=np.float32(0.1), from_general_pool=np.float32(0.1)),
    "realized Decimal (direct charge)": direct(realized=Decimal("2.0"), from_general_pool=Decimal("2.0"), from_validation_reservation=Decimal("0")),
    "total nan": BudgetLedger(total_budget=float("nan"), cost_unit="dimensionless"),
}
for name, led in cases.items():
    try:
        rec = BudgetReader.following(lambda led=led: ({"l": led}, {})).pinned().read(OwnerKind.BUDGET_LEDGER, "l")
    except Exception as exc:
        print(f"{name:34s} REFUSED {type(exc).__name__}: {str(exc)[:110]}")
        continue
    try:
        own = led.digest
    except Exception as exc:
        own = f"owner digest raises {type(exc).__name__}"
    ch = rec.payload["ledger"]["charges"]
    types = {k: type(v).__name__ for k, v in (ch[0].items() if ch else ()) if k in ("charge_id", "iteration",
                                                                                     "predicted", "detail", "realized")}
    back = BudgetLedger.from_dict(rec.payload["ledger"])
    try:
        agree = (led.general_pool, led.validation_pool, led.affordable(7.9, family=ActionFamily.EXPLORE),
                 led.affordable(8.0, family=ActionFamily.EXPLORE)) == \
                (back.general_pool, back.validation_pool, back.affordable(7.9, family=ActionFamily.EXPLORE),
                 back.affordable(8.0, family=ActionFamily.EXPLORE))
    except Exception as exc:
        agree = f"raises {type(exc).__name__}"
    print(f"{name:34s} READ digest==owner {rec.record_digest == own} types {types} decision fields agree {agree}")
