"""MIN-FOUNDATION-ET — executed evidence.

Preregistered in ``docs/milestones/min-foundation-electrothermal-prereg.md``. Every test
here maps to a lettered test in prereg §10, to the N0 gate in §6, or to a
reduction attack in §6.4.

The question under test is: **what does a real two-way electro-thermal
consumer force into existence, over and above the contracts Crafty already
has?** The null hypothesis — that nothing is forced — is allowed to win, and
the gate tests are written so that it would.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import pathlib

import pytest

from src.engcore.domains.thermal_models import lumped as lump
from src.engcore.domains.electrical import material as mat
from src.engcore.domains.electrical.dc import RESISTOR_OHM_MODEL
from src.engcore.domains.electrical.dc.errors import CircuitBindingError
from src.engcore.domains.electrical.dc.problem import resistance_name
from src.engcore.domains.electrical.dc.solver import ElectricalDCSolver
from src.engcore.scientific.composition import (
    QUANTITY_DEPENDENCY_SCHEMA,
    QuantityDependency,
    externally_imposed,
    unresolved_inputs,
)
from src.engcore.scientific.errors import (
    InvalidScientificProblem,
    ScientificCoreError,
)
from src.engcore.scientific.ir.problem import ModelReference
from src.engcore.scientific.ir.variables import VariableRole
from src.engcore.scientific.models.definition import (
    BindingIssueKind,
    InputSourceKind,
    ValidityStatus,
)
from src.engcore.scientific.realizations.definition import ModelFormulation
from src.engcore.scientific.results.provenance import ProvenanceRecord
from src.engcore.scientific.results.validation import (
    ValidationLevel,
    ValidationOutcome,
)
from src.engcore.scientific.solvers.capability import CoreCapabilities
from src.engcore.scientific.twins.definition import TwinDatum, TwinDatumRole
from src.engcore.scientific.units.quantity import Quantity, dimensionality
from src.engcore.systems.electrothermal import (
    ElectroThermalResistor,
    build_twin,
    candidate_sources,
    electrothermal_dependencies,
    electrothermal_problems,
    run_open_loop_pass,
)
from src.engcore.systems.electrothermal import resistor_body

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# The one declared instance every test uses. Fixed numbers so that every
# figure quoted in the evidence document is reproducible.
CONDUCTOR = mat.TemperatureDependentConductor(
    component_id="R1",
    reference_resistance=Quantity(10.0, "ohm"),
    temperature_coefficient=Quantity(0.00393, "1/kelvin"),
    reference_temperature=Quantity(293.15, "kelvin"),
)
BODY = lump.ThermalBody(
    body_id="R1",
    heat_capacity=Quantity(2.5, "joule/kelvin"),
    ambient_conductance=Quantity(0.05, "watt/kelvin"),
    ambient_temperature=Quantity(300.0, "kelvin"),
    initial_temperature=Quantity(300.0, "kelvin"),
    duration=Quantity(120.0, "second"),
)
SYSTEM = ElectroThermalResistor(
    conductor=CONDUCTOR, body=BODY, source_voltage=Quantity(5.0, "volt")
)


@pytest.fixture(scope="module")
def executed():
    """One open-loop pass, shared. It is a handful of scalar evaluations."""
    return run_open_loop_pass(SYSTEM)


def _results_by_problem(passed):
    return {
        r.problem_id: r
        for r in (
            passed.electrical_result,
            passed.property_result,
            passed.thermal_result,
        )
    }


def _values_by_problem(passed):
    return {pid: r.values for pid, r in _results_by_problem(passed).items()}


# =====================================================================
# THE N0 GATE (prereg §6) — run before the new contract is allowed to help
# =====================================================================

def test_gate_a_reader_detects_only_some_of_the_targets():
    """§6.1: which unresolved inputs a records-only reader can even see.

    Three, and it is the *fourth* that carries the result: the resistance the
    circuit uses is modelled as a configured ``ScientificParameter``, so it
    carries a value and reads as settled. Nothing in the contracts
    distinguishes "configured" from "computed elsewhere".
    """
    problems = electrothermal_problems(SYSTEM, Quantity(10.0, "ohm"))
    electrical, prop, thermal = problems

    detected = unresolved_inputs(problems)
    assert set(detected) == {
        (prop.problem_id, mat.TEMPERATURE, "kelvin"),
        (thermal.problem_id, lump.HEAT_INPUT, "watt"),
        (thermal.problem_id, lump.AMBIENT_TEMPERATURE, "kelvin"),
    }

    # The invisible one. It is a parameter, it carries a value, and it is
    # indistinguishable from the genuinely configured parameters beside it.
    target = resistance_name(SYSTEM.component_id)
    parameter = electrical.parameter(target)
    assert isinstance(parameter.value, Quantity)
    assert all(name != target for _, name, _ in detected)


def test_gate_b_dimensional_matching_alone_is_ambiguous(executed):
    """§6.2, the predicted measurement: how many sources could supply each.

    The prediction was "at least two candidates per target". If it had been
    one, the wiring would have been unambiguous and H0(A) would have won.
    """
    results = _values_by_problem(executed)
    counts = {}
    for problem_id, name, unit in unresolved_inputs(executed.problems):
        candidates = candidate_sources(
            unit,
            executed.problems,
            results,
            exclude=(problem_id, name),
        )
        counts[(problem_id, name)] = len(candidates)

    assert all(n >= 2 for n in counts.values()), counts
    # Recorded figures, asserted so the evidence document cannot drift from
    # what the code actually produces.
    assert counts == {
        (executed.problems[1].problem_id, mat.TEMPERATURE): 5,
        (executed.problems[2].problem_id, lump.HEAT_INPUT): 4,
        (executed.problems[2].problem_id, lump.AMBIENT_TEMPERATURE): 5,
    }


def test_gate_c_four_power_valued_metrics_exist_in_one_result(executed):
    """The concrete reason the heat source cannot be picked by dimension."""
    watts = [
        name
        for name, value in executed.electrical_result.values.items()
        if dimensionality(value.units) == dimensionality("watt")
    ]
    assert len(watts) == 4
    assert SYSTEM.power_metric in watts


def test_gate_d_capabilities_carry_one_direction_and_not_the_other():
    """Why the capability layer does not close the gate.

    A scientific capability requirement is a real, typed, machine-checkable
    dependency — and this milestone exercises it, which MODEL0-R did not. But
    it is *asymmetric by physics*, not by oversight.
    """
    tcr = mat.LINEAR_TCR_REALIZATION
    thermal = lump.LUMPED_CLOSED_FORM_REALIZATION

    # thermal -> electrical: expressible, and satisfied.
    assert tcr.required_capabilities == frozenset({mat.REQUIRED_BODY_TEMPERATURE})
    assert thermal.provided_capabilities == frozenset({lump.BODY_TEMPERATURE})
    assert tcr.required_capabilities <= thermal.provided_capabilities

    # electrical -> thermal: NOT expressible, and must not be faked. A lumped
    # balance is satisfied by any heat source, so a requirement on electrical
    # dissipation would be a false claim welding thermal physics to one domain.
    assert thermal.required_capabilities == frozenset()

    # And even where it is expressible, it names no quantity: it orders the
    # sciences, it does not wire the numbers.
    identifiers = {c.identifier for c in tcr.required_capabilities}
    assert identifiers == {"thermal:body_temperature"}
    assert mat.TEMPERATURE not in identifiers


def test_gate_e_the_electrical_domain_is_not_imported_by_the_material_module():
    """A domain requires another domain's science by *identifier*, not import.

    Checked over the module's actual import statements rather than its text: a
    prose mention of a sibling module is not a dependency, and a test that
    could not tell them apart would be measuring the wrong thing.
    """
    tree = ast.parse(
        pathlib.Path(inspect.getfile(mat)).read_text(encoding="utf-8")
    )
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add("." * node.level + (node.module or ""))
    assert imported
    assert not any("thermal" in name for name in imported), imported
    assert not any("domains" in name for name in imported), imported
    # The requirement is nonetheless real and typed.
    assert mat.REQUIRED_BODY_TEMPERATURE.namespace == "thermal"


# =====================================================================
# TEST A — representation completeness
# =====================================================================

def test_a_the_whole_skeleton_is_built_from_typed_contracts(executed):
    electrical, prop, thermal = executed.problems

    # one electrical behaviour, one thermal behaviour, one material property
    assert RESISTOR_OHM_MODEL.model_id == "electrical.dc.resistor_ohm"
    assert lump.LUMPED_CAPACITY_MODEL.model_id == "thermal.lumped.first_order_capacity"
    assert mat.LINEAR_TCR_MODEL.model_id == "electrical.material.linear_tcr_resistance"

    # three separately posed problems, not one merged one
    assert len({p.problem_id for p in executed.problems}) == 3
    assert ModelReference(
        mat.LINEAR_TCR_MODEL.model_id, mat.LINEAR_TCR_MODEL.version
    ) in prop.models
    assert ModelReference(
        lump.LUMPED_CAPACITY_MODEL.model_id, lump.LUMPED_CAPACITY_MODEL.version
    ) in thermal.models

    # the executed pass produced real, physically ordered numbers
    assert executed.resistance_before.magnitude == pytest.approx(10.269205, rel=1e-9)
    assert executed.dissipated_power.magnitude == pytest.approx(2.434463, rel=1e-6)
    assert executed.temperature_after.magnitude == pytest.approx(344.272271, rel=1e-9)
    assert executed.resistance_after.magnitude == pytest.approx(12.009105, rel=1e-6)
    # self-heating raises the resistance of a positive-TCR conductor
    assert executed.resistance_after.magnitude > executed.resistance_before.magnitude

    # every solve validated
    for result in (
        executed.property_result,
        executed.electrical_result,
        executed.thermal_result,
    ):
        assert result.validation.status is ValidationOutcome.PASS

    # provenance carries the model -> realization -> solver relation at arity > 1
    bindings = executed.provenance.bindings
    assert len(bindings) == 5
    assert len({b.solver.key for b in bindings}) == 3
    assert len({b.model.key for b in bindings}) == 5
    assert len({b.realization.key for b in bindings if b.realization}) == 2


def test_a2_provenance_association_is_structural_not_positional(executed):
    """The D2 lesson from MODEL0-R, re-checked at genuine arity > 1."""
    bindings = executed.provenance.bindings
    by_model = {b.model.key: b for b in bindings}
    tcr = by_model[
        (mat.LINEAR_TCR_MODEL.model_id, mat.LINEAR_TCR_MODEL.version)
    ]
    thermal = by_model[
        (lump.LUMPED_CAPACITY_MODEL.model_id, lump.LUMPED_CAPACITY_MODEL.version)
    ]
    assert tcr.solver.solver_id == mat.SOLVER_ID
    assert thermal.solver.solver_id == lump.SOLVER_ID
    assert tcr.solver.key != thermal.solver.key

    # Zipping the derived participant sets would produce a different — and
    # wrong — pairing. The record does not depend on order.
    models = sorted(executed.provenance.models)
    solvers = sorted(executed.provenance.solvers)
    assert len(models) != len(solvers)  # 5 models, 3 solvers: no zip is even possible


# =====================================================================
# TEST B — two-way dependency
# =====================================================================

def test_b_both_directions_are_present_and_recovered_from_records(executed):
    payloads = [json.loads(json.dumps(d.to_dict())) for d in executed.dependencies]
    electrical, prop, thermal = (p.problem_id for p in executed.problems)

    edges = {
        (d["source_problem_id"], d["target_problem_id"]) for d in payloads
    }
    # electrical -> thermal
    assert (electrical, thermal) in edges
    # thermal -> electrical, routed through the material property
    assert (thermal, prop) in edges
    assert (prop, electrical) in edges

    # The loop closes: following the edges from the electrical problem returns
    # to it. Recovered by traversal of records, with no name parsing.
    successors = {s: t for s, t in edges}
    visited, node = [], electrical
    for _ in range(len(edges)):
        node = successors[node]
        visited.append(node)
    assert visited == [thermal, prop, electrical]


def test_b2_every_dependency_checks_clean_against_the_records(executed):
    results = _results_by_problem(executed)
    by_id = {p.problem_id: p for p in executed.problems}
    for dependency in executed.dependencies:
        issues = dependency.check_against(
            target_problem=by_id[dependency.target_problem_id],
            source_problem=by_id[dependency.source_problem_id],
            source_result=results[dependency.source_problem_id],
        )
        assert issues == (), (dependency.name, issues)


def test_b3_a_dimensionally_wrong_wiring_is_refused(executed):
    """The record is a scientific statement, not a pair of strings."""
    electrical, prop, thermal = executed.problems
    wrong = QuantityDependency(
        source_problem_id=electrical.problem_id,
        source_quantity="node_voltage:n1",   # volts
        target_problem_id=thermal.problem_id,
        target_quantity=lump.HEAT_INPUT,     # watts
        unit_exemplar=lump.POWER_UNIT,
    )
    issues = wrong.check_against(
        target_problem=thermal,
        source_result=executed.electrical_result,
    )
    assert [i.kind for i in issues] == [BindingIssueKind.WRONG_DIMENSION]


def test_b3b_values_from_the_wrong_run_are_refused(executed):
    """Falsifier C-12: the post-execution path must not be identity-free.

    ``check_against`` takes a whole result rather than a bare mapping of
    values, precisely so that *which run these numbers came from* is checkable.
    """
    heat = executed.dependencies[0]
    assert heat.check_against(source_result=executed.electrical_result) == ()
    issues = heat.check_against(source_result=executed.thermal_result)
    assert [i.kind for i in issues] == [BindingIssueKind.MISSING]
    assert "states" in issues[0].detail


def test_b4_a_missing_quantity_is_reported_not_invented(executed):
    electrical, prop, thermal = executed.problems
    absent = QuantityDependency(
        source_problem_id=thermal.problem_id,
        source_quantity=lump.TEMPERATURE_METRIC,
        target_problem_id=prop.problem_id,
        target_quantity="no_such_quantity",
        unit_exemplar="kelvin",
    )
    issues = absent.check_against(target_problem=prop)
    assert [i.kind for i in issues] == [BindingIssueKind.MISSING]


def test_b6_an_endpoint_name_must_mean_one_thing(executed):
    """Falsifier D-1, the one BREAKING-RISK, closed before commit.

    An endpoint resolves into ``result.values ∪ variables ∪ parameters``. If a
    domain reuses one name across those namespaces, the *same* record returns
    two different verdicts depending on which side the caller supplies — and
    when the two meanings share a dimension, nothing can notice at all.

    The rule is stated in the contract and the shipped consumer holds it: the
    lumped body's STATE variable and its output metric have distinct names, so
    ``temperature`` at t0 and ``final_temperature`` at t_end cannot be
    confused.
    """
    _, _, thermal = executed.problems
    declared = {v.name for v in thermal.variables} | {
        p.name for p in thermal.parameters
    }
    metrics = set(executed.thermal_result.values)
    assert declared & metrics == set(), declared & metrics

    # The same invariant across every problem/result pair in the system.
    for problem in executed.problems:
        names = {v.name for v in problem.variables} | {
            p.name for p in problem.parameters
        }
        overlap = names & set(_results_by_problem(executed)[problem.problem_id].values)
        assert overlap == set(), (problem.problem_id, overlap)


def test_b7_a_state_fixed_by_a_boundary_condition_is_not_unresolved():
    """Falsifier C-2: the reader must not assume an initial-value problem.

    A steady-state problem whose state is pinned by a Dirichlet condition needs
    no external supplier. An earlier form of ``unresolved_inputs`` tested only
    for an initial condition and would have reported this as environment-
    imposed — a false positive produced inside universal core, containing no
    domain word for a lexical scan to catch.
    """
    from src.engcore.scientific.ir.conditions import BoundaryCondition, BoundaryKind
    from src.engcore.scientific.ir.problem import ScientificProblem
    from src.engcore.scientific.ir.variables import ScientificVariable

    steady = ScientificProblem(
        problem_id="steady-boundary-value",
        variables=(
            ScientificVariable(
                name="phi", unit="kelvin", role=VariableRole.STATE
            ),
        ),
        boundary_conditions=(
            BoundaryCondition(
                name="left",
                variable="phi",
                kind=BoundaryKind.DIRICHLET,
                region="west",
                value=Quantity(300.0, "kelvin"),
            ),
        ),
    )
    assert unresolved_inputs((steady,)) == ()
    assert externally_imposed((steady,), ()) == ()


def test_b8_fan_in_is_representable_and_its_combination_rule_is_not(executed):
    """Falsifier C-4/C-5, measured at the record level rather than asserted.

    Two sources on one target is *representable*: two records, both checking
    clean. What no contract states is how they combine — sum, override, or
    split. ``externally_imposed`` reports the target as supplied either way,
    because it sets no arity expectation.

    This is the measured shape of the fan-in gap. It is recorded, not filled:
    a combination rule invented from one consumer would be a coupling engine's
    semantics decided on no evidence.
    """
    _, _, thermal = executed.problems
    first, second = (
        QuantityDependency(
            source_problem_id=source,
            source_quantity="dissipated_power",
            target_problem_id=thermal.problem_id,
            target_quantity=lump.HEAT_INPUT,
            unit_exemplar=lump.POWER_UNIT,
        )
        for source in ("heater-a", "heater-b")
    )
    assert first != second
    assert first.check_against(target_problem=thermal) == ()
    assert second.check_against(target_problem=thermal) == ()

    # Both declared; the target reads as supplied; nothing says how they add.
    assert (
        thermal.problem_id,
        lump.HEAT_INPUT,
        "watt",
    ) not in externally_imposed(executed.problems, (first, second))
    fields = set(QuantityDependency.__dataclass_fields__)
    for combination in ("weight", "fraction", "operation", "combine", "order"):
        assert combination not in fields


def test_b5_absence_of_a_dependency_is_an_answer(executed):
    """The ambient has no supplier, and that is complete information."""
    imposed = externally_imposed(executed.problems, executed.dependencies)
    assert imposed == (
        (executed.problems[2].problem_id, lump.AMBIENT_TEMPERATURE, "kelvin"),
    )


# =====================================================================
# TEST C — property/state dependency
# =====================================================================

def test_c_the_temperature_dependence_is_typed_and_inspectable():
    """Recoverable from the model record alone: no metadata, no convention."""
    spec = next(
        s for s in mat.LINEAR_TCR_MODEL.inputs if s.name == mat.TEMPERATURE
    )
    assert spec.source_kind is InputSourceKind.VARIABLE
    assert spec.role is VariableRole.STATE
    assert dimensionality(spec.unit_exemplar) == dimensionality("kelvin")
    assert mat.LINEAR_TCR_MODEL.provided_metrics == (mat.RESISTANCE_METRIC,)

    # Nothing about it lives in metadata, anywhere on the path.
    assert mat.LINEAR_TCR_MODEL.metadata == {}
    payload = json.loads(json.dumps(mat.LINEAR_TCR_MODEL.to_dict()))
    assert payload["inputs"][3]["name"] == mat.TEMPERATURE
    assert payload["inputs"][3]["role"] == VariableRole.STATE.value


def test_c2_the_property_declares_when_it_is_valid_and_says_unknown_otherwise():
    problem = mat.build_resistance_problem(CONDUCTOR)
    assert (
        mat.assess_resistance_validity(problem, Quantity(300.0, "kelvin")).status
        is ValidityStatus.IN_DOMAIN
    )
    assert (
        mat.assess_resistance_validity(problem, Quantity(600.0, "kelvin")).status
        is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )
    # A validity condition on a STATE coordinate is never automatic: the
    # context is built from parameters, so the state must be passed explicitly.
    # It reaches the assessment through the ASSEMBLED half now, not through an
    # `extra=` merged into the caller's -- the two namespaces stay apart all the
    # way to the condition, which is what stops a caller parameter of that name
    # deciding it. `temperature` is reserved, so the parameter-built half
    # cannot carry it at all.
    declared = problem.validity_context(reserved=mat.ASSEMBLER_NAMESPACE)
    assert mat.TEMPERATURE not in declared
    assembled = mat.resistance_validity_context(
        problem, Quantity(300.0, "kelvin")
    )
    assert mat.TEMPERATURE in assembled.assembled
    assert mat.TEMPERATURE not in assembled.declared


def test_c3_the_final_state_stayed_inside_the_declared_validity(executed):
    problem = executed.problems[1]
    assert (
        mat.assess_resistance_validity(problem, executed.temperature_after).status
        is ValidityStatus.IN_DOMAIN
    )


def test_c4_validity_and_validation_are_kept_apart():
    """`assess_resistance_validity` is not a check inside a ValidationReport."""
    problem = mat.build_resistance_problem(CONDUCTOR)
    solver = mat.ResistancePropertySolver()
    solver.bind_conductor(
        CONDUCTOR, problem.problem_id, temperature=Quantity(600.0, "kelvin")
    )
    prepared = solver.prepare(problem)
    report = solver.validate(prepared, solver.solve(prepared))
    # Out of declared validity, yet every check still passes: the two
    # questions are different and the record keeps them different.
    assert report.status is ValidationOutcome.PASS
    assert {c.name for c in report.checks} == {
        "resistance_strictly_positive",
        "metric_dimensions",
    }
    # And neither is the validity assessment wearing a different name: no
    # check here reads a validity condition, and the level the report attains
    # is about dimensions, not about applicability.
    assert report.attained_levels == frozenset(
        {ValidationLevel.DIMENSIONALLY_VALID}
    )
    assert mat.assess_resistance_validity(
        problem, Quantity(600.0, "kelvin")
    ).status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


# =====================================================================
# TEST D — no domain leakage
# =====================================================================

def _core_sources():
    return [
        p
        for p in (REPO_ROOT / "src/engcore/scientific").rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def test_d_universal_core_has_no_domain_branch_and_no_domain_literal():
    for path in _core_sources():
        text = path.read_text(encoding="utf-8")
        for pattern in (
            '"electrical"', "'electrical'", '"thermal"', "'thermal'",
            "domain ==", "domain in ", ".domain ==",
            "resistor", "joule", "conductor", "electrothermal",
        ):
            assert pattern not in text, f"{pattern!r} leaked into {path.name}"


def test_d2_the_new_composition_package_carries_no_domain_vocabulary():
    package = REPO_ROOT / "src/engcore/scientific/composition"
    for path in package.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8").lower()
        for word in (
            "electrical", "thermal", "resistor", "resistance", "joule",
            "voltage", "ampere", "ohm", "watt", "temperature", "heat",
            "circuit", "conductor", "dissipation",
        ):
            assert word not in text, f"{word!r} leaked into {path.name}"


def test_d3_another_domain_pair_can_use_the_contract_unchanged():
    """Could a chemical/mechanical consumer use this without reading our code?

    Nothing here is imported from either domain: two arbitrary problem ids and
    quantity names, one dimension, and the record holds.
    """
    dependency = QuantityDependency(
        source_problem_id="mechanical-shaft",
        source_quantity="friction_loss",
        target_problem_id="lubricant-film",
        target_quantity="dissipated_power",
        unit_exemplar="watt",
    )
    assert dependency.dimension == dimensionality("watt")
    assert QuantityDependency.from_dict(dependency.to_dict()) == dependency


# =====================================================================
# TEST E — solver independence
# =====================================================================

def test_e_no_foundation_object_carries_a_concrete_solver_identity(executed):
    for dependency in executed.dependencies:
        blob = json.dumps(dependency.to_dict())
        for leaked in (
            "solver", "backend", "mna", "scipy", "numpy", "tolerance",
            "splu", "device", "gpu", "thread", mat.SOLVER_ID, lump.SOLVER_ID,
        ):
            assert leaked not in blob, f"{leaked!r} leaked into a dependency"

    twin_blob = json.dumps(executed.twin.to_dict())
    for leaked in ("solver", "backend", "scipy", "mna", mat.SOLVER_ID):
        assert leaked not in twin_blob, f"{leaked!r} leaked into the twin"

    assert "solver" not in set(QuantityDependency.__dataclass_fields__)


def test_e2_the_realizations_name_capabilities_and_never_a_backend():
    for realization in (
        mat.LINEAR_TCR_REALIZATION,
        lump.LUMPED_CLOSED_FORM_REALIZATION,
    ):
        blob = json.dumps(realization.to_dict())
        for leaked in ("scipy", "numpy", "splu", "solve_banded", "gpu", "thread"):
            assert leaked not in blob
    ids = {
        c.name
        for c in lump.LUMPED_CLOSED_FORM_REALIZATION.required_solver_capabilities
    }
    assert ids == {"thermal:lumped_capacity_transient", "core:algebraic"}


def test_e3_a_posed_ode_may_require_an_algebraic_solver_capability():
    """The MODEL0-R separation, used rather than restated.

    The claim is an ODE. The computation is a scalar exponential. The record
    can say both, because ``formulation`` and ``required_solver_capabilities``
    answer different questions.
    """
    realization = lump.LUMPED_CLOSED_FORM_REALIZATION
    assert realization.formulation is ModelFormulation.ODE
    assert realization.requires_solver_capability(CoreCapabilities.ALGEBRAIC)
    assert not realization.requires_solver_capability(CoreCapabilities.ODE)


# =====================================================================
# TEST F — twin authority
# =====================================================================

def test_f_the_twin_is_the_only_instance_state_authority(executed):
    twin = executed.twin
    roles = {d.name: d.role for d in twin.declarations}
    assert roles["ambient_temperature"] is TwinDatumRole.OPERATING_CONDITION
    assert roles[f"temperature:{SYSTEM.component_id}"] is TwinDatumRole.STATE
    assert roles[f"source_voltage:V1"] is TwinDatumRole.CONTROL

    # The new record holds no value of any kind — it cannot be a second
    # authority for instance state because it carries no state.
    fields = set(QuantityDependency.__dataclass_fields__)
    assert fields == {
        "source_problem_id", "source_quantity",
        "target_problem_id", "target_quantity",
        "unit_exemplar", "name", "description",
    }
    for dependency in executed.dependencies:
        assert not any(
            isinstance(v, Quantity) for v in dependency.to_dict().values()
        )


def test_f1b_the_twin_is_a_derived_record_that_nothing_reads(executed):
    """Falsifier C-6, recorded honestly rather than dressed up.

    Prereg §4 row 11 called the twin "the only instance authority". What the
    code does is narrower: the problems and the solver bindings are built from
    the domain declarations, and the twin is derived from the same object
    afterwards and consulted by nothing. It is a faithful copy, not an
    authority — and no evidence was gained about whether it *could* be one.

    Nothing links a twin declaration name to a problem quantity name. The
    correspondence below lives in this test, which is exactly the point: it is
    not in any contract.
    """
    # Nothing takes a twin as input: the problems and the bindings are built
    # from the domain declarations, never from the twin.
    for function in (
        run_open_loop_pass,
        electrothermal_problems,
        electrothermal_dependencies,
    ):
        assert "twin" not in inspect.signature(function).parameters
    assert "twin" not in inspect.signature(build_twin).parameters

    # It is at least consistent with what actually executed.
    declared = {d.name: d.value for d in executed.twin.declarations}
    assert declared[f"heat_capacity:{SYSTEM.component_id}"] == BODY.heat_capacity
    assert declared["ambient_temperature"] == BODY.ambient_temperature
    assert (
        declared[f"temperature:{SYSTEM.component_id}"] == BODY.initial_temperature
    )
    assert declared[f"source_voltage:V1"] == SYSTEM.source_voltage


def test_f2_no_system_or_component_instance_type_was_created():
    """Eleven of the twelve candidate abstractions, asserted absent."""
    import src.engcore.scientific as core

    exported = set(core.__all__)
    for forbidden in (
        "SystemDefinition", "SystemInstance", "AssemblyInstance",
        "ComponentDefinition", "ComponentInstance", "ComponentUsage",
        "CausalPort", "PhysicalConnector", "Port", "Connector",
        "MaterialIdentity", "MaterialState", "MaterialProperty",
        "MaterialPropertyIdentity", "PropertyRequirement", "PropertyBinding",
        "StateCoordinateBinding", "FieldDefinition", "Mesh", "Topology",
    ):
        assert forbidden not in exported, f"{forbidden} was created"

    # Exactly one new public record in the new package.
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


# =====================================================================
# TEST G — serialization
# =====================================================================

def test_g_the_new_record_round_trips_deterministically(executed):
    for dependency in executed.dependencies:
        payload = dependency.to_dict()
        assert payload["schema"] == QUANTITY_DEPENDENCY_SCHEMA
        restored = QuantityDependency.from_dict(payload)
        assert restored == dependency
        assert json.dumps(restored.to_dict()) == json.dumps(payload)


def test_g2_an_unknown_schema_is_refused_rather_than_guessed(executed):
    payload = dict(executed.dependencies[0].to_dict())
    payload["schema"] = "quantity_dependency/2"
    with pytest.raises(ScientificCoreError):
        QuantityDependency.from_dict(payload)


def test_g3_no_existing_schema_version_moved():
    """prereg §8.2. The new record is additive; nothing else changed *here*.

    ``scientific_result`` reads ``/3`` rather than the ``/2`` this milestone
    recorded. That is not this milestone's record changing: the recommendations
    round added ``ScientificResult.validity`` and bumped the writer, on the same
    argument DATA-BOUNDARY0 made for ``data_references``. The assertion is
    updated rather than deleted because what it is for is unchanged — a schema
    must never move without somebody having to come here and say why.
    """
    from src.engcore.scientific.ir.problem import PROBLEM_SCHEMA
    from src.engcore.scientific.models.definition import MODEL_SCHEMA
    from src.engcore.scientific.realizations.definition import REALIZATION_SCHEMA
    from src.engcore.scientific.results.provenance import PROVENANCE_SCHEMA
    from src.engcore.scientific.results.result import RESULT_SCHEMA
    from src.engcore.scientific.twins.definition import SCIENTIFIC_TWIN_SCHEMA

    assert PROBLEM_SCHEMA == "scientific_problem/1"
    assert MODEL_SCHEMA == "scientific_model_definition/1"
    assert REALIZATION_SCHEMA == "model_realization_definition/1"
    assert RESULT_SCHEMA == "scientific_result/4"
    assert PROVENANCE_SCHEMA == "provenance_record/3"
    assert SCIENTIFIC_TWIN_SCHEMA == "scientific_twin/1"
    assert QUANTITY_DEPENDENCY_SCHEMA == "quantity_dependency/1"


def test_g4_the_whole_representation_serializes(executed):
    blob = json.dumps(
        {
            "twin": executed.twin.to_dict(),
            "problems": [p.to_dict() for p in executed.problems],
            "dependencies": [d.to_dict() for d in executed.dependencies],
            "results": [
                r.to_dict()
                for r in (
                    executed.property_result,
                    executed.electrical_result,
                    executed.thermal_result,
                )
            ],
        },
        sort_keys=True,
    )
    assert len(blob) > 0
    # byte-identical on a second pass
    assert blob == json.dumps(
        {
            "twin": executed.twin.to_dict(),
            "problems": [p.to_dict() for p in executed.problems],
            "dependencies": [d.to_dict() for d in executed.dependencies],
            "results": [
                r.to_dict()
                for r in (
                    executed.property_result,
                    executed.electrical_result,
                    executed.thermal_result,
                )
            ],
        },
        sort_keys=True,
    )


# =====================================================================
# TEST H — reduction attacks (prereg §6.4)
# =====================================================================

def test_h1_reduction_metadata_is_not_used_anywhere_on_the_path(executed):
    """§6.4(1): the untyped escape hatch is not the home."""
    assert executed.twin.metadata == {}
    for problem in executed.problems[1:]:      # electrical metadata is legacy
        assert problem.metadata == {}
    for record in (executed.property_result, executed.thermal_result):
        assert record.metadata == {}
        assert record.provenance.metadata == {}
    module = pathlib.Path(inspect.getfile(resistor_body)).read_text(encoding="utf-8")
    assert "artifacts=" not in module


def test_h2_reduction_the_supplier_cannot_live_on_the_model(executed):
    """§6.4(2): executed, not argued.

    The *same* thermal model record is reused under a different supplier from a
    different science. If the supplier were a field on the model, this would
    require a second model — and the lumped balance would have become
    electrical physics.
    """
    _, _, thermal = executed.problems
    combustion = QuantityDependency(
        source_problem_id="burner-flame",
        source_quantity="release_rate",
        target_problem_id=thermal.problem_id,
        target_quantity=lump.HEAT_INPUT,
        unit_exemplar=lump.POWER_UNIT,
    )
    assert combustion.check_against(target_problem=thermal) == ()
    # unchanged model, unchanged problem, different supplier
    assert lump.LUMPED_CAPACITY_MODEL.required_capabilities == frozenset(
        {lump.LUMPED_CAPACITY_TRANSIENT.name}
    )
    assert "electric" not in json.dumps(lump.LUMPED_CAPACITY_MODEL.to_dict()).lower()


def test_h3_reduction_a_twin_datum_cannot_hold_a_relation(executed):
    """§6.4(3): a TwinDatum holds a typed value; a relation is not a value."""
    with pytest.raises(ScientificCoreError):
        TwinDatum(name="coupling", value=executed.dependencies[0])
    # and encoding it as text would be the string convention we refuse
    assert not any(
        isinstance(d.value, str) for d in executed.twin.declarations
    )


def test_h4_reduction_provenance_cannot_carry_it_because_it_comes_too_late():
    """§6.4(4): the decisive reduction.

    The dependencies are complete and checkable with **nothing executed**. A
    provenance record does not exist yet at this point, so it cannot be where
    the composition is stated.
    """
    problems = electrothermal_problems(SYSTEM, Quantity(10.0, "ohm"))
    dependencies = electrothermal_dependencies(SYSTEM, problems)
    by_id = {p.problem_id: p for p in problems}
    for dependency in dependencies:
        # targets are checkable before any solve; sources that are result
        # metrics are not, and the contract does not pretend otherwise
        assert dependency.check_against(
            target_problem=by_id[dependency.target_problem_id]
        ) == ()
    assert "run_id" in set(ProvenanceRecord.__dataclass_fields__)


def test_h5_reduction_a_merged_model_is_not_the_representation(executed):
    """§6.4(5): the two claims stay separately statable and separately valid."""
    thermal_payload = json.dumps(lump.LUMPED_CAPACITY_MODEL.to_dict()).lower()
    electrical_payload = json.dumps(RESISTOR_OHM_MODEL.to_dict()).lower()
    assert "resistance" not in thermal_payload
    assert "heat" not in electrical_payload
    # each model is valid or not on its own terms
    assert lump.LUMPED_CAPACITY_MODEL.validity.conditions
    assert mat.LINEAR_TCR_MODEL.validity.conditions


def test_h6_the_endpoint_type_was_reduced_away():
    """A companion `QuantityEndpoint` was considered and is not here.

    Two types where flat fields suffice is what a reduction attack exists to
    kill. The record has four endpoint fields and no endpoint object.
    """
    import src.engcore.scientific.composition.dependency as module

    names = {n for n in dir(module) if not n.startswith("_")}
    assert "QuantityEndpoint" not in names
    assert "DependencyBindingReport" not in names
    # the check reuses the existing issue type rather than minting one
    assert module.BindingIssue.__module__.endswith("models.definition")


# =====================================================================
# TEST I — existing regression / frozen artifacts
# =====================================================================

def test_i_the_frozen_thermal_tree_was_not_edited_or_extended():
    from experiments.thermal_t1.t1_config import THERMAL_FROZEN_FILE_DIGESTS

    for relative, expected in THERMAL_FROZEN_FILE_DIGESTS.items():
        actual = hashlib.sha256((REPO_ROOT / relative).read_bytes()).hexdigest()
        assert actual == expected, f"{relative} changed"
    on_disk = {
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in (REPO_ROOT / "src/engcore/domains/thermal").rglob("*.py")
    }
    assert on_disk == {k.replace("\\", "/") for k in THERMAL_FROZEN_FILE_DIGESTS}


def test_i2_the_electrical_dc_package_was_not_edited():
    """prereg §9. The new material module sits beside it, not inside it."""
    dc = REPO_ROOT / "src/engcore/domains/electrical/dc"
    on_disk = {p.name for p in dc.rglob("*.py") if "__pycache__" not in p.parts}
    assert on_disk == {
        "__init__.py", "circuit.py", "components.py", "errors.py", "mna.py",
        "models.py", "problem.py", "solver.py", "validation.py",
    }
    # and its temperature-independence assumption still stands, unedited
    assert "temperature-independent resistance" in RESISTOR_OHM_MODEL.assumptions


# =====================================================================
# TEST J — the open-loop boundary
# =====================================================================

def test_j_exactly_one_electrical_solve_and_no_coupled_claim(executed):
    """Structural, not textual: the module's AST, so prose cannot fake it."""
    assert executed.coupled_convergence_claimed is False

    tree = ast.parse(
        pathlib.Path(inspect.getfile(resistor_body)).read_text(encoding="utf-8")
    )
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.While)]

    called = [
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert called.count("solve_circuit") == 1

    identifiers = {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
    } | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    } | {
        n.arg for n in ast.walk(tree) if isinstance(n, ast.keyword) and n.arg
    }
    for forbidden in ("relax", "fixed_point", "rollback", "iterate", "residual"):
        assert not any(forbidden in name for name in identifiers), forbidden

    # the feedback resistance was computed and NOT fed back
    assert executed.resistance_after != executed.resistance_before
    resistor = executed.electrical_result.provenance.inputs[
        resistance_name(SYSTEM.component_id)
    ]
    assert resistor.magnitude == pytest.approx(
        executed.resistance_before.magnitude, rel=1e-12
    )


