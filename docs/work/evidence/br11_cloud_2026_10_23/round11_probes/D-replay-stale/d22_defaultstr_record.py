"""R11-D d22: admissions over ledgers whose charges carry values the digest rule's default=str turns into strings
(Decimal, a set, a date, numpy scalars, enums), recorded and replayed; a JSON checkpoint restore of each unchanged
ledger (json.dumps(to_dict(), default=str), and plain json.dumps where it can) gives the same history and record
digest.  argv[1]: output file.  Run under several PYTHONHASHSEEDs; replay with d11_replay.py."""
import datetime
import decimal
import enum
import hashlib
import json
import sys

import numpy as np

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.repsem import canonical_bytes
from engcore.mind.world import AdmissionRecord, BudgetReader, FeasibleActionSpace, OwnerKind, admit, replay_admission
from engcore.mind.world.authority import OwnerUnavailable
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]


class Note(str, enum.Enum):
    RAN = "ran"


CASES = {
    "predicted Decimal": {"predicted": decimal.Decimal("1.50")},
    "detail set": {"detail": {"beta", "alpha", "gamma", "delta"}},
    "detail date": {"detail": datetime.date(2026, 10, 23)},
    "iteration np.int64": {"iteration": np.int64(3)},
    "predicted np.float32": {"predicted": np.float32(0.1)},
    "detail str-enum": {"detail": Note.RAN},
    "detail nested dict": {"detail": {"b": [1, (2, 3)], "a": {"z": None}}},
}
records = {}
for label, kw in CASES.items():
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    o.ledgers[lid].settle(**{"charge_id": "c1", "action_id": "x", "iteration": 1, "family": ActionFamily.EXPLORE,
                             "realized": 0.25, **kw})
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    auth = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
    try:
        first = reader.read(OwnerKind.BUDGET_LEDGER, lid)
    except OwnerUnavailable as e:
        print(f"{label}: OWNER_UNAVAILABLE {str(e)[:120]}")
        continue
    owner_digest = o.ledgers[lid].digest
    w = o.world
    r = admit(FeasibleActionSpace.build(w), o.propose("simulate_pulse", *SIM, world=w), auth)
    rec = json.loads(json.dumps(AdmissionRecord.of(r, auth).to_dict()))
    sha = hashlib.sha256(canonical_bytes(rec)).hexdigest()
    rr = replay_admission(rec)
    restores = []
    for how, dump in (("default=str", lambda d: json.dumps(d, default=str)), ("plain", json.dumps)):
        try:
            text = dump(o.ledgers[lid].to_dict())
        except TypeError as e:
            restores.append(f"{how}: checkpoint impossible ({e})")
            continue
        o.ledgers[lid] = BudgetLedger.from_dict(json.loads(text))
        try:
            again = reader.read(OwnerKind.BUDGET_LEDGER, lid)
            restores.append(f"{how}: same digest {again.record_digest == first.record_digest}")
        except OwnerUnavailable as e:
            restores.append(f"{how}: OWNER_UNAVAILABLE {str(e)[:90]}")
    served = first.payload["ledger"]["charges"][-1]
    print(f"{label}: {r.status.value} replay {rr.outcome.value} sha {sha[:12]} | record digest == owner digest "
          f"{first.record_digest == owner_digest} | served {({k: served[k] for k in ('predicted', 'detail', 'iteration')})}"
          f" | restores: {restores}")
    records[label] = {"record": rec, "sha": sha}
json.dump({"records": records}, open(sys.argv[1], "w"), sort_keys=True)
