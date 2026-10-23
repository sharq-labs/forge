"""The r7 provider test (test_authority_review_r7.py:319-341) at c69e579: which status does the sim.secret check get,
and which check produces the AUTHORITY_STALE the test asserts?"""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.world import FeasibleActionSpace, admit

SIM = ax.base("battery")["simulate_pulse"]
base = b.battery_world()
w2 = b.world(base.world_id, base.variables, entities=base.entities, constraints=base.constraints,
             channels=base.channels, applicability=base.applicability,
             providers=base.providers + (b.provider("sim.secret", "1.0"),), budget=base.budget,
             references=base.references, actions=base.actions)
o2 = ax.owned("battery", w2)
in_force = ax.owned("battery").declaration
print("revisions: world's declaration", o2.declaration.revision, "| in force", in_force.revision)
r = admit(FeasibleActionSpace.build(o2.world), o2.propose("simulate_pulse", *SIM, world=o2.world),
          o2.authorities(declarations=(in_force,), refresh=True))
print("codes:", sorted(r.codes()))
print("sim.secret:", {c.status.value for c in r.verification.checks if c.record_id == "sim.secret"})
print("STALE checks:", [(c.owner_kind.value, c.record_id) for c in r.verification.checks if c.status.value == "stale"])
