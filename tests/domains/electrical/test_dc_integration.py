"""Integration: model binding, solver registry, result/provenance structure.

This is where the V0.0.1 Scientific Core hardening gets exercised by a real
domain rather than by synthetic fixtures.
"""

from __future__ import annotations

import json
import sys

from src.engcore.domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ELECTRICAL_DC_LINEAR,
    ElectricalDCSolver,
    ElectricalNode,
    IDEAL_VOLTAGE_SOURCE_MODEL,
    RESISTOR_OHM_MODEL,
    Resistor,
    build_dc_model_registry,
    build_dc_problem,
    resistor_relation_problem,
    solve_circuit,
    voltage_source_relation_problem,
)
from src.engcore.scientific import (
    AmbiguousSolverError,
    BindingIssueKind,
    CategoricalValue,
    ConvergenceState,
    CoreCapabilities,
    ModelType,
    ModelValidationStatus,
    ProvenanceRecord,
    Quantity,
    ScientificParameter,
    ScientificProblem,
    ScientificResult,
    ScientificVariable,
    SolverIdentity,
    SolverNotFoundError,
    SolverRegistry,
    UncertaintyKind,
    ValidationLevel,
    ValidationOutcome,
    ValueKind,
    VariableRole,
)


def _raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return True
    except Exception as other:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_type.__name__}, got {type(other).__name__}: {other}"
        ) from other
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


GND = ElectricalNode("gnd", is_reference=True)


def _divider() -> DCCircuit:
    return DCCircuit(
        circuit_id="divider",
        nodes=(GND, ElectricalNode("top"), ElectricalNode("mid")),
        resistors=(
            Resistor("R1", "top", "mid", Quantity(1.0, "kohm")),
            Resistor("R2", "mid", "gnd", Quantity(3.0, "kohm")),
        ),
        voltage_sources=(
            DCVoltageSource("V1", "top", "gnd", Quantity(12.0, "volt")),
        ),
    )


# ---- scientific models -------------------------------------------------

def test_dc_models_are_registered_and_honest():
    registry = build_dc_model_registry()
    assert len(registry) == 4
    resistor_model = registry.get("electrical.dc.resistor_ohm", "0.1.0")
    assert resistor_model.model_type is ModelType.CONSTITUTIVE_MODEL

    kcl = registry.get("electrical.dc.kcl", "0.1.0")
    assert kcl.model_type is ModelType.FUNDAMENTAL_RELATION

    source = registry.get("electrical.dc.ideal_voltage_source", "0.1.0")
    assert source.model_type is ModelType.APPROXIMATION

    current_source = registry.get("electrical.dc.ideal_current_source", "0.1.0")
    assert current_source.model_type is ModelType.APPROXIMATION

    for model in registry:
        # Passing unit tests is not experimental validation, and no external
        # benchmark process exists for this domain yet.
        assert model.validation_status is ModelValidationStatus.SELF_CONSISTENT
        assert model.references == ()   # citations are not invented
        assert model.assumptions


def test_model_registry_instances_are_independent():
    first, second = build_dc_model_registry(), build_dc_model_registry()
    first.unregister("electrical.dc.kcl", "0.1.0")
    assert len(first) == 3 and len(second) == 4


# ---- model binding under a real domain --------------------------------

def test_resistor_model_binds_to_a_real_component():
    resistor = Resistor("R1", "a", "b", Quantity(1.0, "kohm"))
    report = RESISTOR_OHM_MODEL.check_against(resistor_relation_problem(resistor))
    assert report.is_satisfied, [i.detail for i in report.issues]
    assert set(report.valid_bindings) == {"resistance", "voltage_across"}


def test_resistor_model_rejects_resistance_with_wrong_dimension():
    """The hardening this proves: a parameter *named* resistance but carrying
    volts must not satisfy the model."""
    bad = ScientificProblem(
        problem_id="bad_resistor",
        variables=(
            ScientificVariable(
                "voltage_across", "volt", role=VariableRole.OBSERVABLE
            ),
        ),
        parameters=(
            ScientificParameter("resistance", Quantity(5.0, "volt")),
        ),
    )
    report = RESISTOR_OHM_MODEL.check_against(bad)
    assert not report.is_satisfied
    issue, = report.of_kind(BindingIssueKind.WRONG_DIMENSION)
    assert issue.name == "resistance"


def test_resistor_model_rejects_wrong_source_kind():
    """Model needs `resistance` as a parameter; supplying it as a variable
    (and the voltage as a parameter) must be reported, not tolerated."""
    swapped = ScientificProblem(
        problem_id="swapped",
        variables=(
            ScientificVariable("resistance", "ohm", role=VariableRole.OBSERVABLE),
        ),
        parameters=(
            ScientificParameter("voltage_across", Quantity(1.0, "volt")),
        ),
    )
    report = RESISTOR_OHM_MODEL.check_against(swapped)
    assert not report.is_satisfied
    kinds = {issue.kind for issue in report.issues}
    assert BindingIssueKind.WRONG_SOURCE_KIND in kinds


