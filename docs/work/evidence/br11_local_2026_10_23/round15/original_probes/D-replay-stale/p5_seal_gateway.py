"""P5: the seal reached through the Mind-facing gateway.
(a) gateway.admit called by an honest caller at a deep stack: at which depths is the reader sealed for good?
(b) a real SIGINT (via _thread.interrupt_main) raised while the execution side's accounts() returns a pair of plain
    dicts: where does the KeyboardInterrupt land, and how often does it seal the reader?"""
import _thread
import sys

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from engcore.mind.world import BudgetReader, ExecutionDesk, FeasibleActionSpace
from engcore.mind.world.authority import OwnerUnavailable
from engcore.mind.world.projection import project_world

SIM = ax.base("battery")["simulate_pulse"]
o = ax.owned("battery")
state = {"interrupt": False}


def accounts():
    mapping = (dict(o.ledgers), dict(o.experiments))
    if state["interrupt"]:
        state["interrupt"] = False
        _thread.interrupt_main()          # Ctrl-C arriving as accounts() hands its (honest) dicts over
    return mapping


def desk():
    reader = BudgetReader.following(accounts)
    base = o.authorities()
    auth = type(base).of(*(reader if type(r) is BudgetReader else r for r in base.readers))
    return reader, auth, ExecutionDesk(auth, lambda a: None, accept_synthetic=True).gateway()


def shallow(auth, gateway):
    try:
        world = project_world(o.declaration, auth)
    except OwnerUnavailable as exc:
        return "SEALED" if "refuses every account from then on" in str(exc) else "refused:" + str(exc)[:50]
    r = gateway.admit(FeasibleActionSpace.build(world), o.propose("simulate_pulse", *SIM, world=world))
    if r.admitted is not None:
        return "FEASIBLE"
    whys = [c.detail.get("why", "") for c in r.verification.failures()]
    return "SEALED" if any("refuses every account from then on" in w for w in whys) else f"{r.status.value}"


def at_depth(n, fn):
    if n <= 0:
        return fn()
    return at_depth(n - 1, fn)


limit = sys.getrecursionlimit()
table = {}
for n in range(limit - 260, limit):
    reader, auth, gateway = desk()
    try:
        at_depth(n, lambda: gateway.admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM)))
        got = "returned"
    except BaseException as exc:  # noqa: BLE001
        got = type(exc).__name__
    table.setdefault((got, shallow(auth, gateway)), []).append(n)
print("(a) gateway.admit at caller depth n, then a shallow admission:")
for (got, s), ns in sorted(table.items()):
    print(f"   {got:15s} -> {s:22s} {len(ns):3d} depths: {ns if len(ns) < 8 else (min(ns), max(ns))}")

counts = {}
for trial in range(40):
    reader, auth, gateway = desk()
    state["interrupt"] = True
    try:
        gateway.admit(FeasibleActionSpace.build(o.world), o.propose("simulate_pulse", *SIM))
        where = "no interrupt"
    except KeyboardInterrupt as exc:
        tb = exc.__traceback__
        frames = []
        while tb is not None:
            frames.append(tb.tb_frame.f_code.co_name)
            tb = tb.tb_next
        where = frames[-1]
    k = (where, shallow(auth, gateway))
    counts[k] = counts.get(k, 0) + 1
print("(b) SIGINT raised as accounts() returns (40 trials): innermost frame -> later shallow admission")
for k, v in sorted(counts.items()):
    print("  ", k, v)
