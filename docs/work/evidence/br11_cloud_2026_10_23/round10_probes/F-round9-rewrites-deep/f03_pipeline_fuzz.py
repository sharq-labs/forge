"""F10 f03: bind / check / mint / record / replay agreement over (deciding set, own set, value, fixed condition), through
the SHIPPED pipeline: the world is bound by b.world (ActionSpec bind), projected as an owned world (ax.owned), checked
(FeasibleActionSpace.check), admitted (admit: verification + mint guards), recorded (AdmissionRecord.of) and replayed
from JSON (replay_admission).  For a fixed condition, 'check' on a value bind refused is evaluated with the shipped
check functions (as_executed + membership + level_problem, exactly _check_domains' fixed branch) on a placeholder world.
Disagreements reported:
  F-BC  fixed: bind accepts, check refuses        F-CB  fixed: check accepts, bind refuses
  X-MINT check feasible but admit raises at mint   X-NOTLEVEL admitted value not exactly its matched level as executed
  X-REPLAY admitted record does not replay REPRODUCED
"""
import collections
import json
import math
import random
import sys

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.repsem import canonical_bytes
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import (ActionMode, AdmissionRecord, DiscreteLevels, FeasibleActionSpace, TemporalSemantics as TS,
                                WorldRefused, admit, replay_admission)
from engcore.mind.world import feasibility as fz
from engcore.mind.world.base import as_unit, converts, value_payload
from engcore.mind.world.domains import membership, matched_level
from engcore.scientific import Quantity
from engcore.sria.decision import ActionFamily
from engcore.sria.decision.replay import ReplayOutcome

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
N = int(sys.argv[2]) if len(sys.argv) > 2 else 60
random.seed(seed)
P = RoleSource.PROTOCOL_METADATA
FAM = [("bar", "psi", "kPa", "Pa"), ("m", "ft", "cm", "inch", "mm"), ("A", "mA", "kA"), ("degC", "degF", "K"),
       ("dimensionless", "percent")]
stats = collections.Counter()
ex = collections.defaultdict(list)


def jitter(m):
    k = random.choice([0, 0, 0, 1, -1, 2, -2, 64, -64, 4096])
    return m + k * math.ulp(m) if m else random.choice([0.0, -0.0, 5e-324, -5e-324, 0.0])


def spell(level, units):
    u = random.choice(units)
    if not converts(level, u):
        u = level.units
    return Quantity(jitter(level.magnitude_in(u)), u)


def mags():
    n = random.randint(1, 3)
    base = random.choice([random.uniform(1, 900), random.uniform(1e3, 1e4), 0.0, random.uniform(0.001, 1)])
    digits = random.choice([3, 6, 9, 12, 13, 15])
    out = set()
    for i in range(n):
        m = base + random.choice([0, 1e-9, 1e-6, 1e-3, 0.5, 3, 40]) * i
        out.add(float(f"{m:.{digits}g}"))
    return sorted(out)


def mk(wid, vu, V, C, fixed_value, role, ctrl_domain_kind, bound_q=None):
    controls = [b.ctrl("mode", b.cats("mode", "a", "b"), P)]
    fixed = ()
    if fixed_value is not None:
        fixed = (b.fixed("T", fixed_value),)
    else:
        controls.append(b.ctrl("T", C, P))
    constraints = ()
    if bound_q is not None:
        constraints = (b.at_most("lim", "T", bound_q),)
    return b.world(wid, (
        b.var("T", role, vu, TS.CONSTANT_PER_RUN, domain=V),
        b.var("mode", R.CONTROLLED_INPUT, "dimensionless", TS.CONSTANT_PER_RUN, domain=b.cats("mode", "a", "b")),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("a", ActionFamily.EXPLORE, ActionMode.INTERVENE, controls=tuple(controls),
                          fixed_conditions=fixed, expected_observables=("y",), estimated_cost=b.cost(1, 0),
                          estimated_duration=b.q(10, "s")),),
        constraints=constraints, channels=(b.channel("y"),), budget=b.budget(5, 0, ledger=wid.replace(".", "_")),
        references=(b.synthetic(f"{wid}/1"),))


