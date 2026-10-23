"""R11-C c1103: the bounded wait counts a verification's READ-BACK as in flight, not only its accounts().  A large
experiment handed to the follower (here NOT read by any world) that records one evaluation between admissions makes
every verification's read-back take ~1 s or more (the owner's whole read-back is quadratic in the evaluations); two
admissions through one desk that overlap by less than their read-back are then refused on the timeout ('another
verification ... was still in flight 1.0 s after this one compared'), on the world's own ledger and experiment, which
are unchanged.  The README and the docstring state the cost only for 'a verification whose accounts() does not return
within WAIT_S', and 'an account no verification reads ... refuses nothing'.

Public API: the fixture's mapping handed to BudgetReader.following, ExecutionDesk(...).gateway().admit."""
import sys
import threading
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, ExecutionDesk, FeasibleActionSpace
from engcore.scientific.experiments.evaluation import EvaluationStatus, ScientificEvaluation

SIM = ax.base("battery")["simulate_pulse"]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3500

o = ax.owned("battery")
big = ax.experiment("unbound.campaign", N + 1000, N)                   # an account no world reads
reader = BudgetReader.following(lambda: (dict(o.ledgers), {**o.experiments, "unbound.campaign": big}))
authorities = type(o.authorities()).of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
gateway = ExecutionDesk(authorities, lambda a: "ran", accept_synthetic=True).gateway()
space = FeasibleActionSpace.build(o.world)
counter = {"i": 0}
out = []


def admit_once(tag):
    t0 = time.perf_counter()
    r = gateway.admit(space, o.propose("simulate_pulse", *SIM))
    why = sorted({c.detail.get("why", "")[:70] for c in r.verification.checks if c.status.name != "VERIFIED"})
    out.append((tag, r.status.value, round(time.perf_counter() - t0, 2), why))


for k in range(3):
    counter["i"] += 1
    big.record(ScientificEvaluation(f"more.{counter['i']}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
    a = threading.Thread(target=admit_once, args=(f"A{k}",))
    b = threading.Thread(target=admit_once, args=(f"B{k}",))
    a.start()
    time.sleep(0.8)                                                      # B starts while A is reading back
    b.start()
    a.join(30)
    b.join(30)
for row in out:
    print(row)
print("sequential control:")
counter["i"] += 1
big.record(ScientificEvaluation(f"more.{counter['i']}", {}, status=EvaluationStatus.NOT_CONVERGED, detail="x"))
admit_once("S")
print(out[-1])
