"""R10-C c1011: R9-C-F1 re-check at c69e579.  (A) an experiment metadata value whose hooks (__deepcopy__, items,
__iter__, __reduce__) read through the follower on the same thread; (B) hooks that take an execution-side lock held by an
admitting thread; (C) an account MAPPING KEY (a str subclass) whose __hash__/__eq__ runs execution-side code: is the
follower's lock held when it runs?  Each case in a daemon thread with a timeout."""
import threading
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, FeasibleActionSpace, OwnerKind, admit
from engcore.mind.world.authority import Authorities, OwnerUnavailable

SIM = ax.base("battery")["simulate_pulse"]
hook = {"fn": None}
ran = []

class Meta(dict):
    def _h(self):
        ran.append(threading.current_thread().name)
        if hook["fn"]: hook["fn"]()
    def __deepcopy__(self, memo): self._h(); return Meta(dict(self))
    def items(self): self._h(); return super().items()
    def __iter__(self): self._h(); return super().__iter__()
    def __reduce__(self): self._h(); return (Meta, (dict(self),))

def run(label, fn, timeout=8):
    out = {}
    def target():
        try: out["r"] = fn()
        except BaseException as exc: out["r"] = f"raised {type(exc).__name__}: {str(exc)[:110]}"
    t = threading.Thread(target=target, daemon=True, name=label); t.start(); t.join(timeout)
    print(f"{label}: {'HUNG' if t.is_alive() else out['r']} | hooks ran: {len(ran)}")

# A
o = ax.owned("battery"); eid = next(iter(o.experiments))
reader = BudgetReader.following(lambda: (o.ledgers, o.experiments))
auth = Authorities.of(*(reader if type(r) is BudgetReader else r for r in o.authorities().readers))
world, prop = o.world, o.propose("simulate_pulse", *SIM)
o.experiments[eid].metadata["note"] = Meta({"a": 1})
hook["fn"] = lambda: reader.read(OwnerKind.EXPERIMENT, eid)
run("A", lambda: admit(FeasibleActionSpace.build(world), prop, auth).codes())

# C: a str-subclass mapping key
held = []
state = {'r': None}
o = ax.owned("battery")
class Key(str):
    def __hash__(self):
        held.append(state['r']._lock.locked() if state['r'] else None); return str.__hash__(self)
    def __eq__(self, other):
        held.append(state['r']._lock.locked() if state['r'] else None); return str.__eq__(self, other)
lid = next(k for k in o.ledgers if k.endswith(".solver"))
mapping = {Key(k) if k == lid else k: v for k, v in o.ledgers.items()}
reader2 = BudgetReader.following(lambda: (mapping, o.experiments))
state['r'] = reader2
held.clear()
reader2.pinned()
print("C key hooks ran", len(held), "times; with the follower's lock held:", sum(1 for h in held if h))
