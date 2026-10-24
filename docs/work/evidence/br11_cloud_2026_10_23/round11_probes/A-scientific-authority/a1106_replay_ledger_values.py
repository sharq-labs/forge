"""Lens A r11: a bound ledger whose charges hold values the owner-rule read-back stringifies (Decimal / np.float32
predicted, a uuid charge id) or floats (np.int64 iteration): is the admission recorded and replayed REPRODUCED, and
does the recorded ledger re-derive the owner's own digest?"""
import json, uuid
from decimal import Decimal
import numpy as np
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import AdmissionRecord, BudgetReader, FeasibleActionSpace, admit, replay_admission
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
for name, kw in [("plain", {}), ("predicted Decimal", {"predicted": Decimal("1.5")}),
                 ("predicted np.float32", {"predicted": np.float32(1.5)}), ("iteration np.int64", {"iteration": np.int64(4)}),
                 ("charge_id uuid", {"charge_id": uuid.UUID(int=9)})]:
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    o.ledgers[lid].settle(**{"charge_id": "c-x", "action_id": "a", "iteration": 1, "family": ActionFamily.EXPLORE,
                             "realized": 1.0, **kw})
    authorities = o.authorities()
    world = o.world
    r = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), authorities)
    try:
        rec = json.loads(json.dumps(AdmissionRecord.of(r, authorities).to_dict()))
        out = replay_admission(rec).outcome.value
    except Exception as exc:
        out = f"{type(exc).__name__}: {str(exc)[:100]}"
    bound = [b for b in world.budget.statements if b.kind == "ledger"] if hasattr(world.budget, "statements") else []
    print(f"{name:22s} admission {r.status.value:22s} replay {out}")
