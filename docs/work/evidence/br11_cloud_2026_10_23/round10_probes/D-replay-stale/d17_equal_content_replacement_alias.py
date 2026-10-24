"""R10-D d17 (B9-m1's case): an experiment is replaced by an equal-content independent copy; the OLD object's metadata
is then changed in place.  The served record must equal the handed account, re-derive to its digest, and replay."""
import copy, json
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind, FeasibleActionSpace, admit, AdmissionRecord, replay_admission
from engcore.mind.world.owners import rederive

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
eid = next(iter(o.experiments))
o.experiments[eid].metadata["runs"] = {"list": ["a"]}
reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
a = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
first = reader.read(OwnerKind.EXPERIMENT, eid)
old = o.experiments[eid]
o.experiments[eid] = type(old).from_dict(copy.deepcopy(old.to_dict()))     # equal content, independent object
old.metadata["runs"]["list"].append("zzz")                                  # the discarded object moves
served = reader.read(OwnerKind.EXPERIMENT, eid)
handed = json.loads(json.dumps(o.experiments[eid].to_dict()))
print("served metadata == handed:", served.payload["experiment"]["metadata"] == handed["metadata"],
      served.payload["experiment"]["metadata"])
print("rederive == record:", rederive(OwnerKind.EXPERIMENT, served.owner_id, eid, json.loads(json.dumps(served.payload)))
      == (served.revision, served.record_digest))
w = o.world
r = admit(FeasibleActionSpace.build(w), o.propose("simulate_pulse", *SIM, world=w), a)
rec = json.loads(json.dumps(AdmissionRecord.of(r, a).to_dict()))
print("admission", r.status.value, "replay", replay_admission(rec).outcome.value)
