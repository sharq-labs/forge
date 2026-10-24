"""R10-D d14b: which JSON-serializable values does each revision read back?  A ledger charge with predicted np.float64,
an IntEnum iteration, a str-subclass detail; an experiment with np.float64 / str-enum metadata."""
import enum, json
import numpy as np
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.sria.decision import ActionFamily


class It(enum.IntEnum):
    ONE = 1


class Why(str, enum.Enum):
    RUN = "run"


def try_read(label, o, kind, rid):
    try:
        r = BudgetReader.following(lambda: (o.ledgers, o.experiments)).read(kind, rid)
        print(f"[{label}] read: revision {r.revision}")
    except OwnerUnavailable as e:
        print(f"[{label}] OWNER_UNAVAILABLE: {str(e)[-60:]}")


for label, kw in {"ledger predicted=np.float64": {"predicted": np.float64(1.5)},
                  "ledger iteration=IntEnum": {"iteration": It.ONE},
                  "ledger detail=str-enum": {"detail": Why.RUN}}.items():
    o = ax.owned("battery"); lid = next(k for k in o.ledgers if k.endswith(".solver"))
    args = dict(charge_id="c1", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0)
    args.update(kw)
    o.ledgers[lid].settle(**args)
    json.dumps(o.ledgers[lid].to_dict())                                  # valid JSON either way
    try_read(label, o, OwnerKind.BUDGET_LEDGER, lid)
for label, v in {"experiment metadata np.float64": np.float64(0.5), "experiment metadata str-enum": Why.RUN}.items():
    o = ax.owned("battery"); eid = next(iter(o.experiments))
    o.experiments[eid].metadata["m"] = v
    json.dumps(o.experiments[eid].to_dict())
    try_read(label, o, OwnerKind.EXPERIMENT, eid)