def test_j2_no_new_convergence_state_member_was_added():
    from src.engcore.scientific.solvers.protocol import ConvergenceState

    assert {s.value for s in ConvergenceState} == {
        "not_applicable", "converged", "not_converged",
        "max_iterations", "diverged", "failed",
    }


def test_j3_a_closed_form_evaluation_reports_not_applicable(executed):
    """The core's own distinction, honoured rather than quietly ignored.

    ``NOT_APPLICABLE`` is for direct evaluation, which neither converges nor
    fails to. Both new solvers are closed-form, so reporting ``CONVERGED``
    would claim a numerical property neither of them has. The electrical MNA
    solve is a genuine linear solve and legitimately reports ``CONVERGED``.
    """
    from src.engcore.scientific.solvers.protocol import ConvergenceState

    assert executed.property_result.convergence is ConvergenceState.NOT_APPLICABLE
    assert executed.thermal_result.convergence is ConvergenceState.NOT_APPLICABLE
    assert executed.electrical_result.convergence is ConvergenceState.CONVERGED


# =====================================================================
# TEST K — the predicted configuration/state conflation
# =====================================================================

def test_k_the_electrical_domain_refuses_a_temperature_updated_resistance(executed):
    """prereg §10 TEST K, predicted before running: **it is refused.**

    ``resistance_ohm`` is part of ``DCCircuit``'s canonical identity and its
    fingerprint, so the same resistor at a second temperature is a different
    physical system as far as the electrical domain is concerned. Recorded, not
    repaired: changing the canonical form would move a fingerprint.
    """
    electrical = executed.problems[0]
    cold = SYSTEM.circuit_at(executed.resistance_before)
    hot = SYSTEM.circuit_at(executed.resistance_after)
    assert cold.fingerprint() != hot.fingerprint()

    solver = ElectricalDCSolver()
    solver.bind_circuit(cold, electrical.problem_id)
    with pytest.raises(CircuitBindingError):
        solver.bind_circuit(hot, electrical.problem_id)


