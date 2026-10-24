"""R10-D d10: STALE vs MISMATCH for unnamed bindings at c69e579.  (a) real older revision (world rev n, in force rev
n+1); (b) same revision, other content; (c) newer revision than the one in force; (d) forged world declaration binding
revision with a non-ASCII digit ('²', isdigit() True, int() fails); (e) forged older revision number with a digest
the owner never held; (f) replay of each recorded admission."""
import dataclasses, json, traceback
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.world import (Authorities, AdmissionRecord, DeclarationReader, FeasibleActionSpace, ScientificWorld,
                                admit, replay_admission, project_world, ExecutionDesk, MindWorldPort)

SIM = ax.base("battery")["simulate_pulse"]


def show(label, world, o, readers):
    try:
        r = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), Authorities.of(*readers))
    except Exception as e:
        print(f"[{label}] admit RAISED {type(e).__name__}: {str(e)[:160]}")
        return None
    secret = sorted({c.status.value for c in r.verification.checks if c.record_id == "sim.secret"})
    decl = sorted({c.status.value for c in r.verification.checks if c.owner_kind.value == "declaration"})
    print(f"[{label}] {r.status.value} {r.codes()} admitted={r.admitted is not None} sim.secret={secret} declaration={decl}")
    try:
        rec = json.loads(json.dumps(AdmissionRecord.of(r, Authorities.of(*readers)).to_dict()))
        print(f"    replay: {replay_admission(rec).outcome.value}")
    except Exception as e:
        print(f"    record/replay raised {type(e).__name__}: {str(e)[:120]}")
    return r


base = b.battery_world()
w2 = b.world(base.world_id, base.variables, entities=base.entities, constraints=base.constraints,
             channels=base.channels, applicability=base.applicability,
             providers=base.providers + (b.provider("sim.secret", "1.0"),), budget=base.budget,
             references=base.references, actions=base.actions)
o2 = ax.owned("battery", w2)
world = o2.world
dw = o2.declaration
print("world declaration revision", world.declaration.revision)


def readers_with(decls):
    decl = DeclarationReader(decls)
    return tuple(decl if type(r) is DeclarationReader else r for r in o2.authorities().readers)


# (a) a real older revision
newer = dataclasses.replace(dw, revision=dw.revision + 1, providers=tuple(p for p in dw.providers if p != "sim.secret"))
show("a: world rev n, in force rev n+1", world, o2, readers_with([newer]))
# (b) same revision, other content
show("b: same revision other content", world, o2, readers_with([ax.owned("battery").declaration]))
# (c) world at a NEWER revision than the one in force
older = dataclasses.replace(dw, revision=dw.revision + 5)
wn = project_world(older, Authorities.of(*readers_with([older])))
show("c: world rev n+5, in force rev n (other content)", wn, o2,
     readers_with([dataclasses.replace(dw, providers=tuple(p for p in dw.providers if p != "sim.secret"))]))


def forged(rev, dig):
    payload = world.to_dict()
    payload["declaration"]["revision"] = rev
    if dig is not None:
        payload["declaration"]["record_digest"] = dig
    return ScientificWorld.from_dict({k: v for k, v in payload.items() if k not in ("content_digest", "revision_id")})


for label, rev in (("d: forged revision '²'", "²"), ("d2: forged revision '١' (Arabic-Indic 1)", "١"),
                   ("d3: forged revision '0'", "0")):
    try:
        fw = forged(rev, "1" * 64)
    except Exception as e:
        print(f"[{label}] world refused at build: {type(e).__name__}: {e}")
        continue
    print(f"[{label}] built; intact={fw.intact()} revision={fw.declaration.revision!r}")
    show(label, fw, o2, readers_with([newer]))

# through the desk / port (the Mind-facing path)
try:
    fw = forged("²", "1" * 64)
    a = Authorities.of(*readers_with([newer]))
    gw = ExecutionDesk(a, lambda x: None, accept_synthetic=True).gateway()
    port = MindWorldPort(FeasibleActionSpace.build(fw))
    r = port.request_admission(o2.propose("simulate_pulse", *SIM, world=fw), gw)
    print("[port] ", r.status.value, r.codes())
except Exception as e:
    print(f"[port] RAISED {type(e).__name__}: {str(e)[:200]}")
