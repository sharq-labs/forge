"""Scientific Core V0 foundation tests.

Runs under pytest, and standalone via ``python -m tests.test_scientific_core``
so the suite does not depend on pytest being installed.

Deterministic and synthetic throughout: no BBOB, no COCO, no network, no
physical-domain implementation.
"""

from __future__ import annotations

import json
import sys

from src.engcore.scientific import (
    AmbiguousSolverError,
    BindingIssueKind,
    BooleanValue,
    BoundaryCondition,
    BoundaryKind,
    CandidateCodec,
    CategoricalValue,
    CategoryCondition,
    ConstraintDefinition,
    ConstraintOperator,
    ConvergenceState,
    CoreCapabilities,
    DuplicateRegistrationError,
    EvaluationStatus,
    ExperimentBudget,
    FlagCondition,
    InitialCondition,
    InputSourceKind,
    IntegerValue,
    InvalidScientificProblem,
    ModelBindingReport,
    ModelInputSpec,
    ModelNotFoundError,
    ModelOutputSpec,
    ModelReference,
    ModelRegistry,
    ModelType,
    ObjectiveDefinition,
    ObjectiveDirection,
    OptimizerAdapter,
    PreparedSolve,
    ProvenanceRecord,
    Quantity,
    RangeCondition,
    RawSolverOutput,
    ScientificCoreError,
    ScientificEvaluation,
    ScientificExperiment,
    ScientificModelDefinition,
    ScientificParameter,
    ScientificProblem,
    ScientificResult,
    ScientificValidationError,
    ScientificVariable,
    SolverIdentity,
    SolverNotFoundError,
    SolverRegistry,
    Uncertainty,
    UncertaintyKind,
    UnitCompatibilityError,
    ValidationCheck,
    ValidationLevel,
    ValidationOutcome,
    ValidationReport,
    ValidityDomain,
    ValidityStatus,
    ValueKind,
    VariableKind,
    VariableRole,
    decode_value,
    normalize_unit,
)
from src.engcore.scientific.solvers.capability import SolverCapability


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


# =====================================================================
# 23. GENERALITY — two synthetic problems through the SAME IR
# =====================================================================

def build_algebraic_problem() -> ScientificProblem:
    """Problem A: steady algebraic-style study (no time, no conditions).

    Synthetic on purpose: a 'device' with a driving level and a scale factor,
    reporting a response and a load. No physical law is implemented.
    """
    return ScientificProblem(
        problem_id="synthetic_algebraic_v0",
        name="Synthetic algebraic study",
        description="Domain-neutral steady-state study used to exercise the IR.",
        variables=(
            ScientificVariable(
                name="drive_level",
                unit="volt",
                lower=Quantity(1.0, "volt"),
                upper=Quantity(12.0, "volt"),
                role=VariableRole.DESIGN,
            ),
            ScientificVariable(
                name="scale_factor",
                unit="ohm",
                lower=Quantity(10.0, "ohm"),
                upper=Quantity(1000.0, "ohm"),
                role=VariableRole.DESIGN,
            ),
            ScientificVariable(
                name="response", unit="ampere", role=VariableRole.OBSERVABLE
            ),
        ),
        parameters=(
            ScientificParameter("ambient", Quantity(300.0, "kelvin")),
        ),
        objectives=(
            ObjectiveDefinition(
                name="minimize_load",
                metric="load",
                direction=ObjectiveDirection.MINIMIZE,
                unit="watt",
            ),
        ),
        constraints=(
            ConstraintDefinition(
                name="response_ceiling",
                metric="response",
                operator=ConstraintOperator.LESS_EQUAL,
                bound=Quantity(0.5, "ampere"),
            ),
        ),
        models=(ModelReference("synthetic.linear_response", "1.0.0"),),
        required_capabilities=frozenset({CoreCapabilities.ALGEBRAIC.name}),
    )


def build_time_state_problem() -> ScientificProblem:
    """Problem B: time-dependent state study — same top-level contract."""
    return ScientificProblem(
        problem_id="synthetic_time_state_v0",
        name="Synthetic time-state study",
        description="Domain-neutral transient study used to exercise the IR.",
        variables=(
            ScientificVariable(
                name="decay_rate",
                unit="1/second",
                lower=Quantity(0.01, "1/second"),
                upper=Quantity(5.0, "1/second"),
                role=VariableRole.DESIGN,
            ),
            ScientificVariable(
                name="state", unit="meter", role=VariableRole.STATE
            ),
        ),
        parameters=(
            ScientificParameter("horizon", Quantity(10.0, "second")),
        ),
        objectives=(
            ObjectiveDefinition(
                name="minimize_settling",
                metric="settling_time",
                direction=ObjectiveDirection.MINIMIZE,
                unit="second",
            ),
        ),
        initial_conditions=(
            InitialCondition(
                variable="state",
                value=Quantity(1.0, "meter"),
                time=Quantity(0.0, "second"),
            ),
        ),
        boundary_conditions=(
            BoundaryCondition(
                name="far_field",
                variable="state",
                kind=BoundaryKind.DIRICHLET,
                region="outer",
                value=Quantity(0.0, "meter"),
            ),
        ),
        models=(ModelReference("synthetic.first_order_decay", "1.0.0"),),
        required_capabilities=frozenset({CoreCapabilities.ODE.name}),
    )


def test_generality_same_ir_two_problem_shapes():
    algebraic = build_algebraic_problem()
    transient = build_time_state_problem()

    assert type(algebraic) is type(transient) is ScientificProblem
    assert not algebraic.is_time_dependent
    assert transient.is_time_dependent
    assert algebraic.required_capabilities != transient.required_capabilities

    # Both round-trip through the identical serialization contract.
    for problem in (algebraic, transient):
        restored = ScientificProblem.from_dict(problem.to_dict())
        assert restored.to_dict() == problem.to_dict()


# =====================================================================
# A/B/C. Problem, variable and bound validation
# =====================================================================

def test_problem_requires_id():
    _raises(InvalidScientificProblem, ScientificProblem, problem_id="  ")


def test_duplicate_variable_and_parameter_names_rejected():
    variable = ScientificVariable("x", "meter")
    _raises(
        InvalidScientificProblem,
        ScientificProblem,
        problem_id="dup",
        variables=(variable, ScientificVariable("x", "second")),
    )
    _raises(
        InvalidScientificProblem,
        ScientificProblem,
        problem_id="dup2",
        variables=(variable,),
        parameters=(ScientificParameter("x", Quantity(1.0, "meter")),),
    )


def test_invalid_bounds_rejected():
    _raises(
        InvalidScientificProblem,
        ScientificVariable,
        name="x",
        unit="meter",
        lower=Quantity(5.0, "meter"),
        upper=Quantity(1.0, "meter"),
    )
    # A non-finite bound is now refused one layer earlier, by Quantity itself.
    _raises(UnitCompatibilityError, Quantity, float("inf"), "meter")
    _raises(InvalidScientificProblem, ScientificVariable, name="", unit="meter")


def test_variable_bounds_must_match_declared_dimension():
    _raises(
        UnitCompatibilityError,
        ScientificVariable,
        name="x",
        unit="meter",
        lower=Quantity(1.0, "second"),
    )


def test_bounds_expressed_in_other_units_are_converted_not_rejected():
    variable = ScientificVariable(
        "length", "meter", lower=Quantity(10.0, "cm"), upper=Quantity(2.0, "m")
    )
    assert variable.lower.units == "meter"
    assert abs(variable.lower.magnitude - 0.1) < 1e-12


def test_categorical_variable_rules():
    ok = ScientificVariable(
        "material", "dimensionless", kind=VariableKind.CATEGORICAL,
        categories=("steel", "aluminium"),
    )
    assert ok.kind is VariableKind.CATEGORICAL
    _raises(
        InvalidScientificProblem,
        ScientificVariable,
        name="material",
        unit="dimensionless",
        kind=VariableKind.CATEGORICAL,
        categories=("steel",),
    )
    _raises(
        InvalidScientificProblem,
        ScientificVariable,
        name="x",
        unit="meter",
        categories=("a", "b"),
    )


def test_condition_must_reference_known_variable():
    _raises(
        InvalidScientificProblem,
        ScientificProblem,
        problem_id="bad_ic",
        variables=(ScientificVariable("state", "meter"),),
        initial_conditions=(
            InitialCondition(variable="ghost", value=Quantity(1.0, "meter")),
        ),
    )


