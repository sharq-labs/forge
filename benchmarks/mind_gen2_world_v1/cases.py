"""Case generator for the GEN2-BR1 synthetic feasibility benchmark (labels come from :mod:`.oracle`).

Every case is a FEASIBLE-by-construction base proposal (``fixtures.base``) with zero, one or two declared mutations,
in a world variant made by one declared change.  The generator READS declarations (levels, bounds, roles, model
ranges) to construct mutations and records them as plain facts; it never calls the feasibility check.  Expected
outcomes are computed by the oracle from those facts, audited in plain arithmetic, and frozen into
``results/CASES.json`` before any arm runs.

    python -m benchmarks.mind_gen2_world_v1.cases            # (re)write results/CASES.json
    python -m benchmarks.mind_gen2_world_v1.cases --check    # verify the committed file is what this code produces
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import sys
from typing import Any, Iterator

from engcore.execution.orchestration.resources import ResourceUsage
from engcore.mind.repsem.roles import VariableRole as R
from engcore.mind.world import DiscreteLevels, ExecutionKind, ProposedAction, ScientificWorld
from engcore.scientific import Quantity, Uncertainty, VariableKind, dimensionality
from engcore.scientific.ir.values import CategoricalValue, IntegerValue, decode_value, encode_value
from engcore.scientific.units.quantity import base_unit

from . import fixtures as fx
from . import oracle

HERE = pathlib.Path(__file__).resolve().parent
CASES_PATH = HERE / "results" / "CASES.json"
SCHEMA = "forge.mind.gen2_world.cases/1"
SOURCES = ("cases.py", "fixtures.py", "oracle.py")


def _enc(value: Any) -> dict[str, Any]:
    return encode_value(value)


def _key(value: Any) -> str:
    return json.dumps(_enc(value), sort_keys=True)


# ---- world variants (one declared change each) ------------------------------------------------------------------------
def variant(world_name: str, spec: dict[str, Any]) -> ScientificWorld:
    w = fx.WORLDS[world_name]()
    kind = spec["kind"]
    if kind == "base":
        return w
    if kind == "provider_down":
        return w.derive(reason="provider unavailable", providers=tuple(
            fx.provider(p.provider_id, p.version, available=False) if p.provider_id == spec["provider"] else p
            for p in w.providers))
    if kind == "provider_other_version":
        return w.derive(reason="provider upgraded", providers=tuple(
            fx.provider(p.provider_id, spec["version"]) if p.provider_id == spec["provider"] else p for p in w.providers))
    if kind == "budget_exhausted":
        b = w.budget
        if spec["dimension"] == "experiments":
            b = dataclasses.replace(b, observations_spent=b.experiments.max_observations - spec["remaining"])
        elif spec["dimension"] == "solver_calls":
            b = dataclasses.replace(b, compute_used=ResourceUsage(
                wall_seconds=b.compute_used.wall_seconds,
                function_evaluations=b.compute.max_function_evaluations - spec["remaining"]))
        else:
            b = dataclasses.replace(b, compute_used=ResourceUsage(
                wall_seconds=float(b.compute.max_wall_seconds) - spec["remaining"],
                function_evaluations=b.compute_used.function_evaluations))
        return w.derive(reason="budget consumed", budget=b)
    if kind == "budget_undeclared":
        b = w.budget
        return w.derive(reason="a budget declaration withdrawn", budget=dataclasses.replace(
            b, unbounded=tuple(x for x in b.unbounded if x[0] != spec["dimension"])))
    if kind == "value":
        value = decode_value(spec["value"])
        unc = fx.interval(value.magnitude, spec["half"], value.units)
        return w.derive(reason="a new reading", variables=tuple(
            dataclasses.replace(v, value=value, uncertainty=unc) if v.name == spec["variable"] else v
            for v in w.variables))
    if kind == "uncertainty_unknown":
        return w.derive(reason="uncertainty withdrawn", variables=tuple(
            dataclasses.replace(v, uncertainty=Uncertainty.unknown("withdrawn")) if v.name == spec["variable"] else v
            for v in w.variables))
    if kind == "fixed_condition":
        value = decode_value(spec["value"])
        return w.derive(reason="another protocol set point", actions=tuple(
            dataclasses.replace(a, fixed_conditions=tuple(dataclasses.replace(f, value=value) if f.name == spec["variable"]
                                                          else f for f in a.fixed_conditions))
            if a.action_id == spec["action"] else a for a in w.actions))
    raise ValueError(f"unknown variant {kind!r}")


def proposal(case: dict[str, Any], world: ScientificWorld) -> ProposedAction:
    return ProposedAction(case["action_id"], world.revision_id,
                          tuple((a["variable"], decode_value(a["value"])) for a in case["assignments"]),
                          tuple(case["observe"]), fx.HUMAN)


# ---- mutation constructors ---------------------------------------------------------------------------------------------
def _member(domain: Any, unit: str) -> Any:
    if domain is None:
        return Quantity(1.0, unit)
    if isinstance(domain, DiscreteLevels):
        return domain.levels[0]
    if domain.kind is VariableKind.CATEGORICAL:
        return CategoricalValue(domain.categories[0])
    if domain.kind is VariableKind.INTEGER:
        return IntegerValue(int(domain.lower.magnitude))
    if domain.kind is VariableKind.BOOLEAN:
        from engcore.scientific.ir.values import BooleanValue
        return BooleanValue(False)
    return domain.lower


def _value_mutations(control: Any) -> Iterator[tuple[str, Any, dict[str, Any]]]:
    d, by = control.domain, control.declared_by.value
    if isinstance(d, DiscreteLevels):
        lv = sorted(level.magnitude_in(d.unit) for level in d.levels)
        value = (lv[0] + lv[1]) / 2 if len(lv) > 1 else lv[0] * 1.15 + 0.1
        yield "OFF_LEVEL", Quantity(value, d.unit), {"declared_by": by, "levels": lv, "value": value, "unit": d.unit}
        return
    if d.kind is VariableKind.CONTINUOUS:
        lo, hi = d.lower.magnitude, d.upper.magnitude
        span = hi - lo
        yield "ABOVE_RANGE", Quantity(hi + 0.1 * span, d.unit), {"declared_by": by, "lower": lo, "upper": hi,
                                                                 "value": hi + 0.1 * span, "unit": d.unit}
        yield "BELOW_RANGE", Quantity(lo - 0.1 * span, d.unit), {"declared_by": by, "lower": lo, "upper": hi,
                                                                 "value": lo - 0.1 * span, "unit": d.unit}
    elif d.kind is VariableKind.INTEGER:
        hi = int(d.upper.magnitude)
        yield "INTEGER_ABOVE_RANGE", IntegerValue(hi + 1), {"declared_by": by, "upper": hi, "value": hi + 1}
        yield "WRONG_KIND", Quantity(float(hi), "dimensionless"), {"declared_by": by, "expected": "integer"}
    elif d.kind is VariableKind.CATEGORICAL:
        yield "UNDECLARED_CATEGORY", CategoricalValue("undeclared_category"), {
            "declared_by": by, "categories": list(d.categories), "value": "undeclared_category"}
        yield "WRONG_KIND", Quantity(1.0, "dimensionless"), {"declared_by": by, "expected": "categorical"}


def _wrong_unit(control: Any, base_value: Any) -> tuple[str, Any, dict[str, Any]] | None:
    d = control.domain
    if not isinstance(base_value, Quantity) or not (isinstance(d, DiscreteLevels) or d.kind is VariableKind.CONTINUOUS):
        return None
    declared = dimensionality(d.unit)
    unit = "A" if declared == dimensionality("s") else "s"
    return "WRONG_UNIT", Quantity(base_value.magnitude, unit), {
        "declared_by": control.declared_by.value, "declared_dimension": declared,
        "proposed_dimension": dimensionality(unit), "unit": unit}


def _first(world: ScientificWorld, role: R, exclude: set[str]) -> Any:
    for v in world.variables:
        if v.role is role and v.name not in exclude:
            return v
    return None


# ---- cases ---------------------------------------------------------------------------------------------------------------
def _case(world_name: str, w_spec: dict[str, Any], action_id: str, assignments: dict[str, Any],
          observe: tuple[str, ...], mutations: list[dict[str, Any]]) -> dict[str, Any]:
    tag = "+".join(f"{m['kind']}:{m['subject']}" + (f"={m['facts']['value']}" if "value" in m["facts"] else "")
                   for m in mutations) or "BASE"
    vtag = w_spec["kind"] + "".join(f":{w_spec[k]}" for k in sorted(w_spec) if k not in ("kind", "value", "half"))
    return {"case_id": f"{world_name}/{vtag}/{action_id}/{tag}", "world": world_name, "variant": w_spec,
            "action_id": action_id,
            "assignments": [{"variable": k, "value": _enc(v)} for k, v in sorted(assignments.items())],
            "observe": list(observe), "mutations": mutations, "expected": oracle.label(mutations),
            "audit": [p for m in mutations for p in oracle.audit(m)]}


def _m(kind: str, subject: str, facts: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"kind": kind, "subject": subject, "facts": facts or {}}


def world_cases(world_name: str) -> list[dict[str, Any]]:
    w = fx.WORLDS[world_name]()
    out: list[dict[str, Any]] = []
    base_spec = {"kind": "base"}
    for aid, (assign, observe) in fx.base(world_name).items():
        spec = w.action(aid)
        controls = {c.variable for c in spec.controls}
        held = controls | {f.name for f in spec.fixed_conditions}
        out.append(_case(world_name, base_spec, aid, assign, observe, []))
        out += list(_valid_cases(world_name, w, spec, assign, observe))
        # -- values of the action's controls
        for c in spec.controls:
            for kind, value, facts in _value_mutations(c):
                out.append(_case(world_name, base_spec, aid, {**assign, c.variable: value}, observe,
                                 [_m(kind, c.variable, facts)]))
            wrong = _wrong_unit(c, assign.get(c.variable))
            if wrong:
                out.append(_case(world_name, base_spec, aid, {**assign, c.variable: wrong[1]}, observe,
                                 [_m(wrong[0], c.variable, wrong[2])]))
            out.append(_case(world_name, base_spec, aid, {k: v for k, v in assign.items() if k != c.variable},
                             observe, [_m("MISSING_CONTROL", c.variable)]))
        # -- two mutations at once: a value mutation on one control and a unit error on another
        if len(spec.controls) >= 2:
            c0, c1 = spec.controls[0], spec.controls[1]
            first = next(iter(_value_mutations(c0)), None)
            wrong = _wrong_unit(c1, assign.get(c1.variable))
            if first and wrong:
                out.append(_case(world_name, base_spec, aid, {**assign, c0.variable: first[1], c1.variable: wrong[1]},
                                 observe, [_m(first[0], c0.variable, first[2]), _m(wrong[0], c1.variable, wrong[2])]))
        # -- setting variables the action does not offer, by role
        for role, kind in ((R.STATE_VARIABLE, "SET_STATE"), (R.MEASUREMENT, "SET_MEASUREMENT"),
                           (R.LATENT_PARAMETER, "SET_LATENT"), (R.NUISANCE_VARIABLE, "SET_NUISANCE"),
                           (R.DERIVED_QUANTITY, "SET_DERIVED"), (R.CONTROLLED_INPUT, "SET_UNOFFERED_INPUT"),
                           (R.FIXED_PROTOCOL_CONDITION, "SET_UNSELECTABLE_PROTOCOL")):
            v = _first(w, role, held)
            if v is not None:
                out.append(_case(world_name, base_spec, aid, {**assign, v.name: _member(v.domain, v.unit)}, observe,
                                 [_m(kind, v.name, {"role": role.value})]))
        for f in spec.fixed_conditions:
            var = w.variable(f.name)
            other = None
            if isinstance(var.domain, DiscreteLevels):
                other = next((lv for lv in var.domain.levels if _key(lv) != _key(f.value)), None)
            elif var.domain is not None and var.domain.kind is VariableKind.CATEGORICAL:
                other = next((CategoricalValue(c) for c in var.domain.categories if c != f.value.value), None)
            elif isinstance(f.value, Quantity) and var.domain is not None:
                lo, hi = var.domain.lower.magnitude_in(f.value.units), var.domain.upper.magnitude_in(f.value.units)
                step = 0.1 * (hi - lo)
                x = f.value.magnitude + step if f.value.magnitude + step <= hi else f.value.magnitude - step
                other = Quantity(x, f.value.units)
            if other is not None:
                out.append(_case(world_name, base_spec, aid, {**assign, f.name: other}, observe,
                                 [_m("CHANGE_FIXED", f.name, {"fixed": _key(f.value), "proposed": _key(other)})]))
        out.append(_case(world_name, base_spec, aid, {**assign, "undeclared_variable": Quantity(1.0, "dimensionless")},
                         observe, [_m("UNDECLARED_VARIABLE", "undeclared_variable")]))
        # -- observation requests
        for role, kind in ((R.LATENT_PARAMETER, "OBSERVE_LATENT"), (R.DERIVED_QUANTITY, "OBSERVE_DERIVED")):
            v = _first(w, role, set())
            if v is not None:
                out.append(_case(world_name, base_spec, aid, assign, observe + (v.name,), [_m(kind, v.name)]))
        no_channel = next((v for v in w.variables if v.role not in (R.LATENT_PARAMETER, R.DERIVED_QUANTITY)
                           and not w.has_channel(v.name)), None)
        if no_channel is not None:
            out.append(_case(world_name, base_spec, aid, assign, observe + (no_channel.name,),
                             [_m("OBSERVE_NO_CHANNEL", no_channel.name)]))
        unoffered = next((c.variable for c in w.channels if c.variable not in spec.expected_observables), None)
        if unoffered is not None:
            out.append(_case(world_name, base_spec, aid, assign, observe + (unoffered,),
                             [_m("OBSERVE_UNOFFERED", unoffered)]))
        if spec.mode.value == "observe":
            out.append(_case(world_name, base_spec, aid, assign, (), [_m("OBSERVE_NOTHING", aid)]))
        # -- world variants: provider, budget, applicability, state, protocol constraints
        for req in spec.provider_requirements:
            out.append(_case(world_name, {"kind": "provider_down", "provider": req.provider_id}, aid, assign, observe,
                             [_m("PROVIDER_DOWN", req.provider_id)]))
            out.append(_case(world_name, {"kind": "provider_other_version", "provider": req.provider_id,
                                          "version": req.provider_version + ".1"}, aid, assign, observe,
                             [_m("PROVIDER_OTHER_VERSION", req.provider_id)]))
        for dim in ("experiments", "solver_calls", "wall_time"):
            if w.budget.status(dim) != "limited":
                continue
            amount = spec.estimated_duration if dim == "wall_time" else spec.cost(dim)
            cost = amount.magnitude_in("s") if dim == "wall_time" else amount.value
            if cost <= 0:
                continue
            remaining = cost - 1
            out.append(_case(world_name, {"kind": "budget_exhausted", "dimension": dim, "remaining": remaining}, aid,
                             assign, observe, [_m("BUDGET_EXHAUSTED", dim, {"cost": cost, "remaining": remaining})]))
        out.append(_case(world_name, {"kind": "budget_undeclared", "dimension": "cost"}, aid, assign, observe,
                         [_m("BUDGET_UNDECLARED", "cost")]))
        if spec.execution is ExecutionKind.MODEL_EXECUTION:
            out += list(_applicability_cases(world_name, w, spec, assign, observe))
        if spec.preconditions:
            out += list(_precondition_cases(world_name, w, spec, assign, observe))
        out += list(_constraint_cases(world_name, w, spec, assign, observe))
    out.append(_case(world_name, base_spec, "undeclared_action", {}, (), [_m("UNDECLARED_ACTION", "undeclared_action")]))
    return out


def _read_elsewhere(w: ScientificWorld, spec: Any) -> set[str]:
    """Variables an in-scope constraint or the action's applicability reads (a valid variant must leave them alone)."""
    names: set[str] = set()
    for c in w.constraints:
        if c.applies(spec.action_id):
            names |= set(c.reads)
    for binding_id in spec.applicability:
        names |= set(w.applicability_binding(binding_id).reads)
    return names