def test_k2_a_thermal_control_may_be_rebound_because_it_is_not_identity():
    """The contrast: an imposed control is an operating point, not a system."""
    problem = lump.build_lumped_thermal_problem(BODY)
    solver = lump.LumpedThermalSolver()
    solver.bind_body(BODY, problem.problem_id, heat_input=Quantity(1.0, "watt"))
    solver.bind_body(BODY, problem.problem_id, heat_input=Quantity(2.0, "watt"))
    other = lump.ThermalBody(
        body_id="B2",
        heat_capacity=Quantity(5.0, "joule/kelvin"),
        ambient_conductance=Quantity(0.05, "watt/kelvin"),
        ambient_temperature=Quantity(300.0, "kelvin"),
        initial_temperature=Quantity(300.0, "kelvin"),
        duration=Quantity(120.0, "second"),
    )
    with pytest.raises(InvalidScientificProblem):
        solver.bind_body(other, problem.problem_id, heat_input=Quantity(1.0, "watt"))


# =====================================================================
# TEST L — model binding by exact name
# =====================================================================

def test_l_check_against_cannot_bind_a_reusable_model_to_an_instance_problem(
    executed,
):
    """prereg §10 TEST L, predicted before running: **MISSING issues.**

    ``check_against`` matches input names exactly. A reusable model declares
    generic names; a multi-instance domain names its quantities per instance.
    The existing electrical domain therefore cannot use this check at all, and
    does not.
    """
    electrical = executed.problems[0]
    report = RESISTOR_OHM_MODEL.check_against(electrical)
    assert not report.is_satisfied
    assert {i.name for i in report.missing} == {"resistance", "voltage_across"}

    # A single-instance problem with generic names binds cleanly, which is why
    # the property and thermal models can use the check and the DC one cannot.
    assert mat.LINEAR_TCR_MODEL.check_against(executed.problems[1]).is_satisfied
    assert lump.LUMPED_CAPACITY_MODEL.check_against(
        executed.problems[2]
    ).is_satisfied
