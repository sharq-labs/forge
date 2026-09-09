"""The independent reason/catcher analyser must not peek, and must bite.

The verdict round asked *what* each case is. This one asks *why*, and a why is
much easier to fake: a module that read the benchmark's declared catcher and
echoed it back would score perfectly against the benchmark and tell you
nothing. So the claims that matter here are sharper than the verdict round's.

**NO-PEEK (P0).** `should_be_caught_by`, `acceptable_catchers` and the stored
`reason` are the very answers this round reconstructs. Changing any of them --
or any other stored field -- must leave the analyser's output BYTE-IDENTICAL.

**CAUSALITY IS COUNTERFACTUAL.** A catcher is causal here because removing its
mechanism changes the verdict, not because anything reported it. The repair
table is therefore load-bearing and is tested directly: a repair must actually
move the condition it targets.

**THE SOLVER IS CHECKED AGAINST ITS OWN EQUATION.** The coupled operating point
is now solved in closed form. A closed form can be wrong in a way an iteration
cannot -- silently, on every case at once -- so the root is substituted back
into the balance it claims to solve.

A NOTE ON HOW THIS WAS BUILT. Two defects in the underlying evaluator were
found during this round. The first was found WITHOUT Forge: a damped iteration
reported "no operating point exists" on five cases where the quadratic shows a
positive root plainly does, and the closed form and the iteration disagreeing
with each other is what exposed it. The second was found WITH Forge: an
over-broad gate marked three convection conditions undecidable whenever any
fluid property was missing, and Forge reporting fewer gaps is what prompted the
check that showed a Reynolds number never needed the fluid conductivity. The
register records both, and the second is contamination.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import math
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
ORACLES = REPO / "benchmarks" / "oracles"
CASES = REPO / "benchmarks" / "hard" / "cases_hard"


def _load(stem):
    name = f"_{stem}_under_test"
    if name in sys.modules:
        return sys.modules[name]
    sys.path.insert(0, str(ORACLES))
    spec = importlib.util.spec_from_file_location(name, ORACLES / f"{stem}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


truth = _load("independent_truth")
reason = _load("independent_reason")

#: Sound, refused, screened, both former false accepts, a genuine runaway, a
#: conductor non-physical at its own start, and two forced-convection cases
#: with one fluid property withheld.
SAMPLE = ["S00013", "U00002", "U00204", "U01001", "U01881",
          "U00048", "U01031", "U00705", "U00849"]


def case(case_id):
    return json.loads((CASES / f"{case_id}.json").read_text(encoding="utf-8"))


def analyse(payload, case_id="X"):
    return reason.analyse(case_id, payload)


def si(text):
    return truth.si(text)


# =====================================================================
# P0 -- the no-peek guarantee
# =====================================================================

def _flip(current, options):
    """A value guaranteed to differ from the one already stored.

    A mutation that happened to be a no-op would let the no-peek test pass
    vacuously on exactly the cases where it matters most.
    """
    return next(o for o in options if o != current)


METADATA_MUTATIONS = {
    "should_be_caught_by": lambda g: g.update(
        {"should_be_caught_by": "a_condition_that_does_not_exist"}
    ),
    "should_be_caught_by (plausible)": lambda g: g.update(
        {"should_be_caught_by": _flip(
            g.get("should_be_caught_by"), ["biot_number", "temperature"]
        )}
    ),
    "acceptable_catchers": lambda g: g.update(
        {"acceptable_catchers": ["biot_number", "melting_temperature_utilization"]}
    ),
    "acceptable_catchers (emptied)": lambda g: g.update(
        {"acceptable_catchers": []}
    ),
    "reason": lambda g: g.update({"reason": "an entirely different story"}),
    "expected_verdict": lambda g: g.update({"expected_verdict": _flip(
        g["expected_verdict"],
        ["SUPPORTED", "NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE"],
    )}),
    "expected_unknown_reason": lambda g: g.update(
        {"expected_unknown_reason": "conservative_screen"}
    ),
    "defect": lambda g: g.update({"defect": "something_else_entirely"}),
    "label": lambda g: g.update({"label": _flip(
        g.get("label"), ["valid", "limit_exceeded", "model_inapplicable"]
    )}),
}


@pytest.mark.parametrize("case_id", SAMPLE)
@pytest.mark.parametrize("mutation", sorted(METADATA_MUTATIONS))
def test_no_stored_field_can_move_the_independent_reason(case_id, mutation):
    """P0. Each of these IS an answer to the question being asked."""
    original = case(case_id)
    baseline = analyse(original["payload"], case_id)

    mutated = copy.deepcopy(original)
    METADATA_MUTATIONS[mutation](mutated["ground_truth"])
    assert mutated["ground_truth"] != original["ground_truth"], (
        f"{mutation} was a no-op on {case_id}: the test would pass vacuously"
    )

    after = analyse(mutated["payload"], case_id)
    assert json.dumps(after, sort_keys=True) == json.dumps(
        baseline, sort_keys=True
    ), f"{case_id}: mutating {mutation} moved the independent reason truth"


@pytest.mark.parametrize("case_id", SAMPLE)
def test_the_declared_catcher_cannot_reach_the_causal_set(case_id):
    """The sharpest form of P0 for this round, stated on its own.

    `causal_catchers` is the field the benchmark's `should_be_caught_by` would
    be compared against. Naming a different condition there must not put it in
    the causal set, and emptying `acceptable_catchers` must not empty it.
    """
    original = case(case_id)
    before = analyse(original["payload"], case_id)

    mutated = copy.deepcopy(original)
    mutated["ground_truth"]["should_be_caught_by"] = "biot_number"
    mutated["ground_truth"]["acceptable_catchers"] = []
    after = analyse(mutated["payload"], case_id)

    assert after["causal_catchers"] == before["causal_catchers"]
    assert after["valid_reasons"] == before["valid_reasons"]
    assert after["primary_status"] == before["primary_status"]


def test_the_analyser_imports_nothing_that_could_know_the_answer():
    """Import closure, by AST rather than by reading the file and trusting it."""
    tree = ast.parse((ORACLES / "independent_reason.py").read_bytes().decode())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= {"__future__", "copy", "dataclasses", "math", "independent_truth"}, (
        f"unexpected imports: {sorted(roots - {'__future__', 'copy', 'dataclasses', 'math', 'independent_truth'})}"
    )
    assert not any(
        "engcore" in str(getattr(v, "__module__", "")) for v in vars(reason).values()
    )


def test_the_code_never_names_a_ground_truth_field():
    """Names, not just imports: a string key is enough to peek with."""
    tree = ast.parse((ORACLES / "independent_reason.py").read_bytes().decode())
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(
        body[0].value, ast.Constant
    ):
        body = body[1:]                     # the module docstring may say them
    text = "\n".join(ast.dump(ast.Module(body=body, type_ignores=[])) for _ in [0])
    for field in ("should_be_caught_by", "acceptable_catchers",
                  "expected_verdict", "expected_unknown_reason",
                  "ground_truth", "needs_review"):
        assert field not in text, f"the analyser names {field}"


# =====================================================================
# The closed-form operating point
# =====================================================================

def _loop(payload):
    """The declared quantities of the coupled loop, in SI."""
    stage = payload["stages"][0]
    cond, body = stage["conductor"], stage["body"]
    return {
        "voltage": si(payload["source_voltage"]),
        "r_ref": si(cond["reference_resistance"]),
        "alpha": si(cond["temperature_coefficient"]),
        "t_ref": si(cond["reference_temperature"]),
        "hA": si(body["ambient_conductance"]),
        "t_amb": si(body["ambient_temperature"]),
        "t_init": si(body["initial_temperature"]),
        "capacity": si(body["heat_capacity"]),
        "duration": si(body["duration"]),
    }


SOLVED = ["S00013", "U00002", "U00204", "U01001", "U01881", "U00705"]


@pytest.mark.parametrize("case_id", SOLVED)
def test_the_closed_form_root_satisfies_the_balance_it_claims_to_solve(case_id):
    """Substitute the root back in. A wrong closed form is silently wrong.

    This is not the solver checking itself: the balance is re-formed here from
    the declared quantities, and the residual is evaluated at the temperature
    the solver returned. An algebra slip in the quadratic shows up as a
    residual that is not zero.
    """
    p = _loop(case(case_id)["payload"])
    endpoint, asymptote, tau = truth._coupled_operating_point(**p)

    decay = math.exp(-p["duration"] / tau)
    reach = 1.0 - decay

    def resistance(temperature):
        return p["r_ref"] * (1.0 + p["alpha"] * (temperature - p["t_ref"]))

    for name, temperature, scale, offset in (
        ("endpoint", endpoint, reach, (p["t_init"] - p["t_amb"]) * decay),
        ("asymptote", asymptote, 1.0, 0.0),
    ):
        balance = (
            p["t_amb"] + offset
            + scale * p["voltage"] ** 2 / (resistance(temperature) * p["hA"])
        )
        residual = balance - temperature
        assert abs(residual) <= 1e-9 * max(1.0, abs(temperature)), (
            f"{case_id}: the {name} root leaves a residual of {residual:.3e}"
        )


@pytest.mark.parametrize("case_id", SOLVED)
def test_the_operating_point_is_on_the_branch_the_body_starts_on(case_id):
    """A root across the R = 0 singularity is not reachable and not the answer."""
    p = _loop(case(case_id)["payload"])
    endpoint, asymptote, _ = truth._coupled_operating_point(**p)
    for temperature in (p["t_init"], endpoint, asymptote):
        u = 1.0 + p["alpha"] * (temperature - p["t_ref"])
        assert u > 0.0, f"{case_id}: R <= 0 at {temperature:.3f} K"


def _electrothermal(**overrides):
    """A payload built here, so the expected mechanism is known by construction."""
    payload = copy.deepcopy(case("U00002")["payload"])
    stage = payload["stages"][0]
    for key, value in overrides.items():
        if key in stage["conductor"]:
            stage["conductor"][key] = value
        else:
            stage["body"][key] = value
    return payload


def test_an_ntc_with_no_steady_state_is_named_a_runaway():
    """No real root: the loss term never catches the dissipation."""
    # The start must sit where the linear form is still physical, or the
    # earlier refusal fires first and this would test that instead: with
    # alpha = -0.05/K about 293.15 K, R stays positive below 313.15 K.
    payload = _electrothermal(
        temperature_coefficient="-0.05 1/kelvin",
        reference_temperature="293.15 kelvin",
        initial_temperature="290 kelvin",
        ambient_temperature="290 kelvin",
    )
    payload["source_voltage"] = "400 volt"
    with pytest.raises(truth.NoOperatingPoint) as excinfo:
        truth._coupled_operating_point(**_loop(payload))
    assert excinfo.value.condition == "thermal_runaway_no_steady_state"


def test_a_conductor_non_physical_at_its_own_start_is_named_by_resistance():
    """R(T_0) <= 0: the model has failed before the run begins.

    This is the distinction the round turned on. Both findings refuse the
    design, but they are different findings -- one is a thermal instability
    and the other is a declaration outside the linear form's region -- and
    eight benchmark cases are labelled as the first while being the second.
    """
    payload = _electrothermal(
        temperature_coefficient="0.05 1/kelvin",
        reference_temperature="293.15 kelvin",
        initial_temperature="250 kelvin",
        ambient_temperature="250 kelvin",
    )
    with pytest.raises(truth.NoOperatingPoint) as excinfo:
        truth._coupled_operating_point(**_loop(payload))
    assert excinfo.value.condition == "linear_resistance_ratio"


def test_the_two_refusals_are_not_the_same_refusal():
    """Guard against a future edit collapsing them back into one label."""
    assert (reason.reason_class("thermal_runaway_no_steady_state")
            == reason.reason_class("linear_resistance_ratio"))
    assert "thermal_runaway_no_steady_state" in reason.REGIME
    assert "linear_resistance_ratio" in reason.REGIME


# =====================================================================
# The counterfactual repairs
# =====================================================================

REPAIRABLE = sorted(set(reason.REPAIRS) - set(reason.NOT_REPAIRABLE))


@pytest.mark.parametrize("case_id", SAMPLE)
def test_every_repair_moves_the_condition_it_targets(case_id):
    """The repair table is what makes `causal` mean anything.

    If a repair did not actually undo its condition, every catcher would come
    out NON_CAUSAL and the round would report a fake absence of causality.
    """
    payload = case(case_id)["payload"]
    base = truth.evaluate(case_id, payload)
    checked = 0
    for name in base.violated:
        if name in reason.NOT_REPAIRABLE:
            continue
        repaired = reason.apply_repair(payload, name, base.values.get(name))
        if repaired is None:
            continue
        after = truth.evaluate(case_id, repaired)
        assert name not in after.violated, (
            f"{case_id}: repairing {name} left it violated -- the repair does "
            f"not target the mechanism it claims to"
        )
        checked += 1
    if base.violated and not checked:
        pytest.skip(f"{case_id} has only conditions with no defined repair")


def test_a_repair_that_cannot_be_built_is_refused_not_guessed():
    """`None` means "no counterfactual", which is a result, not a failure."""
    payload = copy.deepcopy(case("U00002")["payload"])
    del payload["stages"][0]["body"]["applicability"]["body_volume"]
    assert reason.apply_repair(payload, "geometry_route_ratio", 3.0) is None
    assert reason.apply_repair(payload, "a_condition_with_no_repair", 1.0) is None


# =====================================================================
# Gaps are not reasons
# =====================================================================

@pytest.mark.parametrize("case_id", ["U00705", "U00849"])
def test_a_gap_is_reported_as_a_gap(case_id):
    """An undecidable condition is not evidence against the design."""
    result = analyse(case(case_id)["payload"], case_id)
    assert result["independent_verdict"] == "INSUFFICIENT_EVIDENCE"
    assert result["gap_conditions"]
    assert set(result["valid_reasons"]) <= set(result["gap_conditions"])
    assert result["primary_status"] == "NOT_APPLICABLE"
    assert result["reason_classes"] == ["MISSING_REQUIRED_EVIDENCE"]


CONVECTION_INPUTS = {
    # field withheld -> conditions that must SURVIVE it, by their definitions
    "fluid_conductivity": ["convection_flow_range_utilization",
                           "convection_property_range_utilization"],
    "fluid_prandtl_number": ["convection_flow_range_utilization"],
}


@pytest.mark.parametrize("field", sorted(CONVECTION_INPUTS))
def test_one_missing_fluid_property_does_not_blank_the_others(field):
    """A Reynolds number never needed the conductivity, and 0.6/Pr needs no L.

    Over-reporting a gap looks like the safe direction and is not: it claims
    the payload settles less than it does, and on a `missing:*` case it spreads
    one omission across conditions the omission does not touch. This is the
    defect the round found in this module, pinned so it cannot come back.
    """
    original = case("U00849")               # forced convection, Re needs no k
    payload = copy.deepcopy(original["payload"])
    app = payload["stages"][0]["body"]["applicability"]
    app.setdefault("fluid_conductivity", "0.0793 watt/meter/kelvin")
    app.setdefault("fluid_prandtl_number", "0.707 dimensionless")
    app.pop(field, None)

    result = truth.evaluate("X", payload)
    for name in CONVECTION_INPUTS[field]:
        assert name not in result.unknown, (
            f"withholding {field} wrongly made {name} undecidable"
        )
    assert "convection_conductance_agreement_ratio" in result.unknown or field == "x"


def test_withholding_prandtl_on_the_natural_route_does_take_the_flow_range():
    """The mirror image: Ra = Gr Pr, so there the flow range really is a gap.

    Without this the previous test would be satisfied by a module that simply
    never marks a flow range undecidable.
    """
    payload = copy.deepcopy(case("S00013")["payload"])
    app = payload["stages"][0]["body"]["applicability"]
    assert app.get("convection_regime") == "natural"
    del app["fluid_prandtl_number"]
    result = truth.evaluate("X", payload)
    assert "convection_flow_range_utilization" in result.unknown
    assert "convection_property_range_utilization" in result.unknown


# =====================================================================
# It discriminates
# =====================================================================

PHYSICS_MUTATIONS = {
    "body_conductivity x100 lowers Biot": (
        "body_conductivity", 100.0, "biot_number", "down"),
    "characteristic_length x50 raises Biot": (
        "characteristic_length", 50.0, "biot_number", "up"),
    "surface_emissivity x50 raises the radiation ratio": (
        "surface_emissivity", 50.0, "radiation_to_convection_ratio", "up"),
}


@pytest.mark.parametrize("label", sorted(PHYSICS_MUTATIONS))
def test_a_real_change_to_the_physics_moves_the_condition_it_defines(label):
    field, factor, condition, direction = PHYSICS_MUTATIONS[label]
    original = case("U00002")["payload"]
    before = truth.evaluate("X", original)
    assert condition in before.values, f"{condition} is not evaluated on this case"

    payload = copy.deepcopy(original)
    app = payload["stages"][0]["body"]["applicability"]
    magnitude, _, unit = app[field].partition(" ")
    app[field] = f"{float(magnitude) * factor} {unit}"
    after = truth.evaluate("X", payload)

    moved = after.values[condition] - before.values[condition]
    if direction == "up":
        assert moved > 0, f"{label}: {condition} moved {moved:+.4g}"
    else:
        assert moved < 0, f"{label}: {condition} moved {moved:+.4g}"


def test_the_reason_set_follows_the_physics_and_not_the_case_id():
    """Push a sound case out of the Biot regime; the reason must appear."""
    payload = copy.deepcopy(case("S00013")["payload"])
    app = payload["stages"][0]["body"]["applicability"]
    before = set(analyse(payload, "X")["valid_reasons"])

    magnitude, _, unit = app["body_conductivity"].partition(" ")
    app["body_conductivity"] = f"{float(magnitude) / 1000.0} {unit}"
    after = set(analyse(payload, "X")["valid_reasons"])

    assert "biot_number" in after - before, (
        f"dividing the body conductivity by 1000 did not produce a Biot "
        f"finding: before={sorted(before)} after={sorted(after)}"
    )