def _valid_cases(world_name, w, spec, assign, observe):
    base_spec = {"kind": "base"}
    read = _read_elsewhere(w, spec)
    for c in spec.controls:
        current = assign.get(c.variable)
        d = c.domain
        if isinstance(current, Quantity):
            respelled = current.to(base_unit(current.units))
            if respelled.units != current.units:
                yield _case(world_name, base_spec, spec.action_id, {**assign, c.variable: respelled}, observe,
                            [_m("VALID_RESPELL", c.variable, {"base_value": current.magnitude_in(respelled.units),
                                                              "respelled_in_base": respelled.magnitude})])
        if c.variable in read:
            continue
        if isinstance(d, DiscreteLevels):
            lv = sorted(level.magnitude_in(d.unit) for level in d.levels)
            for level in d.levels:
                if _key(level) != _key(current):
                    yield _case(world_name, base_spec, spec.action_id, {**assign, c.variable: level}, observe,
                                [_m("VALID_LEVEL", c.variable, {"levels": lv, "value": level.magnitude_in(d.unit)})])
        elif d.kind is VariableKind.CONTINUOUS:
            for bound in (d.lower, d.upper):
                yield _case(world_name, base_spec, spec.action_id, {**assign, c.variable: bound}, observe,
                            [_m("VALID_BOUNDARY", c.variable, {"lower": d.lower.magnitude, "upper": d.upper.magnitude,
                                                               "value": bound.magnitude})])
        elif d.kind is VariableKind.INTEGER:
            for i in (int(d.lower.magnitude), int(d.upper.magnitude)):
                yield _case(world_name, base_spec, spec.action_id, {**assign, c.variable: IntegerValue(i)}, observe,
                            [_m("VALID_INTEGER_BOUND", c.variable, {"lower": int(d.lower.magnitude),
                                                                    "upper": int(d.upper.magnitude), "value": i})])
    for f in spec.fixed_conditions:
        if isinstance(f.value, Quantity):
            respelled = f.value.to(base_unit(f.value.units))
            yield _case(world_name, base_spec, spec.action_id, {**assign, f.name: respelled}, observe,
                        [_m("VALID_FIXED_RESTATE", f.name, {"base_value": f.value.magnitude_in(respelled.units),
                                                            "respelled_in_base": respelled.magnitude})])
    for name in spec.expected_observables:
        if (name,) != tuple(observe):
            yield _case(world_name, base_spec, spec.action_id, assign, (name,), [_m("VALID_OBSERVE_SUBSET", name)])


