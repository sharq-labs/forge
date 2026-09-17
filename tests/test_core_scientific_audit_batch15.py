"""Batch 15 of the 2026-09-16 core re-audit: the declarations a problem makes are read (I-19, R-72).

`ScientificProblem` carries two declarations that read, to any engineer holding the record, as gates:
`validation_requirements` names the checks a result must carry, and `UncertaintySpecification` demands
REPORTED or QUANTIFIED uncertainty on named metrics at a named confidence level. **Nothing in src reads
either.** A result carrying one unrelated check and UNKNOWN uncertainty is `is_usable`, its report status is
PASS, and `TrustedExecutionRuntime` -- which holds the admitted problem AND the validation report -- calls the
record `trusted`. A requirement name is never validated, so `numerically_convergd` is accepted; and
`ScientificProblem.from_dict` ignores unknown keys, so a record whose `validation_requirements` key is
misspelled round-trips to a problem with no requirements at all, silently.

Preregistered in `benchmarks/core_v4_false_confidence/BATCH15_THRESHOLD_PROTOCOL.json`.
"""

from __future__ import annotations

import pytest

from engcore.scientific.ir.problem import (
    ScientificProblem,
    ScientificVariable,
    UncertaintyRequirement,
    UncertaintySpecification,
)
from engcore.scientific.results.uncertainty import Uncertainty, UncertaintyKind
from engcore.scientific.results.validation import (
    ValidationCheck,
    ValidationOutcome,
    ValidationReport,
)
from engcore.scientific.units.quantity import Quantity

AMPERE = "ampere"


def _requirements_module():
    """Imported by name so a reproduction fails on its own assertion, not on an ImportError."""
    import importlib

    try:
        return importlib.import_module("engcore.scientific.results.requirements")
    except ModuleNotFoundError:
        return None


def _problem(*, requirements=(), uncertainty=None, problem_id="r72") -> ScientificProblem:
    return ScientificProblem(
        problem_id=problem_id,
        variables=(ScientificVariable(name="I_R1", unit=AMPERE),),
        validation_requirements=frozenset(requirements),
        uncertainty=uncertainty or UncertaintySpecification(),
    )


def _report(*names, outcome=ValidationOutcome.PASS) -> ValidationReport:
    return ValidationReport(
        checks=tuple(
            ValidationCheck(name=name, outcome=outcome, detail="a fixture check") for name in names
        )
    )


# =====================================================================
# R-72: the record is parsed strictly
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_a_misspelled_requirements_key_is_refused():
    """The audited case: the declaration does not arrive and the record still reads as though it had."""
    honest = _problem(requirements=("power_balance",))
    payload = dict(honest.to_dict())
    payload["validation_requirementss"] = sorted(payload.pop("validation_requirements"))
    with pytest.raises(Exception, match="validation_requirementss"):
        ScientificProblem.from_dict(payload)


@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_a_misspelled_uncertainty_key_is_refused():
    honest = _problem(
        uncertainty=UncertaintySpecification(
            requirement=UncertaintyRequirement.QUANTIFIED, metrics=("I_R1",)
        )
    )
    payload = dict(honest.to_dict())
    payload["uncertaintyy"] = payload.pop("uncertainty")
    with pytest.raises(Exception, match="uncertaintyy"):
        ScientificProblem.from_dict(payload)


@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_an_unknown_key_inside_the_uncertainty_specification_is_refused():
    spec = UncertaintySpecification(requirement=UncertaintyRequirement.REPORTED, metrics=("I_R1",))
    payload = dict(spec.to_dict())
    payload["confidence_levl"] = 0.95
    with pytest.raises(Exception, match="confidence_levl"):
        UncertaintySpecification.from_dict(payload)


