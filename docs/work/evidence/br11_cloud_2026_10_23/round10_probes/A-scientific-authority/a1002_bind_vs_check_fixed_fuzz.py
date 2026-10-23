"""Lens A r10: at c69e579, is bind == every check for a fixed condition of a level-set variable (A9-F1 / F9-3)?
And what does round 9's bind change refuse or accept relative to ceaf8cd's bind rule (raw conversion)?
bind: the real ActionSpec.bind on a world that declares the variable.  check: the real domain-family predicate
(feasibility.as_executed, domains.membership, feasibility.level_problem, as _check_domains runs them for a fixed
condition).  Old bind: ceaf8cd's rule restated (_fixed_level_problem, then membership of the RAW conversion)."""
import dataclasses, math, random, sys
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import ActionMode, FeasibleActionSpace, TemporalSemantics as TS, WorldRefused
from engcore.mind.world import feasibility as fz
from engcore.mind.world.actions import _fixed_level_problem
from engcore.mind.world.domains import DiscreteLevels, membership
from engcore.mind.world.base import as_unit, same_value, converts
from engcore.scientific import Quantity
from engcore.sria.decision import ActionFamily
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 10
N = int(sys.argv[2]) if len(sys.argv) > 2 else 300
random.seed(seed)
P = RoleSource.PROTOCOL_METADATA
FAM = [["degC", "K", "degF", "degR"], ["A", "mA", "kA"], ["m", "mm", "ft", "inch", "km"], ["bar", "Pa", "kPa", "psi"],
       ["dimensionless", "percent", "radian", "degree"], ["s", "ms", "minute", "hour"]]


def world0(vu, lv):
    return b.world("synthetic.a1002", (
        b.var("T", R.FIXED_PROTOCOL_CONDITION, vu, TS.CONSTANT_PER_RUN, domain=lv),
        b.var("mode", R.CONTROLLED_INPUT, "dimensionless", TS.CONSTANT_PER_RUN, domain=b.cats("mode", "a", "b")),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("a", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                          controls=(b.ctrl("mode", b.cats("mode", "a", "b"), P),), expected_observables=("y",),
                          estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
        channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="a1002"), references=(b.synthetic("a1002/1"),))


def check_ok(w, spec, s):
    var = w.variable("T")
    executed = fz.as_executed(w, spec, "T", s)
    found = membership(var.domain, executed)
    if found is None:
        found = fz.level_problem(w, spec, "T", s, executed)
    return found is None, executed


def old_bind_ok(var, s):
    if _fixed_level_problem(var.domain, s):
        return False
    return membership(var.domain, as_unit(s, var.unit)) is None


def ulps(m, k):
    for _ in range(abs(k)):
        m = math.nextafter(m, math.inf if k > 0 else -math.inf)
    return m


stats = {"cases": 0, "bind!=check": 0, "new_refused": 0, "new_accepted": 0, "worlds": 0, "world_refused": 0,
         "e2e": 0, "e2e_mismatch": 0}
ex = {}
for t in range(N):
    fam = random.choice(FAM)
    vu, du = random.choice(fam), random.choice(fam)
    n = random.randint(1, 3)
    digits = random.choice([6, 9, 12, 13, 14, 15])
    vals = sorted({float(f"{random.uniform(0.5, 999.0) * 10 ** random.randint(-2, 3):.{digits}g}") for _ in range(n)})
    if random.random() < 0.15:
        vals = sorted({0.0, *vals})
    lv = DiscreteLevels(du, tuple(Quantity(v, du) for v in vals))
    try:
        w = world0(vu, lv)
    except WorldRefused as exc:
        stats["world_refused"] += 1
        continue
    stats["worlds"] += 1
    spec0 = w.action("a")
    var = w.variable("T")
    spellings = []
    for L in lv.levels:
        for u in fam:
            try:
                m = L.magnitude_in(u)
            except Exception:
                continue
            for k in (-2, -1, 0, 1, 2):
                spellings.append(Quantity(ulps(m, k), u))
            spellings.append(Quantity(float(f"{m:.15g}"), u))
            spellings.append(Quantity(float(f"{m:.12g}"), u))
    for s in spellings:
        if not converts(s, var.unit):
            continue
        stats["cases"] += 1
        spec = dataclasses.replace(spec0, fixed_conditions=(b.fixed("T", s),))
        try:
            spec.bind(w)
            bok = True
        except WorldRefused as exc:
            bok = False
            why = str(exc)
        cok, executed = check_ok(w, spec, s)
        ook = old_bind_ok(var, s)
        if bok != cok:
            stats["bind!=check"] += 1
            ex.setdefault("bind!=check", (vu, du, vals, s, bok, cok, executed))
        if ook and not bok:
            stats["new_refused"] += 1
            ex.setdefault("new_refused", (vu, du, vals, s, "check_ok", cok, executed))
            if cok:
                ex.setdefault("new_refused_but_check_ok", (vu, du, vals, s, executed))
        if bok and not ook:
            stats["new_accepted"] += 1
            ex.setdefault("new_accepted", (vu, du, vals, s, "check_ok", cok, executed))
        if bok and random.random() < 0.02:                  # end to end: build the world with it and check
            stats["e2e"] += 1
            wf = b.world("synthetic.a1002f", tuple(w.variables), actions=(spec,), channels=(b.channel("y"),),
                         budget=b.budget(5, 0, ledger="a1002"), references=(b.synthetic("a1002/1"),)) \
                if False else None
            try:
                wf = b.world("synthetic.a1002f", (
                    b.var("T", R.FIXED_PROTOCOL_CONDITION, vu, TS.CONSTANT_PER_RUN, domain=lv),
                    b.var("mode", R.CONTROLLED_INPUT, "dimensionless", TS.CONSTANT_PER_RUN, domain=b.cats("mode", "a", "b")),
                    b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
                    actions=(b.action("a", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                                      controls=(b.ctrl("mode", b.cats("mode", "a", "b"), P),),
                                      fixed_conditions=(b.fixed("T", s),), expected_observables=("y",),
                                      estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
                    channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="a1002"), references=(b.synthetic("a1002/1"),))
                d = FeasibleActionSpace.build(wf).check(b.propose(wf, "a", {"mode": b.cat("a")}, ("y",)))
                dom = [r.code for r in d.reasons if r.subject == "T"]
                if dom:
                    stats["e2e_mismatch"] += 1
                    ex.setdefault("e2e_mismatch", (vu, du, vals, s, dom))
            except WorldRefused as exc:
                stats["e2e_mismatch"] += 1
                ex.setdefault("e2e_bind_refused", (vu, du, vals, s, str(exc)[:120]))
print(stats)
for k, v in ex.items():
    print(k, v)
