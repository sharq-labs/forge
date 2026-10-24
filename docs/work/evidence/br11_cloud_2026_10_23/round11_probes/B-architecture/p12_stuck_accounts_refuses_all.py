"""The ticket rule couples verifications: one verification whose accounts() (or read-back) never returns keeps its
ticket in flight, and every LATER verification of the reader, on any thread, is refused 'an earlier verification ...
still in flight' for as long as it does not return (no bound, no timeout).  At ceaf8cd (accounts() unlocked, read-back
and compare locked) the same stuck call delayed nobody.  Public API only: the execution side's accounts() blocks on
one worker thread (e.g. a store call without a timeout); the desk keeps admitting on the main thread."""
import os, threading, time
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import Authorities, BudgetReader, ExecutionDesk, FeasibleActionSpace

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
world = o.world
never = threading.Event()

def accounts():
    if threading.current_thread().name == "stuck":
        never.wait()                       # an execution-side store call that never returns
    return o.ledgers, o.experiments

reader = BudgetReader.following(accounts)
auth = Authorities.of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
gateway = ExecutionDesk(auth, lambda a: "executed").gateway()

def admit_once():
    r = gateway.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world))
    return r.status.value + ("" if r.admitted else " " + str(sorted(r.codes())))

print("before:", admit_once())
threading.Thread(target=lambda: reader.pinned(), name="stuck", daemon=True).start()
time.sleep(0.3)
seen = [admit_once() for _ in range(5)]
print("5 admissions after one stuck verification started:", seen)
time.sleep(1.0)
print("1.3 s later:", admit_once())
os._exit(0)