def test_r72_every_payload_this_tree_writes_is_still_accepted():
    """No-regression, and the reason the refusal above is honest: both writers emit every key they read."""
    honest = _problem(
        requirements=("power_balance",),
        uncertainty=UncertaintySpecification(
            requirement=UncertaintyRequirement.QUANTIFIED, metrics=("I_R1",), confidence_level=0.95
        ),
    )
    back = ScientificProblem.from_dict(honest.to_dict())
    assert back.validation_requirements == honest.validation_requirements
    assert back.uncertainty == honest.uncertainty


# =====================================================================
# R-72: a requirement names a registered check kind
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_a_requirement_naming_no_check_kind_is_unsatisfiable():
    """`numerically_convergd` was accepted and, because nothing read the field, never noticed."""
    module = _requirements_module()
    assert module is not None, "engcore.scientific.results.requirements exists"
    problem = _problem(requirements=("power_balance", "numerically_convergd"))
    assert module.unsatisfiable_validation_requirements(problem) == ("numerically_convergd",)
    unmet = module.unmet_validation_requirements(problem, _report("power_balance"))
    assert unmet == ("numerically_convergd",), unmet


@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_the_kinds_the_three_declaring_problems_name_are_all_registered():
    """The registry is populated beside the emitters, and the pinned thermal tree's from the package root."""
    module = _requirements_module()
    assert module is not None, "engcore.scientific.results.requirements exists"
    import engcore.domains  # noqa: F401  -- registers the SHA-pinned conduction1d tree's kinds
    import engcore.domains.electrical.dc.validation  # noqa: F401
    import engcore.domains.kinetics.cstr.validation  # noqa: F401

    registered = module.registered_validation_check_kinds()
    declared = {
        "dimensional_consistency", "linear_system_residual", "kirchhoff_current_law",
        "resistor_metric_consistency", "voltage_source_relation", "power_balance",
        "integration_reported_success", "state_physically_admissible", "trajectory_finite",
        "boundary_conditions_held", "field_finite", "amplitude_decay",
    }
    assert declared <= registered, sorted(declared - registered)


# =====================================================================
# R-72: a declared requirement is unmet unless a check of that name passed
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_a_declared_check_that_is_absent_is_unmet():
    module = _requirements_module()
    assert module is not None, "engcore.scientific.results.requirements exists"
    problem = _problem(requirements=("kirchhoff_current_law", "power_balance"))
    unmet = module.unmet_validation_requirements(problem, _report("dimensional_consistency"))
    assert unmet == ("kirchhoff_current_law", "power_balance"), unmet


@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_a_declared_check_that_did_not_pass_is_unmet():
    """A NOT_RUN check of the right name says the opposite of what the declaration promises."""
    module = _requirements_module()
    assert module is not None, "engcore.scientific.results.requirements exists"
    problem = _problem(requirements=("power_balance",))
    for outcome in (ValidationOutcome.NOT_RUN, ValidationOutcome.WARNING, ValidationOutcome.FAIL):
        unmet = module.unmet_validation_requirements(
            problem, _report("power_balance", outcome=outcome)
        )
        assert unmet == ("power_balance",), (outcome, unmet)
    assert module.unmet_validation_requirements(problem, _report("power_balance")) == ()


# =====================================================================
# R-72: the uncertainty specification is read
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_a_quantified_demand_is_unmet_by_an_unknown_record():
    module = _requirements_module()
    assert module is not None, "engcore.scientific.results.requirements exists"
    problem = _problem(
        uncertainty=UncertaintySpecification(
            requirement=UncertaintyRequirement.QUANTIFIED, metrics=("I_R1",)
        )
    )
    unknown = {"I_R1": Uncertainty.unknown("nothing was quantified")}
    assert module.unmet_uncertainty_requirements(problem, unknown) == ("I_R1",)
    quantified = {
        "I_R1": Uncertainty(
            kind=UncertaintyKind.STANDARD,
            standard_uncertainty=Quantity(1.0e-3, AMPERE),
            method="a fixture estimate",
        )
    }
    assert module.unmet_uncertainty_requirements(problem, quantified) == ()


