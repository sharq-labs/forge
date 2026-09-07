"""ELECTRO-THERMAL VERTICAL PROOF — the first closed-loop execution.

Preregistration: ``docs/milestones/electrothermal-vertical-prereg.md`` (commit 81d9b9b),
written and committed before any source file on this branch was added or edited.
Test identifiers below are the preregistration's, §7 and §11.

Every predicted number in the preregistration was computed analytically, from
the equations of its §4.1, in a throwaway script importing nothing from
``engcore``. The assertions here are against those preregistered values.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import math
import pathlib
import textwrap

import pytest

from src.engcore.domains.thermal_models import lumped as lump
from src.engcore.domains.electrical import material as mat
from src.engcore.domains.electrical.dc import ElectricalDCSolver
from src.engcore.domains.electrical.dc.errors import CircuitBindingError
from src.engcore.scientific.composition import QuantityDependency
from src.engcore.scientific.errors import (
    InvalidScientificProblem,
    ScientificCoreError,
)
from src.engcore.scientific.models.definition import ValidityStatus
from src.engcore.scientific.results.provenance import ProvenanceRecord
from src.engcore.scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
)
from src.engcore.scientific.solvers.protocol import ConvergenceState
from src.engcore.scientific.units.quantity import Quantity, dimensionality
from src.engcore.systems.electrothermal import coupled as cp
from src.engcore.systems.electrothermal import resistor_body
from src.engcore.systems.electrothermal.resistor_body import (
    ElectroThermalResistor,
    run_open_loop_pass,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

KELVIN = "kelvin"
TOL = Quantity(1e-6, KELVIN)


# =====================================================================
# Declarations
# =====================================================================

def conductor(cid, r_ref, alpha, t_ref=293.15):
    return mat.TemperatureDependentConductor(
        component_id=cid,
        reference_resistance=Quantity(r_ref, "ohm"),
        temperature_coefficient=Quantity(alpha, "1/kelvin"),
        reference_temperature=Quantity(t_ref, KELVIN),
    )


def body(cid, capacity, conductance, ambient=300.0, initial=300.0, duration=120.0):
    return lump.ThermalBody(
        body_id=cid,
        heat_capacity=Quantity(capacity, "joule/kelvin"),
        ambient_conductance=Quantity(conductance, "watt/kelvin"),
        ambient_temperature=Quantity(ambient, KELVIN),
        initial_temperature=Quantity(initial, KELVIN),
        duration=Quantity(duration, "second"),
    )


def system(*stages, volts):
    return cp.CoupledElectroThermalSystem(
        stages=tuple(stages), source_voltage=Quantity(volts, "volt")
    )


#: The nominal declaration, reusing MIN-FOUNDATION-ET's numbers so the two
#: milestones are directly comparable.
NOMINAL = system(
    cp.CoupledStage(conductor("R1", 10.0, 0.00393), body("R1", 2.5, 0.05)),
    volts=5.0,
)

#: CASE C2 — a negative-TCR conductor at a non-contracting operating point.
MARGINAL = system(
    cp.CoupledStage(
        conductor("R1", 10.0, -0.004, t_ref=300.0), body("R1", 2.5, 0.04)
    ),
    volts=5.0,
)

#: CASE F — converges outside the property model's declared validity domain.
OVERHEATED = system(
    cp.CoupledStage(
        conductor("R1", 10.0, 0.00393), body("R1", 2.5, 0.04, duration=600.0)
    ),
    volts=12.0,
)

#: CASE E — two conductors in series, each with its own body.
TWO_STAGE = system(
    cp.CoupledStage(conductor("R1", 10.0, 0.00393), body("R1", 2.5, 0.05)),
    cp.CoupledStage(conductor("R2", 20.0, 0.00060), body("R2", 5.0, 0.02)),
    volts=12.0,
)


def compose(sys, *, metric=lump.TEMPERATURE_METRIC):
    problems = cp.coupled_problems(
        sys,
        {s.component_id: s.conductor.reference_resistance for s in sys.stages},
    )
    return problems, cp.coupled_dependencies(sys, problems, temperature_metric=metric)


def execute(
    sys, *, metric=lump.TEMPERATURE_METRIC, seed=300.0, budget=50,
    tolerance=TOL, run_id="et",
):
    problems, dependencies = compose(sys, metric=metric)
    plan = cp.nominal_plan(
        sys, dependencies, seed=Quantity(seed, KELVIN),
        tolerance=tolerance, max_iterations=budget,
    )
    return cp.run_fixed_point_coupling(sys, plan, run_id=run_id), problems, plan


@pytest.fixture(scope="module")
def case_a():
    return execute(NOMINAL, run_id="caseA")


@pytest.fixture(scope="module")
def case_e():
    return execute(TWO_STAGE, run_id="caseE")


def only_temperature(run):
    (value,) = run.final_values.values()
    return value.magnitude_in(KELVIN)


def _code_only(source: str) -> str:
    """The source with every string constant blanked.

    Docstrings explain a rule; they are not the rule. A scan that cannot tell
    the two apart proves nothing about what the code does.
    """
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    return ast.unparse(tree)


# =====================================================================
# GATE G0 — is the declared dependency set executable as declared?
# =====================================================================

def test_gate_g0_the_declared_cycle_has_no_execution_order():
    """Preregistered §7.1. **Predicted 0 / 3 / 0.**

    Measured, not argued: the reader is given the serialized records and asked
    for an order. It gets none, three tears are equally admissible, and no
    record supplies a seed for any of them.
    """
    problems, dependencies = compose(NOMINAL)
    ids = [p.problem_id for p in problems]

    # 1. admissible topological orders
    assert cp.execution_order(ids, dependencies) == ()
    assert len(cp.cycle_edges(ids, dependencies)) == 3

    # 2. admissible single-edge tears
    tears = [
        d
        for d in dependencies
        if cp.execution_order(ids, [e for e in dependencies if e is not d])
    ]
    assert len(tears) == 3

    # 3. seed-supplying records, per candidate tear, from conditions alone
    by_id = {p.problem_id: p for p in problems}
    seeds_from_conditions = {}
    seeds_from_parameters = {}
    for tear in tears:
        target = by_id[tear.target_problem_id]
        seeds_from_conditions[tear.name] = [
            c.variable
            for c in target.initial_conditions + target.boundary_conditions
            if c.variable == tear.target_quantity
        ]
        seeds_from_parameters[tear.name] = [
            p.name
            for p in target.parameters
            if p.name == tear.target_quantity and isinstance(p.value, Quantity)
        ]
    assert all(not v for v in seeds_from_conditions.values())

    # The one apparent seed, and why it is not one. `R:R1` carries a value only
    # because the DC domain models a computed quantity as a configured
    # parameter, and the value it carries is whatever the caller passed to
    # build the problem. A rule "tear the edge whose target already carries a
    # value" would select this edge on a modelling accident.
    supplied = [k for k, v in seeds_from_parameters.items() if v]
    assert len(supplied) == 1
    assert supplied[0].startswith(cp.DEPENDENCY_RESISTANCE)


def test_gate_g0b_the_property_state_has_no_condition_and_the_time_levels_differ():
    """Why the seed is not recoverable, stated as two facts about records."""
    problems, _ = compose(NOMINAL)
    prop = problems[1]
    assert prop.initial_conditions == ()
    assert prop.boundary_conditions == ()

    thermal = problems[2]
    (condition,) = thermal.initial_conditions
    # The thermal condition is on a DELIBERATELY different endpoint from the
    # metric the loop transports — severed by MIN-FOUNDATION-ET finding D-1.
    assert condition.variable == lump.TEMPERATURE
    assert lump.TEMPERATURE != lump.TEMPERATURE_METRIC
    # Three kelvin-valued endpoints on one problem; dimension separates none.
    levels = (
        lump.TEMPERATURE,
        lump.TEMPERATURE_METRIC,
        lump.STEADY_STATE_TEMPERATURE_METRIC,
    )
    assert len(set(levels)) == 3
    assert len({dimensionality(KELVIN)}) == 1


def test_gate_g1_no_universal_reader_of_coupling_execution_exists():
    """Preregistered §7.2. **Predicted 0.**

    The lexical hits under ``engcore/scientific`` for planner/scheduler/coupling
    vocabulary are counted, then reduced to those that survive stripping
    comments and docstrings. Every one is prose declaring the reader's absence.
    """
    root = REPO_ROOT / "src/engcore/scientific"
    words = (
        "schedul", "planner", "execution_order", "fixed_point",
        "orchestrat", "coupling", "relax",
    )
    lexical = 0
    executable = 0
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        lexical += sum(text.lower().count(w) for w in words)
        tree = ast.parse(text)
        # strip every docstring, then look for the vocabulary in real code
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                continue
            for name in (
                getattr(node, "id", None),
                getattr(node, "name", None),
                getattr(node, "attr", None),
                getattr(node, "arg", None),
            ):
                if name and any(w in str(name).lower() for w in words):
                    executable += 1
    assert lexical > 0, "the vocabulary is discussed in core"
    assert executable == 0, "core gained an executable coupling reader"


# =====================================================================
# TEST A — the loop really closes
# =====================================================================

def test_a_a_later_electrical_solve_consumes_a_temperature_updated_resistance(case_a):
    """The single thing MIN-FOUNDATION-ET did not do.

    Asserted against the **electrical result's own provenance**, not against a
    variable of the runner: iteration *n*'s circuit was built from the
    resistance iteration *n*'s property solve produced, and that resistance came
    from the temperature iteration *n-1*'s thermal solve produced.
    """
    run, problems, _ = case_a
    electrical, prop, thermal = (p.problem_id for p in problems)
    assert run.iterations_run >= 2

    seen = []
    for iteration in run.iterations:
        resistance = iteration.result_for(prop).value(mat.RESISTANCE_METRIC)
        used = iteration.result_for(electrical).provenance.inputs["R:R1"]
        assert used.magnitude_in("ohm") == pytest.approx(
            resistance.magnitude_in("ohm"), rel=1e-15
        )
        seen.append(resistance.magnitude_in("ohm"))

    # the resistance genuinely changed between solves
    assert seen[0] != seen[1]
    assert abs(seen[1] - seen[0]) / seen[0] > 0.15

    # and each iteration's temperature is the previous iteration's thermal output
    for previous, current in zip(run.iterations, run.iterations[1:]):
        produced = previous.result_for(thermal).value(lump.TEMPERATURE_METRIC)
        consumed = current.result_for(prop).provenance.inputs[mat.TEMPERATURE]
        assert consumed.magnitude_in(KELVIN) == pytest.approx(
            produced.magnitude_in(KELVIN), rel=1e-15
        )


def test_a1_case_a_reproduces_the_preregistered_trace(case_a):
    """Preregistration §10 CASE A, digit for digit."""
    run, problems, _ = case_a
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert run.iterations_run == 10

    electrical, prop, thermal = (p.problem_id for p in problems)
    predicted = [
        # R(T) ohm,      P watt,        T_end kelvin,   |dT| kelvin
        (10.269205000, 2.434463038, 344.272270673, 4.427e+01),
        (12.009105237, 2.081753761, 337.858026420, 6.414e+00),
        (11.757025438, 2.126388186, 338.669732046, 8.117e-01),
        (11.788925469, 2.120634325, 338.565094379, 1.046e-01),
    ]
    for iteration, (r, p, t, d) in zip(run.iterations, predicted):
        assert iteration.result_for(prop).value(
            mat.RESISTANCE_METRIC
        ).magnitude_in("ohm") == pytest.approx(r, rel=1e-9)
        assert iteration.result_for(electrical).value(
            "resistor_power:R1"
        ).magnitude_in("watt") == pytest.approx(p, rel=1e-9)
        assert iteration.result_for(thermal).value(
            lump.TEMPERATURE_METRIC
        ).magnitude_in(KELVIN) == pytest.approx(t, rel=1e-9)
        assert iteration.largest_iterate_change.magnitude_in(
            KELVIN
        ) == pytest.approx(d, rel=1e-3)

    assert only_temperature(run) == pytest.approx(338.577018, abs=1e-6)
    assert run.final.result_for(prop).value(
        mat.RESISTANCE_METRIC
    ).magnitude_in("ohm") == pytest.approx(11.785282, abs=1e-6)
    assert run.final.result_for(electrical).value(
        "resistor_power:R1"
    ).magnitude_in("watt") == pytest.approx(2.121290, abs=1e-6)
    assert run.final_iterate_change.magnitude_in(KELVIN) <= 1e-6


def test_a2_iteration_one_reproduces_the_previous_milestones_open_loop_pass(case_a):
    """Continuity: the closed loop's first pass **is** the open-loop pass.

    MIN-FOUNDATION-ET evaluated ``R(T1)`` and refused to feed it back. Iteration
    2 here is precisely the electrical solve it declined to perform.
    """
    run, problems, _ = case_a
    open_loop = run_open_loop_pass(
        ElectroThermalResistor(
            conductor=conductor("R1", 10.0, 0.00393),
            body=body("R1", 2.5, 0.05),
            source_voltage=Quantity(5.0, "volt"),
        ),
        run_id="continuity",
    )
    first = run.iterations[0]
    electrical, prop, thermal = (p.problem_id for p in problems)

    assert first.result_for(prop).value(mat.RESISTANCE_METRIC).magnitude_in(
        "ohm"
    ) == pytest.approx(open_loop.resistance_before.magnitude_in("ohm"), rel=1e-12)
    assert first.result_for(electrical).value(
        "resistor_power:R1"
    ).magnitude_in("watt") == pytest.approx(
        open_loop.dissipated_power.magnitude_in("watt"), rel=1e-12
    )
    assert first.result_for(thermal).value(
        lump.TEMPERATURE_METRIC
    ).magnitude_in(KELVIN) == pytest.approx(
        open_loop.temperature_after.magnitude_in(KELVIN), rel=1e-12
    )

    # the resistance the open-loop pass computed and did not use
    assert run.iterations[1].result_for(prop).value(
        mat.RESISTANCE_METRIC
    ).magnitude_in("ohm") == pytest.approx(
        open_loop.resistance_after.magnitude_in("ohm"), rel=1e-12
    )
    # ...is the one the second electrical solve consumed.
    assert run.iterations[1].result_for(electrical).provenance.inputs[
        "R:R1"
    ].magnitude_in("ohm") == pytest.approx(
        open_loop.resistance_after.magnitude_in("ohm"), rel=1e-12
    )
    assert open_loop.coupled_convergence_claimed is False


def test_a3_the_transported_endpoint_decides_the_physics():
    """One field changed, no code changed, 3.376 K of different answer.

    ``final_temperature`` and ``steady_state_temperature`` are both kelvin, both
    metrics of the same problem, and both check clean against the same
    dependency. Only the enumerated name separates them, and the converged
    physics differs.
    """
    transient, _, _ = execute(NOMINAL, run_id="ep-final")
    steady, _, _ = execute(
        NOMINAL, metric=lump.STEADY_STATE_TEMPERATURE_METRIC, run_id="ep-steady"
    )
    assert steady.iterations_run == 11
    assert only_temperature(transient) == pytest.approx(338.577018, abs=1e-6)
    assert only_temperature(steady) == pytest.approx(341.953436, abs=1e-6)
    assert abs(
        only_temperature(steady) - only_temperature(transient)
    ) == pytest.approx(3.376418, abs=1e-5)

    # both endpoints are dimensionally identical, so no check could have chosen
    (a,) = [d for d in compose(NOMINAL)[1] if d.target_quantity == mat.TEMPERATURE]
    (b,) = [
        d
        for d in compose(NOMINAL, metric=lump.STEADY_STATE_TEMPERATURE_METRIC)[1]
        if d.target_quantity == mat.TEMPERATURE
    ]
    assert a.dimension == b.dimension
    assert a.source_quantity != b.source_quantity
    problems, _ = compose(NOMINAL)
    assert a.check_against(target_problem=problems[1]) == ()
    assert b.check_against(target_problem=problems[1]) == ()


# =====================================================================
# TEST B — coupling convergence is explicit and typed
# =====================================================================

def test_b_coupling_convergence_has_its_own_type(case_a):
    run, _, _ = case_a
    assert isinstance(run.outcome, cp.CouplingOutcome)
    assert run.outcome is not ConvergenceState.CONVERGED
    assert set(cp.CouplingOutcome) == {
        cp.CouplingOutcome.CRITERION_MET,
        cp.CouplingOutcome.ITERATION_LIMIT_REACHED,
        # Added when the transfer boundary gained a second exit. Earned rather
        # than minted: it names the outcome of a test that is implemented and
        # has a definite answer, unlike the DIVERGED member the enum still
        # correctly refuses.
        cp.CouplingOutcome.TRANSFER_REFUSED,
    }
    # It is not a ConvergenceState, and no ConvergenceState member was added.
    assert {s.value for s in ConvergenceState} == {
        "not_applicable", "converged", "not_converged",
        "max_iterations", "diverged", "failed",
    }
    assert not set(cp.CouplingOutcome) & set(ConvergenceState)


def test_b2_the_outcome_lives_in_no_untyped_channel(case_a):
    """Preregistered fail condition §12.5, asserted over the serialized run."""
    run, _, plan = case_a
    payload = json.dumps(run.to_dict(), sort_keys=True)
    coupling_tolerance = plan.absolute_tolerance.magnitude_in(KELVIN)
    for iteration in run.iterations:
        for result in iteration.results:
            assert result.metadata == {} or "criterion" not in json.dumps(
                dict(result.metadata)
            )
            assert result.artifacts == ()
            assert result.data_references == ()
            # Solvers legitimately record their OWN numerical tolerances here.
            # What must not appear is the coupling criterion.
            assert coupling_tolerance not in set(
                result.provenance.tolerances.values()
            )
            for check in result.validation.checks:
                assert "coupl" not in check.name.lower()
    # The coupling criterion belongs to coupling execution and lives on the
    # plan alone: the run's own provenance records no tolerance at all.
    assert run.provenance.tolerances == {}
    assert run.provenance.metadata == {}
    # The coupling verdict appears exactly once in the whole serialized run,
    # at its top level. (``"outcome"`` as a *key* also names each
    # ValidationCheck's own pass/fail, which is a different question about a
    # different thing — which is the point.)
    assert payload.count("criterion_met") == 1
    assert run.to_dict()["outcome"] == "criterion_met"
    assert all(
        "criterion_met" not in json.dumps(r.to_dict())
        for i in run.iterations
        for r in i.results
    )


def test_b3_the_outcome_is_not_computed_from_the_participants(case_a):
    """Every sub-solve reports success in a converged run *and* in one that is not.

    So the participants' own convergence carries no information about the
    coupled outcome, in either direction.
    """
    converged, _, _ = case_a
    stalled, _, _ = execute(NOMINAL, budget=2, run_id="stalled")

    def states(run):
        return {r.convergence for i in run.iterations for r in i.results}

    assert states(converged) == states(stalled) == {
        ConvergenceState.CONVERGED, ConvergenceState.NOT_APPLICABLE
    }
    assert converged.outcome is not stalled.outcome
    assert all(r.is_usable for i in stalled.iterations for r in i.results)


# =====================================================================
# TEST C — solver convergence is not coupling convergence
# =====================================================================

def test_c1_the_iteration_budget_stops_a_run_whose_sub_solves_all_succeeded():
    """Preregistration §10 CASE C1."""
    run, _, _ = execute(NOMINAL, budget=2, run_id="caseC1")
    assert run.outcome is cp.CouplingOutcome.ITERATION_LIMIT_REACHED
    assert run.criterion_met is False
    assert run.iterations_run == 2
    assert run.final_iterate_change.magnitude_in(KELVIN) == pytest.approx(
        6.414244, abs=1e-5
    )
    assert all(
        r.convergence.value in ("converged", "not_applicable")
        for i in run.iterations
        for r in i.results
    )
    assert all(
        r.validation.status is not ValidationOutcome.FAIL
        for i in run.iterations
        for r in i.results
    )


def test_c2_a_non_contracting_configuration_does_not_converge_on_legitimate_physics():
    """Preregistration §10 CASE C2. `|g'| = 1` exactly at the fixed point.

    A negative-TCR conductor at its double root. Nothing is capped artificially:
    the iterate creeps as ``O(1/n)`` and the change decays as ``O(1/n²)``, so no
    reachable budget converges it. Every iterate stays inside the property
    model's declared validity domain and every resistance stays positive.
    """
    run, problems, _ = execute(
        MARGINAL, metric=lump.STEADY_STATE_TEMPERATURE_METRIC,
        budget=50, run_id="caseC2",
    )
    assert run.outcome is cp.CouplingOutcome.ITERATION_LIMIT_REACHED
    assert run.iterations_run == 50
    assert run.final_iterate_change.magnitude_in(KELVIN) == pytest.approx(
        4.901961e-02, rel=1e-4
    )

    prop = problems[1].problem_id
    resistances = [
        i.result_for(prop).value(mat.RESISTANCE_METRIC).magnitude_in("ohm")
        for i in run.iterations
    ]
    assert min(resistances) > 0.0
    assert min(resistances) == pytest.approx(5.1, abs=1e-9)

    temperatures = [
        i.result_for(problems[2].problem_id)
        .value(lump.STEADY_STATE_TEMPERATURE_METRIC)
        .magnitude_in(KELVIN)
        for i in run.iterations
    ]
    assert max(temperatures) < 450.0  # inside the declared validity domain
    for temperature in temperatures:
        assessment = mat.assess_resistance_validity(
            problems[1], Quantity(temperature, KELVIN)
        )
        assert assessment.status is not ValidityStatus.OUTSIDE_VALIDATED_DOMAIN

    # every sub-solve succeeded in all fifty iterations
    assert {r.convergence for i in run.iterations for r in i.results} == {
        ConvergenceState.CONVERGED, ConvergenceState.NOT_APPLICABLE
    }
    # the changes are monotonically shrinking and still nowhere near tolerance
    changes = [c.magnitude_in(KELVIN) for c in run.iterate_changes]
    assert changes == sorted(changes, reverse=True)
    assert changes[-1] > 1e6 * 1e-6 * 1e-2


# =====================================================================
# TEST D — scientific validity stays separate
# =====================================================================

def test_d_a_converged_coupling_does_not_make_the_model_valid():
    """Preregistration §10 CASE F. Three verdicts, one run, none overwriting another."""
    run, problems, _ = execute(OVERHEATED, run_id="caseF")
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert run.iterations_run == 25
    assert only_temperature(run) == pytest.approx(498.994793, abs=1e-6)

    # 1. coupling converged
    assert run.criterion_met is True
    # 2. every sub-solve succeeded and passed its own checks
    for iteration in run.iterations:
        for result in iteration.results:
            assert result.validation.status is not ValidationOutcome.FAIL
    # 3. and the model is outside the domain it declares itself valid in
    assessment = mat.assess_resistance_validity(
        problems[1], Quantity(only_temperature(run), KELVIN)
    )
    assert assessment.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert mat.TEMPERATURE in assessment.violated

    # The coupling outcome upgraded nothing. ANALYTICALLY_VERIFIED does appear
    # in this run, and the assertion below is what says it was not the coupling
    # that put it there: it is attached to one per-solve check, the lumped
    # solver's comparison against its independent series reference, which runs
    # identically whether the fixed point converges or not. It is verification
    # of a closed form against the equation, and it leaves verdict 3 above
    # exactly where it was — the material model is still outside its domain.
    levels = {
        level
        for iteration in run.iterations
        for result in iteration.results
        for level in result.attained_levels
    }
    assert ValidationLevel.EXPERIMENTALLY_VALIDATED not in levels
    awarding = {
        check.name
        for iteration in run.iterations
        for result in iteration.results
        for check in result.validation.checks
        if check.passed
        and check.establishes is ValidationLevel.ANALYTICALLY_VERIFIED
    }
    assert awarding == {"analytic_reference_agreement"}


# =====================================================================
# TEST E — provenance
# =====================================================================

def test_e_provenance_preserves_model_realization_solver(case_a):
    run, _, _ = case_a
    bindings = run.provenance.bindings
    assert len(bindings) >= 5
    assert len(run.provenance.solvers) == 3
    assert len(run.provenance.realizations) == 2

    # the two realization-bearing bindings name the right solvers
    assert run.provenance.solvers_for_realization(
        mat.LINEAR_TCR_REALIZATION.realization_id
    ) == (mat.ResistancePropertySolver().identity,)
    assert run.provenance.solvers_for_realization(
        lump.LUMPED_CLOSED_FORM_REALIZATION.realization_id
    ) == (lump.LumpedThermalSolver().identity,)

    # the electrical models carry a solver and, honestly, no realization
    electrical = run.provenance.bindings_for_model("electrical.dc.kcl")
    assert electrical
    assert all(b.realization is None for b in electrical)

    # association is structural: reordering states the same thing
    reordered = ProvenanceRecord(
        run_id=run.provenance.run_id, bindings=tuple(reversed(bindings))
    )
    assert reordered.bindings == bindings


def test_e2_every_iteration_result_is_individually_attributable(case_a):
    run, problems, _ = case_a
    for iteration in run.iterations:
        assert len(iteration.results) == len(problems)
        for result in iteration.results:
            assert isinstance(result.provenance, ProvenanceRecord)
            assert result.provenance.run_id
            assert result.solver is not None
            assert result.problem_id in {p.problem_id for p in problems}
        ids = [r.provenance.run_id for r in iteration.results]
        assert len(set(ids)) == len(ids)


# =====================================================================
# TEST F — the feedback cycle is representable and traversable
# =====================================================================

def test_f_both_directions_are_present_and_the_cycle_closes_by_traversal():
    problems, dependencies = compose(NOMINAL)
    electrical, prop, thermal = (p.problem_id for p in problems)

    edges = {(d.source_problem_id, d.target_problem_id) for d in dependencies}
    assert (electrical, thermal) in edges          # electrical -> thermal
    assert (thermal, prop) in edges                # thermal -> ...
    assert (prop, electrical) in edges             # ... -> electrical

    # walk it without parsing a single name
    node, visited = electrical, []
    outgoing = {d.source_problem_id: d.target_problem_id for d in dependencies}
    for _ in range(len(dependencies)):
        visited.append(node)
        node = outgoing[node]
    assert node == electrical
    assert set(visited) == {electrical, prop, thermal}


# =====================================================================
# TEST G — dimensional incompatibility is refused before execution
# =====================================================================

def test_g_a_dimensionally_wrong_edge_is_refused_before_the_first_iteration():
    """CASE D-i: volts declared as the source of a watt-valued heat input."""
    problems, dependencies = compose(NOMINAL)
    broken = QuantityDependency(
        source_problem_id=problems[0].problem_id,
        source_quantity="V:n0",
        target_problem_id=problems[2].problem_id,
        target_quantity=lump.HEAT_INPUT,
        unit_exemplar="volt",
        name="wrong-dimension",
    )
    # Replaces the correct heat edge rather than joining it: two edges into one
    # endpoint is a different refusal (test_h4b), and this case is about the
    # dimension.
    kept = tuple(d for d in dependencies if d.target_quantity != lump.HEAT_INPUT)
    plan = cp.FixedPointCouplingPlan(
        plan_id="broken-dimension",
        dependencies=kept + (broken,),
        torn=cp.nominal_plan(
            NOMINAL, dependencies, seed=Quantity(300.0, KELVIN)
        ).torn,
        absolute_tolerance=TOL,
        max_iterations=5,
    )
    issues = plan.check_against(problems)
    assert issues and any("wrong_dimension" in i for i in issues)
    with pytest.raises(InvalidScientificProblem):
        cp.run_fixed_point_coupling(NOMINAL, plan, run_id="broken")


def test_g2_an_undeclared_quantity_is_refused_before_the_first_iteration():
    """CASE D-ii."""
    problems, dependencies = compose(NOMINAL)
    broken = QuantityDependency(
        source_problem_id=problems[0].problem_id,
        source_quantity="resistor_power:R1",
        target_problem_id=problems[2].problem_id,
        target_quantity="heat_flux",
        unit_exemplar=lump.POWER_UNIT,
        name="undeclared-target",
    )
    plan = cp.FixedPointCouplingPlan(
        plan_id="broken-name",
        dependencies=tuple(dependencies) + (broken,),
        torn=cp.nominal_plan(
            NOMINAL, dependencies, seed=Quantity(300.0, KELVIN)
        ).torn,
        absolute_tolerance=TOL,
        max_iterations=5,
    )
    issues = plan.check_against(problems)
    assert issues and any("missing" in i for i in issues)
    with pytest.raises(InvalidScientificProblem):
        cp.run_fixed_point_coupling(NOMINAL, plan, run_id="broken2")


def test_g3_a_tolerance_of_the_wrong_dimension_is_refused_at_construction():
    """CASE D-iii, and the executed justification for a typed tolerance.

    A ``float`` tolerance could not be checked at all.
    """
    _, dependencies = compose(NOMINAL)
    with pytest.raises(InvalidScientificProblem, match="tolerance"):
        cp.nominal_plan(
            NOMINAL, dependencies, seed=Quantity(300.0, KELVIN),
            tolerance=Quantity(1e-6, "watt"),
        )


def test_g4_torn_edges_of_mixed_dimension_are_refused_rather_than_normalized():
    """CASE D-iv. One scalar tolerance cannot serve two dimensions.

    No record states a normalization between them, so the plan refuses instead
    of inventing one. This is the measured boundary of the single-scalar
    criterion, not a limitation hidden in prose.
    """
    problems, dependencies = compose(NOMINAL)
    temperature_edge = next(
        d for d in dependencies if d.target_quantity == mat.TEMPERATURE
    )
    power_edge = next(
        d for d in dependencies if d.target_quantity == lump.HEAT_INPUT
    )
    with pytest.raises(InvalidScientificProblem, match="different"):
        cp.FixedPointCouplingPlan(
            plan_id="mixed",
            dependencies=dependencies,
            torn=(
                cp.TornEndpoint(temperature_edge, Quantity(300.0, KELVIN)),
                cp.TornEndpoint(power_edge, Quantity(2.0, "watt")),
            ),
            absolute_tolerance=TOL,
            max_iterations=5,
        )


def test_g5_a_seed_of_the_wrong_dimension_is_refused():
    _, dependencies = compose(NOMINAL)
    edge = next(d for d in dependencies if d.target_quantity == mat.TEMPERATURE)
    with pytest.raises(InvalidScientificProblem, match="seed"):
        cp.TornEndpoint(edge, Quantity(300.0, "watt"))
    with pytest.raises(InvalidScientificProblem, match="Quantity"):
        cp.TornEndpoint(edge, 300.0)


def test_g6_an_uncut_cycle_and_an_unknown_tear_are_both_refused():
    problems, dependencies = compose(NOMINAL)
    with pytest.raises(InvalidScientificProblem, match="cut at least one"):
        cp.FixedPointCouplingPlan(
            plan_id="uncut", dependencies=dependencies, torn=(),
            absolute_tolerance=TOL, max_iterations=5,
        )
    foreign = QuantityDependency(
        source_problem_id="a", source_quantity="x",
        target_problem_id="b", target_quantity="y", unit_exemplar=KELVIN,
    )
    with pytest.raises(InvalidScientificProblem, match="not one of"):
        cp.FixedPointCouplingPlan(
            plan_id="foreign", dependencies=dependencies,
            torn=(cp.TornEndpoint(foreign, Quantity(1.0, KELVIN)),),
            absolute_tolerance=TOL, max_iterations=5,
        )


# =====================================================================
# TEST H — multiplicity
# =====================================================================

def test_h_two_stages_converge_and_nothing_aliases(case_e):
    """Preregistration §10 CASE E."""
    run, problems, _ = case_e
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert run.iterations_run == 8

    values = {k: v.magnitude_in(KELVIN) for k, v in run.final_values.items()}
    assert values[("resistance-tcr-R1", mat.TEMPERATURE)] == pytest.approx(
        328.898146, abs=1e-6
    )
    assert values[("resistance-tcr-R2", mat.TEMPERATURE)] == pytest.approx(
        355.089513, abs=1e-6
    )

    final = run.final
    assert final.result_for("resistance-tcr-R1").value(
        mat.RESISTANCE_METRIC
    ).magnitude_in("ohm") == pytest.approx(11.404902, abs=1e-6)
    assert final.result_for("resistance-tcr-R2").value(
        mat.RESISTANCE_METRIC
    ).magnitude_in("ohm") == pytest.approx(20.743274, abs=1e-6)

    electrical = final.result_for(problems[0].problem_id)
    assert electrical.value("resistor_power:R1").magnitude_in(
        "watt"
    ) == pytest.approx(1.589064, abs=1e-6)
    assert electrical.value("resistor_power:R2").magnitude_in(
        "watt"
    ) == pytest.approx(2.890195, abs=1e-6)
    assert electrical.value("source_current:V1").magnitude_in(
        "ampere"
    ) == pytest.approx(-0.373271562, abs=1e-9)


def test_h2_one_problem_carries_both_instances_and_the_endpoints_stay_distinct(case_e):
    """The identity question `MIN-FOUNDATION-ET` could not ask at arity 1.

    The electrical domain packs N resistors into **one** problem and separates
    them by embedding the component id in the quantity name. The dependency
    record never parses that name — it references an enumerated one — and the
    endpoints stay distinct because the *domain* names per instance.
    """
    run, problems, _ = case_e
    electrical = problems[0]
    names = {p.name for p in electrical.parameters}
    assert {"R:R1", "R:R2"} <= names

    metrics = run.final.result_for(electrical.problem_id).values
    assert {"resistor_power:R1", "resistor_power:R2"} <= set(metrics)

    _, dependencies = compose(TWO_STAGE)
    assert len(dependencies) == 6
    endpoints = {
        (d.target_problem_id, d.target_quantity) for d in dependencies
    }
    sources = {(d.source_problem_id, d.source_quantity) for d in dependencies}
    assert len(endpoints) == 6 and len(sources) == 6

    # the two stages' cycles are genuinely coupled: they share one problem
    assert len({d.target_problem_id for d in dependencies}) == 5
    assert sum(
        1 for d in dependencies if d.target_problem_id == electrical.problem_id
    ) == 2

    # and every dependency binds cleanly against the records it names
    by_id = {p.problem_id: p for p in problems}
    for dependency in dependencies:
        assert dependency.check_against(
            target_problem=by_id[dependency.target_problem_id]
        ) == ()


def test_h3_two_stages_sharing_a_component_id_are_refused():
    """Aliasing is refused at declaration, not discovered in the numbers."""
    with pytest.raises(InvalidScientificProblem, match="duplicate component id"):
        system(
            cp.CoupledStage(conductor("R1", 10.0, 0.00393), body("R1", 2.5, 0.05)),
            cp.CoupledStage(conductor("R1", 20.0, 0.00060), body("R1", 5.0, 0.02)),
            volts=12.0,
        )
    with pytest.raises(InvalidScientificProblem, match="share an id"):
        cp.CoupledStage(conductor("R1", 10.0, 0.00393), body("B1", 2.5, 0.05))


def test_h4_fan_in_remains_representable_unreported_and_uncombined():
    """The gap `MIN-FOUNDATION-ET` measured, re-measured and still not filled.

    Two sources on one target check clean at the **record** level, and no record
    states sum, override or split. A combination rule invented from one consumer
    would be a coupling engine decided on no evidence.
    """
    problems, dependencies = compose(TWO_STAGE)
    by_id = {p.problem_id: p for p in problems}
    thermal_one = "thermal-lumped-R1"
    fan_in = QuantityDependency(
        source_problem_id=problems[0].problem_id,
        source_quantity="resistor_power:R2",
        target_problem_id=thermal_one,
        target_quantity=lump.HEAT_INPUT,
        unit_exemplar=lump.POWER_UNIT,
        name="second-source-on-one-body",
    )
    assert fan_in.check_against(target_problem=by_id[thermal_one]) == ()
    existing = next(
        d
        for d in dependencies
        if d.target_problem_id == thermal_one
        and d.target_quantity == lump.HEAT_INPUT
    )
    assert existing.check_against(target_problem=by_id[thermal_one]) == ()
    # two records, one target, both valid, and nothing anywhere combines them
    assert (existing.target_problem_id, existing.target_quantity) == (
        fan_in.target_problem_id, fan_in.target_quantity
    )
    payload = json.dumps([existing.to_dict(), fan_in.to_dict()])
    for word in ("sum", "override", "split", "combine", "accumulate"):
        assert word not in payload.lower()


def test_h4b_a_plan_refuses_fan_in_rather_than_resolving_it_by_declaration_order():
    """The falsifier's F-1, closed before commit.

    An earlier form of the loop keyed transported values by ``target_quantity``
    in a dict, so two edges into one endpoint resolved silently to whichever was
    declared last — a combination rule invented from one consumer and hidden in
    an insertion order, on a run that still reported ``CRITERION_MET``. It was
    invisible to every scan in this file because it contains no domain word.

    The gap stays measured and unfilled (``test_h4``); the plan simply refuses to
    fill it by accident.
    """
    problems, dependencies = compose(TWO_STAGE)
    fan_in = QuantityDependency(
        source_problem_id=problems[0].problem_id,
        source_quantity="resistor_power:R2",
        target_problem_id="thermal-lumped-R1",
        target_quantity=lump.HEAT_INPUT,
        unit_exemplar=lump.POWER_UNIT,
        name="second-source-on-one-body",
    )
    torn = cp.nominal_plan(
        TWO_STAGE, dependencies, seed=Quantity(300.0, KELVIN)
    ).torn
    with pytest.raises(InvalidScientificProblem, match="more than one"):
        cp.FixedPointCouplingPlan(
            plan_id="fan-in",
            dependencies=tuple(dependencies) + (fan_in,),
            torn=torn,
            absolute_tolerance=TOL,
            max_iterations=5,
        )
    # and the same refusal for two seeds on one endpoint
    temperature_edge = next(
        d for d in dependencies if d.target_quantity == mat.TEMPERATURE
    )
    with pytest.raises(InvalidScientificProblem, match="more than one"):
        cp.FixedPointCouplingPlan(
            plan_id="double-seed",
            dependencies=dependencies,
            torn=(
                cp.TornEndpoint(temperature_edge, Quantity(300.0, KELVIN)),
                cp.TornEndpoint(temperature_edge, Quantity(310.0, KELVIN)),
            ),
            absolute_tolerance=TOL,
            max_iterations=5,
        )


# =====================================================================
# Falsifier corrections, closed before commit
# =====================================================================

def test_x1_cycle_edges_reports_only_the_cyclic_core():
    """Falsifier F-16: an exported reader that returned a false statement.

    The earlier form asked :func:`execution_order` for its settled set — which
    that function discards whenever no order exists — so on any cyclic graph the
    settled set was empty and **every** edge was reported as cyclic. On this
    milestone's own pure 3-cycle that was indistinguishable from the right
    answer; on a graph with an acyclic feeder it was wrong.
    """
    def edge(a, b):
        return QuantityDependency(
            source_problem_id=a, source_quantity="x",
            target_problem_id=b, target_quantity="y", unit_exemplar=KELVIN,
        )

    # the milestone's own graph: a pure 3-cycle, every edge on it
    problems, dependencies = compose(NOMINAL)
    ids = [p.problem_id for p in problems]
    assert len(cp.cycle_edges(ids, dependencies)) == 3

    # A feeds B, B and C cycle. A->B is NOT on a cycle.
    nodes = ["A", "B", "C"]
    graph = (edge("A", "B"), edge("B", "C"), edge("C", "B"))
    core = cp.cycle_edges(nodes, graph)
    assert {(d.source_problem_id, d.target_problem_id) for d in core} == {
        ("B", "C"), ("C", "B")
    }

    # C also feeds a sink D, which is likewise not on the cycle
    nodes = ["A", "B", "C", "D"]
    graph = (edge("A", "B"), edge("B", "C"), edge("C", "B"), edge("C", "D"))
    core = cp.cycle_edges(nodes, graph)
    assert {(d.source_problem_id, d.target_problem_id) for d in core} == {
        ("B", "C"), ("C", "B")
    }

    # a genuinely acyclic graph has no cyclic core at all
    assert cp.cycle_edges(["A", "B"], (edge("A", "B"),)) == ()


def test_x2_one_notion_of_edge_identity_is_used_everywhere():
    """Falsifier F-9: torn membership and ``uncut`` disagreed.

    Membership was tested by whole-record equality and ``uncut`` by a four-field
    quad, so two records differing only in ``unit_exemplar`` were distinct for
    one purpose and identical for the other. `MIN-FOUNDATION-ET` predicted this
    as known unknown 6; this is its first executed instance.
    """
    _, dependencies = compose(NOMINAL)
    edge = next(d for d in dependencies if d.target_quantity == mat.TEMPERATURE)
    twin = QuantityDependency(
        source_problem_id=edge.source_problem_id,
        source_quantity=edge.source_quantity,
        target_problem_id=edge.target_problem_id,
        target_quantity=edge.target_quantity,
        unit_exemplar="rankine",          # same edge, different exemplar
        name="near-duplicate",
    )
    assert cp.edge_key(twin) == cp.edge_key(edge)
    assert twin != edge
    # the near-duplicate is now caught as a second edge into one endpoint
    with pytest.raises(InvalidScientificProblem, match="more than one"):
        cp.FixedPointCouplingPlan(
            plan_id="near-duplicate",
            dependencies=tuple(dependencies) + (twin,),
            torn=(cp.TornEndpoint(edge, Quantity(300.0, KELVIN)),),
            absolute_tolerance=TOL,
            max_iterations=5,
        )


def test_x3_the_loop_verifies_what_its_executors_returned():
    """Falsifier F-4: the one place that composes results had no pairing guard.

    Every domain in this repository has one — ``verify_problem_matches_circuit``,
    ``verify_problem_matches_body``, ``verify_problem_matches_conductor``. The
    next milestone replaces a participant with an external provider, which is
    the producer most likely to return a result carrying its own identity.
    """
    problems, dependencies = compose(NOMINAL)
    plan = cp.nominal_plan(
        NOMINAL, dependencies, seed=Quantity(300.0, KELVIN), max_iterations=3
    )
    honest = cp._executors(NOMINAL, problems)

    # 1. a missing executor is refused before the first sweep
    with pytest.raises(InvalidScientificProblem, match="no executor"):
        cp.run_fixed_point(
            problems, {k: v for k, v in list(honest.items())[:1]}, plan,
            run_id="uncovered", software_version="test",
        )

    # 2. a duplicated problem id is refused
    with pytest.raises(InvalidScientificProblem, match="duplicate problem id"):
        cp.run_fixed_point(
            tuple(problems) + (problems[1],), honest, plan,
            run_id="dupe", software_version="test",
        )

    # 3. a result attributed to the wrong problem is refused
    target = problems[1].problem_id
    liar = dict(honest)
    liar[target] = lambda inputs, run_id: dataclasses.replace(
        honest[target](inputs, run_id), problem_id="somewhere-else"
    )
    with pytest.raises(InvalidScientificProblem, match="attributed to"):
        cp.run_fixed_point(
            problems, liar, plan, run_id="liar", software_version="test",
        )


def test_x4_seeding_over_a_declared_condition_is_refused():
    """Falsifier F-17: the seed would override the condition — that is time marching."""
    problems, dependencies = compose(NOMINAL)
    thermal = next(p for p in problems if p.problem_id == "thermal-lumped-R1")
    # an edge onto the thermal problem's own t0 STATE, which its initial
    # condition already determines
    onto_state = QuantityDependency(
        source_problem_id="thermal-lumped-R1",
        source_quantity=lump.TEMPERATURE_METRIC,
        target_problem_id=thermal.problem_id,
        target_quantity=lump.TEMPERATURE,
        unit_exemplar=KELVIN,
        name="time-marching",
    )
    plan = cp.FixedPointCouplingPlan(
        plan_id="marcher",
        dependencies=(onto_state,),
        torn=(cp.TornEndpoint(onto_state, Quantity(300.0, KELVIN)),),
        absolute_tolerance=TOL,
        max_iterations=3,
    )
    issues = plan.check_against(problems)
    assert any("seeded_over_condition" in i for i in issues)
    with pytest.raises(InvalidScientificProblem, match="time marching"):
        cp.run_fixed_point(
            problems, cp._executors(NOMINAL, problems), plan,
            run_id="marcher", software_version="test",
        )


def test_x5_run_provenance_unions_every_iteration_not_only_the_last(case_a):
    """Falsifier F-7: a last-iteration-only record can under-claim.

    For this consumer every sweep binds the same participants, so the two agree.
    The union is asserted because the function is generic and an executor that
    changed realization mid-run would otherwise leave those bindings out.
    """
    run, _, _ = case_a
    from_all = set()
    for iteration in run.iterations:
        for result in iteration.results:
            from_all |= {b.key for b in result.provenance.bindings}
    assert from_all <= {b.key for b in run.provenance.bindings}


def test_x6_an_unsupplied_input_is_reported_but_cannot_be_refused():
    """Falsifier F-5, answered honestly rather than papered over.

    Prereg §5 promised that an unbindable dependency is refused before the first
    iteration. An **under-declared** composition is a different case and is
    **not** records-refusable: core's own ``externally_imposed`` cannot tell an
    ambient legitimately imposed by the environment from a heat source someone
    forgot. Both read identically. So the plan reports and the caller decides.
    """
    problems, dependencies = compose(NOMINAL)
    complete = cp.nominal_plan(
        NOMINAL, dependencies, seed=Quantity(300.0, KELVIN)
    )
    # the correct composition still has one unsupplied input, and it is right
    assert {q for _, q, _ in complete.unsupplied(problems)} == {
        lump.AMBIENT_TEMPERATURE
    }

    under = cp.FixedPointCouplingPlan(
        plan_id="under-declared",
        dependencies=tuple(
            d for d in dependencies if d.target_quantity != lump.HEAT_INPUT
        ),
        torn=complete.torn,
        absolute_tolerance=TOL,
        max_iterations=3,
    )
    # the information IS available before execution...
    assert {q for _, q, _ in under.unsupplied(problems)} == {
        lump.AMBIENT_TEMPERATURE, lump.HEAT_INPUT
    }
    # ...but the two are indistinguishable to any records-only rule, so nothing
    # refuses it and the executor is where it fails.
    assert under.check_against(problems) == ()


def test_x7_a_coupled_run_refuses_the_states_its_siblings_refuse(case_a):
    """Falsifier F-15: ``CoupledRun`` validated less than every record beside it."""
    run, _, plan = case_a
    with pytest.raises(InvalidScientificProblem, match="no iterations"):
        cp.CoupledRun(
            plan=plan, outcome=cp.CouplingOutcome.CRITERION_MET,
            iterations=(), final_values={}, provenance=run.provenance,
        )
    with pytest.raises(InvalidScientificProblem, match="ProvenanceRecord"):
        cp.CoupledRun(
            plan=plan, outcome=cp.CouplingOutcome.CRITERION_MET,
            iterations=run.iterations, final_values={}, provenance=None,
        )
    with pytest.raises(InvalidScientificProblem, match="CoupledIteration"):
        cp.CoupledRun(
            plan=plan, outcome=cp.CouplingOutcome.CRITERION_MET,
            iterations=("not an iteration",), final_values={},
            provenance=run.provenance,
        )
    with pytest.raises(InvalidScientificProblem, match="Quantity"):
        cp.CoupledRun(
            plan=plan, outcome=cp.CouplingOutcome.CRITERION_MET,
            iterations=run.iterations, final_values={("a", "b"): 1.0},
            provenance=run.provenance,
        )


def test_x8_the_final_values_key_is_structural_and_the_name_is_honest(case_a):
    """Falsifier F-2 and F-3, closed before commit.

    The field was ``converged_values`` keyed by ``f"{problem}::{quantity}"``.
    Both problem ids and quantity names already contain colons, so the key had
    to be parsed to be read; and the field is populated identically on both exit
    paths, so on a budget-exhausted run it named an unconverged number
    *converged* — one name meaning two things, the defect `MIN-FOUNDATION-ET`
    caught pre-commit as D-1.
    """
    run, _, _ = case_a
    stalled, _, _ = execute(NOMINAL, budget=2, run_id="x8")

    for key in run.final_values:
        assert isinstance(key, tuple) and len(key) == 2
    assert not hasattr(run, "converged_values")

    # the honest name survives a run that did not converge: this value sits
    # 0.72 K from the fixed point and its own last step moved 6.4 K, six orders
    # above the criterion it never met.
    assert stalled.outcome is cp.CouplingOutcome.ITERATION_LIMIT_REACHED
    (value,) = stalled.final_values.values()
    assert value.magnitude_in(KELVIN) != pytest.approx(338.577018, abs=1e-6)
    assert stalled.final_iterate_change.magnitude_in(KELVIN) > 6.0
    assert stalled.criterion_met is False

    # and the serialized form carries the endpoint without joining it
    payload = run.to_dict()
    assert "converged_values" not in payload
    for entry in payload["final_values"]:
        assert set(entry) == {"problem_id", "quantity", "value"}
    assert cp.CoupledRun.from_dict(payload).final_values == run.final_values

    # the one composite key that remains is in frozen core and is documented
    assert any("::" in k for k in run.provenance.inputs)


# =====================================================================
# TEST I — no domain leakage, in either direction
# =====================================================================

def test_i_universal_core_gained_nothing():
    """`ET-VERTICAL` adds no file and no export under ``engcore/scientific``."""
    from src.engcore.scientific import composition

    assert set(composition.__all__) == {
        "QUANTITY_DEPENDENCY_SCHEMA",
        "QuantityDependency",
        # Added by the core round: the *realization* of a dependency -- the
        # value that crossed, the record it came from, the instant it was read
        # at. It is a second record in this package, not a twelfth candidate
        # abstraction: no system, component, port, connector, material or mesh
        # type was created, which is what the loop above still asserts.
        "QUANTITY_TRANSFER_SCHEMA",
        "QuantityTransfer",
        "externally_imposed",
        "require_agreeing_transfers",
        "unresolved_inputs",
    }
    package = REPO_ROOT / "src/engcore/scientific/composition"
    assert sorted(
        p.name for p in package.rglob("*.py") if "__pycache__" not in p.parts
    ) == ["__init__.py", "dependency.py", "transfer.py"]

    for path in (REPO_ROOT / "src/engcore/scientific").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in (
            '"electrical"', "'electrical'", '"thermal"', "'thermal'",
            "domain ==", "domain in ", ".domain ==",
            "resistor", "joule", "conductor", "electrothermal",
        ):
            assert pattern not in text, f"{pattern!r} leaked into {path.name}"


def test_i2_the_new_module_uses_published_contracts_only():
    """The reverse leak: does the pack reach into core internals?

    Every ``engcore.scientific`` name it imports must be one the core package
    publishes in its own ``__all__``.
    """
    import src.engcore.scientific as core

    source = pathlib.Path(inspect.getfile(cp)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    published = set(core.__all__)
    imported: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if "scientific" in node.module or node.level >= 3:
                for alias in node.names:
                    imported.append((node.module or "", alias.name))
    scientific = [
        name
        for module, name in imported
        if "scientific" in module and not name.startswith("_")
    ]
    assert scientific, "the module does import core contracts"
    unpublished = sorted(set(n for n in scientific if n not in published))
    # Exactly four, and each is a serialization or units utility the sibling
    # domain packs already use. Everything else the pack imports from core is
    # in `engcore.scientific.__all__` — the published surface.
    assert unpublished == [
        "registry", "require_schema", "require_unit", "schema_string"
    ], unpublished


def test_i3_the_coupling_records_carry_no_domain_vocabulary(case_a):
    """H0(B): does the machinery secretly know it is electro-thermal?

    Asserted over the serialized **plan**, which is the record that makes a
    cyclic composition executable. It names problems and quantities the
    composition enumerated, and nothing else.
    """
    _, _, plan = case_a

    # The claim is precise: the ITERATION and the GRAPH READERS contain no
    # domain branch. The pack's own declaration types legitimately name the
    # domain classes they validate — that is what a system pack is for, and
    # asserting otherwise would be asserting the wrong thing.
    for function in (
        cp.run_fixed_point, cp.execution_order, cp.cycle_edges,
        cp.is_ratio_scale,
    ):
        tree = ast.parse(_code_only(inspect.getsource(function)))
        rendered = ast.dump(tree).lower()
        for word in ("electrical", "thermal", "joule", "resistor",
                     "kelvin", "watt", "ohm", "temperature", "heat"):
            assert word not in rendered, f"{word!r} in {function.__name__}"
        assert not [
            n for n in ast.walk(tree)
            if isinstance(n, (ast.If, ast.IfExp))
            and any(
                w in ast.dump(n.test).lower()
                for w in ("electrical", "thermal", "joule", "resistor")
            )
        ]

    # the record types themselves are domain-free as *code*. Their docstrings
    # cite this milestone's documents by filename, which is prose about the
    # record and not a fact the record carries.
    for cls in (
        cp.TornEndpoint, cp.FixedPointCouplingPlan, cp.CoupledIteration,
        cp.CoupledRun, cp.CouplingOutcome,
    ):
        rendered = _code_only(inspect.getsource(cls)).lower()
        for word in ("electrical", "thermal", "joule", "resistor", "kelvin",
                     "watt", "ohm", "circuit", "temperature"):
            assert word not in rendered, f"{word!r} in {cls.__name__}"

    # and the executed plan names only quantities the composition enumerates
    problems, _ = compose(NOMINAL)
    declared = {
        (p.problem_id, q.name)
        for p in problems
        for q in tuple(p.variables) + tuple(p.parameters)
    }
    for endpoint in plan.torn:
        assert endpoint.endpoint in declared


def test_i4_the_plan_and_the_graph_readers_work_for_an_unrelated_domain_pair():
    """Written with no electro-thermal import: a mechanical/lubricant cycle."""
    friction = QuantityDependency(
        source_problem_id="mechanical-shaft",
        source_quantity="friction_loss",
        target_problem_id="lubricant-film",
        target_quantity="dissipated_power",
        unit_exemplar="watt",
    )
    viscosity = QuantityDependency(
        source_problem_id="lubricant-film",
        source_quantity="film_temperature",
        target_problem_id="lubricant-viscosity",
        target_quantity="temperature",
        unit_exemplar=KELVIN,
    )
    drag = QuantityDependency(
        source_problem_id="lubricant-viscosity",
        source_quantity="dynamic_viscosity",
        target_problem_id="mechanical-shaft",
        target_quantity="mu",
        unit_exemplar="pascal*second",
    )
    nodes = ["mechanical-shaft", "lubricant-film", "lubricant-viscosity"]
    edges = (friction, viscosity, drag)
    assert cp.execution_order(nodes, edges) == ()
    plan = cp.FixedPointCouplingPlan(
        plan_id="tribology",
        dependencies=edges,
        torn=(cp.TornEndpoint(viscosity, Quantity(340.0, KELVIN)),),
        absolute_tolerance=Quantity(1e-4, KELVIN),
        max_iterations=20,
    )
    assert cp.execution_order(nodes, plan.uncut) == (
        "lubricant-viscosity", "mechanical-shaft", "lubricant-film"
    )
    assert cp.FixedPointCouplingPlan.from_dict(plan.to_dict()) == plan


# =====================================================================
# TEST J — no bulk-data regression
# =====================================================================

def test_j_nothing_bulk_is_inlined_anywhere_on_the_path(case_a, case_e):
    """DATA-BOUNDARY0 holds: no array leaves a store into a result."""
    for run, _, _ in (case_a, case_e):
        assert run.iterations_run <= run.plan.max_iterations
        for iteration in run.iterations:
            for result in iteration.results:
                assert result.artifacts == ()
                assert result.data_references == ()
                for value in result.metadata.values():
                    assert not isinstance(value, (list, tuple)) or len(value) <= 8
        payload = run.to_dict()
        assert "data_references" not in json.dumps(payload["plan"])
        for entry in payload["iterations"]:
            for result in entry["results"]:
                assert result["data_references"] == []
                assert result["artifacts"] == []


def test_j2_the_trace_is_bounded_in_count_and_grows_in_bytes():
    """Falsifier F-8, measured rather than asserted away.

    Prereg TEST J claims the trace is ``O(max_iterations)``. That is true of the
    **count** and not of the **size**: ``solve_circuit`` writes the full
    ``circuit.canonical_dict()`` into ``ProvenanceRecord.metadata`` on every
    solve, and this run retains every result, so one 50-iteration record inlines
    50 canonical topologies. An earlier form of this test looked at
    ``result.metadata`` — which is small — and not at
    ``result.provenance.metadata``, which is where the growth is.

    This is **not** a DATA-BOUNDARY0 violation: nothing bulk leaves a store, and
    `data_references`/`artifacts` are empty throughout. It is the same growth
    pattern one level up, and it is recorded as a known unknown rather than
    fixed here — the DC domain is not editable under this milestone's change
    policy.
    """
    short, _, _ = execute(NOMINAL, budget=2, run_id="size-2")
    long_run, _, _ = execute(NOMINAL, budget=8, run_id="size-8")

    canonical = [
        r.provenance.metadata["circuit_canonical"]
        for run in (short, long_run)
        for i in run.iterations
        for r in i.results
        if "circuit_canonical" in r.provenance.metadata
    ]
    assert len(canonical) == short.iterations_run + long_run.iterations_run

    small = len(json.dumps(short.to_dict(), sort_keys=True))
    large = len(json.dumps(long_run.to_dict(), sort_keys=True))
    # linear in iterations, with a per-iteration payload that is not O(1)
    per_iteration = (large - small) / (
        long_run.iterations_run - short.iterations_run
    )
    assert per_iteration > 2000
    assert large < 200_000  # bounded by the budget, for this composition


# =====================================================================
# TEST L — the preregistered contraction result
# =====================================================================

def test_l_the_measured_contraction_matches_the_closed_form(case_a):
    """Prediction P-C of the preregistration §4.6, checked against measurement.

    **Deviation from the preregistration, recorded rather than hidden.** §4.6
    derives ``|g'| = α(T*−T_amb)/(1 + α(T*−T_ref))`` by eliminating ``V²`` at
    the *steady-state* fixed point, and TEST L's parenthetical then proposed
    reusing it for configuration (i) with a damping factor. That is imprecise:
    configuration (i) converges to a different ``T*`` (338.577 K rather than
    341.953 K), so the elimination step does not apply there and the identity
    is off by ~10 %. The underlying derivative — which is what P-C is about — is
    unaffected, and is asserted here directly:

        |g'| = (1 − e^(−t/τ)) · V²·α·R_ref / (hA · R(T*)²)

    Configuration (ii), where the identity was derived, is checked in its
    identity form below.
    """
    run, problems, _ = case_a
    changes = [c.magnitude_in(KELVIN) for c in run.iterate_changes]
    measured = changes[-1] / changes[-2]

    alpha, r_ref, volts, h_a = 0.00393, 10.0, 5.0, 0.05
    r_star = run.final.result_for(problems[1].problem_id).value(
        mat.RESISTANCE_METRIC
    ).magnitude_in("ohm")
    damping = 1.0 - math.exp(-120.0 / (2.5 / h_a))
    predicted = damping * volts**2 * alpha * r_ref / (h_a * r_star**2)

    assert measured == pytest.approx(predicted, rel=0.01)
    assert predicted < 1.0

    # configuration (ii): the identity as §4.6 derived it, in its own regime
    steady, steady_problems, _ = execute(
        NOMINAL, metric=lump.STEADY_STATE_TEMPERATURE_METRIC, run_id="pc-steady"
    )
    steady_changes = [c.magnitude_in(KELVIN) for c in steady.iterate_changes]
    t_star = only_temperature(steady)
    t_ref, t_amb = 293.15, 300.0
    identity = alpha * (t_star - t_amb) / (1.0 + alpha * (t_star - t_ref))
    assert steady_changes[-1] / steady_changes[-2] == pytest.approx(
        identity, rel=0.01
    )
    assert identity < 1.0

    # P-C's structural claim: contraction holds exactly when R(T_amb) > 0
    assert alpha * (t_ref - t_amb) < 1.0
    assert r_ref * (1.0 + alpha * (t_amb - t_ref)) > 0.0


def test_l2_the_marginal_configuration_measures_a_ratio_of_one():
    run, _, _ = execute(
        MARGINAL, metric=lump.STEADY_STATE_TEMPERATURE_METRIC,
        budget=50, run_id="ratio",
    )
    changes = [c.magnitude_in(KELVIN) for c in run.iterate_changes]
    assert changes[-1] / changes[-2] == pytest.approx(1.0, abs=0.05)

    alpha, t_ref, t_amb = -0.004, 300.0, 300.0
    t_star = t_amb + 1.0 / (2.0 * abs(alpha))
    ratio = abs(alpha * (t_star - t_amb) / (1.0 + alpha * (t_star - t_ref)))
    assert ratio == pytest.approx(1.0, abs=1e-12)


def test_l3_no_relaxation_appears_anywhere_in_the_module():
    """Fail condition §12.10: relaxation is a separate decision, not a knob."""
    source = pathlib.Path(inspect.getfile(cp)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    identifiers = (
        {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        | {n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)}
        | {
            n.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))
        }
    )
    for forbidden in ("omega", "relax", "damp", "aitken", "anderson",
                      "rollback", "checkpoint"):
        assert not any(forbidden in name.lower() for name in identifiers), forbidden


# =====================================================================
# TEST M — offset units are refused
# =====================================================================

def test_m_an_affine_scale_may_not_carry_a_coupling_tolerance():
    """The hazard, verified against this repository's own Quantity.

    ``Quantity(0.001,'kelvin').magnitude_in('degC') == -273.149`` and the two
    units share a dimensionality, so no dimension check can protect the
    comparison.
    """
    assert Quantity(0.001, KELVIN).magnitude_in("degC") == pytest.approx(
        -273.149, abs=1e-9
    )
    assert dimensionality("degC") == dimensionality(KELVIN)

    assert cp.is_ratio_scale(KELVIN) is True
    assert cp.is_ratio_scale("rankine") is True     # a temperature unit that passes
    assert cp.is_ratio_scale("degC") is False
    assert cp.is_ratio_scale("degF") is False
    assert cp.is_ratio_scale("watt") is True

    _, dependencies = compose(NOMINAL)
    with pytest.raises(InvalidScientificProblem, match="conventional"):
        cp.nominal_plan(
            NOMINAL, dependencies, seed=Quantity(300.0, KELVIN),
            tolerance=Quantity(1e-6, "degC"),
        )
    # rankine is accepted, so the rule tests a ratio scale and not a unit name
    plan = cp.nominal_plan(
        NOMINAL, dependencies, seed=Quantity(300.0, KELVIN),
        tolerance=Quantity(1.8e-6, "rankine"), max_iterations=50,
    )
    run = cp.run_fixed_point_coupling(NOMINAL, plan, run_id="rankine")
    assert run.outcome is cp.CouplingOutcome.CRITERION_MET
    assert only_temperature(run) == pytest.approx(338.577018, abs=1e-6)
    assert run.final_iterate_change.units == "degree_Rankine"


def test_m2_the_refusal_contains_no_temperature_knowledge():
    """The rule, not the prose about it.

    The docstrings name ``degC`` and ``rankine`` as examples, which is what a
    docstring is for. The executable rule names no unit at all: it asks whether
    zero maps to zero, and that question has no dimension.
    """
    code = _code_only(
        inspect.getsource(cp.is_ratio_scale)
    ) + _code_only(inspect.getsource(cp._require_ratio_scale))
    for word in ("kelvin", "celsius", "degc", "degf", "temperature",
                 "rankine", "watt", "ohm"):
        assert word not in code.lower(), word


# =====================================================================
# TEST N — the twin is not the runtime state
# =====================================================================

def test_n_the_twin_is_not_mutated_and_is_not_an_input(case_a):
    run, _, _ = case_a
    before = cp.build_coupled_twin(NOMINAL)
    after = cp.build_coupled_twin(NOMINAL)
    assert before == after
    assert before.to_dict() == after.to_dict()

    # it is not an argument to the loop, and it is not reachable from the run
    signature = inspect.signature(cp.run_fixed_point_coupling)
    assert "twin" not in signature.parameters
    assert "twin" not in json.dumps(run.to_dict(), sort_keys=True).lower()

    # what carrying the iterate would have cost: one version per iteration
    versions_required = run.iterations_run + 1
    assert versions_required == 11
    assert before.version == "0.1.0"

    # the twin declares the instance's state at t0, once — not per iteration
    states = [
        d for d in before.declarations if d.role.value == "state"
    ]
    assert len(states) == 1
    assert states[0].value.magnitude_in(KELVIN) == 300.0


# =====================================================================
# TEST O — serialization
# =====================================================================

def test_o_every_new_record_round_trips(case_a):
    run, _, plan = case_a
    assert cp.FixedPointCouplingPlan.from_dict(plan.to_dict()) == plan
    assert json.dumps(plan.to_dict(), sort_keys=True) == json.dumps(
        cp.FixedPointCouplingPlan.from_dict(plan.to_dict()).to_dict(),
        sort_keys=True,
    )
    for endpoint in plan.torn:
        assert cp.TornEndpoint.from_dict(endpoint.to_dict()) == endpoint

    revived = cp.CoupledRun.from_dict(run.to_dict())
    assert revived.outcome is run.outcome
    assert revived.iterations_run == run.iterations_run
    assert json.dumps(revived.to_dict(), sort_keys=True) == json.dumps(
        run.to_dict(), sort_keys=True
    )
    iteration = run.iterations[0]
    assert json.dumps(
        cp.CoupledIteration.from_dict(iteration.to_dict()).to_dict(),
        sort_keys=True,
    ) == json.dumps(iteration.to_dict(), sort_keys=True)


def test_o2_an_unknown_schema_is_rejected(case_a):
    _, _, plan = case_a
    payload = plan.to_dict()
    payload["schema"] = "electrothermal_fixed_point_plan/2"
    with pytest.raises(ScientificCoreError):
        cp.FixedPointCouplingPlan.from_dict(payload)


def test_o3_no_existing_schema_version_moved():
    """``scientific_result`` reads ``/3``: the recommendations round added
    ``ScientificResult.validity`` and bumped the writer deliberately. Updated
    rather than deleted, so a schema still cannot move without an edit here."""
    from src.engcore.scientific.composition.dependency import (
        QUANTITY_DEPENDENCY_SCHEMA,
    )
    from src.engcore.scientific.results.provenance import (
        EXECUTION_BINDING_SCHEMA, PROVENANCE_SCHEMA,
    )
    from src.engcore.scientific.results.result import RESULT_SCHEMA
    from src.engcore.scientific.solvers.protocol import RAW_OUTPUT_SCHEMA

    assert QUANTITY_DEPENDENCY_SCHEMA == "quantity_dependency/1"
    assert PROVENANCE_SCHEMA == "provenance_record/3"
    assert EXECUTION_BINDING_SCHEMA == "execution_binding/1"
    assert RESULT_SCHEMA == "scientific_result/4"
    assert RAW_OUTPUT_SCHEMA == "raw_solver_output/2"
    # and the four new ones are new
    assert cp.TORN_ENDPOINT_SCHEMA == "electrothermal_torn_endpoint/1"
    assert cp.FIXED_POINT_PLAN_SCHEMA == "electrothermal_fixed_point_plan/1"
    assert cp.COUPLED_ITERATION_SCHEMA == "electrothermal_coupled_iteration/1"
    assert cp.COUPLED_RUN_SCHEMA == "electrothermal_coupled_run/1"


# =====================================================================
# TEST P — the loop iterates the coupling, not time
# =====================================================================

def test_p_the_thermal_initial_condition_is_identical_in_every_iteration(case_a):
    """Fail condition §12.11. Time marching is a different thing, named and refused."""
    run, problems, _ = case_a
    thermal = problems[2].problem_id
    starts = {
        iteration.result_for(thermal).provenance.inputs[
            lump.TEMPERATURE
        ].magnitude_in(KELVIN)
        for iteration in run.iterations
    }
    assert starts == {300.0}

    durations = {
        iteration.result_for(thermal).provenance.inputs["duration"].magnitude_in(
            "second"
        )
        for iteration in run.iterations
    }
    assert durations == {120.0}

    # and the state the twin declares is that same t0 value, unchanged
    twin = cp.build_coupled_twin(NOMINAL)
    (state,) = [d for d in twin.declarations if d.role.value == "state"]
    assert state.value.magnitude_in(KELVIN) == 300.0


# =====================================================================
# Reduction attacks — preregistration §9
# =====================================================================

def test_r1_kwargs_cannot_carry_what_the_plan_carries(case_a):
    """R1: ``(seed=…, tol=…, max_iter=…)`` instead of a record. **Fails.**

    Three things are lost, and each is asserted rather than argued: the plan is
    checkable before anything runs, it is serializable, and it can refuse a
    tolerance that does not fit the edge it stops. A kwarg is none of those.
    """
    _, _, plan = case_a
    problems, _ = compose(NOMINAL)

    # inspectable and checkable before execution
    assert plan.check_against(problems) == ()
    # serializable, and equal after a round trip
    assert cp.FixedPointCouplingPlan.from_dict(plan.to_dict()) == plan
    # and it knows which edges it cuts, which a bag of scalars cannot
    assert plan.torn_endpoints == (("resistance-tcr-R1", mat.TEMPERATURE),)
    assert len(plan.uncut) == len(plan.dependencies) - len(plan.torn)


def test_r2_a_boolean_reproduces_every_assertion_this_milestone_makes():
    """R2: ``converged: bool`` instead of :class:`CouplingOutcome`. **Succeeds.**

    Executed, not argued: at two members the enum carries no fact a boolean
    does not. Both runs below are distinguishable by a single bit, and nothing
    in this milestone reads the outcome for anything else.

    The enum is nevertheless **kept**, on a naming argument recorded at `L0`:
    a field named ``converged`` on a coupling record, in a codebase where
    ``convergence`` already names a solver's own termination, is the collapse
    fail condition §12.4 forbids. It is the weakest new type here and the first
    candidate for deletion if a third member is never earned.
    """
    converged, _, _ = execute(NOMINAL, run_id="r2-yes")
    stalled, _, _ = execute(NOMINAL, budget=2, run_id="r2-no")

    as_bool = {
        run.plan.plan_id + str(run.iterations_run): run.criterion_met
        for run in (converged, stalled)
    }
    assert set(as_bool.values()) == {True, False}
    assert converged.criterion_met is not stalled.criterion_met
    # These two runs exercise the two outcomes a *converging* composition can
    # reach. TRANSFER_REFUSED is the third and is reached only when a
    # participant's own validation rejects its result, which neither of these
    # does; tests/test_coupled_transport_admission.py covers it.
    assert {run.outcome for run in (converged, stalled)} == set(
        cp.CouplingOutcome
    ) - {cp.CouplingOutcome.TRANSFER_REFUSED}
    assert len(cp.CouplingOutcome) == 3


def test_r4_a_float_tolerance_cannot_detect_either_mistake():
    """R4: ``float`` instead of ``Quantity``. **Fails, and both failures are shown.**

    A bare ``1e-6`` is compatible with a watt-valued edge, with an affine
    temperature scale, and with a mixed-dimension plan. The typed tolerance
    refuses all three; the float refuses none, because there is nothing on it
    to check.
    """
    _, dependencies = compose(NOMINAL)
    bare = 1e-6
    assert isinstance(bare, float)  # nothing to interrogate

    for bad in (Quantity(bare, "watt"), Quantity(bare, "degC")):
        with pytest.raises(InvalidScientificProblem):
            cp.nominal_plan(
                NOMINAL, dependencies, seed=Quantity(300.0, KELVIN), tolerance=bad
            )
    good = cp.nominal_plan(
        NOMINAL, dependencies, seed=Quantity(300.0, KELVIN),
        tolerance=Quantity(bare, KELVIN),
    )
    assert good.comparison_unit == KELVIN
    assert good.absolute_tolerance.magnitude_in(KELVIN) == bare


def test_r5_the_policy_is_not_a_property_of_the_dependency(case_a):
    """R5: fields on ``QuantityDependency`` instead of a plan. **Fails.**

    The *same* dependency records, unchanged and byte-identical, drive two runs
    with different tolerances, budgets and outcomes. Putting the policy on the
    declaration would make one composition into two, and a reusable statement of
    what feeds what into a statement about one study.
    """
    run_a, _, plan_a = case_a
    problems, dependencies = compose(NOMINAL)
    strict = cp.nominal_plan(
        NOMINAL, dependencies, seed=Quantity(300.0, KELVIN),
        tolerance=Quantity(1e-6, KELVIN), max_iterations=2, plan_id="strict",
    )
    run_b = cp.run_fixed_point_coupling(NOMINAL, strict, run_id="r5")

    assert [d.to_dict() for d in plan_a.dependencies] == [
        d.to_dict() for d in strict.dependencies
    ]
    assert run_a.outcome is not run_b.outcome
    # and a schema bump would be the cost of moving it onto the declaration
    from src.engcore.scientific.composition.dependency import (
        QUANTITY_DEPENDENCY_SCHEMA,
    )

    assert QUANTITY_DEPENDENCY_SCHEMA == "quantity_dependency/1"
    for dependency in dependencies:
        payload = dependency.to_dict()
        for banned in ("tolerance", "seed", "max_iterations", "outcome",
                       "relaxation", "order"):
            assert banned not in payload


def test_h0b_the_loop_cannot_run_without_the_declared_dependencies():
    """H0(B): does the machinery know it is electro-thermal without being told?

    Delete one edge from the plan and the iteration stops being able to supply
    an input — there is no fallback that reconstructs it from a name, a
    convention or a domain assumption, because there is none to reconstruct it
    with.
    """
    problems, dependencies = compose(NOMINAL)
    torn = cp.nominal_plan(
        NOMINAL, dependencies, seed=Quantity(300.0, KELVIN)
    ).torn
    missing_heat = tuple(
        d for d in dependencies if d.target_quantity != lump.HEAT_INPUT
    )
    plan = cp.FixedPointCouplingPlan(
        plan_id="edge-deleted",
        dependencies=missing_heat,
        torn=torn,
        absolute_tolerance=TOL,
        max_iterations=5,
    )
    assert plan.check_against(problems) == ()  # every remaining edge is valid
    with pytest.raises(KeyError):
        cp.run_fixed_point_coupling(NOMINAL, plan, run_id="edge-deleted")


def test_r3_the_torn_pairing_is_structural_and_not_positional(case_a):
    """R3: two parallel tuples would carry the association in an index."""
    _, _, plan = case_a
    reordered = cp.FixedPointCouplingPlan(
        plan_id=plan.plan_id,
        dependencies=tuple(reversed(plan.dependencies)),
        torn=plan.torn,
        absolute_tolerance=plan.absolute_tolerance,
        max_iterations=plan.max_iterations,
    )
    assert reordered.torn_endpoints == plan.torn_endpoints
    assert {d.name for d in reordered.uncut} == {d.name for d in plan.uncut}
    run = cp.run_fixed_point_coupling(NOMINAL, reordered, run_id="reordered")
    assert only_temperature(run) == pytest.approx(
        338.577018, abs=1e-6
    )


def test_r7_provenance_cannot_be_the_plan_because_it_needs_a_run(case_a):
    """R7: a representation that cannot exist before the run is not the plan."""
    _, _, plan = case_a
    with pytest.raises(ScientificCoreError):
        ProvenanceRecord(run_id="")
    # the plan, by contrast, is fully checkable before anything executes
    problems, _ = compose(NOMINAL)
    assert plan.check_against(problems) == ()
    assert cp.FixedPointCouplingPlan.from_dict(plan.to_dict()) == plan


def test_r8_the_stored_iterate_change_agrees_with_the_derived_one(case_a):
    """R8: it is derivable — and it is stored as the record of what was compared.

    The two must agree; if they ever disagree the stored value is the one that
    says what the loop actually did.
    """
    run, _, plan = case_a
    seeds = {e.endpoint: e.initial_value for e in plan.torn}
    previous = dict(seeds)
    for iteration in run.iterations:
        derived = max(
            abs(
                iteration.transported(endpoint.dependency).magnitude_in(KELVIN)
                - previous[endpoint.endpoint].magnitude_in(KELVIN)
            )
            for endpoint in plan.torn
        )
        assert iteration.largest_iterate_change.magnitude_in(
            KELVIN
        ) == pytest.approx(derived, rel=1e-15)
        previous = {
            e.endpoint: iteration.transported(e.dependency) for e in plan.torn
        }


# =====================================================================
# Regression boundary — the previous milestone is untouched
# =====================================================================

def test_k_the_open_loop_module_is_unchanged_and_still_open_loop():
    """`resistor_body.py` keeps its AST guard: no loop, one electrical solve."""
    tree = ast.parse(
        pathlib.Path(inspect.getfile(resistor_body)).read_text(encoding="utf-8")
    )
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.While)]
    calls = [
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert calls.count("solve_circuit") == 1


def test_k2_the_electrical_domain_still_refuses_a_rebound_circuit():
    """MIN-FOUNDATION-ET TEST K, unchanged — and why a fresh problem per pass.

    The DC domain folds resistance into the circuit's canonical identity, so a
    temperature-updated resistance is a different physical system to it. The
    loop therefore builds a fresh circuit, problem and solver every iteration;
    the ``problem_id`` is stable while the problem *record* is not.
    """
    problems, _ = compose(NOMINAL)
    cold = NOMINAL.circuit_at({"R1": Quantity(10.0, "ohm")})
    hot = NOMINAL.circuit_at({"R1": Quantity(12.0, "ohm")})
    assert cold.fingerprint() != hot.fingerprint()

    solver = ElectricalDCSolver()
    solver.bind_circuit(cold, problems[0].problem_id)
    with pytest.raises(CircuitBindingError):
        solver.bind_circuit(hot, problems[0].problem_id)


def test_k3_the_problem_id_is_stable_while_the_problem_record_is_not(case_a):
    """A finding, recorded: the endpoint survives iteration, the record does not."""
    run, problems, _ = case_a
    electrical = problems[0].problem_id
    fingerprints = {
        iteration.result_for(electrical).metadata["circuit_fingerprint"]
        for iteration in run.iterations
    }
    assert len(fingerprints) == run.iterations_run
    assert all(
        iteration.result_for(electrical).problem_id == electrical
        for iteration in run.iterations
    )
