"""The independent case evaluator must not be able to peek, and must bite.

Two claims are load-bearing for everything the independent-truth round reports,
and neither may rest on inspection:

**NO-PEEK (P0).** The evaluator reads the payload and nothing else. Changing a
stored expected verdict, a declared catcher, a label, a reason or an acceptable
catcher must leave its output BYTE-IDENTICAL. If that ever stops holding, every
agreement figure the round produced is contaminated and must be discarded.

**IT DISCRIMINATES.** An evaluator that returned the same verdict regardless of
the physics would also agree with Forge on every case. So payload mutations --
real changes to the science -- must move the truth, and the module must be shown
to refuse rather than guess when an input is missing.

A NOTE ON HOW THE EVALUATOR WAS BUILT, because it bears on how much the
agreement figure is worth: three defects in it were found by looking at where it
disagreed with Forge, and each was then fixed on an argument that stands without
Forge (a two-route comparison with one route is vacuous, not undecidable; a
melting point below a declared ceiling is a self-contradiction between two
declarations; a missing fluid property is a gap, not an unreconstructable case).
The module is structurally independent -- it imports nothing from engcore -- but
its DEVELOPMENT was Forge-guided, and the register says so.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
ORACLES = REPO / "benchmarks" / "oracles"
CASES = REPO / "benchmarks" / "hard" / "cases_hard"


def _load():
    name = "_independent_truth_under_test"
    spec = importlib.util.spec_from_file_location(
        name, ORACLES / "independent_truth.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


truth = _load()

#: A spread of cases: sound, refused, screened, and both former false accepts.
SAMPLE = ["S00013", "U00002", "U00004", "U00005", "U00204", "U01001", "U01881"]


def case(case_id):
    return json.loads((CASES / f"{case_id}.json").read_text(encoding="utf-8"))


def evaluate(payload, case_id="X"):
    return truth.evaluate(case_id, payload).to_dict()


# =====================================================================
# PHASE C -- the no-peek guarantee
# =====================================================================

def _flip(current, options):
    """Pick a value guaranteed different from the one already stored.

    A mutation that happened to be a no-op would make the no-peek test pass
    vacuously on exactly the cases where it matters most.
    """
    return next(o for o in options if o != current)


METADATA_MUTATIONS = {
    "expected_verdict": lambda g: g.update({
        "expected_verdict": _flip(
            g["expected_verdict"],
            ["SUPPORTED", "NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE"],
        )
    }),
    "expected_verdict (other way)": lambda g: g.update({
        "expected_verdict": _flip(
            g["expected_verdict"],
            ["INSUFFICIENT_EVIDENCE", "NOT_SUPPORTED", "SUPPORTED"],
        )
    }),
    "label": lambda g: g.update({
        "label": _flip(g["label"], ["valid", "limit_exceeded", "model_inapplicable"])
    }),
    "should_be_caught_by": lambda g: g.update(
        {"should_be_caught_by": "a_condition_that_does_not_exist"}
    ),
    "reason": lambda g: g.update({"reason": "an entirely different story"}),
    "acceptable_catchers": lambda g: g.update(
        {"acceptable_catchers": ["biot_number", "melting_temperature_utilization"]}
    ),
    "expected_unknown_reason": lambda g: g.update(
        {"expected_unknown_reason": "conservative_screen"}
    ),
    "needs_review": lambda g: g.update({"needs_review": not g["needs_review"]}),
    "defect": lambda g: g.update({"defect": "something_else_entirely"}),
}


@pytest.mark.parametrize("case_id", SAMPLE)
@pytest.mark.parametrize("mutation", sorted(METADATA_MUTATIONS))
def test_no_stored_truth_field_can_move_the_independent_verdict(case_id, mutation):
    """P0. Every one of these is an answer; none may reach the evaluator."""
    original = case(case_id)
    baseline = evaluate(original["payload"], case_id)

    mutated = copy.deepcopy(original)
    METADATA_MUTATIONS[mutation](mutated["ground_truth"])
    assert mutated["ground_truth"] != original["ground_truth"], mutation

    after = evaluate(mutated["payload"], case_id)
    assert json.dumps(after, sort_keys=True) == json.dumps(
        baseline, sort_keys=True
    ), f"{case_id}: mutating {mutation} moved the independent truth"


@pytest.mark.parametrize("case_id", SAMPLE)
def test_the_evaluator_is_never_handed_anything_but_the_payload(case_id):
    """The signature is the guarantee: `evaluate(case_id, payload, system)`.

    Passing a payload stripped of every sibling key must give the same answer
    as passing the one that sat beside a full ground-truth block.
    """
    full = case(case_id)
    baseline = evaluate(full["payload"], case_id)
    bare = evaluate(copy.deepcopy(full["payload"]), case_id)
    assert json.dumps(bare, sort_keys=True) == json.dumps(
        baseline, sort_keys=True
    )


def test_the_module_imports_nothing_from_engcore():
    """Structural independence, checked by reading the source.

    Stronger than "does not call the function under test": there is no path
    from this evaluator to Forge's applicability evaluator, validity
    assessment, verdict derivation, solvers, or even its unit registry.
    """
    source = (ORACLES / "independent_truth.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert imported == {"__future__", "math", "dataclasses"}, sorted(imported)

    # ...and the loaded module's namespace holds nothing from engcore either,
    # which catches an import smuggled in at call time.
    for name, value in vars(truth).items():
        module_name = getattr(value, "__module__", "") or ""
        assert "engcore" not in module_name, (name, module_name)


def test_the_evaluator_never_names_a_stored_truth_field():
    """A defence against the subtler leak: reading ground_truth from a payload
    that happens to carry it."""
    source = (ORACLES / "independent_truth.py").read_text(encoding="utf-8")
    body = "\n".join(
        line for line in source.splitlines()
        if not line.strip().startswith("#")
    )
    # Split the docstring off; the prose legitimately discusses these names.
    _, _, code = body.partition('"""\n\nfrom __future__')
    for forbidden in (
        "ground_truth", "expected_verdict", "should_be_caught_by",
        "acceptable_catchers", "needs_review", '"label"',
    ):
        assert forbidden not in code, forbidden


