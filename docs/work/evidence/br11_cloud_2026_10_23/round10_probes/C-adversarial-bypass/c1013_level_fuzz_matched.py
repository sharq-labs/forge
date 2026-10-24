"""R10-C c1013 (r01 adapted, adds oracle (e): executed is exactly the MATCHED level of the proposal's class as executed; prints per family).
R8-C p01: broad level fuzz through the PUBLIC Mind-facing API (MindWorldPort + ExecutionDesk.gateway()).

Unit families x (variable unit, own-level unit, action-level unit); two declared levels (sometimes very close); a
strict or inclusive specification constraint AT a level (spelled in a random unit of the family), optionally a model
validity endpoint (exclusive or inclusive) at a level; the role is CONTROLLED_INPUT or FIXED_PROTOCOL_CONDITION.
Proposals spell each level in every unit of the family, with +-1..4 ulp and +-4.9e-13 / 5.1e-13 relative nudges.

Independent oracle on everything the executor RECEIVED:
  (a) the executed magnitude is exactly an action (deciding-set) level as executed (converted into the variable unit);
  (b) the executed value is a member of the variable's own levels by the owner's identity rule;
  (c) every constraint holds on the executed value by the owner's own ConstraintDefinition.check;
  (d) every applicability binding is IN_DOMAIN at the executed value.
And a consistency count: per level class, the set of distinct executed values over all admitted spellings."""
import itertools
import math
import random
import sys
import time

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import (ActionMode, ApplicabilityBinding, DeclaredConstraint, ExecutionDesk, ExecutionKind,
                                FeasibleActionSpace, MindWorldPort, TemporalSemantics as TS, WorldRefused,
                                project_world)
from engcore.mind.world.base import same_value
from engcore.mind.world.domains import DiscreteLevels
from engcore.scientific import (ConstraintDefinition, ConstraintOperator as Op, Quantity, RangeCondition,
                                ScientificCoreError, ScientificModelDefinition, ValidityDomain, ValidityStatus)
from engcore.scientific.models.definition import InputSourceKind, ModelInputSpec
from engcore.sria.decision import ActionFamily

FAMILIES = {
    "length": ("m", "mm", "cm", "km", "inch", "ft", "micrometer"),
    "current": ("A", "mA", "kA", "uA"),
    "pressure": ("Pa", "kPa", "bar", "psi", "atm", "mmHg"),
    "time": ("s", "ms", "minute", "hour"),
    "temperature": ("degC", "K", "degF", "degR"),
    "delta_temperature": ("delta_degC", "delta_degF"),
    "energy": ("J", "kWh", "BTU", "cal"),
    "mass": ("kg", "g", "lb"),
    "angle": ("degree", "radian"),
    "ratio": ("percent", "ppm", "dimensionless"),
    "speed": ("m/s", "km/h", "mph"),
}
OPS = (Op.LESS_THAN, Op.LESS_EQUAL, Op.GREATER_THAN, Op.GREATER_EQUAL)

