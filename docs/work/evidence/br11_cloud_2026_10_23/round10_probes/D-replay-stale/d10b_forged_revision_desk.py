"""R10-D d10b: a submitted world whose declaration binding revision is '²' (str.isdigit() True, int() raises) and
whose digest is not the one in force: through admit(), the Mind port and the desk with live readers."""
import dataclasses, json
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import (Authorities, AdmissionRecord, DeclarationReader, FeasibleActionSpace, ScientificWorld,
                                admit, replay_admission, ExecutionDesk, MindWorldPort)

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
world = o.world
d = o.declaration
held = {"set": [d]}
decl = DeclarationReader.following(lambda: held["set"])
a = Authorities.of(*(decl if type(r) is DeclarationReader else r for r in o.authorities().readers))
gw = ExecutionDesk(a, lambda x: None, accept_synthetic=True).gateway()


def forged(rev, dig):
    payload = world.to_dict()
    payload["declaration"]["revision"] = rev
    payload["declaration"]["record_digest"] = dig
    return ScientificWorld.from_dict({k: v for k, v in payload.items() if k not in ("content_digest", "revision_id")})


for rev in ("2", "²", "¹⁰", "1" * 5000):
    fw = forged(rev, "1" * 64)
    print(f"--- revision {rev[:12]!r} (len {len(rev)}): built, intact={fw.intact()}")
    try:
        r = admit(FeasibleActionSpace.build(fw), o.propose("simulate_pulse", *SIM, world=fw), a)
        print("  admit:", r.status.value, r.codes())
        rec = json.loads(json.dumps(AdmissionRecord.of(r, a).to_dict()))
        print("  replay:", replay_admission(rec).outcome.value)
    except Exception as e:
        print(f"  admit RAISED {type(e).__name__}: {str(e)[:150]}")
    try:
        port = MindWorldPort(FeasibleActionSpace.build(fw))
        r = port.request_admission(o.propose("simulate_pulse", *SIM, world=fw), gw)
        print("  port.request_admission:", r.status.value, r.codes())
    except Exception as e:
        print(f"  port.request_admission RAISED {type(e).__name__}: {str(e)[:150]}")
# the honest world still works afterwards
r = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), a)
print("honest world after:", r.status.value, r.codes())