def test_voltage_source_model_binds_and_detects_wrong_dimension():
    source = DCVoltageSource("V1", "p", "n", Quantity(10.0, "volt"))
    good = IDEAL_VOLTAGE_SOURCE_MODEL.check_against(
        voltage_source_relation_problem(source)
    )
    assert good.is_satisfied, [i.detail for i in good.issues]

    bad = ScientificProblem(
        problem_id="bad_source",
        variables=(
            ScientificVariable(
                "terminal_voltage", "ampere", role=VariableRole.OBSERVABLE
            ),
        ),
        parameters=(ScientificParameter("source_voltage", Quantity(1.0, "volt")),),
    )
    assert not IDEAL_VOLTAGE_SOURCE_MODEL.check_against(bad).is_satisfied


def test_millivolt_source_still_binds_dimensionally():
    """Binding compares dimension, not unit string."""
    source = DCVoltageSource("V1", "p", "n", Quantity(500.0, "millivolt"))
    report = IDEAL_VOLTAGE_SOURCE_MODEL.check_against(
        voltage_source_relation_problem(source)
    )
    assert report.is_satisfied


# ---- IR mapping --------------------------------------------------------

def test_problem_carries_scientific_meaning_not_metadata():
    problem = build_dc_problem(_divider())
    names = {v.name for v in problem.variables}
    assert names == {"V:top", "V:mid", "I:V1"}
    assert all(v.role is VariableRole.OBSERVABLE for v in problem.variables)
    assert problem.design_variables == ()   # a DC analysis chooses nothing

    parameters = {p.name: p for p in problem.parameters}
    assert parameters["R:R1"].value == Quantity(1.0, "kohm")
    assert parameters["Vs:V1"].value == Quantity(12.0, "volt")

    # typed categorical parameters, not metadata strings
    assert parameters["reference_node"].kind is ValueKind.CATEGORICAL
    assert parameters["reference_node"].value.value == "gnd"
    assert parameters["analysis_type"].kind is ValueKind.CATEGORICAL

    assert ELECTRICAL_DC_LINEAR.name in problem.required_capabilities
    # only the models this circuit actually invokes: no current source here
    assert {m.model_id for m in problem.models} == {
        "electrical.dc.kcl",
        "electrical.dc.resistor_ohm",
        "electrical.dc.ideal_voltage_source",
    }
    assert "kirchhoff_current_law" in problem.validation_requirements
    # metadata carries identity only; every scientific value is in typed IR
    assert set(problem.metadata) == {
        "domain_artifact_type",
        "domain_artifact_fingerprint",
        "domain_artifact_schema",
        "domain_artifact_label",
    }
    assert problem.metadata["domain_artifact_type"] == "electrical_dc_circuit"


def test_problem_round_trips_through_the_universal_ir():
    problem = build_dc_problem(_divider())
    restored = ScientificProblem.from_dict(problem.to_dict())
    assert restored.to_dict() == problem.to_dict()


def test_validity_context_comes_from_typed_parameters():
    problem = build_dc_problem(_divider())
    context = problem.validity_context()
    assert context["reference_node"] == "gnd"
    assert context["analysis_type"] == "dc_steady_state"
    assert isinstance(context["R:R1"], Quantity)


# ---- solver registry ---------------------------------------------------

class _UnrelatedSolver:
    """A solver for a different mathematical shape entirely."""

    @property
    def identity(self):
        return SolverIdentity("other.ode", "1.0.0")

    @property
    def capabilities(self):
        return frozenset({CoreCapabilities.ODE})

    def supports(self, problem) -> bool:
        return CoreCapabilities.ODE.name in problem.required_capabilities

    def prepare(self, problem):
        raise NotImplementedError

    def solve(self, prepared):
        raise NotImplementedError

    def validate(self, prepared, raw):
        raise NotImplementedError

    def extract_metrics(self, prepared, raw):
        raise NotImplementedError


class _SecondDCSolver(ElectricalDCSolver):
    """Same capability, different identity — creates a genuine ambiguity."""

    @property
    def identity(self):
        return SolverIdentity("electrical.dc.alternative", "0.1.0")


def test_registry_resolves_the_dc_solver():
    registry = SolverRegistry([ElectricalDCSolver(), _UnrelatedSolver()])
    problem = build_dc_problem(_divider())
    resolved = registry.resolve(problem)
    assert resolved.identity.solver_id == "electrical.dc.mna"


