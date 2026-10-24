"""P3: lasting refusals of the unread-entries rule (not read back, behind unread, rewrote unread, sealed) are recordable
with AdmissionRecord.of and replay REPRODUCED; record bytes are compared across hash seeds by the driver.

usage: p3_record_replay.py make <outdir>   |   p3_record_replay.py replay <record.json>"""
import hashlib
import json
import os
import sys
import types

mode = sys.argv[1]
if mode == "replay":
    from engcore.mind.world.admission import replay_admission
    from engcore.mind.repsem import canonical_bytes
    payload = json.load(open(sys.argv[2]))
    r = replay_admission(payload)
    print(os.path.basename(sys.argv[2]), os.environ.get("PYTHONHASHSEED"), r.outcome.value,
          hashlib.sha256(canonical_bytes(r.recomputed)).hexdigest()[:16] if r.recomputed else "-", (r.detail or "")[:80])
    sys.exit(0)

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.repsem import canonical_bytes
from engcore.mind.world import BudgetReader, FeasibleActionSpace, admit
from engcore.mind.world.admission import AdmissionRecord
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

out = sys.argv[2]
os.makedirs(out, exist_ok=True)
SIM = ax.base("battery")["simulate_pulse"]


class SelfFillingNote:
    def __str__(self):
        cache = {"a": 1}
        for k in cache:
            cache[k + "x"] = 2
        return "unreached"


def setup(accounts=None):
    o = ax.owned("battery")
    lid = next(k for k in o.ledgers if k.endswith(".solver"))
    reader = BudgetReader.following(accounts(o) if accounts else (lambda: (dict(o.ledgers), dict(o.experiments))))
    base = o.authorities()
    auth = type(base).of(*(reader if type(r) is BudgetReader else r for r in base.readers))
    return o, lid, reader, auth


def record(name, o, auth):
    res = admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM), auth)
    why = sorted({(c.status.value, (c.detail or {}).get("why", "")[:70]) for c in res.verification.failures()})
    try:
        rec = AdmissionRecord.of(res, auth)
    except Exception as exc:  # noqa: BLE001
        print(f"{name}: {res.status.value} {why} -> NOT RECORDABLE: {exc}")
        return
    d = rec.to_dict()
    with open(os.path.join(out, name + ".json"), "w") as f:
        json.dump(d, f, sort_keys=True)
    print(f"{name}: {res.status.value} {why} result={hashlib.sha256(canonical_bytes(d['result'])).hexdigest()[:16]}")


o, lid, reader, auth = setup()
record("r0_feasible", o, auth)
live = o.ledgers[lid]
earlier = live.charges
earlier_obj = BudgetLedger.from_dict(live.to_dict())
live.settle(charge_id="run.1", action_id="simulate_pulse", iteration=1, family=ActionFamily.EXPLORE, realized=0.5,
            detail=SelfFillingNote())
record("r1_not_read_back", o, auth)
object.__setattr__(live, "charges", earlier)                  # back in place: a prefix of the unread entries
record("r2_behind_unread", o, auth)
o.ledgers[lid] = earlier_obj                                  # object-replacing restore: rewrote them
record("r3_rewrote_unread", o, auth)

state = {"proxy": False}
o2, lid2, reader2, auth2 = setup(lambda o: (lambda: ((types.MappingProxyType(dict(o.ledgers)) if state["proxy"]
                                                       else dict(o.ledgers)), dict(o.experiments))))
state["proxy"] = True
record("r4_sealed", o2, auth2)