def test_parameter_requires_quantity():
    _raises(InvalidScientificProblem, ScientificParameter, name="p", value=3.0)


# =====================================================================
# D/E/F. Units
# =====================================================================

def test_unit_conversion():
    assert abs(Quantity(10.0, "cm").to("m").magnitude - 0.1) < 1e-15
    assert abs(Quantity(1.0, "kilometer").magnitude_in("meter") - 1000.0) < 1e-9
    voltage = Quantity(12.0, "V")
    assert voltage.magnitude == 12.0 and voltage.dimensionality != ""
    resistance = Quantity(100.0, "ohm")
    assert resistance.is_compatible_with("ohm")


def test_dimensional_compatibility_of_compound_units():
    force = Quantity(1.0, "kg * m / s**2")
    assert force.is_compatible_with(Quantity(1.0, "newton"))
    assert abs(force.to("newton").magnitude - 1.0) < 1e-15


def test_incompatible_dimensions_rejected():
    _raises(UnitCompatibilityError, Quantity(1.0, "meter").to, "second")
    _raises(
        UnitCompatibilityError,
        lambda: Quantity(1.0, "meter") + Quantity(1.0, "kelvin"),
    )
    assert not Quantity(1.0, "volt").is_compatible_with("ampere")


def test_unparsable_and_empty_units_rejected():
    _raises(UnitCompatibilityError, Quantity, 1.0, "not_a_unit_xyz")
    _raises(UnitCompatibilityError, Quantity, 1.0, "   ")


def test_quantity_never_parses_a_bare_number():
    _raises(UnitCompatibilityError, Quantity.parse, "42")


def test_quantity_serialization_round_trip():
    quantity = Quantity(2.5, "kilogram")
    assert Quantity.from_dict(quantity.to_dict()) == quantity


# =====================================================================
# G/H. Objectives and constraints
# =====================================================================

def test_objective_serialization():
    objective = ObjectiveDefinition(
        name="minimize_mass", metric="mass",
        direction=ObjectiveDirection.MINIMIZE, unit="kilogram", weight=2.0,
    )
    payload = objective.to_dict()
    assert payload["direction"] == "minimize"
    assert ObjectiveDefinition.from_dict(payload) == objective
    assert objective.sense == -1
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload


def test_objective_rejects_nonpositive_weight():
    _raises(
        InvalidScientificProblem,
        ObjectiveDefinition,
        name="o", metric="m", direction=ObjectiveDirection.MAXIMIZE, weight=0.0,
    )


def test_constraint_unit_consistency_and_checking():
    constraint = ConstraintDefinition(
        name="temperature_limit",
        metric="temperature",
        operator=ConstraintOperator.LESS_EQUAL,
        bound=Quantity(350.0, "kelvin"),
    )
    satisfied = constraint.check(Quantity(300.0, "kelvin"))
    assert satisfied.satisfied and satisfied.margin.magnitude > 0

    violated = constraint.check(Quantity(400.0, "kelvin"))
    assert not violated.satisfied and violated.margin.magnitude < 0

    # A value in a different but compatible unit is converted, not refused.
    converted = constraint.check(Quantity(20.0, "degC"))
    assert converted.satisfied

    # An incompatible metric value is refused rather than silently compared.
    _raises(UnitCompatibilityError, constraint.check, Quantity(1.0, "volt"))
    assert ConstraintDefinition.from_dict(constraint.to_dict()) == constraint


def test_constraint_tolerance_must_share_dimension():
    _raises(
        UnitCompatibilityError,
        ConstraintDefinition,
        name="c", metric="m", operator=ConstraintOperator.LESS_EQUAL,
        bound=Quantity(1.0, "kelvin"), tolerance=Quantity(1.0, "volt"),
    )


def test_constraint_bound_must_be_quantity():
    _raises(
        InvalidScientificProblem,
        ConstraintDefinition,
        name="c", metric="m", operator=ConstraintOperator.LESS_EQUAL, bound=3.0,
    )


# =====================================================================
# I/J. Model registry and validity
# =====================================================================

def _demo_model() -> ScientificModelDefinition:
    return ScientificModelDefinition(
        model_id="synthetic.linear_response",
        version="1.0.0",
        name="Synthetic linear response",
        domain="synthetic",
        model_type=ModelType.APPROXIMATION,
        inputs=(
            ModelInputSpec(
                name="drive_level",
                source_kind=InputSourceKind.VARIABLE,
                unit_exemplar="volt",
                role=VariableRole.DESIGN,
            ),
            ModelInputSpec(
                name="scale_factor",
                source_kind=InputSourceKind.VARIABLE,
                unit_exemplar="ohm",
            ),
            ModelInputSpec(
                name="ambient",
                source_kind=InputSourceKind.PARAMETER,
                unit_exemplar="kelvin",
            ),
        ),
        outputs=(
            ModelOutputSpec(metric="response", unit_exemplar="ampere"),
            ModelOutputSpec(metric="load", unit_exemplar="watt"),
        ),
        assumptions=("synthetic demo model", "no physical law implemented"),
        validity=ValidityDomain(
            conditions=(
                RangeCondition(
                    name="ambient",
                    minimum=Quantity(250.0, "kelvin"),
                    maximum=Quantity(350.0, "kelvin"),
                ),
                CategoryCondition(name="regime", allowed=frozenset({"linear"})),
                FlagCondition(name="steady_state", expected=True),
            )
        ),
        required_capabilities=frozenset({CoreCapabilities.ALGEBRAIC.name}),
    )


def test_model_registry_register_get_duplicate():
    registry = ModelRegistry()
    model = _demo_model()
    registry.register(model)
    assert registry.get("synthetic.linear_response", "1.0.0") is model
    assert len(registry) == 1
    _raises(DuplicateRegistrationError, registry.register, model)
    _raises(ModelNotFoundError, registry.get, "synthetic.linear_response", "9.9.9")
    _raises(ModelNotFoundError, registry.get, "missing", "1.0.0")


def test_model_registry_is_not_global():
    first, second = ModelRegistry(), ModelRegistry()
    first.register(_demo_model())
    assert len(first) == 1 and len(second) == 0


def test_model_registry_listing_and_resolution():
    registry = ModelRegistry([_demo_model()])
    assert len(registry.list(domain="synthetic")) == 1
    assert len(registry.list(domain="thermal")) == 0
    assert len(registry.list(provides_metric="load")) == 1
    assert registry.versions("synthetic.linear_response") == ("1.0.0",)
    resolved = registry.resolve(ModelReference("synthetic.linear_response", "1.0.0"))
    assert resolved.model_id == "synthetic.linear_response"


def test_model_validity_states():
    model = _demo_model()

    in_domain = model.assess_validity(
        {"ambient": Quantity(300.0, "kelvin"), "regime": "linear",
         "steady_state": True}
    )
    assert in_domain.status is ValidityStatus.IN_DOMAIN

    outside = model.assess_validity(
        {"ambient": Quantity(500.0, "kelvin"), "regime": "linear",
         "steady_state": True}
    )
    assert outside.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert "ambient" in outside.violated

    unknown = model.assess_validity({"regime": "linear", "steady_state": True})
    assert unknown.status is ValidityStatus.UNKNOWN
    assert "ambient" in unknown.unknown

    wrong_regime = model.assess_validity(
        {"ambient": Quantity(300.0, "kelvin"), "regime": "turbulent",
         "steady_state": True}
    )
    assert wrong_regime.status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN


def test_empty_validity_domain_is_unknown_not_valid():
    model = ScientificModelDefinition(model_id="m", version="1")
    assert model.assess_validity({"anything": True}).status is ValidityStatus.UNKNOWN


def test_model_serialization_round_trip():
    model = _demo_model()
    assert ScientificModelDefinition.from_dict(model.to_dict()) == model


# =====================================================================
# G/H. Typed model binding (replaces name-only requirements)
# =====================================================================

def test_model_binding_accepts_correct_problem():
    report = _demo_model().check_against(build_algebraic_problem())
    assert report.is_satisfied, [i.detail for i in report.issues]
    assert set(report.valid_bindings) == {
        "drive_level", "scale_factor", "ambient"
    }


def test_model_binding_reports_missing_inputs():
    report = _demo_model().check_against(build_time_state_problem())
    assert not report.is_satisfied
    missing = {i.name for i in report.missing}
    assert {"drive_level", "scale_factor", "ambient"} <= missing


