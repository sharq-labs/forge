"""Round 8 caches an experiment's read-back FORM (rebuilt.to_dict()) per account and serves deep copies of it while the
content digest of the account's current to_dict() is unchanged.  Round 8 also dropped round 7's copy.deepcopy of the
payload, so the cached form shares the account's metadata VALUE OBJECTS (ScientificExperiment.to_dict/from_dict copy
metadata shallowly).  If the execution side replaces the account by an equal-content copy (a restore) and the OLD object's
metadata is later mutated in place, the follower serves the OLD object's mutated metadata under the cached digest: the
served payload is not the record its digest names and not the account handed over.  AdmissionRecord.of records it,
and replay refuses it (REPLAY_DEPENDENCY_UNAVAILABLE).

Uses only public objects (o.experiments is the execution side's own account mapping; metadata is a public attribute).
"""
import copy
import json

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import AdmissionRecord, BudgetReader, FeasibleActionSpace, OwnerKind, admit, replay_admission
from engcore.mind.world.owners import rederive
from engcore.scientific import Quantity
from engcore.scientific.experiments.experiment import ScientificExperiment

POOL = ("pool_query", {"I_A": Quantity(1, "A"), "t_on_s": Quantity(60, "s")})

o = ax.gen1_pool()
eid = next(iter(o.experiments))
E1 = o.experiments[eid]
E1.metadata["notes"] = ["calibrated"]          # an execution-side metadata value (JSON-writable list)
o._world = None
auth = o.authorities()
world = o.world
r1 = admit(FeasibleActionSpace.build(world), o.propose(*POOL, world=world), auth)
print("admission 1:", r1.status.value, "admitted" if r1.admitted else "not admitted")

# the execution side restores the account: an equal-content, independent object
E2 = ScientificExperiment.from_dict(copy.deepcopy(E1.to_dict()))
o.experiments[eid] = E2
# somebody still holding the old object edits its metadata in place (E2 is untouched)
E1.metadata["notes"].append("REWRITTEN-ON-THE-OLD-OBJECT")

rec = auth.read(OwnerKind.EXPERIMENT, eid)
served_notes = rec.payload["experiment"]["metadata"]["notes"]
print("account handed over (E2) metadata:", E2.metadata["notes"])
print("served payload metadata          :", served_notes)
kind_rev, digest = rederive(OwnerKind.EXPERIMENT, rec.owner_id, rec.record_id, rec.payload)
print("served record digest == digest re-derived from its own payload:", digest == rec.record_digest)

r2 = admit(FeasibleActionSpace.build(world), o.propose(*POOL, world=world), auth)
print("admission 2:", r2.status.value, "admitted" if r2.admitted else "not admitted")
record = json.loads(json.dumps(AdmissionRecord.of(r2, auth).to_dict()))
print("replay of admission 2:", replay_admission(record).outcome.value)
