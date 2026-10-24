"""Lens A r11: does domains.executed_level (d89dd3b) change any executed value or bind outcome relative to c69e579?
Old rules restated verbatim from c69e579 (git show c69e579:src/engcore/mind/world/actions.py, feasibility.py):
  old _fixed_as_executed: guard converts(value, domain.unit); matched_level(domain, value, also=domain.levels)
  old as_executed: _matched(world, spec, name, value) then as_unit(level or value, unit)
Both compared byte for byte (value_payload + repr of magnitude) on a1002's generator, for fixed conditions (bind) and
for control assignments (as_executed with an action level set in another unit)."""
import dataclasses, math, random, sys
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import ActionMode, TemporalSemantics as TS, WorldRefused
from engcore.mind.world import feasibility as fz
from engcore.mind.world.actions import _fixed_as_executed
from engcore.mind.world.domains import DiscreteLevels, matched_level
from engcore.mind.world.base import as_unit, converts
from engcore.scientific import Quantity
from engcore.sria.decision import ActionFamily
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 11
N = int(sys.argv[2]) if len(sys.argv) > 2 else 400
random.seed(seed)
P = RoleSource.PROTOCOL_METADATA
FAM = [["degC", "K", "degF", "degR"], ["A", "mA", "kA"], ["m", "mm", "ft", "inch", "km"], ["bar", "Pa", "kPa", "psi"],
       ["dimensionless", "percent", "radian", "degree"], ["s", "ms", "minute", "hour"]]


def old_fixed(domain, value, unit_):
    if isinstance(domain, DiscreteLevels) and isinstance(value, Quantity) and converts(value, domain.unit):
        level = matched_level(domain, value, also=domain.levels)
        if level is not None:
            return as_unit(level, unit_)
    return as_unit(value, unit_)


def old_as_executed(world, spec, name, value):
    if not isinstance(value, Quantity) or not world.declares(name):
        return value
    unit = world.variable(name).unit
    if not converts(value, unit):
        return value
    level = fz._matched(world, spec, name, value)
    return as_unit(value if level is None else level, unit)


def key(q):
    try:
        return (repr(float(q.magnitude)), str(q.units), math.copysign(1, q.magnitude))
    except Exception as exc:
        return ("ERR", type(exc).__name__)


def ulps(m, k):
    for _ in range(abs(k)):
        m = math.nextafter(m, math.inf if k > 0 else -math.inf)
    return m


def world_ctrl(vu, own, ctrl_levels):
    return b.world("synthetic.a1101c", (
        b.var("T", R.CONTROLLED_INPUT, vu, TS.CONSTANT_PER_RUN, domain=own),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("a", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                          controls=(b.ctrl("T", ctrl_levels, P),), expected_observables=("y",),
                          estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
        channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="a1101"), references=(b.synthetic("a1101/1"),))


stats = {"fixed_cases": 0, "fixed_diff": 0, "fixed_err_diff": 0, "ctrl_worlds": 0, "ctrl_cases": 0, "ctrl_diff": 0,
         "world_refused": 0}
ex = {}
for t in range(N):
    fam = random.choice(FAM)
    vu, du, cu = random.choice(fam), random.choice(fam), random.choice(fam)
    digits = random.choice([6, 9, 12, 13, 14, 15])
    vals = sorted({float(f"{random.uniform(0.5, 999.0) * 10 ** random.randint(-2, 3):.{digits}g}")
                   for _ in range(random.randint(1, 3))})
    if random.random() < 0.15:
        vals = sorted({0.0, *vals})
    lv = DiscreteLevels(du, tuple(Quantity(v, du) for v in vals))
    spellings = []
    for L in lv.levels:
        for u in fam:
            try:
                m = L.magnitude_in(u)
            except Exception:
                continue
            for k in (-2, -1, 0, 1, 2):
                spellings.append(Quantity(ulps(m, k), u))
            spellings.append(Quantity(float(f"{m:.12g}"), u))
            spellings.append(Quantity(-m if m else -0.0, u))
    # fixed conditions: bind's executed value, old vs new
    for s in spellings:
        stats["fixed_cases"] += 1
        try:
            new = key(_fixed_as_executed(lv, s, vu))
        except Exception as exc:
            new = ("RAISE", type(exc).__name__)
        try:
            old = key(old_fixed(lv, s, vu))
        except Exception as exc:
            old = ("RAISE", type(exc).__name__)
        if new != old:
            stats["fixed_diff"] += 1
            ex.setdefault("fixed_diff", (vu, du, vals, repr(s), old, new))
    # control assignments: as_executed with an action level set in another unit, old vs new
    cl = DiscreteLevels(cu, tuple(Quantity(L.magnitude_in(cu), cu) for L in lv.levels))
    own = lv if random.random() < 0.5 else None
    try:
        w = world_ctrl(vu, own, cl)
    except WorldRefused:
        stats["world_refused"] += 1
        continue
    stats["ctrl_worlds"] += 1
    spec = w.action("a")
    for s in spellings:
        stats["ctrl_cases"] += 1
        try:
            new = fz.as_executed(w, spec, "T", s)
            new = key(new) if isinstance(new, Quantity) else repr(new)
        except Exception as exc:
            new = ("RAISE", type(exc).__name__)
        try:
            old = old_as_executed(w, spec, "T", s)
            old = key(old) if isinstance(old, Quantity) else repr(old)
        except Exception as exc:
            old = ("RAISE", type(exc).__name__)
        if new != old:
            stats["ctrl_diff"] += 1
            ex.setdefault("ctrl_diff", (vu, du, cu, vals, repr(s), old, new))
print(stats)
for k, v in ex.items():
    print(k, v)