def test_model_binding_rejects_wrong_dimension():
    """The defect this contract exists to prevent: a name match in volts
    satisfying a requirement declared in kelvin."""
    model = ScientificModelDefinition(
        model_id="m", version="1",
        inputs=(
            ModelInputSpec(
                name="temperature",
                source_kind=InputSourceKind.VARIABLE,
                unit_exemplar="kelvin",
            ),
        ),
    )
    problem = ScientificProblem(
        problem_id="p", variables=(ScientificVariable("temperature", "volt"),)
    )
    report = model.check_against(problem)
    assert not report.is_satisfied
    issue, = report.of_kind(BindingIssueKind.WRONG_DIMENSION)
    assert issue.name == "temperature"


def test_model_binding_accepts_compatible_but_different_units():
    """degC and kelvin are the same dimension; exact unit strings are not
    required."""
    model = ScientificModelDefinition(
        model_id="m", version="1",
        inputs=(
            ModelInputSpec(
                name="temperature",
                source_kind=InputSourceKind.VARIABLE,
                unit_exemplar="kelvin",
            ),
        ),
    )
    problem = ScientificProblem(
        problem_id="p", variables=(ScientificVariable("temperature", "degC"),)
    )
    assert model.check_against(problem).is_satisfied


def test_model_binding_rejects_wrong_source_kind():
    """A required variable supplied as a parameter (and vice versa)."""
    as_variable = ScientificModelDefinition(
        model_id="m", version="1",
        inputs=(
            ModelInputSpec(
                name="mass", source_kind=InputSourceKind.VARIABLE,
                unit_exemplar="kilogram",
            ),
        ),
    )
    problem_with_parameter = ScientificProblem(
        problem_id="p",
        parameters=(ScientificParameter("mass", Quantity(2.0, "kilogram")),),
    )
    report = as_variable.check_against(problem_with_parameter)
    assert not report.is_satisfied
    assert report.of_kind(BindingIssueKind.WRONG_SOURCE_KIND)

    as_parameter = ScientificModelDefinition(
        model_id="m2", version="1",
        inputs=(
            ModelInputSpec(
                name="mass", source_kind=InputSourceKind.PARAMETER,
                unit_exemplar="kilogram",
            ),
        ),
    )
    problem_with_variable = ScientificProblem(
        problem_id="p2", variables=(ScientificVariable("mass", "kilogram"),)
    )
    report = as_parameter.check_against(problem_with_variable)
    assert not report.is_satisfied
    assert report.of_kind(BindingIssueKind.WRONG_SOURCE_KIND)


def test_model_binding_rejects_wrong_value_type():
    model = ScientificModelDefinition(
        model_id="m", version="1",
        inputs=(
            ModelInputSpec(
                name="phase", source_kind=InputSourceKind.PARAMETER,
                value_kind=ValueKind.CATEGORICAL,
            ),
        ),
    )
    problem = ScientificProblem(
        problem_id="p",
        parameters=(ScientificParameter("phase", BooleanValue(True)),),
    )
    report = model.check_against(problem)
    assert not report.is_satisfied
    assert report.of_kind(BindingIssueKind.WRONG_VALUE_TYPE)


def test_model_binding_rejects_wrong_role():
    model = ScientificModelDefinition(
        model_id="m", version="1",
        inputs=(
            ModelInputSpec(
                name="x", source_kind=InputSourceKind.VARIABLE,
                unit_exemplar="meter", role=VariableRole.DESIGN,
            ),
        ),
    )
    problem = ScientificProblem(
        problem_id="p",
        variables=(
            ScientificVariable("x", "meter", role=VariableRole.OBSERVABLE),
        ),
    )
    report = model.check_against(problem)
    assert not report.is_satisfied
    assert report.of_kind(BindingIssueKind.WRONG_ROLE)


def test_model_binding_optional_input_is_not_missing():
    model = ScientificModelDefinition(
        model_id="m", version="1",
        inputs=(
            ModelInputSpec(
                name="optional_hint", source_kind=InputSourceKind.PARAMETER,
                value_kind=ValueKind.BOOLEAN, required=False,
            ),
        ),
    )
    assert model.check_against(ScientificProblem(problem_id="p")).is_satisfied


def test_model_output_dimensional_check():
    """A model producing load in amperes cannot serve a problem that
    declares load in watts."""
    model = ScientificModelDefinition(
        model_id="m", version="1",
        outputs=(ModelOutputSpec(metric="load", unit_exemplar="ampere"),),
    )
    report = model.check_against(build_algebraic_problem())
    assert not report.is_satisfied
    issue, = report.of_kind(BindingIssueKind.WRONG_DIMENSION)
    assert issue.name == "load"

    # A metric the problem never references is not an error.
    unreferenced = ScientificModelDefinition(
        model_id="m2", version="1",
        outputs=(ModelOutputSpec(metric="not_requested", unit_exemplar="ampere"),),
    )
    assert unreferenced.check_against(build_algebraic_problem()).is_satisfied


def test_model_input_spec_validation_and_round_trip():
    spec = ModelInputSpec(
        name="t", source_kind=InputSourceKind.VARIABLE, unit_exemplar="kelvin"
    )
    assert spec.value_kind is ValueKind.QUANTITY  # inferred from the exemplar
    assert ModelInputSpec.from_dict(spec.to_dict()) == spec

    output = ModelOutputSpec(metric="load", unit_exemplar="watt")
    assert ModelOutputSpec.from_dict(output.to_dict()) == output

    # A quantity-valued input must state a dimension to be checkable.
    _raises(
        InvalidScientificProblem, ModelInputSpec, name="t",
        source_kind=InputSourceKind.PARAMETER, value_kind=ValueKind.QUANTITY,
    )
    # A unit exemplar is meaningless for a non-quantity input.
    _raises(
        InvalidScientificProblem, ModelInputSpec, name="t",
        source_kind=InputSourceKind.PARAMETER, unit_exemplar="kelvin",
        value_kind=ValueKind.BOOLEAN,
    )
    # Role applies to variables only.
    _raises(
        InvalidScientificProblem, ModelInputSpec, name="t",
        source_kind=InputSourceKind.PARAMETER, value_kind=ValueKind.BOOLEAN,
        role=VariableRole.DESIGN,
    )
    _raises(UnitCompatibilityError, ModelInputSpec, name="t",
            source_kind=InputSourceKind.VARIABLE, unit_exemplar="not_a_unit_xyz")


def test_model_binding_report_round_trip():
    report = _demo_model().check_against(build_time_state_problem())
    assert ModelBindingReport.from_dict(report.to_dict()) == report


# =====================================================================
# K. Solver registry
# =====================================================================

class _DemoSolver:
    """Minimal solver satisfying the protocol. No science implemented."""

    def __init__(self, solver_id: str, capabilities, version: str = "1.0.0"):
        self._identity = SolverIdentity(solver_id, version, backend="synthetic")
        self._capabilities = frozenset(capabilities)

    @property
    def identity(self) -> SolverIdentity:
        return self._identity

    @property
    def capabilities(self):
        return self._capabilities

    def supports(self, problem) -> bool:
        declared = {c.name for c in self._capabilities}
        return set(problem.required_capabilities).issubset(declared)

    def prepare(self, problem) -> PreparedSolve:
        return PreparedSolve(problem=problem, solver=self._identity)

    def solve(self, prepared: PreparedSolve) -> RawSolverOutput:
        return RawSolverOutput(
            convergence=ConvergenceState.NOT_APPLICABLE, values={"load": 1.0}
        )

    def validate(self, prepared, raw) -> ValidationReport:
        return ValidationReport(
            checks=(
                ValidationCheck(
                    name="dimensional_consistency",
                    outcome=ValidationOutcome.PASS,
                    establishes=ValidationLevel.DIMENSIONALLY_VALID,
                ),
            )
        )

    def extract_metrics(self, prepared, raw):
        return {"load": Quantity(raw.values["load"], "watt")}


def test_solver_registry_no_match():
    registry = SolverRegistry()
    _raises(SolverNotFoundError, registry.resolve, build_algebraic_problem())

    registry.register(_DemoSolver("ode_only", {CoreCapabilities.ODE}))
    _raises(SolverNotFoundError, registry.resolve, build_algebraic_problem())


