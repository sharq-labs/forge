"""Which binding check reports what for a world stating a non-ASCII / huge / zero declaration revision (aad2f69)."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import ExecutionDesk, FeasibleActionSpace, ScientificWorld, admit

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
print("in force revision:", o.declaration.revision)
for rev in ["1²", "²", "٠", "0", "00", "1" * 5000, "", " 1", "+0", "-1"]:
    payload = o.world.to_dict()
    payload["declaration"]["revision"] = rev
    payload["declaration"]["record_digest"] = "f" * 64
    try:
        world = ScientificWorld.from_dict({k: v for k, v in payload.items() if k not in ("content_digest", "revision_id")})
    except Exception as exc:  # noqa: BLE001
        print(repr(rev[:8]), "world refused:", type(exc).__name__, str(exc)[:80]); continue
    try:
        r = admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world), o.authorities())
        checks = sorted({(c.record_id[:40], c.status.value) for c in r.verification.checks if c.status.value != "CURRENT"}) if r.verification else None
        print(repr(rev[:8]), r.status.value, sorted(r.codes()), checks)
    except Exception as exc:  # noqa: BLE001
        print(repr(rev[:8]), "RAISED", type(exc).__name__, str(exc)[:80])