@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_a_demanded_confidence_level_is_the_one_the_record_must_declare():
    module = _requirements_module()
    assert module is not None, "engcore.scientific.results.requirements exists"
    problem = _problem(
        uncertainty=UncertaintySpecification(
            requirement=UncertaintyRequirement.QUANTIFIED, metrics=("I_R1",), confidence_level=0.95
        )
    )
    at_68 = {
        "I_R1": Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(-1.0e-3, AMPERE),
            upper=Quantity(1.0e-3, AMPERE),
            confidence_level=0.68,
        )
    }
    assert module.unmet_uncertainty_requirements(problem, at_68) == ("I_R1",)
    at_95 = {
        "I_R1": Uncertainty(
            kind=UncertaintyKind.INTERVAL,
            lower=Quantity(-2.0e-3, AMPERE),
            upper=Quantity(2.0e-3, AMPERE),
            confidence_level=0.95,
        )
    }
    assert module.unmet_uncertainty_requirements(problem, at_95) == ()


@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_a_metric_the_problem_does_not_carry_can_never_be_satisfied():
    module = _requirements_module()
    assert module is not None, "engcore.scientific.results.requirements exists"
    problem = _problem(
        uncertainty=UncertaintySpecification(
            requirement=UncertaintyRequirement.REPORTED, metrics=("not_a_value_here",)
        )
    )
    assert module.unmet_uncertainty_requirements(problem, {}) == ("not_a_value_here",)


# =====================================================================
# R-72: what is unmet becomes a NOT_RUN check
# =====================================================================
@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_what_is_unmet_becomes_a_not_run_check_and_nothing_else_does():
    module = _requirements_module()
    assert module is not None, "engcore.scientific.results.requirements exists"
    problem = _problem(
        requirements=("power_balance",),
        uncertainty=UncertaintySpecification(
            requirement=UncertaintyRequirement.QUANTIFIED, metrics=("I_R1",)
        ),
    )
    checks = module.requirement_checks(
        problem,
        validation=_report("dimensional_consistency"),
        uncertainty={"I_R1": Uncertainty.unknown("nothing was quantified")},
    )
    assert [c.name for c in checks] == [
        module.DECLARED_VALIDATION_REQUIREMENTS_CHECK,
        module.DECLARED_UNCERTAINTY_REQUIREMENT_CHECK,
    ]
    assert all(c.outcome is ValidationOutcome.NOT_RUN for c in checks)
    assert "power_balance" in checks[0].detail and "I_R1" in checks[1].detail
    # and nothing at all when the declaration is met, so a compliant result keeps its bytes
    assert module.requirement_checks(
        problem,
        validation=_report("power_balance"),
        uncertainty={
            "I_R1": Uncertainty(
                kind=UncertaintyKind.STANDARD,
                standard_uncertainty=Quantity(1.0e-3, AMPERE),
                method="a fixture estimate",
            )
        },
    ) == ()


# =====================================================================
# R-72: the two boundaries that hold both the problem and the result
# =====================================================================
def _declared_support():
    from engcore.scientific.solvers.protocol import DeclaredSupport

    return DeclaredSupport


class _RequirementSolver(_declared_support()):
    """A solver whose validation report names one check the problem does not require.

    The shape of the audited trusted-runtime reproduction: `validation checks ['dimensional_consistency']
    status pass trusted True admitted True` against a problem requiring two other checks.
    """

    serves_capabilities = frozenset({"core:algebraic"})

    def __init__(self, model) -> None:
        from engcore.scientific.ir.problem import ModelReference

        self.served_models = (ModelReference(model.model_id, model.version),)

    @property
    def identity(self):
        from engcore.scientific.solvers.protocol import SolverIdentity

        return SolverIdentity("batch15.test", "1", backend="python")

    @property
    def capabilities(self):
        from engcore.scientific.solvers.capability import SolverCapability

        return frozenset({SolverCapability("core:algebraic")})

    def prepare(self, problem):
        from engcore.scientific.solvers.protocol import PreparedSolve, SolverSettings

        return PreparedSolve(
            problem=problem, solver=self.identity,
            settings=SolverSettings(options={"route": "batch15"}),
            payload={"assembled": True}, notes=("prepared by batch 15",))

    def solve(self, prepared):
        from engcore.scientific.solvers.protocol import ConvergenceState, RawSolverOutput

        return RawSolverOutput(convergence=ConvergenceState.CONVERGED, values={"answer": 2.0})

    def extract_metrics(self, prepared, raw):
        return {"answer": Quantity(2.0, "volt")}

    def validate(self, prepared, raw):
        return _report("dimensional_consistency")