def test_solver_registry_single_match():
    registry = SolverRegistry([_DemoSolver("algebraic", {CoreCapabilities.ALGEBRAIC})])
    solver = registry.resolve(build_algebraic_problem())
    assert solver.identity.solver_id == "algebraic"


def test_solver_registry_ambiguous_match():
    registry = SolverRegistry(
        [
            _DemoSolver("first", {CoreCapabilities.ALGEBRAIC}),
            _DemoSolver("second", {CoreCapabilities.ALGEBRAIC}),
        ]
    )
    problem = build_algebraic_problem()
    _raises(AmbiguousSolverError, registry.resolve, problem)

    # An explicit rule resolves it — the choice is recorded, never implicit.
    chosen = registry.resolve(
        problem,
        selection_rule=lambda solvers: min(
            solvers, key=lambda s: s.identity.solver_id
        ),
    )
    assert chosen.identity.solver_id == "first"


def test_solver_registry_duplicate_and_capabilities():
    solver = _DemoSolver("algebraic", {CoreCapabilities.ALGEBRAIC})
    registry = SolverRegistry([solver])
    _raises(DuplicateRegistrationError, registry.register, solver)
    assert registry.capability_names() == (CoreCapabilities.ALGEBRAIC.name,)
    registry.unregister("algebraic", "1.0.0")
    assert len(registry) == 0
    _raises(SolverNotFoundError, registry.unregister, "algebraic", "1.0.0")


def test_capability_identifier_is_extensible():
    domain_capability = SolverCapability("electrical:dc", "future domain capability")
    registry = SolverRegistry([_DemoSolver("dc", {domain_capability})])
    problem = ScientificProblem(
        problem_id="future_domain",
        variables=(ScientificVariable("v", "volt"),),
        required_capabilities=frozenset({"electrical:dc"}),
    )
    assert registry.resolve(problem).identity.solver_id == "dc"
    _raises(ScientificCoreError, SolverCapability, "has whitespace")


# =====================================================================
# L/M/N. Result, validation report, provenance
# =====================================================================

def _provenance() -> ProvenanceRecord:
    return ProvenanceRecord(
        run_id="run-0001",
        software_version="scientific-core-v0",
        git_commit="0" * 40,
        models=(("synthetic.linear_response", "1.0.0"),),
        solvers=(("algebraic", "1.0.0"),),
        inputs={"drive_level": Quantity(5.0, "volt")},
        assumptions=("synthetic demo",),
        tolerances={"rtol": 1e-9},
        environment={"python": "3.x"},
        timestamp="2026-01-01T00:00:00+00:00",
    )


def _result(**overrides) -> ScientificResult:
    payload = dict(
        result_id="res-0001",
        problem_id="synthetic_algebraic_v0",
        values={"load": Quantity(2.5, "watt"), "response": Quantity(0.1, "ampere")},
        models=(("synthetic.linear_response", "1.0.0"),),
        solver=SolverIdentity("algebraic", "1.0.0"),
        convergence=ConvergenceState.NOT_APPLICABLE,
        validation=ValidationReport(
            checks=(
                ValidationCheck(
                    name="dimensional_consistency",
                    outcome=ValidationOutcome.PASS,
                    establishes=ValidationLevel.DIMENSIONALLY_VALID,
                ),
            )
        ),
        uncertainty={"load": Uncertainty.unknown("not evaluated in V0")},
        assumptions=("synthetic demo",),
        provenance=_provenance(),
    )
    payload.update(overrides)
    return ScientificResult(**payload)


def test_result_serialization_round_trip():
    result = _result()
    payload = result.to_dict()
    restored = ScientificResult.from_dict(payload)
    assert restored.to_dict() == payload
    assert json.loads(json.dumps(payload, sort_keys=True)) == payload
    assert restored.value("load").units == "watt"


def test_result_rejects_bare_numbers_and_missing_provenance():
    _raises(ScientificCoreError, _result, values={"load": 2.5})
    _raises(
        ScientificCoreError, ScientificResult, result_id="r", values={},
        provenance=None,
    )


def test_result_uncertainty_defaults_to_unknown():
    result = _result()
    assert result.uncertainty_of("load").kind is UncertaintyKind.UNKNOWN
    assert result.uncertainty_of("response").kind is UncertaintyKind.UNKNOWN
    assert not result.uncertainty_of("response").is_quantified


def test_result_unit_check_against_problem():
    problem = build_algebraic_problem()
    _result().check_units_against(problem.metric_units())
    bad = _result(values={"load": Quantity(2.5, "ampere")})
    _raises(UnitCompatibilityError, bad.check_units_against, problem.metric_units())


def test_validation_report_states():
    empty = ValidationReport()
    assert empty.status is ValidationOutcome.NOT_RUN
    assert empty.attained_levels == frozenset()

    mixed = ValidationReport(
        checks=(
            ValidationCheck("a", ValidationOutcome.PASS,
                            establishes=ValidationLevel.DIMENSIONALLY_VALID),
            ValidationCheck("b", ValidationOutcome.WARNING),
            ValidationCheck("c", ValidationOutcome.NOT_RUN),
        )
    )
    assert mixed.status is ValidationOutcome.WARNING
    assert len(mixed.warnings) == 1 and len(mixed.not_run) == 1

    failed = mixed.with_check(ValidationCheck("d", ValidationOutcome.FAIL))
    assert failed.status is ValidationOutcome.FAIL
    assert len(failed.failures) == 1


def test_validation_level_requires_a_passing_check():
    """Guardrail: a result may not claim validation that was not performed."""
    not_run = ValidationReport(
        checks=(
            ValidationCheck(
                "benchmark", ValidationOutcome.NOT_RUN,
                establishes=ValidationLevel.BENCHMARK_VALIDATED,
            ),
        )
    )
    assert not not_run.claims(ValidationLevel.BENCHMARK_VALIDATED)
    _raises(
        ScientificValidationError,
        not_run.require_level,
        ValidationLevel.BENCHMARK_VALIDATED,
    )

    failed = ValidationReport(
        checks=(
            ValidationCheck(
                "benchmark", ValidationOutcome.FAIL,
                establishes=ValidationLevel.BENCHMARK_VALIDATED,
            ),
        )
    )
    assert not failed.claims(ValidationLevel.BENCHMARK_VALIDATED)

    passed = ValidationReport(
        checks=(
            ValidationCheck(
                "benchmark", ValidationOutcome.PASS,
                establishes=ValidationLevel.BENCHMARK_VALIDATED,
            ),
        )
    )
    assert passed.claims(ValidationLevel.BENCHMARK_VALIDATED)
    passed.require_level(ValidationLevel.BENCHMARK_VALIDATED)


def test_forged_validation_claim_is_rejected_on_load():
    payload = ValidationReport(
        checks=(ValidationCheck("x", ValidationOutcome.NOT_RUN),)
    ).to_dict()
    payload["attained_levels"] = ["experimentally_validated"]
    _raises(ScientificValidationError, ValidationReport.from_dict, payload)


def test_validation_report_round_trip_and_duplicate_names():
    report = ValidationReport(
        checks=(
            ValidationCheck("a", ValidationOutcome.PASS,
                            establishes=ValidationLevel.NUMERICALLY_CONVERGED,
                            residual=1e-12, tolerance=1e-9),
        )
    )
    assert ValidationReport.from_dict(report.to_dict()) == report
    _raises(
        ScientificValidationError,
        ValidationReport,
        checks=(
            ValidationCheck("a", ValidationOutcome.PASS),
            ValidationCheck("a", ValidationOutcome.FAIL),
        ),
    )


def test_uncertainty_rules():
    unknown = Uncertainty.unknown()
    assert unknown.kind is UncertaintyKind.UNKNOWN and not unknown.is_quantified

    standard = Uncertainty(
        kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(0.1, "watt"),
        method="linearized_least_squares",
    )
    assert standard.is_quantified
    assert Uncertainty.from_dict(standard.to_dict()) == standard

    # UNKNOWN must not smuggle values, and quantified kinds must state a method.
    _raises(
        Exception, Uncertainty, kind=UncertaintyKind.UNKNOWN,
        standard_uncertainty=Quantity(0.1, "watt"),
    )
    _raises(
        Exception, Uncertainty, kind=UncertaintyKind.STANDARD,
        standard_uncertainty=Quantity(0.1, "watt"),
    )
    _raises(ScientificCoreError, Uncertainty, kind=UncertaintyKind.INTERVAL,
            lower=Quantity(1.0, "watt"), method="m")


