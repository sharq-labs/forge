"""Round 9's _plain (owners.py:97-113) walks the account's serialization with an explicit stack and no visited set, so a
reference cycle in an experiment's metadata never terminates.  ScientificExperiment.to_dict copies metadata shallowly
(experiment.py:329), so a cycle reaches _plain.  At ceaf8cd the same account was refused OWNER_UNAVAILABLE (to_json's
json.dumps detects the cycle).  The cyclic account is UNBOUND (no world reads it): README §4 says such an account
'refuses nothing'.  Every verification pins every reader (Authorities.memoized), so every admission through the desk
now spins in _plain.  Public API only: the execution side's account mapping, its desk and the gateway."""
import sys, threading, time
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import Authorities, BudgetReader, ExecutionDesk, FeasibleActionSpace

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
world = o.world
extra = ax.experiment("campaign.notes", 10, 1)          # an UNBOUND observation account the execution side also keeps
extra.metadata["notes"] = {"owner": "campaign"}
experiments = dict(o.experiments, **{"campaign.notes": extra})
reader = BudgetReader.following(lambda: (o.ledgers, experiments))
auth = Authorities.of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
gateway = ExecutionDesk(auth, lambda a: "executed").gateway()

def admit_once(label, out):
    t0 = time.time()
    try:
        r = gateway.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world))
        out[label] = f"{r.status.value} after {time.time() - t0:.2f}s"
    except Exception as exc:  # noqa: BLE001
        out[label] = f"{type(exc).__name__}: {str(exc)[:90]}"

out = {}
admit_once("before the cycle", out)
extra.metadata["notes"]["self"] = extra.metadata["notes"]   # the execution side's metadata acquires a cycle
threads = [threading.Thread(target=admit_once, args=(f"admission {i} after the cycle", out), daemon=True)
           for i in range(2)]
for t in threads:
    t.start()
    time.sleep(0.5)
for t in threads:
    t.join(timeout=10)
for t, i in zip(threads, range(2)):
    if t.is_alive():
        out[f"admission {i} after the cycle"] = "still running after 10 s (spinning in the read-back)"
for k, v in out.items():
    print(f"{k}: {v}")
print("tickets in flight:", sorted(getattr(reader, "_in_flight", set())))
sys.stdout.flush()
import os; os._exit(0)