def _trusted_record(*, requirements=("kirchhoff_current_law", "power_balance")):
    from engcore.execution.trusted import TrustedExecutionRuntime
    from engcore.scientific.ir.problem import ModelReference
    from engcore.scientific.models.definition import ScientificModelDefinition
    from engcore.scientific.realizations.definition import (
        ModelFormulation,
        ModelRealizationDefinition,
    )
    from engcore.scientific.solvers.capability import SolverCapabilityId

    model = ScientificModelDefinition(
        model_id="batch15.algebraic", version="1",
        exclusions=("not a general physical model",),
        required_capabilities=frozenset({"core:algebraic"}))
    problem = ScientificProblem(
        problem_id="batch15-case",
        models=(ModelReference(model.model_id, model.version),),
        required_capabilities=frozenset({"core:algebraic"}),
        validation_requirements=frozenset(requirements))
    realization = ModelRealizationDefinition(
        realization_id="batch15.algebraic.closed_form", version="1",
        model=ModelReference(model.model_id, model.version),
        formulation=ModelFormulation.ALGEBRAIC,
        provided_capabilities=frozenset({"batch15:evaluate"}),
        required_solver_capabilities=frozenset({SolverCapabilityId("core:algebraic")}))
    return TrustedExecutionRuntime().run(
        problem=problem, model=model, realization=realization,
        solver=_RequirementSolver(model),
        prepared_payload_encoder=lambda prepared: b"canonical-prepared-payload",
        environment={"python": "3.12"})


@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_the_trusted_runtime_does_not_call_such_a_record_trusted():
    """The audited case on a production-reaching path: the one place in src that holds both."""
    record = _trusted_record()
    assert record.admission.admitted
    assert record.validation.status is ValidationOutcome.PASS
    assert tuple(getattr(record, "unmet_declared_requirements", ())) == (
        "kirchhoff_current_law", "power_balance",
    ), getattr(record, "unmet_declared_requirements", None)
    assert not record.trusted


def test_r72_a_record_whose_problem_declares_nothing_is_still_trusted():
    """No-regression: the rule reads a DECLARATION, and a problem that declares none is unaffected."""
    record = _trusted_record(requirements=())
    assert record.trusted
    assert tuple(getattr(record, "unmet_declared_requirements", ())) == ()


@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_a_record_that_meets_its_declaration_is_still_trusted():
    record = _trusted_record(requirements=("dimensional_consistency",))
    unmet = getattr(record, "unmet_declared_requirements", None)
    assert unmet is not None, "a trusted record says which declared requirements are unmet"
    assert tuple(unmet) == ()
    assert record.trusted


@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_the_credibility_boundary_carries_the_unmet_declaration_when_it_is_given_the_problem():
    from engcore.mcp.evidence import CredibilityEvidenceReport
    from engcore.scientific.results.provenance import ProvenanceRecord
    from engcore.scientific.results.result import ScientificResult

    module = _requirements_module()
    assert module is not None, "engcore.scientific.results.requirements exists"
    problem = _problem(requirements=("power_balance",), problem_id="batch15-report")
    result = ScientificResult(
        result_id="batch15-report", problem_id=problem.problem_id,
        values={"I_R1": Quantity(1.0, AMPERE)},
        validation=_report("dimensional_consistency"),
        provenance=ProvenanceRecord(run_id="batch15-report"))
    without = CredibilityEvidenceReport.from_result(result)
    assert module.DECLARED_VALIDATION_REQUIREMENTS_CHECK not in [c.name for c in without.validation]
    with_problem = CredibilityEvidenceReport.from_result(result, problem=problem)
    named = [c for c in with_problem.validation
             if c.name == module.DECLARED_VALIDATION_REQUIREMENTS_CHECK]
    assert len(named) == 1 and named[0].outcome is ValidationOutcome.NOT_RUN
    assert "power_balance" in named[0].detail


