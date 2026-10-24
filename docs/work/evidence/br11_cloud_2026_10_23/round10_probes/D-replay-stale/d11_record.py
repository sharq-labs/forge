"""R10-D d11: record admissions (followed accounts; experiments with plain metadata of several shapes, a JSON-restored
experiment and ledger, behind / rewrite / in-flight refusals, older-revision STALE) and write them to argv[1]; print a
line per case.  Run under several PYTHONHASHSEEDs and compare; replay with d11_replay.py under other seeds."""
import dataclasses, hashlib, json, sys, threading
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.repsem import canonical_bytes
from engcore.mind.world import (AdmissionRecord, FeasibleActionSpace, admit, replay_admission, WorldRefused,
                                project_world, BudgetReader, DeclarationReader, Authorities)
from engcore.scientific.experiments import ScientificEvaluation, EvaluationStatus
from engcore.sria.campaign.budget import BudgetLedger
from engcore.sria.decision import ActionFamily

SIM = ax.base("battery")["simulate_pulse"]
records = {}


def swap(o, **kw):
    return type(o.authorities()).of(*(kw.get(type(r).__name__, r) for r in o.authorities().readers))


def rec(label, o, auth, world=None):
    w = world if world is not None else project_world(o.declaration, auth)
    r = admit(FeasibleActionSpace.build(w), o.propose("simulate_pulse", *SIM, world=w), auth)
    try:
        record = json.loads(json.dumps(AdmissionRecord.of(r, auth).to_dict()))
    except WorldRefused as e:
        print(f"{label}: {r.status.value} {r.codes()} NOT RECORDABLE: {e}")
        return r
    rr = replay_admission(record)
    sha = hashlib.sha256(canonical_bytes(record)).hexdigest()
    exp = [x for x in record["snapshot"].get("records", [])] if isinstance(record.get("snapshot"), dict) else []
    print(f"{label}: {r.status.value} {r.codes()} | replay {rr.outcome.value} | sha {sha[:16]}")
    records[label] = {"record": record, "sha": sha}
    return r


def followed(o):
    fol = BudgetReader.following(lambda: (o.ledgers, o.experiments))
    return fol, swap(o, BudgetReader=fol)


# experiments with plain metadata of several shapes (tuples, nested, -0.0, big int, unicode, floats)
for label, meta in {"meta none": None,
                    "meta nested": {"z": {"b": [1, 2.5, None, True], "a": "x"}, "a": [{"k": -0.0}]},
                    "meta tuple": {"t": (1, 2, (3, 4))},
                    "meta bigint/unicode": {"n": 2 ** 70, "u": "é中\U0001F600", "f": 1e-310},
                    "meta float-int": {"one": 1.0, "i": 1}}.items():
    o = ax.owned("battery"); eid = next(iter(o.experiments))
    if meta is not None:
        o.experiments[eid].metadata.update(meta)
    for k in range(2):
        o.experiments[eid].record(ScientificEvaluation(f"{eid}.e{k}", {}, status=EvaluationStatus.FAILED, detail="s"))
    fol, a = followed(o)
    rec(f"experiment {label}", o, a)
    # a JSON restore of the unchanged experiment (object replaced): not behind, not a rewrite
    o.experiments[eid] = type(o.experiments[eid]).from_dict(json.loads(json.dumps(o.experiments[eid].to_dict())))
    rec(f"experiment {label}, JSON-restored", o, a)

# ledger with charges, JSON-restored
o = ax.owned("battery"); lid = next(k for k in o.ledgers if k.endswith(".solver"))
o.ledgers[lid].settle(charge_id="c1", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=0.25)
fol, a = followed(o)
rec("ledger with a charge", o, a)
o.ledgers[lid] = BudgetLedger.from_dict(json.loads(json.dumps(o.ledgers[lid].to_dict())))
rec("ledger with a charge, JSON-restored", o, a)

# behind, then rewrite
o = ax.owned("battery"); lid = next(k for k in o.ledgers if k.endswith(".solver"))
fol, a = followed(o)
w0 = project_world(o.declaration, a)
before = BudgetLedger.from_dict(o.ledgers[lid].to_dict())
o.ledgers[lid].settle(charge_id="run-1", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0)
project_world(o.declaration, a)
o.ledgers[lid] = before
rec("ledger behind", o, a, world=w0)
rw = BudgetLedger.from_dict(before.to_dict())
rw.settle(charge_id="other", action_id="x", iteration=1, family=ActionFamily.EXPLORE, realized=1.0)
o.ledgers[lid] = rw
rec("ledger rewrite", o, a, world=w0)

# in flight: an earlier verification paused inside accounts() on another thread
o = ax.owned("battery")
handed, resume = threading.Event(), threading.Event()
def accounts():
    m = (dict(o.ledgers), dict(o.experiments))
    if threading.current_thread().name == "P" and not resume.is_set():
        handed.set(); resume.wait(10)
    return m
fol = BudgetReader.following(accounts); a = swap(o, BudgetReader=fol)
w = project_world(o.declaration, a)
t = threading.Thread(target=fol.pinned, name="P", daemon=True); t.start(); handed.wait(10)
rec("in flight (earlier verification paused)", o, a, world=w)
resume.set(); t.join(10)
rec("after the earlier verification completed", o, a, world=w)

# older revision world (STALE) with following declarations
o = ax.owned("battery"); w1 = o.world
lid = next(k for k in o.ledgers if k.endswith(".solver"))
o.ledgers["battery.solver.v2"] = ax.ledger(o.ledgers[lid].total_budget, 0.0, o.ledgers[lid].cost_unit, "v2")
d1 = o.declaration
b2 = tuple(dataclasses.replace(x, ref="battery.solver.v2") if x.ref == lid else x for x in d1.budget)
d2 = type(d1).from_dict(dataclasses.replace(d1, revision=d1.revision + 1, budget=b2).to_dict())
o.declaration = d2
rec("older-revision world", o, o.authorities(), world=w1)
json.dump({"records": records}, open(sys.argv[1], "w"), sort_keys=True)
