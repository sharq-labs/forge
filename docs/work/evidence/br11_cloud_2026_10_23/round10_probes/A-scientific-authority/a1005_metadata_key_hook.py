"""Lens A r10: README §4 / owners.py: 'an experiment is read back only from plain JSON data ... so no code of the
account's values runs'.  ScientificExperiment.to_dict sorts metadata keys before the plain-data walk, so a non-str
key's __lt__ runs during the read-back (before the refusal)."""
from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
ran = []


class K:
    def __init__(self, n):
        self.n = n

    def __lt__(self, other):
        ran.append(("__lt__", self.n))
        return self.n < getattr(other, "n", 0)

    def __hash__(self):
        return self.n


o = ax.gen1_pool()
eid = next(iter(o.experiments))
o.experiments[eid].metadata.update({K(1): "a", K(2): "b"})
try:
    BudgetReader.following(lambda: (o.ledgers, o.experiments)).read(OwnerKind.EXPERIMENT, eid)
    print("read")
except OwnerUnavailable as exc:
    print("refused:", str(exc)[:120])
print("execution-side code that ran during the read-back:", ran)
