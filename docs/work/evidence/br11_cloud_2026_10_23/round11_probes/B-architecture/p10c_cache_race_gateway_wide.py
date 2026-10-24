"""p10 through the Mind-facing gateway: concurrent admissions on one desk whose execution side hands over a changing set
of (unbound) campaign experiments besides the world's own accounts.  The cache-prune race (owners.py:421 iterating the
shared dict that a concurrent snapshot's unlocked read-back inserts into at owners.py:389) raises RuntimeError in the
comparing verification; _Memo keeps it as the pin error and re-raises it at the first budget read, which
Authorities.check does not catch (it catches OwnerUnavailable / WorldRefused), so gateway.admit raises RuntimeError
instead of returning a refusal.  Nothing is admitted on it (fails closed); the outcome is neither a refusal nor
recordable.  Public API only."""
import collections, sys, threading
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import Authorities, BudgetReader, ExecutionDesk, FeasibleActionSpace

sys.setswitchinterval(1e-6)
SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
world = o.world
POOL = [ax.experiment(f"camp{j}", 400, 3) for j in range(150)]
n = {"calls": 0}
lk = threading.Lock()

def accounts():
    with lk:
        n["calls"] += 1
        c = n["calls"]
    campaigns = {f"campaign.{(c * 150 + j)}": POOL[j] for j in range(150)}
    return o.ledgers, {**o.experiments, **campaigns}

reader = BudgetReader.following(accounts)
auth = Authorities.of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
gateway = ExecutionDesk(auth, lambda a: "executed").gateway()
space = FeasibleActionSpace.build(world)
out = collections.Counter()

def worker():
    for _ in range(40):
        try:
            r = gateway.admit(space, o.propose("simulate_pulse", *SIM, world=world))
            out[r.status.value + (" admitted" if r.admitted else " " + ",".join(sorted(r.codes())))] += 1
        except Exception as exc:  # noqa: BLE001
            out[f"raised {type(exc).__name__}: {exc}"] += 1

ts = [threading.Thread(target=worker) for _ in range(4)]
[t.start() for t in ts]; [t.join() for t in ts]
for k, v in sorted(out.items()):
    print(f"{v:4d}  {k}")
