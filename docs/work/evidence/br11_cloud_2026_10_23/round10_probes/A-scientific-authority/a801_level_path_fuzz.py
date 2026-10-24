"""Round 8, lens A: fuzz the level path at whatever tree PYTHONPATH selects (run from that tree's own root).

Worlds: a variable with a level domain (its own unit, the levels possibly in another unit), an action control whose
domain is (a) a level subset in a third unit (exact conversion / 15g / 12g printed), (b) a continuous range covering the
levels, or (c) the same level set; offset temperatures, delta temperatures, current, length, pressure, time; zero levels
and integer-valued levels; one protocol constraint at one level with a random operator (strict or inclusive).
Proposals: every level, spelled in every unit of the family (exact conversion, 15g, 12g) and ulp-perturbed.
Fixed-condition worlds: the variable a FIXED_PROTOCOL_CONDITION held by the action's fixed condition, spelled likewise.

One JSON line per case.  Invariants (checked by a801_check.py on the HEAD output):
 I1 feasible => executed is EXACTLY one deciding-set level as executed
 I2 feasible => the proposal is same_value to that level (never executed at another level)
 I3 feasible => no declared level of either set with another key is strictly nearer the proposal than the executed one
"""
import json, math, random, sys
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import ActionMode, DeclaredConstraint, FeasibleActionSpace, TemporalSemantics as TS
from engcore.mind.world import WorldRefused
from engcore.mind.world.domains import DiscreteLevels
from engcore.mind.world.base import same_value, as_unit, value_payload
from engcore.scientific import ConstraintDefinition, ConstraintOperator as Op, Quantity
from engcore.scientific.units.quantity import base_unit
from engcore.sria.decision import ActionFamily

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 8
trials = int(sys.argv[2]) if len(sys.argv) > 2 else 40
random.seed(seed)
FAM = [["degC", "K", "degF", "degR"], ["delta_degC", "delta_degF"], ["A", "mA", "uA", "kA"],
       ["m", "mm", "cm", "ft", "inch", "km"], ["bar", "Pa", "kPa", "psi", "atm"], ["s", "ms", "minute", "hour"]]
OPS = [Op.LESS_THAN, Op.LESS_EQUAL, Op.GREATER_THAN, Op.GREATER_EQUAL]
P = RoleSource.PROTOCOL_METADATA


def conv(x, u, how):
    m = x.magnitude_in(u)
    if how == "15g":
        m = float(f"{m:.15g}")
    elif how == "12g":
        m = float(f"{m:.12g}")
    return Quantity(m, u)


def spellings(level, units):
    out = []
    for u in units:
        for how in ("exact", "15g", "12g"):
            try:
                s = conv(level, u, how)
            except Exception:
                continue
            out.append((f"{u}/{how}", s))
            if how == "exact":
                m = s.magnitude
                for k, tag in ((1, "+1ulp"), (-1, "-1ulp"), (3, "+3ulp"), (-3, "-3ulp")):
                    mm = m
                    for _ in range(abs(k)):
                        mm = math.nextafter(mm, math.inf if k > 0 else -math.inf)
                    out.append((f"{u}/{tag}", Quantity(mm, u)))
    return out


def pick_values(scale_lo, scale_hi):
    n = random.randint(2, 4)
    mode = random.choice(["spread", "close", "zero", "int"])
    scale = 10 ** random.uniform(scale_lo, scale_hi)
    if mode == "spread":
        vals = {round(random.uniform(0.05, 1) * scale * (i + 1), 6) for i in range(n)}
    elif mode == "close":
        base = random.uniform(0.1, 1) * scale
        vals = {base * (1 + i * 1e-9) for i in range(n)}
    elif mode == "zero":
        vals = {0.0, *[round(random.uniform(0.05, 1) * scale * (i + 1), 6) for i in range(n - 1)]}
    else:
        vals = {float(random.randint(1, 50)) for _ in range(n)}
    return mode, sorted(vals)


def emit(**kw):
    print(json.dumps(kw, default=str))