def _applicability_cases(world_name, w, spec, assign, observe):
    for binding_id in spec.applicability:
        model = w.applicability_binding(binding_id).model
        for cond in model.validity.conditions:
            name, unit = cond.name, cond.maximum.units
            lo, hi = cond.minimum.magnitude, cond.maximum.magnitude
            control = spec.control(name)
            if control is not None:
                clo, chi = control.domain.lower.magnitude_in(unit), control.domain.upper.magnitude_in(unit)
                if chi > hi:
                    value = hi + 0.5 * (chi - hi)
                elif clo < lo:
                    value = lo - 0.5 * (lo - clo)
                else:
                    continue
                yield _case(world_name, {"kind": "base"}, spec.action_id, {**assign, name: Quantity(value, unit)},
                            observe, [_m("APPLICABILITY_OUTSIDE", name, {
                                "model_lower": lo, "model_upper": hi, "value": value, "control_lower": clo,
                                "control_upper": chi})])
            elif spec.fixed(name) is not None:
                value = hi + 0.1 * (hi - lo)
                yield _case(world_name, {"kind": "fixed_condition", "action": spec.action_id, "variable": name,
                                         "value": _enc(Quantity(value, unit))}, spec.action_id, assign, observe,
                            [_m("APPLICABILITY_OUTSIDE", name, {"model_lower": lo, "model_upper": hi, "value": value})])
            else:
                value = hi + 0.1 * (hi - lo) + 1.0
                yield _case(world_name, {"kind": "value", "variable": name, "value": _enc(Quantity(value, unit)),
                                         "half": 0.5}, spec.action_id, assign, observe,
                            [_m("APPLICABILITY_OUTSIDE", name, {"model_lower": lo, "model_upper": hi, "value": value})])