@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_that_check_lowers_a_real_supported_production_verdict():
    """The consequence, measured on the production electrothermal report rather than asserted."""
    import dataclasses

    from engcore.mcp.evidence import CredibilityVerdict
    from engcore.mcp.problem import example_electrothermal_payload, run_electrothermal_case

    module = _requirements_module()
    assert module is not None, "engcore.scientific.results.requirements exists"
    report = run_electrothermal_case(example_electrothermal_payload(), run_id="batch15").reports[0]
    assert report.verdict is CredibilityVerdict.SUPPORTED
    unmet = ValidationCheck(
        name=module.DECLARED_VALIDATION_REQUIREMENTS_CHECK,
        outcome=ValidationOutcome.NOT_RUN,
        detail="the problem declares power_balance and no check of that name passed")
    lowered = dataclasses.replace(report, validation=(*report.validation, unmet))
    assert lowered.verdict is CredibilityVerdict.INSUFFICIENT_EVIDENCE


# =====================================================================
# R-72: the two editable domains whose problems declare requirements
# =====================================================================
def _dc_circuit():
    from engcore.domains.electrical.dc.circuit import (
        DCCircuit,
        DCVoltageSource,
        ElectricalNode,
        Resistor,
    )

    return DCCircuit(
        circuit_id="batch15-divider",
        nodes=(ElectricalNode("gnd", is_reference=True), ElectricalNode("top"),
               ElectricalNode("mid")),
        resistors=(Resistor("R1", "top", "mid", Quantity(1.0, "kohm")),
                   Resistor("R2", "mid", "gnd", Quantity(3.0, "kohm"))),
        voltage_sources=(DCVoltageSource("V1", "top", "gnd", Quantity(12.0, "volt")),))


def test_r72_the_dc_solve_meets_its_own_declaration():
    """No-regression, and the measurement the protocol's blast-radius claim rests on."""
    from engcore.domains.electrical.dc.problem import build_dc_problem
    from engcore.domains.electrical.dc.solver import solve_circuit

    circuit = _dc_circuit()
    problem = build_dc_problem(circuit)
    result = solve_circuit(circuit, run_id="batch15-dc")
    passed = {c.name for c in result.validation.checks if c.outcome is ValidationOutcome.PASS}
    assert problem.validation_requirements <= passed, sorted(problem.validation_requirements - passed)


@pytest.mark.xfail(strict=True, reason="I-19 not implemented yet (batch 15 preregistration)")
def test_r72_a_dc_result_says_so_when_a_declared_check_is_missing():
    import dataclasses

    from engcore.domains.electrical.dc.problem import build_dc_problem
    from engcore.domains.electrical.dc.solver import solve_circuit

    module = _requirements_module()
    assert module is not None, "engcore.scientific.results.requirements exists"
    circuit = _dc_circuit()
    problem = build_dc_problem(circuit)
    # `amplitude_decay` is a registered kind -- the frozen conduction1d tree emits it -- that a DC solve
    # cannot produce, so the requirement is satisfiable in principle and unmet in fact.
    demanding = dataclasses.replace(
        problem, validation_requirements=problem.validation_requirements | {"amplitude_decay"})
    result = solve_circuit(circuit, run_id="batch15-dc-demanding", problem=demanding)
    named = [c for c in result.validation.checks
             if c.name == module.DECLARED_VALIDATION_REQUIREMENTS_CHECK]
    assert len(named) == 1 and named[0].outcome is ValidationOutcome.NOT_RUN
    assert "amplitude_decay" in named[0].detail
