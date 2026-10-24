"""Lens A r11: which honest numpy/enum/Decimal values in an evaluation's metadata does the owner-rule read-back
(to_json -> from_dict) accept, and what does it serve for them (meaning preserved?)."""
import enum
from decimal import Decimal
import numpy as np
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.scientific.experiments import EvaluationStatus, ScientificEvaluation


class Mode(str, enum.Enum):
    A = "a"


class Lvl(enum.IntEnum):
    ONE = 1


for name, v in [("np.float64", np.float64(0.5)), ("np.float32", np.float32(0.5)), ("np.int64", np.int64(3)),
                ("np.bool_", np.bool_(True)), ("str Enum", Mode.A), ("IntEnum", Lvl.ONE), ("Decimal", Decimal("0.5")),
                ("tuple", (1, 2)), ("nested list", [[1, 2]]), ("bool", True)]:
    o = ax.owned("battery")
    eid = next(iter(o.experiments))
    o.experiments[eid].record(ScientificEvaluation("e.np", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x",
                                                   metadata={"v": v}))
    reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    try:
        rec = reader.pinned().read(OwnerKind.EXPERIMENT, eid)
        served = rec.payload["experiment"]["evaluations"][-1]["metadata"]["v"]
        print(f"{name:12s} READ served {served!r} ({type(served).__name__})")
    except Exception as exc:
        print(f"{name:12s} REFUSED {str(exc)[:100]}")