def pipeline(w, assignments, tag, deciding, value):
    o = ax.owned(tag, w)
    space = FeasibleActionSpace.build(o.world)
    prop = o.propose("a", assignments, ("y",))
    d = space.check(prop)
    try:
        r = admit(space, prop, o.authorities())
    except WorldRefused as exc:
        if d.feasible:
            stats["X-MINT check feasible, admit raised"] += 1
            ex["X-MINT"].append((tag, repr(value), str(exc)[:100]))
        else:
            stats["admit raised on infeasible?"] += 1
        return
    if (r.admitted is not None) != d.feasible:
        stats["X-ADMIT/CHECK status differ"] += 1
        ex["X-ADMIT"].append((tag, repr(value), d.codes(), r.codes()))
        return
    if r.admitted is None:
        stats[f"refused {sorted(set(r.codes()))}"] += 1
        return
    stats["admitted"] += 1
    executed = dict(r.admitted.configuration)["T"]
    if deciding is not None:
        own = o.world.variable("T").domain
        lvl = matched_level(deciding, value, also=own.levels if isinstance(own, DiscreteLevels) else ())
        vu = o.world.variable("T").unit
        if lvl is None or canonical_bytes(value_payload(executed)) != canonical_bytes(value_payload(as_unit(lvl, vu))):
            stats["X-NOTLEVEL"] += 1
            ex["X-NOTLEVEL"].append((tag, repr(value), repr(executed), repr(lvl)))
    rec = json.loads(json.dumps(AdmissionRecord.of(r, o.authorities()).to_dict()))
    out = replay_admission(rec).outcome
    if out is not ReplayOutcome.REPRODUCED:
        stats["X-REPLAY"] += 1
        ex["X-REPLAY"].append((tag, repr(value), out.value))


for it in range(N):
    fam = random.choice(FAM)
    vu = random.choice(fam)
    lu_v, lu_c = random.choice(fam), random.choice(fam)
    ms = mags()
    try:
        V = DiscreteLevels(lu_v, tuple(Quantity(m, lu_v) for m in ms))
        sub = random.sample(V.levels, random.randint(1, len(V.levels)))
        C = DiscreteLevels(lu_c, tuple(Quantity(lv.magnitude_in(lu_c), lu_c) for lv in sub))
    except (WorldRefused, Exception) as exc:  # noqa: BLE001
        stats["levels refused"] += 1
        continue
    bound_q = None
    if random.random() < 0.4:
        lv = random.choice(V.levels)
        bound_q = spell(lv, fam)
    # ---- fixed conditions
    role = random.choice([R.FIXED_PROTOCOL_CONDITION, R.CONTROLLED_INPUT])
    try:
        placeholder = mk(f"synthetic.f03p{it}", vu, V, C, V.levels[0], role, "levels", bound_q)
    except WorldRefused as exc:
        stats["fixed: placeholder refused at bind"] += 1
        placeholder = None
    for k in range(3):
        f = spell(random.choice(V.levels), fam)
        if not converts(f, vu):
            continue
        try:
            w = mk(f"synthetic.f03f{it}_{k}", vu, V, C, f, role, "levels", bound_q)
            bind_ok, why = True, ""
        except WorldRefused as exc:
            bind_ok, why = False, str(exc)
        if placeholder is not None:
            spec = placeholder.action("a")
            executed = fz.as_executed(placeholder, spec, "T", f)
            found = membership(V, executed) or fz.level_problem(placeholder, spec, "T", f, executed)
            check_ok = found is None
            if bind_ok and not check_ok:
                stats["F-BC fixed: bind accepts, check refuses"] += 1
                ex["F-BC"].append((repr(V.levels), vu, repr(f), found[0]))
            elif check_ok and not bind_ok:
                stats["F-CB fixed: check accepts, bind refuses"] += 1
                ex["F-CB"].append((repr(V.levels), vu, repr(f), why[:140]))
            else:
                stats[f"fixed: bind/check agree ({'ok' if bind_ok else 'refused'})"] += 1
        if bind_ok:
            pipeline(w, {"mode": b.cat("a")}, f"f03f{it}_{k}", V, f)
    # ---- controls (action level set C, own level set V)
    try:
        w = mk(f"synthetic.f03c{it}", vu, V, C, None, R.CONTROLLED_INPUT, "levels", bound_q)
    except WorldRefused:
        stats["control: world refused at bind"] += 1
        continue
    for k in range(3):
        f = spell(random.choice(C.levels + V.levels), fam)
        if not converts(f, vu):
            continue
        pipeline(w, {"mode": b.cat("a"), "T": f}, f"f03c{it}_{k}", C, f)

for k, v in sorted(stats.items()):
    print(f"{v:6d}  {k}")
for k, v in ex.items():
    print(k, len(v))
    for e in v[:4]:
        print("   ", e)