def test_provenance_deterministic_round_trip():
    record = _provenance()
    payload = record.to_dict()
    restored = ProvenanceRecord.from_dict(payload)
    assert restored == record
    assert restored.to_dict() == payload
    # Deterministic: identical inputs serialize byte-identically.
    assert json.dumps(payload, sort_keys=True) == json.dumps(
        ProvenanceRecord.from_dict(payload).to_dict(), sort_keys=True
    )


def test_provenance_requires_units_and_run_id():
    _raises(ScientificCoreError, ProvenanceRecord, run_id="")
    _raises(ScientificCoreError, ProvenanceRecord, run_id="r", inputs={"x": 1.0})


def test_provenance_lineage():
    parent = _provenance()
    child = parent.derived("run-0002")
    assert child.parent_run_id == parent.run_id and child.run_id == "run-0002"


# =====================================================================
# O. Experiment and evaluation
# =====================================================================

def _evaluation(index: int, load: float, status=EvaluationStatus.OK):
    problem = build_algebraic_problem()
    constraint = problem.constraints[0]
    result = _result(result_id=f"res-{index}") if status is EvaluationStatus.OK else None
    return ScientificEvaluation(
        evaluation_id=f"eval-{index}",
        candidate={
            "drive_level": Quantity(5.0, "volt"),
            "scale_factor": Quantity(100.0, "ohm"),
        },
        status=status,
        result=result,
        objective_values={"minimize_load": Quantity(load, "watt")},
        constraint_checks=(constraint.check(Quantity(0.1, "ampere")),),
    )


def test_experiment_records_and_budget():
    problem = build_algebraic_problem()
    experiment = ScientificExperiment(
        "exp-0001", problem, ExperimentBudget(max_observations=2)
    )
    assert experiment.remaining_observations == 2

    experiment.record(_evaluation(1, 5.0))
    experiment.record(_evaluation(2, 3.0))
    assert experiment.observations == 2 and experiment.remaining_observations == 0
    assert experiment.is_exhausted
    _raises(ScientificCoreError, experiment.record, _evaluation(3, 1.0))


def test_experiment_failed_evaluation_does_not_consume_observation_budget():
    problem = build_algebraic_problem()
    experiment = ScientificExperiment(
        "exp-0002", problem, ExperimentBudget(max_observations=1, max_attempts=3)
    )
    experiment.record(_evaluation(1, 5.0, status=EvaluationStatus.FAILED))
    assert experiment.attempts == 1
    assert experiment.observations == 0
    assert experiment.failures == 1
    assert experiment.remaining_observations == 1


def test_experiment_best_respects_direction():
    problem = build_algebraic_problem()
    experiment = ScientificExperiment(
        "exp-0003", problem, ExperimentBudget(max_observations=5)
    )
    experiment.record(_evaluation(1, 5.0))
    experiment.record(_evaluation(2, 2.0))
    experiment.record(_evaluation(3, 9.0))
    best = experiment.best("minimize_load")
    assert best is not None and best.evaluation_id == "eval-2"
    _raises(ScientificCoreError, experiment.best, "no_such_objective")


def test_experiment_round_trip_and_objective_subset_rule():
    problem = build_algebraic_problem()
    experiment = ScientificExperiment(
        "exp-0004", problem, ExperimentBudget(max_observations=3)
    )
    experiment.record(_evaluation(1, 4.0))
    payload = experiment.to_dict()
    restored = ScientificExperiment.from_dict(payload)
    assert restored.to_dict() == payload
    assert restored.observations == 1

    foreign = ObjectiveDefinition(
        name="not_declared", metric="x", direction=ObjectiveDirection.MAXIMIZE
    )
    _raises(
        ScientificCoreError, ScientificExperiment, "exp-bad", problem,
        ExperimentBudget(max_observations=1), objectives=(foreign,),
    )


def test_failed_evaluation_may_not_carry_a_result():
    _raises(
        ScientificCoreError, ScientificEvaluation, evaluation_id="e",
        candidate={}, status=EvaluationStatus.FAILED, result=_result(),
    )


def test_ok_evaluation_requires_a_result():
    _raises(
        ScientificCoreError, ScientificEvaluation, evaluation_id="e",
        candidate={}, status=EvaluationStatus.OK,
    )


# =====================================================================
# P. Optimizer adapter
# =====================================================================

def test_codec_round_trip_scientific_to_vector_to_scientific():
    problem = build_algebraic_problem()
    codec = CandidateCodec.from_problem(problem)
    assert codec.dimension == 2
    assert codec.names == ("drive_level", "scale_factor")

    candidate = {
        "drive_level": Quantity(6.5, "volt"),
        "scale_factor": Quantity(505.0, "ohm"),
    }
    vector = codec.encode(candidate)
    assert all(0.0 <= v <= 1.0 for v in vector)

    restored = codec.decode(vector)
    for name, value in candidate.items():
        assert restored[name].units == value.units
        assert abs(restored[name].magnitude - value.magnitude) < 1e-9


def test_codec_accepts_compatible_units_and_rejects_bare_numbers():
    problem = build_algebraic_problem()
    codec = CandidateCodec.from_problem(problem)
    vector = codec.encode(
        {
            "drive_level": Quantity(6500.0, "millivolt"),  # == 6.5 V
            "scale_factor": Quantity(0.505, "kiloohm"),    # == 505 ohm
        }
    )
    restored = codec.decode(vector)
    assert abs(restored["drive_level"].magnitude - 6.5) < 1e-9
    assert abs(restored["scale_factor"].magnitude - 505.0) < 1e-6

    _raises(
        ScientificCoreError, codec.encode,
        {"drive_level": 6.5, "scale_factor": Quantity(1.0, "ohm")},
    )
    _raises(ScientificCoreError, codec.decode, (0.5,))


def test_codec_requires_bounded_continuous_variables():
    unbounded = ScientificProblem(
        problem_id="unbounded",
        variables=(ScientificVariable("x", "meter"),),
    )
    _raises(InvalidScientificProblem, CandidateCodec.from_problem, unbounded)

    categorical = ScientificProblem(
        problem_id="categorical",
        variables=(
            ScientificVariable(
                "material", "dimensionless", kind=VariableKind.CATEGORICAL,
                categories=("a", "b"), lower=Quantity(0.0, "dimensionless"),
                upper=Quantity(1.0, "dimensionless"),
            ),
        ),
    )
    _raises(InvalidScientificProblem, CandidateCodec.from_problem, categorical)


def test_optimizer_adapter_encodes_objective_direction():
    problem = build_algebraic_problem()
    adapter = OptimizerAdapter.for_problem(problem)
    # The declared objective minimizes; a search backend that maximizes must
    # therefore receive a negated score.
    assert adapter.objective.sense == -1
    assert adapter.objective.encode(Quantity(3.0, "watt")) == -3.0
    assert adapter.objective.decode(-3.0) == Quantity(3.0, "watt")
    assert adapter.objective.encode(Quantity(3000.0, "milliwatt")) == -3.0
    _raises(ScientificCoreError, adapter.objective.encode, 3.0)
    assert adapter.to_dict()["objective_sense"] == -1


def test_optimizer_adapter_refuses_silent_objective_choice():
    problem = build_algebraic_problem()
    two_objectives = ScientificProblem(
        problem_id=problem.problem_id,
        variables=problem.variables,
        objectives=(
            problem.objectives[0],
            ObjectiveDefinition(
                name="maximize_response", metric="response",
                direction=ObjectiveDirection.MAXIMIZE, unit="ampere",
            ),
        ),
    )
    _raises(InvalidScientificProblem, OptimizerAdapter.for_problem, two_objectives)
    chosen = OptimizerAdapter.for_problem(two_objectives, "maximize_response")
    assert chosen.objective.sense == 1