rng = random.Random(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
N_PER = int(sys.argv[2]) if len(sys.argv) > 2 else 2


def nudges(m):
    out = {m}
    if m != 0:
        for k in (1, 2, 4):
            out |= {m + k * math.ulp(m), m - k * math.ulp(m)}
        for r in (4.9e-13, 5.1e-13):
            out |= {m * (1 + r), m * (1 - r)}
    return out


def build(fam, vu, ou, au, L, role, op, con_unit, con_level_idx, validity):
    own = DiscreteLevels(ou, tuple(Quantity(x, ou) for x in L))
    act = DiscreteLevels(au, tuple(Quantity(Quantity(x, ou).magnitude_in(au), au) for x in L))
    con_q = Quantity(Quantity(L[con_level_idx], ou).magnitude_in(con_unit), con_unit)
    cons = (DeclaredConstraint("c", ConstraintDefinition("c", "x", op, con_q), None, ("*",),
                               RoleSource.PROTOCOL_METADATA if role is R.FIXED_PROTOCOL_CONDITION
                               else RoleSource.PROBLEM_SPECIFICATION, "synthetic constraint at a level"),)
    kw, apps, provs = {}, (), ()
    if validity is not None:
        excl_lo, which = validity
        lv = Quantity(L[which], ou)
        lo = lv if which == 0 else Quantity(Quantity(L[0], ou).magnitude_in(ou) - abs(L[1] - L[0]) * 10, ou)
        hi = lv if which == 1 else Quantity(Quantity(L[1], ou).magnitude_in(ou) + abs(L[1] - L[0]) * 10, ou)
        model = ScientificModelDefinition(
            "synthetic.fz", "1", inputs=(ModelInputSpec("x", InputSourceKind.VARIABLE, unit_exemplar=ou),),
            exclusions=(), excludes_nothing_because="synthetic",
            validity=ValidityDomain((RangeCondition("x", minimum=lo, maximum=hi, minimum_inclusive=not excl_lo,
                                                    maximum_inclusive=not excl_lo),)))
        route = ApplicabilityBinding(model)
        apps = (route,)
        provs = (b.provider("sim.fz", "1.0"),)
        kw = dict(execution=ExecutionKind.MODEL_EXECUTION, provider_requirements=(b.binding("sim.fz", "1.0"),),
                  applicability=(route.binding_id,))
    src = b.P if role is R.FIXED_PROTOCOL_CONDITION else b.S
    w = b.world("synthetic.fz", (
        b.var("x", role, vu, TS.CONSTANT_PER_RUN, role_source=src, domain=own),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("go", ActionFamily.EXPLORE, ActionMode.INTERVENE,
                          controls=(b.ctrl("x", act, b.P),), expected_observables=("y",),
                          estimated_cost=b.cost(1, 1), estimated_duration=b.q(10, "s"), **kw),),
        constraints=cons, channels=(b.channel("y"),), applicability=apps, providers=provs,
        budget=b.budget(10 ** 6, 0, solver=(10 ** 6, 0), ledger="fz"), references=(b.synthetic("fz/1"),))
    return w, own, act


def oracle(world, sent, act):
    bad = []
    vu = world.variable("x").unit
    e = Quantity(dict(sent.settings)["x"], vu)
    if not any(Quantity(lv.magnitude_in(vu), vu).magnitude == e.magnitude for lv in act.levels):
        bad.append(f"(a) executed {e!r} is not exactly an action level as executed")
    if not any(same_value(e, lv) for lv in world.variable("x").domain.levels):
        bad.append(f"(b) executed {e!r} is not a variable level")
    for con in world.constraints:
        if not con.consequence.check(e).satisfied:
            bad.append(f"(c) {con.consequence.operator.value} {con.consequence.limit} violated by executed {e!r}")
    for bid in world.action("go").applicability:
        st = world.applicability_binding(bid).assess({"x": e}).status
        if st is not ValidityStatus.IN_DOMAIN:
            bad.append(f"(d) applicability {st.value} at executed {e!r}")
    return bad


t0 = time.time()
stats = dict(worlds=0, refused_world=0, proposals=0, admitted=0, dispatched=0, mint_refused=0, problems=0)
problems, inconsist = [], []
for fam, units in FAMILIES.items():
    print(fam, stats, f"{time.time() - t0:.0f}s", flush=True)
    for vu, ou, au in itertools.product(units, repeat=3):
        for _ in range(N_PER):
            base = rng.uniform(0.3, 900)
            digits = rng.choice([1, 2, 3, 6, 9])
            L0 = round(base, digits)
            sep = rng.choice([0.5, 0.1, 1e-6, 1e-9, 1e-10])
            L1 = round(L0 * (1 + sep), 12)
            if L1 == L0:
                continue
            L = (L0, L1)
            role = rng.choice([R.CONTROLLED_INPUT, R.FIXED_PROTOCOL_CONDITION])
            op = rng.choice(OPS)
            con_unit = rng.choice(units)
            idx = rng.choice([0, 1])
            validity = rng.choice([None, None, (True, 0), (True, 1), (False, 0)])
            try:
                w, own, act = build(fam, vu, ou, au, L, role, op, con_unit, idx, validity)
                o = ax.owned("fz", w)
                auth = o.authorities()
                calls = []
                gw = ExecutionDesk(auth, calls.append, accept_synthetic=True).gateway()
                port = MindWorldPort(FeasibleActionSpace.build(project_world(o.declaration, auth)))
            except (WorldRefused, ScientificCoreError, ValueError) as exc:
                stats["refused_world"] += 1
                continue
            stats["worlds"] += 1
            pw = port.world
            by_class = {}
            for li, lv in enumerate(L):
                q = Quantity(lv, ou)
                for su in units:
                    try:
                        m = q.magnitude_in(su)
                    except ScientificCoreError:
                        continue
                    for x in nudges(m):
                        sp = Quantity(x, su)
                        stats["proposals"] += 1
                        try:
                            r = port.request_admission(o.propose("go", {"x": sp}, ("y",), world=pw), gw)
                        except WorldRefused as exc:
                            stats["mint_refused"] += 1
                            continue
                        if r.admitted is None:
                            continue
                        stats["admitted"] += 1
                        n = len(calls)
                        port.execute(r.admitted, gw)
                        stats["dispatched"] += 1
                        sent = calls[n]
                        bad = oracle(pw, sent, act)
                        cls = next((i for i, lv2 in enumerate(L) if same_value(sp, Quantity(lv2, ou))), None)
                        e_mag = dict(sent.settings)["x"]
                        if cls is None or e_mag != act.levels[cls].magnitude_in(vu):
                            bad = bad + [f"(e) executed {e_mag!r} is not the matched level {cls} as executed"]
                        by_class.setdefault(cls, set()).add(dict(sent.settings)["x"])
                        if bad:
                            stats["problems"] += 1
                            if len(problems) < 25:
                                problems.append(f"{fam} var={vu} own={ou} act={au} L={L} role={role.value} "
                                                f"con={op.value} {L[idx]} {ou}->{con_unit} validity={validity}: "
                                                f"proposed {sp!r} -> {bad}")
            for cls, vals in by_class.items():
                if len(vals) > 1 and len(inconsist) < 10:
                    inconsist.append(f"{fam} var={vu} own={ou} act={au} L={L} class {cls}: executed {sorted(vals)}")
print(stats, f"{time.time() - t0:.0f}s")
print("problems:")
print("\n".join(problems) or "  none")
print("one level class executed at more than one value:")
print("\n".join(inconsist) or "  none")
