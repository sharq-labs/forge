"""P6: the execution side projecting a world (project_world, the public projection API) or reading through the reader
(reader.read) at a deep stack: depths at which the honest reader is sealed for good."""
import sys

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.projection import project_world

o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))


def setup():
    reader = BudgetReader.following(lambda: (dict(o.ledgers), dict(o.experiments)))
    base = o.authorities()
    return reader, type(base).of(*(reader if type(r) is BudgetReader else r for r in base.readers))


def sealed(reader):
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
        return False
    except OwnerUnavailable as exc:
        return "refuses every account from then on" in str(exc)


def at_depth(n, fn):
    return fn() if n <= 0 else at_depth(n - 1, fn)


limit = sys.getrecursionlimit()
for label, call in (("project_world", lambda r, a: project_world(o.declaration, a)),
                    ("reader.read", lambda r, a: r.read(OwnerKind.BUDGET_LEDGER, lid))):
    hits, errs = [], 0
    for n in range(limit - 300, limit):
        reader, auth = setup()
        try:
            at_depth(n, lambda: call(reader, auth))
        except BaseException:  # noqa: BLE001
            errs += 1
        if sealed(reader):
            hits.append(n)
    print(f"{label}: sealed for good at {len(hits)} of 300 caller depths {hits}; {errs} depths raised")