# =====================================================================
# PHASE R -- physics mutations must move the truth
# =====================================================================

def _bump(payload, path, factor):
    """Scale one declared quantity, keeping its unit."""
    node = payload
    for key in path[:-1]:
        node = node[key]
    value, unit = node[path[-1]].split(None, 1)
    node[path[-1]] = f"{float(value) * factor} {unit}"


#: (label, path, factor, condition, direction). `direction` is the sign the
#: condition's value must move in, taken from its DEFINITION rather than from
#: running anything: Bi = hL/k rises with L and falls with k; the melting
#: utilisation is T_peak/T_melt, so it rises as the melting point falls; the
#: geometry ratio is L_c/(V/A_s), so it falls as the volume grows; the
#: radiation share is h_r/h, which rises with emissivity.
PHYSICS_MUTATIONS = [
    ("body conductivity down 1000x",
     ["stages", 0, "body", "applicability", "body_conductivity"], 1e-3,
     "biot_number", +1),
    ("characteristic length up 1000x",
     ["stages", 0, "body", "applicability", "characteristic_length"], 1e3,
     "biot_number", +1),
    ("surface emissivity up 30x",
     ["stages", 0, "body", "applicability", "surface_emissivity"], 30.0,
     "radiation_to_convection_ratio", +1),
    ("melting temperature down 100x",
     ["stages", 0, "body", "applicability", "melting_temperature"], 1e-2,
     "melting_temperature_utilization", +1),
    ("body volume up 100x",
     ["stages", 0, "body", "applicability", "body_volume"], 1e2,
     "geometry_route_ratio", -1),
    ("source voltage up 2x",
     ["source_voltage"], 2.0, "operating_temperature_utilization", +1),
]