def control_world(fam, trial):
    vu = random.choice(fam)                  # the variable's unit
    du = random.choice(fam)                  # the unit its own levels are stated in
    au = random.choice(fam)                  # the action's level unit
    mode, vals = pick_values(-2, 3) if not fam[0].startswith("deg") else pick_values(0, 2.5)
    shape = random.choice(["subset", "same", "range"])
    op = random.choice(OPS)
    var_lv = tuple(Quantity(v, du) for v in vals)
    if shape == "range":
        lo = min(x.magnitude_in(vu) for x in var_lv)
        hi = max(x.magnitude_in(vu) for x in var_lv)
        span = (hi - lo) or abs(hi) or 1.0
        dom = b.crange("I", vu, lo - 0.1 * span, hi + 0.1 * span)
        act_lv = var_lv
    else:
        sub = var_lv if shape == "same" else random.sample(var_lv, k=max(1, len(var_lv) - 1))
        how = random.choice(["exact", "15g", "12g"])
        act_lv = tuple(conv(x, au, how) for x in sub)
        dom = DiscreteLevels(au, act_lv)
    star = random.choice(var_lv)
    lim = DeclaredConstraint("lim", ConstraintDefinition("lim", "I", op, star), None, ("*",), P, "synthetic limit")
    sig = dict(kind="control", fam=fam[0], vu=vu, du=du, au=au, mode=mode, shape=shape, op=op.value,
               var=[x.magnitude for x in var_lv], act=[x.magnitude for x in act_lv] if shape != "range" else None,
               star=star.magnitude)
    try:
        w = b.world("synthetic.a801", (
            b.var("I", R.CONTROLLED_INPUT, vu, TS.CONSTANT_PER_RUN, domain=DiscreteLevels(du, var_lv)),
            b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
            constraints=(lim,),
            actions=(b.action("a", ActionFamily.EXPLORE, ActionMode.INTERVENE, controls=(b.ctrl("I", dom, P),),
                              expected_observables=("y",), estimated_cost=b.cost(1, 0),
                              estimated_duration=b.q(10, "s")),),
            channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="a801"), references=(b.synthetic("a801/1"),))
    except Exception as exc:
        emit(trial=trial, sig=sig, bind_refused=str(exc)[:100])
        return
    space = FeasibleActionSpace.build(w)
    spec = w.action("a")
    deciding = act_lv if shape != "range" else var_lv
    for li, level in enumerate(var_lv):
        for tag, s in spellings(level, fam):
            d = space.check(b.propose(w, "a", {"I": s}, ("y",)))
            ex = dict(getattr(d, "decided", ()) or ()).get("I") if d.feasible else None
            emit(trial=trial, sig=sig, li=li, tag=tag, s=[s.magnitude, s.units], same=same_value(s, level),
                 feasible=d.feasible, codes=list(d.codes()),
                 ex=None if ex is None else [ex.magnitude, ex.units],
                 deciding_exec=[as_unit(x, vu).magnitude for x in deciding],
                 all_levels=[[x.magnitude, x.units] for x in (*var_lv, *(act_lv if shape != "range" else ()))])


def fixed_world(fam, trial):
    vu = random.choice(fam)
    du = random.choice(fam)
    mode, vals = pick_values(-2, 3) if not fam[0].startswith("deg") else pick_values(0, 2.5)
    var_lv = tuple(Quantity(v, du) for v in vals)
    op = random.choice(OPS)
    star = random.choice(var_lv)
    li = random.randrange(len(var_lv))
    level = var_lv[li]
    lim = DeclaredConstraint("lim", ConstraintDefinition("lim", "T", op, star), None, ("*",), P, "synthetic limit")
    sig = dict(kind="fixed", fam=fam[0], vu=vu, du=du, mode=mode, op=op.value, var=[x.magnitude for x in var_lv],
               star=star.magnitude)
    sp = spellings(level, fam)
    for tag, s in random.sample(sp, k=min(8, len(sp))):
        try:
            w = b.world("synthetic.a801f", (
                b.var("T", R.FIXED_PROTOCOL_CONDITION, vu, TS.CONSTANT_PER_RUN, domain=DiscreteLevels(du, var_lv)),
                b.var("mode", R.CONTROLLED_INPUT, "dimensionless", TS.CONSTANT_PER_RUN, domain=b.cats("mode", "a", "b")),
                b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
                constraints=(lim,),
                actions=(b.action("a", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                                  controls=(b.ctrl("mode", b.cats("mode", "a", "b"), P),),
                                  fixed_conditions=(b.fixed("T", s),),
                                  expected_observables=("y",), estimated_cost=b.cost(1, 0),
                                  estimated_duration=b.q(10, "s")),),
                channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="a801"), references=(b.synthetic("a801/1"),))
        except Exception as exc:
            emit(trial=trial, sig=sig, li=li, tag=tag, s=[s.magnitude, s.units], same=same_value(s, level),
                 bind_refused=str(exc)[:100])
            continue
        space = FeasibleActionSpace.build(w)
        d = space.check(b.propose(w, "a", {"mode": b.cat("a")}, ("y",)))
        ex = dict(getattr(d, "decided", ()) or ()).get("T") if d.feasible else None
        emit(trial=trial, sig=sig, li=li, tag=tag, s=[s.magnitude, s.units], same=same_value(s, level),
             feasible=d.feasible, codes=list(d.codes()), ex=None if ex is None else [ex.magnitude, ex.units],
             deciding_exec=[as_unit(x, vu).magnitude for x in var_lv],
             all_levels=[[x.magnitude, x.units] for x in var_lv])


for fam in FAM:
    for t in range(trials):
        control_world(fam, t)
    for t in range(trials // 2):
        fixed_world(fam, t)