def test_adapter_drives_a_synthetic_search_backend_end_to_end():
    """Scientific candidate -> vector -> backend -> vector -> candidate.

    Uses a deterministic stub backend: the core must never import a concrete
    optimizer, so the contract is what is tested.
    """
    problem = build_algebraic_problem()
    adapter = OptimizerAdapter.for_problem(problem)

    class _StubBackend:
        def __init__(self):
            self.told: list[tuple[tuple[float, ...], float]] = []
            self._grid = [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]

        def ask(self, count: int = 1):
            return [self._grid[len(self.told) % len(self._grid)]] * count

        def tell(self, points, scores):
            for point, score in zip(points, scores):
                self.told.append((tuple(point), float(score)))

    backend = _StubBackend()
    for _ in range(3):
        (point,) = backend.ask(1)
        candidate = adapter.codec.decode(point)
        # A "simulator" stands in here; the core does not implement science.
        load = Quantity(
            candidate["drive_level"].magnitude
            * candidate["scale_factor"].magnitude
            / 1000.0,
            "watt",
        )
        backend.tell([point], [adapter.objective.encode(load)])

    assert len(backend.told) == 3
    # Minimization: the best score corresponds to the smallest physical load.
    best_point, best_score = max(backend.told, key=lambda item: item[1])
    best_candidate = adapter.codec.decode(best_point)
    assert best_candidate["drive_level"].units == "volt"
    assert best_score <= 0.0


# =====================================================================
# 24. Architectural guardrails
# =====================================================================

def test_scientific_core_has_no_ai_or_platform_dependencies():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "engcore" / "scientific"
    banned = (
        "openai", "anthropic", "google.generativeai", "gemini", "cohere",
        "langchain", "fastapi", "flask", "django", "sqlalchemy", "torch",
        "bbob", "cocoex",
    )
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                for name in banned:
                    if name in stripped:
                        offenders.append(f"{path.name}: {stripped}")
    assert not offenders, f"forbidden imports in Scientific Core: {offenders}"


def test_scientific_core_contains_no_eval_or_exec():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "engcore" / "scientific"
    offenders = []
    for path in root.rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "eval(" in stripped or "exec(" in stripped:
                offenders.append(f"{path.name}:{number}")
    assert not offenders, f"dynamic execution found: {offenders}"


def test_scientific_core_does_not_import_the_optimizer_stack():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "engcore" / "scientific"
    banned = ("stacked_engine", "adaptive_stacked", "logei_engine", "validation.")
    offenders = []
    for path in root.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                for name in banned:
                    if name in stripped:
                        offenders.append(f"{path.name}: {stripped}")
    assert not offenders, f"Scientific Core must not bind to an optimizer: {offenders}"


# =====================================================================
# V0.0.1 HARDENING — adversarial tests for each confirmed defect
# =====================================================================

NAN = float("nan")
POS_INF = float("inf")
NEG_INF = float("-inf")


# ---- A/B/C/D. non-finite policy, by layer ---------------------------

def test_quantity_rejects_non_finite():
    for bad in (NAN, POS_INF, NEG_INF):
        _raises(UnitCompatibilityError, Quantity, bad, "meter")


def test_non_finite_cannot_reach_interpreted_science():
    """One invariant in Quantity closes every downstream layer at once.

    Each case is deferred through a lambda because the rejection now happens
    at Quantity construction — which is precisely the point: a non-finite
    value cannot even be *expressed* as a scientific quantity, so it can
    never be handed to a parameter, bound, result or provenance record.
    """
    cases = {
        "parameter": lambda: ScientificParameter("p", Quantity(NAN, "meter")),
        "constraint bound": lambda: ConstraintDefinition(
            name="c", metric="m", operator=ConstraintOperator.LESS_EQUAL,
            bound=Quantity(NAN, "kelvin"),
        ),
        "constraint tolerance": lambda: ConstraintDefinition(
            name="c", metric="m", operator=ConstraintOperator.LESS_EQUAL,
            bound=Quantity(1.0, "kelvin"), tolerance=Quantity(NAN, "kelvin"),
        ),
        "uncertainty": lambda: Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(NAN, "watt"), method="m",
        ),
        "result value": lambda: ScientificResult(
            result_id="r", values={"v": Quantity(NAN, "watt")},
            provenance=ProvenanceRecord(run_id="r"),
        ),
        "provenance input": lambda: ProvenanceRecord(
            run_id="r", inputs={"i": Quantity(POS_INF, "meter")},
        ),
        "initial condition": lambda: InitialCondition(
            variable="s", value=Quantity(NAN, "meter"),
        ),
        "variable bound": lambda: ScientificVariable(
            "x", "meter", lower=Quantity(NEG_INF, "meter"),
        ),
    }
    for label, construct in cases.items():
        try:
            construct()
        except UnitCompatibilityError:
            continue
        raise AssertionError(f"non-finite value accepted by {label}")


def test_raw_solver_output_still_permits_non_finite():
    """A diverged backend must be able to report NaN honestly."""
    raw = RawSolverOutput(
        convergence=ConvergenceState.DIVERGED,
        values={"x": NAN, "y": POS_INF},
        residuals={"r": NAN},
    )
    assert raw.values["x"] != raw.values["x"]      # NaN preserved
    assert raw.values["y"] == POS_INF
    assert not raw.succeeded
    assert RawSolverOutput.from_dict(raw.to_dict()).convergence is (
        ConvergenceState.DIVERGED
    )


def test_objective_weight_rejects_non_finite():
    for bad in (NAN, POS_INF, NEG_INF):
        _raises(
            InvalidScientificProblem, ObjectiveDefinition, name="o",
            metric="m", direction=ObjectiveDirection.MINIMIZE, weight=bad,
        )


def test_solver_tolerance_rejects_non_finite():
    from src.engcore.scientific import SolverSettings

    for bad in (NAN, POS_INF, NEG_INF):
        _raises(ScientificCoreError, SolverSettings, tolerances={"rtol": bad})
    assert SolverSettings(tolerances={"rtol": 1e-9}).tolerances["rtol"] == 1e-9


# ---- E/F. typed scientific values ------------------------------------

def test_typed_parameter_round_trips():
    cases = {
        "mass": Quantity(2.0, "kilogram"),
        "segment_count": IntegerValue(5),
        "steady_state": BooleanValue(True),
        "material": CategoricalValue("aluminum", vocabulary=("aluminum", "steel")),
    }
    for name, value in cases.items():
        parameter = ScientificParameter(name, value)
        restored = ScientificParameter.from_dict(parameter.to_dict())
        assert restored == parameter
        assert type(restored.value) is type(value)   # type preserved
        assert json.loads(json.dumps(parameter.to_dict(), sort_keys=True)) == (
            parameter.to_dict()
        )

    kinds = {
        n: ScientificParameter(n, v).kind for n, v in cases.items()
    }
    assert kinds == {
        "mass": ValueKind.QUANTITY,
        "segment_count": ValueKind.INTEGER,
        "steady_state": ValueKind.BOOLEAN,
        "material": ValueKind.CATEGORICAL,
    }


def test_typed_values_reject_invalid_payloads():
    # bool is an int subclass; the union must not erase the distinction
    _raises(InvalidScientificProblem, IntegerValue, True)
    _raises(InvalidScientificProblem, IntegerValue, 1.5)
    _raises(InvalidScientificProblem, BooleanValue, 1)
    _raises(InvalidScientificProblem, CategoricalValue, "")
    _raises(
        InvalidScientificProblem, CategoricalValue, "copper",
        vocabulary=("aluminum", "steel"),
    )
    # raw python objects are still refused as parameter values
    _raises(InvalidScientificProblem, ScientificParameter, "p", "aluminum")
    _raises(InvalidScientificProblem, ScientificParameter, "p", True)
    _raises(InvalidScientificProblem, ScientificParameter, "p", 5)
    _raises(InvalidScientificProblem, ScientificParameter, "p", object())
    # unknown / mistyped serialized payloads
    _raises(ScientificCoreError, decode_value, {"schema": "bogus/1", "value": 1})
    _raises(
        InvalidScientificProblem, IntegerValue.from_dict,
        {"schema": "integer_value/1", "value": True},
    )


def test_validity_context_derives_from_typed_parameters():
    problem = ScientificProblem(
        problem_id="ctx",
        parameters=(
            ScientificParameter("ambient", Quantity(300.0, "kelvin")),
            ScientificParameter("regime", CategoricalValue("linear")),
            ScientificParameter("steady_state", BooleanValue(True)),
        ),
    )
    context = problem.validity_context()
    assert context["regime"] == "linear"
    assert context["steady_state"] is True
    assert isinstance(context["ambient"], Quantity)

    model = _demo_model()
    assert model.assess_validity(context).status is ValidityStatus.IN_DOMAIN

    # callers extend explicitly; metadata is not a secret channel
    extended = problem.validity_context({"regime": "turbulent"})
    assert model.assess_validity(extended).status is (
        ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )


