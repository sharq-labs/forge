"""Critic k01: which ordinary owner-produced values does round 9's exact-type plain rule refuse?  Builds experiment
evaluations and ledgers through the OWNERS' public constructors (no in-process introspection) and reports, per value
kind, whether owners._plain accepts the owner's own to_dict()."""
import numpy as np

from engcore.mind.world.owners import _plain
from engcore.scientific import Quantity
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily


def first_nonplain(x, path="$"):
    t = type(x)
    if t is dict:
        for k, v in x.items():
            if type(k) is not str:
                return f"{path} key {k!r} ({type(k).__name__})"
            r = first_nonplain(v, f"{path}.{k}")
            if r:
                return r
        return None
    if t in (list, tuple):
        for i, v in enumerate(x):
            r = first_nonplain(v, f"{path}[{i}]")
            if r:
                return r
        return None
    if t in (str, int, float, bool, type(None)):
        return None
    return f"{path} = {x!r} ({t.__module__}.{t.__name__})"


cases = {
    "Quantity(np.float64)": lambda: ScientificEvaluation("e", {"x": Quantity(np.float64(1.5), "A")}),
    "Quantity(np.int64)": lambda: ScientificEvaluation("e", {"x": Quantity(np.int64(2), "A")}),
    "objective np.float64": lambda: ScientificEvaluation("e", {"x": Quantity(1.0, "A")},
                                                         objective_values={"y": Quantity(np.float64(3.0), "V")}),
    "metadata flat np.float64": lambda: ScientificEvaluation("e", {"x": Quantity(1.0, "A")}, metadata={"s": np.float64(1)}),
    "metadata flat str": lambda: ScientificEvaluation("e", {"x": Quantity(1.0, "A")}, metadata={"s": "a"}),
    "metadata nested list": lambda: ScientificEvaluation("e", {"x": Quantity(1.0, "A")}, metadata={"s": [1, 2]}),
    "metadata nested dict": lambda: ScientificEvaluation("e", {"x": Quantity(1.0, "A")}, metadata={"s": {"a": 1}}),
    "metadata tuple": lambda: ScientificEvaluation("e", {"x": Quantity(1.0, "A")}, metadata={"s": (1, 2)}),
}
for label, make in cases.items():
    try:
        ev = make()
        d = ev.to_dict()
        print(f"evaluation {label:28s} plain={_plain(d)!s:5s} first non-plain: {first_nonplain(d)}")
    except Exception as exc:  # noqa: BLE001
        print(f"evaluation {label:28s} constructor refuses: {type(exc).__name__}: {str(exc)[:80]}")

for label, kw in {"settle python": dict(iteration=1, predicted=2.0, realized=2.0),
                  "settle realized np.float64": dict(iteration=1, predicted=None, realized=np.float64(2.0)),
                  "settle predicted np.float64": dict(iteration=1, predicted=np.float64(2.0), realized=2.0),
                  "settle iteration np.int64": dict(iteration=np.int64(1), predicted=None, realized=2.0),
                  "settle predicted int": dict(iteration=1, predicted=2, realized=2.0)}.items():
    led = BudgetLedger(total_budget=10.0)
    led.settle(charge_id="c", action_id="a", family=ActionFamily.EXPLORE, **kw)
    d = led.to_dict()
    print(f"ledger {label:32s} plain={_plain(d)!s:5s} first non-plain: {first_nonplain(d)}")
for label, kw in {"total np.float64": dict(total_budget=np.float64(10.0)),
                  "enforced_cap np.float64": dict(total_budget=10.0, enforced_cap=np.float64(5.0))}.items():
    try:
        led = BudgetLedger(**kw)
        d = led.to_dict()
        print(f"ledger {label:32s} plain={_plain(d)!s:5s} first non-plain: {first_nonplain(d)}")
    except Exception as exc:  # noqa: BLE001
        print(f"ledger {label:32s} constructor refuses: {type(exc).__name__}: {str(exc)[:80]}")