def _precondition_cases(world_name, w, spec, assign, observe):
    pre = spec.preconditions[0]
    unit = pre.bound.units
    b = pre.bound.magnitude
    half = 0.05 * max(1.0, abs(b))
    op = pre.operator.value
    value = b + 2 * half if op in ("<=", "<") else b - 2 * half
    yield _case(world_name, {"kind": "value", "variable": pre.metric, "value": _enc(Quantity(value, unit)), "half": half},
                spec.action_id, assign, observe, [_m("PRECONDITION_VIOLATED", pre.name, {
                    "operator": op, "bound": b, "lower_edge": value - half, "upper_edge": value + half})])
    yield _case(world_name, {"kind": "uncertainty_unknown", "variable": pre.metric}, spec.action_id, assign, observe,
                [_m("PRECONDITION_UNCERTAIN", pre.name)])


def _constraint_cases(world_name, w, spec, assign, observe):
    for c in w.constraints:
        if not c.applies(spec.action_id) or c.guard is None:
            continue
        guard_control = spec.control(c.guard.variable)
        metric_control = spec.control(c.consequence.metric)
        if guard_control is None or metric_control is None or isinstance(metric_control.domain, DiscreteLevels):
            continue
        unit = c.consequence.bound.units
        b = c.consequence.bound.magnitude
        lo = metric_control.domain.lower.magnitude_in(unit)
        hi = metric_control.domain.upper.magnitude_in(unit)
        op = c.consequence.operator.value
        if op in ("<=", "<") and hi > b:
            value = b + 0.5 * (hi - b)
        elif op in (">=", ">") and lo < b:
            value = b - 0.5 * (b - lo)
        else:
            continue
        yield _case(world_name, {"kind": "base"}, spec.action_id,
                    {**assign, c.guard.variable: c.guard.values[0], c.consequence.metric: Quantity(value, unit)},
                    observe, [_m("CONSTRAINT_VIOLATED", c.constraint_id, {
                        "declared_by": c.declared_by.value, "operator": op, "bound": b, "value": value,
                        "control_lower": lo, "control_upper": hi})])


def build() -> dict[str, Any]:
    cases = [c for name in sorted(fx.WORLDS) for c in world_cases(name)]
    ids = [c["case_id"] for c in cases]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise AssertionError(f"duplicate case ids {dup}")
    failed = [c["case_id"] for c in cases if c["audit"]]
    if failed:
        raise AssertionError(f"construction audit failed for {failed}")
    sources = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in SOURCES}
    return {"schema": SCHEMA, "sources": sources, "count": len(cases), "cases": cases}


def dump(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=1, allow_nan=False) + "\n").encode("utf-8")


def load() -> dict[str, Any]:
    payload = json.loads(CASES_PATH.read_bytes().decode("utf-8"))
    if payload.get("schema") != SCHEMA:
        raise ValueError("not a GEN2-BR1 case file")
    return payload


def main(argv: list[str]) -> int:
    payload = build()
    if "--check" in argv:
        same = CASES_PATH.read_bytes() == dump(payload)
        print("CASES INTACT" if same else "CASES DIFFER")
        return 0 if same else 1
    CASES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CASES_PATH.write_bytes(dump(payload))
    print(f"wrote {payload['count']} cases to {CASES_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
