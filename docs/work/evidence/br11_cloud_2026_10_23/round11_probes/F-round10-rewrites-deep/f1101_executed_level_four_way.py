"""R11-F f1101: does ONE executed value hold across bind, check, mint and replay at aad2f69 (round 10's executed_level)?

For random (variable unit, own level set or range or none, action level set or none, fixed condition or control value)
combinations, each spelled near a declared level (-2..+2 ulps, 12/15-digit restatements, every unit of the family):
  bind   : the world is built with the action (ActionSpec.bind runs), or refused
  check  : FeasibleActionSpace.check(proposal): any reason whose subject is T
  as_exec: feasibility.as_executed (the check's rule) and actions._fixed_as_executed (bind's rule) for a fixed condition
  mint   : admit(...) through ax.owned(base=world)'s live owners -> the admitted configuration's T
  replay : AdmissionRecord.of + replay_admission (REPRODUCED) and replay_decision (REPRODUCED)
Asserts: bind accepts a fixed condition  <=>  check gives no T reason; mint == as_executed == bind's executed value
(bytes); every admitted case replays REPRODUCED; no case raises."""
import dataclasses
import json
import math
import random
import sys
import traceback

from benchmarks.mind_gen2_authority_v1 import fixtures as ax
from benchmarks.mind_gen2_world_v1 import fixtures as b
from engcore.mind.repsem.roles import RoleSource, VariableRole as R
from engcore.mind.world import (ActionMode, AdmissionRecord, FeasibleActionSpace, TemporalSemantics as TS,
                                WorldRefused, admit, replay_admission, replay_decision)
from engcore.mind.world import actions as act
from engcore.mind.world import feasibility as fz
from engcore.mind.world.base import converts, value_payload
from engcore.mind.world.domains import DiscreteLevels
from engcore.scientific import Quantity
from engcore.sria.decision import ActionFamily
from engcore.sria.decision.replay import ReplayOutcome

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
N = int(sys.argv[2]) if len(sys.argv) > 2 else 60
E2E = float(sys.argv[3]) if len(sys.argv) > 3 else 0.25
random.seed(seed)
P = RoleSource.PROTOCOL_METADATA
FAM = [["degC", "K", "degF"], ["A", "mA", "kA"], ["m", "mm", "ft", "inch"], ["bar", "Pa", "kPa", "psi"],
       ["s", "ms", "minute", "hour"]]


def ulps(m, k):
    for _ in range(abs(k)):
        m = math.nextafter(m, math.inf if k > 0 else -math.inf)
    return m


def build(vu, own, fixed=None, tctrl=None):
    controls = [b.ctrl("mode", b.cats("mode", "a", "b"), P)]
    if tctrl is not None:
        controls.append(b.ctrl("T", tctrl, P))
    return b.world("synthetic.f1101", (
        b.var("T", R.FIXED_PROTOCOL_CONDITION, vu, TS.CONSTANT_PER_RUN, domain=own),
        b.var("mode", R.CONTROLLED_INPUT, "dimensionless", TS.CONSTANT_PER_RUN, domain=b.cats("mode", "a", "b")),
        b.var("y", R.MEASUREMENT, "V", TS.TIME_SERIES)),
        actions=(b.action("a", ActionFamily.EXPLORE, ActionMode.INTERVENE, controls=tuple(controls),
                          fixed_conditions=() if fixed is None else (b.fixed("T", fixed),), expected_observables=("y",),
                          estimated_cost=b.cost(1, 0), estimated_duration=b.q(10, "s")),),
        channels=(b.channel("y"),), budget=b.budget(5, 0, ledger="f1101"), references=(b.synthetic("f1101/1"),))


def levels(du):
    n = random.randint(1, 3)
    digits = random.choice([6, 9, 12, 13, 15])
    vals = sorted({float(f"{random.uniform(0.5, 999.0) * 10 ** random.randint(-1, 2):.{digits}g}") for _ in range(n)})
    return DiscreteLevels(du, tuple(Quantity(v, du) for v in vals))


def spellings(lv, fam):
    out = []
    for L in lv.levels:
        for u in fam:
            try:
                m = L.magnitude_in(u)
            except Exception:  # noqa: BLE001
                continue
            for k in (-2, -1, 0, 1, 2):
                out.append(Quantity(ulps(m, k), u))
            out.append(Quantity(float(f"{m:.12g}"), u))
    return out


stats = dict(worlds=0, fixed_cases=0, ctrl_cases=0, bind_ne_check=0, exec_ne=0, mint_ne=0, admitted=0, replays=0,
             replay_bad=0, raised=0, bind_refused=0, world_refused=0)
