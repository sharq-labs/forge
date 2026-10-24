"""_plain coverage at c69e579 (owners.py:97-113), through the public reader: each value is placed in an experiment's
metadata and read by a following reader."""
import collections, json
import numpy as np
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.owners import rederive
from engcore.scientific import to_json
from engcore.scientific.experiments.experiment import ScientificExperiment

class S(str): pass
cases = {"dict subclass": collections.OrderedDict(a=1), "tuple": (1, 2), "numpy float64": np.float64(1.5),
         "numpy int64": np.int64(3), "nan": float("nan"), "inf": float("inf"), "bool": True, "str subclass": S("x"),
         "-0.0": -0.0, "big int": 2**70, "lone surrogate key": {"\ud800": 1}}
for name, value in cases.items():
    o = ax.gen1_pool()
    eid = next(iter(o.experiments))
    o.experiments[eid].metadata["v"] = value
    try:
        rec = BudgetReader.following(lambda: (o.ledgers, o.experiments)).read(OwnerKind.EXPERIMENT, eid)
        served = rec.payload["experiment"]["metadata"]["v"]
        _, dig = rederive(OwnerKind.EXPERIMENT, rec.owner_id, rec.record_id, rec.payload)
        restored = ScientificExperiment.from_dict(json.loads(to_json(o.experiments[eid])))
        o.experiments[eid] = restored
        rec2 = BudgetReader.following(lambda: (o.ledgers, o.experiments)).read(OwnerKind.EXPERIMENT, eid)
        print(f"{name:20s} served {served!r:16} rederives {dig == rec.record_digest}; JSON restore same digest "
              f"{rec2.record_digest == rec.record_digest}")
    except OwnerUnavailable as exc:
        print(f"{name:20s} OwnerUnavailable: {str(exc)[len('experiment '):][:90]}")