# ---- I. constraint operator boundaries -------------------------------

def test_constraint_operators_at_exact_boundary_zero_tolerance():
    """x == b with tolerance 0: strict operators must FAIL."""
    expected = {
        ConstraintOperator.LESS_THAN: False,
        ConstraintOperator.LESS_EQUAL: True,
        ConstraintOperator.GREATER_THAN: False,
        ConstraintOperator.GREATER_EQUAL: True,
        ConstraintOperator.EQUAL: True,
    }
    for operator, should_pass in expected.items():
        constraint = ConstraintDefinition(
            name="c", metric="x", operator=operator,
            bound=Quantity(10.0, "kelvin"),
        )
        check = constraint.check(Quantity(10.0, "kelvin"))
        assert check.satisfied is should_pass, f"{operator.value} at boundary"
        # margin is zero exactly at the decision boundary
        assert abs(check.margin.magnitude) < 1e-12


def test_constraint_operators_away_from_boundary():
    below = Quantity(9.0, "kelvin")
    above = Quantity(11.0, "kelvin")
    bound = Quantity(10.0, "kelvin")

    def check(operator, value):
        return ConstraintDefinition(
            name="c", metric="x", operator=operator, bound=bound
        ).check(value)

    assert check(ConstraintOperator.LESS_THAN, below).satisfied
    assert not check(ConstraintOperator.LESS_THAN, above).satisfied
    assert check(ConstraintOperator.GREATER_THAN, above).satisfied
    assert not check(ConstraintOperator.GREATER_THAN, below).satisfied
    assert check(ConstraintOperator.LESS_THAN, below).margin.magnitude > 0
    assert check(ConstraintOperator.LESS_THAN, above).margin.magnitude < 0


def test_constraint_tolerance_relaxes_non_strict_and_tightens_strict():
    tol = Quantity(0.5, "kelvin")
    bound = Quantity(10.0, "kelvin")

    def check(operator, value):
        return ConstraintDefinition(
            name="c", metric="x", operator=operator, bound=bound, tolerance=tol
        ).check(Quantity(value, "kelvin")).satisfied

    # <= relaxed to 10.5 ; < tightened to strictly below 9.5
    assert check(ConstraintOperator.LESS_EQUAL, 10.4)
    assert not check(ConstraintOperator.LESS_EQUAL, 10.6)
    assert check(ConstraintOperator.LESS_THAN, 9.4)
    assert not check(ConstraintOperator.LESS_THAN, 9.5)

    # >= relaxed to 9.5 ; > tightened to strictly above 10.5
    assert check(ConstraintOperator.GREATER_EQUAL, 9.6)
    assert not check(ConstraintOperator.GREATER_EQUAL, 9.4)
    assert check(ConstraintOperator.GREATER_THAN, 10.6)
    assert not check(ConstraintOperator.GREATER_THAN, 10.5)

    # == within tolerance
    assert check(ConstraintOperator.EQUAL, 10.4)
    assert not check(ConstraintOperator.EQUAL, 10.6)


def test_exact_equality_with_zero_tolerance_is_permitted():
    constraint = ConstraintDefinition(
        name="c", metric="x", operator=ConstraintOperator.EQUAL,
        bound=Quantity(10.0, "kelvin"),
    )
    assert constraint.check(Quantity(10.0, "kelvin")).satisfied
    assert not constraint.check(Quantity(10.000001, "kelvin")).satisfied


# ---- J/K/L. condition dimensional rules ------------------------------

def test_initial_condition_dimensional_mismatch_rejected():
    _raises(
        UnitCompatibilityError, ScientificProblem, problem_id="p",
        variables=(ScientificVariable("temperature", "kelvin"),),
        initial_conditions=(
            InitialCondition(variable="temperature", value=Quantity(12.0, "volt")),
        ),
    )


def test_initial_condition_compatible_unit_accepted():
    problem = ScientificProblem(
        problem_id="p",
        variables=(ScientificVariable("temperature", "kelvin"),),
        initial_conditions=(
            InitialCondition(variable="temperature", value=Quantity(20.0, "degC")),
        ),
    )
    assert problem.is_time_dependent


def test_dirichlet_dimensional_mismatch_rejected():
    _raises(
        UnitCompatibilityError, ScientificProblem, problem_id="p",
        variables=(ScientificVariable("temperature", "kelvin"),),
        boundary_conditions=(
            BoundaryCondition(
                name="wall", variable="temperature",
                kind=BoundaryKind.DIRICHLET, region="w",
                value=Quantity(12.0, "volt"),
            ),
        ),
    )


def test_neumann_is_not_forced_to_the_field_dimension():
    """A Neumann condition is a flux/derivative; requiring it to match the
    field would reject correct physics. The core must stay out of it."""
    problem = ScientificProblem(
        problem_id="p",
        variables=(ScientificVariable("temperature", "kelvin"),),
        boundary_conditions=(
            BoundaryCondition(
                name="flux", variable="temperature",
                kind=BoundaryKind.NEUMANN, region="w",
                value=Quantity(500.0, "watt / meter**2"),
            ),
        ),
    )
    assert problem.boundary_conditions[0].kind is BoundaryKind.NEUMANN


def test_robin_and_periodic_are_not_dimensionally_constrained_by_core():
    problem = ScientificProblem(
        problem_id="p",
        variables=(ScientificVariable("temperature", "kelvin"),),
        boundary_conditions=(
            BoundaryCondition(
                name="convective", variable="temperature",
                kind=BoundaryKind.ROBIN, region="w",
                coefficients={
                    "h": Quantity(25.0, "watt / meter**2 / kelvin"),
                    "T_inf": Quantity(300.0, "kelvin"),
                },
            ),
            BoundaryCondition(
                name="wrap", variable="temperature",
                kind=BoundaryKind.PERIODIC, region="edges",
            ),
        ),
    )
    assert len(problem.boundary_conditions) == 2


# ---- M. codec bound enforcement --------------------------------------

def _bounded_codec() -> CandidateCodec:
    return CandidateCodec(
        variables=(
            ScientificVariable(
                "x", "volt", lower=Quantity(1.0, "volt"),
                upper=Quantity(10.0, "volt"),
            ),
        )
    )


def test_codec_encode_rejects_out_of_bounds_candidate():
    codec = _bounded_codec()
    assert codec.encode({"x": Quantity(1.0, "volt")}) == (0.0,)
    assert codec.encode({"x": Quantity(10.0, "volt")}) == (1.0,)
    _raises(
        InvalidScientificProblem, codec.encode, {"x": Quantity(50.0, "volt")}
    )
    _raises(
        InvalidScientificProblem, codec.encode, {"x": Quantity(0.5, "volt")}
    )


def test_codec_decode_rejects_components_outside_unit_cube():
    codec = _bounded_codec()
    assert codec.decode((0.0,))["x"] == Quantity(1.0, "volt")
    assert codec.decode((1.0,))["x"] == Quantity(10.0, "volt")
    for bad in (-0.001, 1.001, -2.0, 3.0):
        _raises(ScientificCoreError, codec.decode, (bad,))
    for bad in (NAN, POS_INF, NEG_INF):
        _raises(ScientificCoreError, codec.decode, (bad,))


def test_codec_clip_remains_the_explicit_correction_path():
    codec = _bounded_codec()
    assert codec.clip((-2.0,)) == (0.0,)
    assert codec.clip((3.0,)) == (1.0,)
    assert codec.clip((0.25,)) == (0.25,)
    # a clipped proposal decodes cleanly — the correction is explicit
    assert codec.decode(codec.clip((3.0,)))["x"] == Quantity(10.0, "volt")
    _raises(ScientificCoreError, codec.clip, (NAN,))


def test_require_within_bounds_replaces_clamp_to_bounds():
    variable = ScientificVariable(
        "x", "volt", lower=Quantity(1.0, "volt"), upper=Quantity(10.0, "volt")
    )
    assert variable.require_within_bounds(Quantity(5.0, "volt")).magnitude == 5.0
    _raises(
        InvalidScientificProblem, variable.require_within_bounds,
        Quantity(50.0, "volt"),
    )
    assert not hasattr(variable, "clamp_to_bounds")


# ---- N. metric dimensional coherence ---------------------------------

