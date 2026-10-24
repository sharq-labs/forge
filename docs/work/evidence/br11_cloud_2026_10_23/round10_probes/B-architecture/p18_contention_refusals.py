"""Steady concurrency under the ticket rule: K verifier threads admit through one desk whose budget reader FOLLOWS the
execution side's accounts (BudgetReader.following), while a background spender settles small charges in place.  Count
how many admissions are refused only because another verification was in flight or behind (transient), per thread.
Compare with ceaf8cd (round 8: verifications queued on the lock instead)."""
import collections, sys, threading, time
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import Authorities, BudgetReader, ExecutionDesk, FeasibleActionSpace
from engcore.sria.decision import ActionFamily

K = int(sys.argv[1]) if len(sys.argv) > 1 else 3
N = int(sys.argv[2]) if len(sys.argv) > 2 else 30
SPEND = (sys.argv[3] if len(sys.argv) > 3 else "1") == "1"
SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))
world = o.world
reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
auth = Authorities.of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
gw = ExecutionDesk(auth, lambda a: "ran", accept_synthetic=True).gateway()
space = FeasibleActionSpace.build(world)
stop = threading.Event()
per = collections.defaultdict(collections.Counter)

def spender():
    i = 0
    while not stop.is_set():
        i += 1
        o.ledgers[lid].settle(charge_id=f"bg-{i}", action_id="bg", iteration=i, family=ActionFamily.EXPLORE, realized=0.0)
        time.sleep(0.005)

def verifier(name):
    for _ in range(N):
        try:
            r = gw.admit(space, o.propose("simulate_pulse", *SIM, world=world))
            why = "" if r.admitted else ("in flight" if "in flight" in str(r.to_dict()) else
                                         "behind" if "behind" in str(r.to_dict()) else ",".join(sorted(r.codes())))
            per[name][r.status.value + (" " + why if why else "")] += 1
        except Exception as exc:  # noqa: BLE001
            per[name][f"raised {type(exc).__name__}"] += 1

t0 = time.perf_counter()
if SPEND:
    threading.Thread(target=spender, daemon=True).start()
vs = [threading.Thread(target=verifier, args=(f"v{i}",)) for i in range(K)]
[v.start() for v in vs]; [v.join() for v in vs]
stop.set()
tot = collections.Counter()
for name in sorted(per):
    tot.update(per[name])
    print(name, dict(per[name]))
print(f"K={K} spender={SPEND}: total {dict(tot)} in {time.perf_counter() - t0:.1f}s")
