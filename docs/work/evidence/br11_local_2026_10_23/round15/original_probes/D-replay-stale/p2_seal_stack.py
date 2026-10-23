"""P2: an honest following reader handed a pair of plain dicts is SEALED for good (every account refused from then on,
with the text 'handed over what is not a pair of account dicts') when the verifying caller's stack is exhausted inside
the reader's handing step, or when an interrupt lands there (simulated deterministically with a one-shot trace hook)."""
import sys

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, OwnerKind
from engcore.mind.world.authority import OwnerUnavailable

o = ax.owned("battery")
lid = next(k for k in o.ledgers if k.endswith(".solver"))


def accounts():
    return dict(o.ledgers), dict(o.experiments)


def at_depth(n, fn):
    if n <= 0:
        return fn()
    return at_depth(n - 1, fn)


def state(reader):
    try:
        reader.read(OwnerKind.BUDGET_LEDGER, lid)
        return "readable"
    except OwnerUnavailable as exc:
        return "SEALED" if "refuses every account from then on" in str(exc) else f"refused: {str(exc)[:60]}"


limit = sys.getrecursionlimit()
outcomes = {}
example = None
for n in range(limit - 120, limit):
    reader = BudgetReader.following(accounts)
    try:
        at_depth(n, reader.pinned)
        got = "ok"
    except BaseException as exc:  # noqa: BLE001
        got = type(exc).__name__
    s = state(reader)
    outcomes.setdefault((got, s), []).append(n)
    if s == "SEALED" and example is None:
        example = (n, reader._sealed)
print("recursion limit", limit)
for (got, s), ns in sorted(outcomes.items()):
    print(f"  pin at depth -> {got:16s} then shallow read -> {s:12s}: {len(ns)} depths ({min(ns)}..{max(ns)})")
if example:
    print("  example sealed depth", example[0], "->", example[1])
    reader = BudgetReader.following(accounts)
    at_depth(example[0], lambda: _swallow(reader.pinned)) if False else None

# one-shot interrupt landing in the handing step (a Ctrl-C at that moment), simulated with a trace hook
reader = BudgetReader.following(accounts)


def tracer(frame, event, arg):
    if event == "call" and frame.f_code.co_name == "_handed":
        sys.settrace(None)
        raise KeyboardInterrupt
    return None


sys.settrace(tracer)
try:
    reader.pinned()
    print("no interrupt?")
except KeyboardInterrupt:
    print("interrupt in _handed re-raised")
finally:
    sys.settrace(None)
for i in range(3):
    print(f"  later read {i}:", state(reader))
print("  sealed text:", reader._sealed)