def test_metric_units_must_be_dimensionally_coherent():
    _raises(
        InvalidScientificProblem, ScientificProblem, problem_id="p",
        objectives=(
            ObjectiveDefinition(
                name="o", metric="temperature",
                direction=ObjectiveDirection.MINIMIZE, unit="kelvin",
            ),
        ),
        constraints=(
            ConstraintDefinition(
                name="c", metric="temperature",
                operator=ConstraintOperator.LESS_EQUAL,
                bound=Quantity(5.0, "volt"),
            ),
        ),
    )


def test_compatible_units_for_one_metric_are_accepted():
    for objective_unit, bound in (("kelvin", Quantity(350.0, "degC")),
                                  ("meter", Quantity(5.0, "cm"))):
        problem = ScientificProblem(
            problem_id="p",
            objectives=(
                ObjectiveDefinition(
                    name="o", metric="m",
                    direction=ObjectiveDirection.MINIMIZE, unit=objective_unit,
                ),
            ),
            constraints=(
                ConstraintDefinition(
                    name="c", metric="m",
                    operator=ConstraintOperator.LESS_EQUAL, bound=bound,
                ),
            ),
        )
        assert problem.metric_units()["m"] == normalize_unit(objective_unit)


def test_two_constraints_on_one_metric_must_agree():
    _raises(
        InvalidScientificProblem, ScientificProblem, problem_id="p",
        constraints=(
            ConstraintDefinition(
                name="lo", metric="m", operator=ConstraintOperator.GREATER_EQUAL,
                bound=Quantity(1.0, "kelvin"),
            ),
            ConstraintDefinition(
                name="hi", metric="m", operator=ConstraintOperator.LESS_EQUAL,
                bound=Quantity(5.0, "volt"),
            ),
        ),
    )


# =====================================================================
# V0.0.2 — open/closed validity ranges
# =====================================================================

def _range_status(value, **kwargs):
    return RangeCondition(name="x", **kwargs).evaluate(value)


def test_inclusive_bounds_are_the_default_and_accept_the_endpoint():
    condition = RangeCondition(
        name="t", minimum=Quantity(0.0, "kelvin"), maximum=Quantity(100.0, "kelvin")
    )
    assert condition.minimum_inclusive is True
    assert condition.maximum_inclusive is True
    assert condition.evaluate(Quantity(0.0, "kelvin")) is ValidityStatus.IN_DOMAIN
    assert condition.evaluate(Quantity(100.0, "kelvin")) is ValidityStatus.IN_DOMAIN
    assert condition.evaluate(Quantity(50.0, "kelvin")) is ValidityStatus.IN_DOMAIN


def test_exclusive_minimum_rejects_the_endpoint():
    kwargs = {"minimum": Quantity(0.0, "ohm"), "minimum_inclusive": False}
    assert _range_status(Quantity(0.0, "ohm"), **kwargs) is (
        ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )
    assert _range_status(Quantity(1e-12, "ohm"), **kwargs) is ValidityStatus.IN_DOMAIN
    assert _range_status(Quantity(-1.0, "ohm"), **kwargs) is (
        ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )


def test_inclusive_minimum_accepts_the_endpoint():
    kwargs = {"minimum": Quantity(0.0, "ohm")}
    assert _range_status(Quantity(0.0, "ohm"), **kwargs) is ValidityStatus.IN_DOMAIN


def test_exclusive_maximum_rejects_the_endpoint():
    kwargs = {"maximum": Quantity(1.0, "meter"), "maximum_inclusive": False}
    assert _range_status(Quantity(1.0, "meter"), **kwargs) is (
        ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )
    assert _range_status(Quantity(0.999, "meter"), **kwargs) is (
        ValidityStatus.IN_DOMAIN
    )


def test_double_bounded_open_interval():
    kwargs = {
        "minimum": Quantity(0.0, "meter"),
        "maximum": Quantity(1.0, "meter"),
        "minimum_inclusive": False,
        "maximum_inclusive": False,
    }
    assert _range_status(Quantity(0.0, "meter"), **kwargs) is (
        ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )
    assert _range_status(Quantity(1.0, "meter"), **kwargs) is (
        ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )
    assert _range_status(Quantity(0.5, "meter"), **kwargs) is ValidityStatus.IN_DOMAIN


def test_half_open_interval():
    kwargs = {
        "minimum": Quantity(0.0, "second"),
        "maximum": Quantity(10.0, "second"),
        "minimum_inclusive": False,
    }
    assert _range_status(Quantity(0.0, "second"), **kwargs) is (
        ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )
    assert _range_status(Quantity(10.0, "second"), **kwargs) is (
        ValidityStatus.IN_DOMAIN
    )


def test_inclusivity_flag_is_inert_when_its_bound_is_absent():
    """A maximum_inclusive flag with no maximum must not affect anything."""
    strict_min_only = RangeCondition(
        name="x", minimum=Quantity(1.0, "meter"),
        minimum_inclusive=False, maximum_inclusive=False,
    )
    assert strict_min_only.evaluate(Quantity(1000.0, "meter")) is (
        ValidityStatus.IN_DOMAIN
    )
    assert strict_min_only.evaluate(Quantity(1.0, "meter")) is (
        ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )


def test_boundary_inclusivity_survives_unit_conversion():
    """1 m and 100 cm are the same boundary, so the endpoint decision must be
    identical regardless of the unit the value arrives in."""
    inclusive = RangeCondition(name="x", minimum=Quantity(1.0, "meter"))
    exclusive = RangeCondition(
        name="x", minimum=Quantity(1.0, "meter"), minimum_inclusive=False
    )
    assert inclusive.evaluate(Quantity(100.0, "cm")) is ValidityStatus.IN_DOMAIN
    assert exclusive.evaluate(Quantity(100.0, "cm")) is (
        ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    )
    assert exclusive.evaluate(Quantity(101.0, "cm")) is ValidityStatus.IN_DOMAIN


def test_range_condition_round_trip_preserves_inclusivity():
    for minimum_inclusive in (True, False):
        for maximum_inclusive in (True, False):
            condition = RangeCondition(
                name="x",
                minimum=Quantity(0.0, "ohm"),
                maximum=Quantity(10.0, "ohm"),
                minimum_inclusive=minimum_inclusive,
                maximum_inclusive=maximum_inclusive,
            )
            payload = condition.to_dict()
            assert payload["minimum_inclusive"] is minimum_inclusive
            assert payload["maximum_inclusive"] is maximum_inclusive
            assert RangeCondition.from_dict(payload) == condition
            assert json.loads(json.dumps(payload, sort_keys=True)) == payload


def test_legacy_range_payload_defaults_to_inclusive():
    """Records written before open ranges existed described closed ranges."""
    legacy = {
        "schema": "validity_range_condition/1",
        "name": "resistance",
        "minimum": Quantity(0.0, "ohm").to_dict(),
        "maximum": None,
        "description": "written by an older version",
    }
    restored = RangeCondition.from_dict(legacy)
    assert restored.minimum_inclusive is True
    assert restored.maximum_inclusive is True
    assert restored.evaluate(Quantity(0.0, "ohm")) is ValidityStatus.IN_DOMAIN


def test_open_range_inside_a_validity_domain():
    """The end-to-end path a domain model uses: R > 0 as a validity claim."""
    model = ScientificModelDefinition(
        model_id="m", version="1",
        validity=ValidityDomain(
            conditions=(
                RangeCondition(
                    name="resistance",
                    minimum=Quantity(0.0, "ohm"),
                    minimum_inclusive=False,
                ),
            )
        ),
    )
    assert model.assess_validity(
        {"resistance": Quantity(0.0, "ohm")}
    ).status is ValidityStatus.OUTSIDE_VALIDATED_DOMAIN
    assert model.assess_validity(
        {"resistance": Quantity(1.0, "kohm")}
    ).status is ValidityStatus.IN_DOMAIN


# =====================================================================
# standalone runner (pytest optional)
# =====================================================================

def _all_tests():
    module = sys.modules[__name__]
    return [
        (name, getattr(module, name))
        for name in sorted(dir(module))
        if name.startswith("test_") and callable(getattr(module, name))
    ]


def main() -> int:
    print("Scientific Core V0 — foundation tests")
    print("=" * 72)
    failures = 0
    for name, test in _all_tests():
        try:
            test()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
    print("=" * 72)
    total = len(_all_tests())
    if failures:
        print(f"Scientific Core V0 tests: FAIL ({failures}/{total})")
        return 1
    print(f"Scientific Core V0 tests: PASS ({total}/{total})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
