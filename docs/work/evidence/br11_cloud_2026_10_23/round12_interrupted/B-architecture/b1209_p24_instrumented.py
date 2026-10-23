"""R12-B b1209: r11 p24 (adapted) with every failed read-back attempt counted (measurement only).
Liveness under steady concurrency at aad2f69 when a handed account is large: K verifier threads admit through one
desk whose following budget reader is handed, besides the bound accounts, one UNBOUND experiment of E evaluations that
the execution side extends now and then (each new content is read back whole by its owner at the next verification:
quadratic in E, README section 8).  Under the GIL a pending verification's read-back can outlast WAIT_S, so the
verifications that compared meanwhile wait WAIT_S and are refused.  Count refusals and latency."""
import collections, statistics, sys, threading, time
from engcore.mind.world import owners as _ow
_FAILS = collections.Counter()
_orig = _ow.BudgetReader._read_once
def _counted(self, key):
    try:
        return _orig(self, key)
    except _ow._Failed as f:
        _FAILS[f.why[:60]] += 1
        raise
_ow.BudgetReader._read_once = _counted
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import Authorities, BudgetReader, ExecutionDesk, FeasibleActionSpace
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation

K = int(sys.argv[1]); N = int(sys.argv[2]); E = int(sys.argv[3]); PERIOD = float(sys.argv[4])
SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
world = o.world
side = ax.experiment("campaign.side", 10 ** 6, E)
reader = BudgetReader.following(lambda: (o.ledgers, {**o.experiments, "campaign.side": side}))
auth = Authorities.of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
gw = ExecutionDesk(auth, lambda a: "ran", accept_synthetic=True).gateway()
space = FeasibleActionSpace.build(world)
stop = threading.Event()
out, lat = collections.Counter(), []

def spender():
    i = 0
    while not stop.is_set():
        i += 1
        side.record(ScientificEvaluation(f"bg.{i}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
        time.sleep(PERIOD)

def verifier():
    for _ in range(N):
        t0 = time.perf_counter()
        r = gw.admit(space, o.propose("simulate_pulse", *SIM, world=world))
        lat.append(time.perf_counter() - t0)
        s = str(r.to_dict())
        out[r.status.value + ("" if r.admitted else (" in flight" if "in flight" in s else " behind" if "behind" in s else " other"))] += 1

threading.Thread(target=spender, daemon=True).start()
t0 = time.perf_counter()
vs = [threading.Thread(target=verifier) for _ in range(K)]
[v.start() for v in vs]; [v.join() for v in vs]
stop.set()
lat.sort()
print(f"read-back failures: {dict(_FAILS)}")
print(f"K={K} N={N} E={E} period={PERIOD}s: {dict(out)} in {time.perf_counter()-t0:.1f}s; latency p50 {statistics.median(lat)*1e3:.0f} ms, max {lat[-1]*1e3:.0f} ms")
