"""projection._named_records (round 9, projection.py:183-185) decides STALE vs MISMATCH with str.isdigit() and int().
str.isdigit() is True for digits int() does not parse (superscripts such as '²'), so a submitted world whose
declaration binding names a revision like '2²' (any digest other than the one in force) makes int() raise
ValueError inside verified_projection, which admit() does not catch: the gateway raises ValueError instead of
returning a refusal.  Before round 9 the same world was AUTHORITY_STALE/MISMATCH.  Public API only: a proposer builds
the world payload it submits."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import Authorities, ExecutionDesk, FeasibleActionSpace, ScientificWorld

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
gateway = ExecutionDesk(o.authorities(), lambda a: "executed").gateway()
payload = o.world.to_dict()
import sys; payload["declaration"]["revision"] = sys.argv[1] if len(sys.argv) > 1 else "1²"
payload["declaration"]["record_digest"] = "f" * 64
try:
    world = ScientificWorld.from_dict({k: v for k, v in payload.items() if k not in ("content_digest", "revision_id")})
except Exception as exc:  # noqa: BLE001
    print("the world is refused when built:", type(exc).__name__, exc); raise SystemExit
print("world built; declaration revision", repr(world.declaration.revision))
try:
    r = gateway.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world))
    print("admission:", r.status.value, sorted(r.codes()))
except Exception as exc:  # noqa: BLE001
    print("gateway.admit raised", type(exc).__name__ + ":", exc)