examples = {}
for t in range(N):
    fam = random.choice(FAM)
    vu = random.choice(fam)
    shape = random.choice(["own", "own", "own+ctrl", "ctrl", "range"])
    own = levels(random.choice(fam)) if shape in ("own", "own+ctrl") else None
    if shape == "range":
        lo = random.uniform(1, 50)
        own = b.crange("T", random.choice(fam), lo, lo * random.uniform(1.5, 4))
    tctrl = None
    if shape in ("own+ctrl", "ctrl"):
        tctrl = DiscreteLevels(random.choice(fam), tuple(
            Quantity(L.magnitude_in(random.choice(fam)) if own is not None and random.random() < 0.7 else L.magnitude, L.units)
            for L in (own.levels if own is not None else levels(random.choice(fam)).levels)))
        try:
            tctrl = DiscreteLevels(tctrl.unit, tuple(Quantity(L.magnitude_in(tctrl.unit), tctrl.unit) for L in tctrl.levels))
        except Exception:  # noqa: BLE001
            continue
    try:
        w0 = build(vu, own, tctrl=tctrl)
    except WorldRefused:
        stats["world_refused"] += 1
        continue
    stats["worlds"] += 1
    probe_levels = tctrl if tctrl is not None else (own if isinstance(own, DiscreteLevels) else
                                                    DiscreteLevels(own.unit, (own.lower, own.upper)))
    for s in spellings(probe_levels, fam):
        if not converts(s, vu):
            continue
        is_ctrl = tctrl is not None
        stats["ctrl_cases" if is_ctrl else "fixed_cases"] += 1
        try:
            if is_ctrl:
                w = w0
                bok = True
            else:
                try:
                    w = build(vu, own, fixed=s)
                    bok = True
                except WorldRefused:
                    bok = False
                    stats["bind_refused"] += 1
                    w = None
                    # the check on the same action spec, unbound (dataclasses.replace skips bind)
                    spec_u = dataclasses.replace(w0.action("a"), fixed_conditions=(b.fixed("T", s),))
                    executed = fz.as_executed(w0, spec_u, "T", s)
                    found = fz.membership(w0.variable("T").domain, executed) if w0.variable("T").domain is not None else None
                    if found is None:
                        found = fz.level_problem(w0, spec_u, "T", s, executed)
                    if found is None:
                        stats["bind_ne_check"] += 1
                        examples.setdefault("bind_refused_check_ok", (vu, own, s))
                    continue
            spec = w.action("a")
            assign = {"mode": b.cat("a")}
            if is_ctrl:
                assign["T"] = s
            prop = b.propose(w, "a", assign, ("y",))
            d = FeasibleActionSpace.build(w).check(prop)
            t_reasons = [r.code for r in d.reasons if r.subject == "T"]
            ex_check = fz.as_executed(w, spec, "T", s)
            if not is_ctrl:
                ex_bind = act._fixed_as_executed(w.variable("T").domain, s, w.variable("T").unit)
                if value_payload(ex_bind) != value_payload(ex_check):
                    stats["exec_ne"] += 1
                    examples.setdefault("exec_ne", (vu, own, s, value_payload(ex_bind), value_payload(ex_check)))
                if t_reasons:
                    stats["bind_ne_check"] += 1
                    examples.setdefault("bind_ok_check_refuses", (vu, own, s, t_reasons))
            if random.random() > E2E:
                continue
            o = ax.owned("f1101", base=w)
            authorities = o.authorities()
            wp = o.world
            prop2 = o.propose("a", assign, ("y",))
            r = admit(FeasibleActionSpace.build(wp), prop2, authorities)
            if r.admitted is None:
                if not t_reasons and not is_ctrl:
                    examples.setdefault("not_admitted_no_T_reason", (vu, own, s, r.codes()))
                continue
            stats["admitted"] += 1
            minted = dict(r.admitted.configuration)["T"]
            if value_payload(minted) != value_payload(fz.as_executed(wp, wp.action("a"), "T", s)) or \
                    value_payload(minted) != value_payload(ex_check):
                stats["mint_ne"] += 1
                examples.setdefault("mint_ne", (vu, own, s, value_payload(minted), value_payload(ex_check)))
            rec = json.loads(json.dumps(AdmissionRecord.of(r, authorities).to_dict()))
            out1 = replay_admission(rec).outcome
            out2 = replay_decision(json.loads(json.dumps(FeasibleActionSpace.build(wp).check(prop2).to_dict())),
                                   json.loads(json.dumps(wp.to_dict())), json.loads(json.dumps(prop2.to_dict()))).outcome
            stats["replays"] += 1
            if out1 is not ReplayOutcome.REPRODUCED or out2 is not ReplayOutcome.REPRODUCED:
                stats["replay_bad"] += 1
                examples.setdefault("replay_bad", (vu, own, s, out1, out2))
        except Exception as exc:  # noqa: BLE001
            stats["raised"] += 1
            examples.setdefault("raised", (vu, own, s, repr(exc), traceback.format_exc()[-600:]))
print(stats)
for k, v in examples.items():
    print(k, v)
