"""Same-thread read-through from inside the read-back (not accounts()): a metadata KEY whose __lt__ reads through the
follower (ScientificExperiment.to_dict sorts metadata keys, experiment.py:329).  At c69e579 the thread-local flag spans
the read-back, so the nested pin is refused at once and the account is OWNER_UNAVAILABLE.  Mutant m9 (flag reset
before the read-back) survives the whole suite: this probe is a control it would fail (nested pins recurse)."""
import sys
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

state = {"reader": None, "nested": 0}
class Key:
    def __init__(self, s): self.s = s
    def __hash__(self): return hash(self.s)
    def __eq__(self, o): return isinstance(o, Key) and o.s == self.s
    def __lt__(self, o):
        r = state["reader"]
        if r is not None and state["nested"] < 50:
            state["nested"] += 1
            try:
                r.read(OwnerKind.BUDGET_LEDGER, "x")
            except OwnerUnavailable:
                pass
        return self.s < getattr(o, "s", str(o))

o = ax.owned("battery")
extra = ax.experiment("campaign.notes", 10, 1)
experiments = dict(o.experiments, **{"campaign.notes": extra})
reader = BudgetReader.following(lambda: (o.ledgers, experiments))
extra.metadata[Key("a")] = 1
extra.metadata[Key("b")] = 2
state["reader"] = reader
try:
    reader.read(OwnerKind.EXPERIMENT, "campaign.notes")
    print("served")
except OwnerUnavailable as exc:
    print("OwnerUnavailable:", str(exc)[:100])
print("nested pins that entered the reader:", state["nested"])