def test_registry_rejects_an_unrelated_problem():
    registry = SolverRegistry([ElectricalDCSolver()])
    ode_problem = ScientificProblem(
        problem_id="ode",
        variables=(ScientificVariable("x", "meter"),),
        required_capabilities=frozenset({CoreCapabilities.ODE.name}),
    )
    _raises(SolverNotFoundError, registry.resolve, ode_problem)


def test_registry_reports_ambiguity_and_honours_a_selection_rule():
    registry = SolverRegistry([ElectricalDCSolver(), _SecondDCSolver()])
    problem = build_dc_problem(_divider())
    _raises(AmbiguousSolverError, registry.resolve, problem)

    chosen = registry.resolve(
        problem,
        selection_rule=lambda solvers: min(
            solvers, key=lambda s: s.identity.solver_id
        ),
    )
    assert chosen.identity.solver_id == "electrical.dc.alternative"


def test_supports_does_not_execute_a_solve():
    """supports() answers on capability alone: no circuit is bound here, so
    a solve would be impossible, yet support must still be True."""
    solver = ElectricalDCSolver()
    problem = build_dc_problem(_divider())
    assert solver.bound_circuit(problem.problem_id) is None
    assert solver.supports(problem) is True


# ---- result / provenance structure ------------------------------------

def test_result_is_a_full_scientific_record():
    result = solve_circuit(
        _divider(),
        run_id="run-integration-1",
        git_commit="0" * 40,
        timestamp="2026-01-01T00:00:00+00:00",
        environment={"python": "3.14"},
    )
    assert result.convergence is ConvergenceState.CONVERGED
    assert result.problem_id == "electrical_dc:divider"
    assert result.solver.solver_id == "electrical.dc.mna"
    assert set(result.models) == {
        ("electrical.dc.resistor_ohm", "0.1.0"),
        ("electrical.dc.kcl", "0.1.0"),
        ("electrical.dc.ideal_voltage_source", "0.1.0"),
    }
    # every reported value carries units
    assert all(isinstance(v, Quantity) for v in result.values.values())
    assert result.assumptions

    provenance = result.provenance
    assert provenance.run_id == "run-integration-1"
    assert provenance.solvers == (("electrical.dc.mna", "0.1.0"),)
    assert provenance.tolerances["kcl_atol_ampere"] > 0
    assert provenance.inputs["R:R1"] == Quantity(1.0, "kohm")
    assert provenance.metadata["formulation"] == "modified_nodal_analysis"


def test_uncertainty_remains_honestly_unknown():
    result = solve_circuit(_divider(), run_id="run-unc")
    for name in result.values:
        record = result.uncertainty_of(name)
        assert record.kind is UncertaintyKind.UNKNOWN
        assert not record.is_quantified


def test_only_established_validation_levels_are_claimed():
    result = solve_circuit(_divider(), run_id="run-levels")
    levels = result.attained_levels
    assert ValidationLevel.DIMENSIONALLY_VALID in levels
    assert ValidationLevel.NUMERICALLY_CONVERGED in levels
    # runtime analysis compares against no independent analytical evidence
    assert ValidationLevel.ANALYTICALLY_VERIFIED not in levels
    assert ValidationLevel.BENCHMARK_VALIDATED not in levels
    assert ValidationLevel.CROSS_SOLVER_VALIDATED not in levels
    assert ValidationLevel.EXPERIMENTALLY_VALIDATED not in levels


def test_result_serializes_deterministically():
    result = solve_circuit(
        _divider(), run_id="run-ser", timestamp="2026-01-01T00:00:00+00:00"
    )
    payload = result.to_dict()
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload
    restored = ScientificResult.from_dict(payload)
    assert restored.to_dict() == payload


def test_failed_circuit_still_produces_an_auditable_record():
    """A singular circuit is a scientific finding, not an exception to hide:
    the record keeps its provenance and says plainly that it failed."""
    floating = DCCircuit(
        circuit_id="floating",
        nodes=(GND, ElectricalNode("n1"), ElectricalNode("n2")),
        resistors=(Resistor("R1", "n1", "n2", Quantity(1.0, "kohm")),),
    )
    result = solve_circuit(floating, run_id="run-failed")
    assert result.convergence is ConvergenceState.FAILED
    assert result.validation.status is ValidationOutcome.FAIL
    assert isinstance(result.provenance, ProvenanceRecord)
    assert result.warnings
    assert not result.is_usable


def _all_tests():
    module = sys.modules[__name__]
    return [
        (n, getattr(module, n))
        for n in sorted(dir(module))
        if n.startswith("test_") and callable(getattr(module, n))
    ]


def main() -> int:
    failures = 0
    for name, test in _all_tests():
        try:
            test()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    total = len(_all_tests())
    print(f"dc integration: {'FAIL' if failures else 'PASS'} "
          f"({total - failures}/{total})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