@pytest.mark.parametrize(
    "label,path,factor,condition,direction",
    PHYSICS_MUTATIONS,
    ids=[m[0] for m in PHYSICS_MUTATIONS],
)
def test_a_real_change_to_the_physics_moves_the_condition_it_should(
    label, path, factor, condition, direction
):
    """The complement of no-peek: this evaluator must not be inert.

    Asserting the VALUE moves in the direction the definition predicts is the
    honest test here. Demanding a verdict flip would only work where the body
    happens to sit near that particular bound -- for S00013 radiation cannot
    dominate at any physical emissivity, which is a fact about the body rather
    than a weakness in the evaluator.
    """
    original = case("S00013")
    baseline = evaluate(original["payload"], "S00013")
    assert baseline["independent_verdict"] == "SUPPORTED", baseline
    assert condition in baseline["values"], condition

    mutated = copy.deepcopy(original["payload"])
    _bump(mutated, path, factor)
    after = evaluate(mutated, "S00013")

    before_value = baseline["values"][condition]
    after_value = after["values"].get(condition)
    assert after_value is not None, f"{label}: {condition} stopped being computed"
    assert (after_value - before_value) * direction > 0, (
        f"{label}: {condition} went {before_value:.6g} -> {after_value:.6g}, "
        f"the wrong way for its definition"
    )


def test_enough_of_those_mutations_actually_flip_the_verdict():
    """Direction is necessary; a flip somewhere proves it can still refuse."""
    original = case("S00013")
    flipped = [
        label
        for label, path, factor, _condition, _direction in PHYSICS_MUTATIONS
        if evaluate(
            _mutated_payload(original["payload"], path, factor), "S00013"
        )["independent_verdict"] != "SUPPORTED"
    ]
    assert len(flipped) >= 4, f"only {flipped} flipped"


def _mutated_payload(payload, path, factor):
    mutated = copy.deepcopy(payload)
    _bump(mutated, path, factor)
    return mutated


def test_removing_a_declaration_produces_a_gap_and_never_a_pass():
    """An omitted input must reach UNKNOWN, not be silently dropped.

    This is the semantics the whole `missing:*` corpus turns on, and an
    earlier draft of the evaluator got it wrong by skipping the condition.
    """
    original = case("S00013")
    for key in ("melting_temperature", "body_conductivity", "surface_emissivity"):
        payload = copy.deepcopy(original["payload"])
        del payload["stages"][0]["body"]["applicability"][key]
        after = evaluate(payload, "S00013")
        assert after["independent_verdict"] == "INSUFFICIENT_EVIDENCE", key
        assert any(
            after["unknown_reasons"].get(name) == "not_supplied"
            for name in after["unknown"]
        ), key


def test_an_unknown_unit_is_refused_rather_than_guessed():
    """The unit table is closed on purpose: a mis-scaled input would produce a
    confident wrong truth, which is worse than no truth."""
    payload = copy.deepcopy(case("S00013")["payload"])
    payload["source_voltage"] = "19.6 furlongs_per_fortnight"
    with pytest.raises(truth.UnresolvedInput, match="not in this evaluator"):
        truth.si(payload["source_voltage"])


# =====================================================================
# The conservative screen, reconstructed independently
# =====================================================================

def test_a_screened_condition_reports_a_gap_and_not_a_finding():
    """Under the Fourier floor the criterion observed nothing.

    Adjudicated 2026-09-09; the evaluator implements it from that decision
    rather than from Forge's code, and this pins that it did.
    """
    result = evaluate(case("U00005")["payload"], "U00005")
    assert "internal_fourier_number" in result["unknown"]
    assert result["unknown_reasons"]["internal_fourier_number"] == (
        "conservative_screen"
    )
    assert "internal_fourier_number" not in result["violated"]
    assert result["independent_verdict"] == "INSUFFICIENT_EVIDENCE"


def test_policy_dependence_is_carried_on_the_result():
    """A verdict that turns on an INTERNAL_POLICY number must say so."""
    result = evaluate(case("U01881")["payload"], "U01881")
    assert "radiation_to_convection_ratio" in result["policy_bound_ids"], result
    assert result["truth_class"] in (
        "POLICY_DEPENDENT", "MIXED_SCIENCE_AND_POLICY"
    ), result["truth_class"]
