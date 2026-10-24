"""F10 f08: round 9 says an experiment read back from plain JSON data changes no digest across a JSON round trip.
Plain values at the edges (negative zero, subnormal, 2**70, nan, inf, tuple, bool, nested empty) in an experiment's
metadata: live admission, AdmissionRecord.of, JSON round trip, replay; and the JSON-restored account is not a rewrite."""
import json
import math

import engcore
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import AdmissionRecord, BudgetReader, FeasibleActionSpace, OwnerKind, admit, replay_admission
from engcore.mind.world.authority import Authorities
from engcore.scientific import Quantity
from engcore.scientific.experiments.experiment import ScientificExperiment

print("engcore from", engcore.__file__)
POOL = ("pool_query", {"I_A": Quantity(1, "A"), "t_on_s": Quantity(60, "s")})
for label, value in [("neg zero", -0.0), ("subnormal", 5e-324), ("2**70", 2 ** 70), ("nan", math.nan),
                     ("inf", math.inf), ("tuple", (1, "a", (2.5,))), ("bool", True), ("nested empty", {"a": [], "b": {}}),
                     ("unicode", "é "), ("big float", 1.7976931348623157e308)]:
    o = ax.gen1_pool()
    eid = next(iter(o.experiments))
    o.experiments[eid].metadata["v"] = value
    o._world = None
    try:
        auth = o.authorities()
        world = o.world
        r = admit(FeasibleActionSpace.build(world), o.propose(*POOL, world=world), auth)
        rec = json.loads(json.dumps(AdmissionRecord.of(r, auth).to_dict()))
        rep = replay_admission(rec)
        # JSON restore of the unchanged account under a following reader: not a rewrite
        reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
        reader.read(OwnerKind.EXPERIMENT, eid)
        o.experiments[eid] = ScientificExperiment.from_dict(json.loads(json.dumps(o.experiments[eid].to_dict())))
        try:
            again = reader.read(OwnerKind.EXPERIMENT, eid).revision
        except Exception as exc:  # noqa: BLE001
            again = f"REFUSED: {str(exc)[:80]}"
        print(f"{label:13s}: admission {r.status.value} admitted={r.admitted is not None}; replay {rep.outcome.value} "
              f"{(rep.detail or '')[:70]}; JSON restore -> {again}")
    except Exception as exc:  # noqa: BLE001
        print(f"{label:13s}: {type(exc).__name__}: {str(exc)[:150]}")
