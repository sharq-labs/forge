import numpy as np
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader
o = ax.owned("battery")
eid = next(iter(o.experiments))
try:
    BudgetReader.following(lambda: (dict(o.ledgers), {np.str_(k): v for k, v in o.experiments.items()}))
    print("numpy keys at construction: accepted")
except Exception as exc:
    print("numpy keys at construction:", type(exc).__name__, exc)
