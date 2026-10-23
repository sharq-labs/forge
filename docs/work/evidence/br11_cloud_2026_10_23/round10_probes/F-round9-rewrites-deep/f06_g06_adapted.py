"""Round 8 caches an experiment's read-back FORM (`back = from_dict(payload).to_dict()`) per account, keyed by the
content digest of the live payload.  `to_dict` / `from_dict` copy metadata shallowly, and round 8 dropped the
read's deepcopy, so the cached form holds the execution side's own metadata VALUE objects.  An execution side that
replaces a metadata value with an equal one (the content digest is unchanged: a cache hit) and later edits the object
it replaced serves a record that is neither the owner's current statement nor the content its digest names.  No
concurrency is needed.  Live admission and AdmissionRecord.of accept it; replay refuses the record."""
import json
import engcore
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import AdmissionRecord, FeasibleActionSpace, OwnerKind, admit, project_world, replay_admission

print("engcore from", engcore.__file__)
POOL = ("pool_query", {"I_A": ax.Quantity(1, "A") if hasattr(ax, "Quantity") else None, "t_on_s": None})
from engcore.scientific import Quantity
POOL = ("pool_query", {"I_A": Quantity(1, "A"), "t_on_s": Quantity(60, "s")})

o = ax.gen1_pool()
eid = next(iter(o.experiments))
n1 = {"k": 1}
o.experiments[eid].metadata["note"] = n1
auth = o.authorities()                                   # the execution side's one live set of readers
world = project_world(o.declaration, auth)               # reads the experiment back: the cache entry aliases n1
o.experiments[eid].metadata["note"] = {"k": 1}           # replaced by an equal value: same content digest
n1["k"] = 5                                              # the execution side edits the object it replaced
rec = auth.read(OwnerKind.EXPERIMENT, eid)
print("live metadata:", o.experiments[eid].metadata, "| served metadata:", rec.payload["experiment"]["metadata"])
r = admit(FeasibleActionSpace.build(world), o.propose(*POOL, world=world), auth)
print("admission:", r.status.value, "admitted:", r.admitted is not None)
record = json.loads(json.dumps(AdmissionRecord.of(r, auth).to_dict()))
served = [x for x in record["snapshot"]["records"] if x["owner_kind"] == "experiment"]
print("recorded experiment metadata:", [x["record"]["payload"]["experiment"]["metadata"] for x in served])
rep = replay_admission(record)
print("replay:", rep.outcome.value, (rep.detail or "")[:160])
