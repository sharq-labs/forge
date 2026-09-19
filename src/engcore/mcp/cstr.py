"""Production claim boundary for the non-isothermal CSTR Domain Pack."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from ..claims.capabilities import (
    AttainableLevel,
    CapabilityDeclaration,
    CapabilityRun,
    InputDeclaration,
    InputKind,
    InputRole,
    InstanceReport,
    ModelUse,
    ProducedQuantity,
    ProvidedCapability,
    RouteDeclaration,
    RouteKind,
    SolverUse,
    UncertaintyCapability,
)
from ..claims.contract import ClaimKind
from ..credibility.evidence import CredibilityEvidenceReport
from ..domains.kinetics.cstr import (
    CA_FINAL_METRIC,
    CONCENTRATION_UNIT,
    CONVERSION_METRIC,
    CSTR_MODEL,
    CSTRSolver,
    DIMENSIONLESS,
    IntegrationSettings,
    ReactorChemistry,
    ReactorOperation,
    ReactorRun,
    SOLVER_ID,
    SOLVER_VERSION,
    T_AT_MAX_METRIC,
    T_FINAL_METRIC,
    T_MAX_METRIC,
    TEMPERATURE_UNIT,
    TIME_UNIT,
    build_cstr_problem,
    run_verification_gate,
    solve_reactor,
)
from ..domains.kinetics.cstr.realization import (
    CSTR_REALIZATION,
    CSTR_TRANSIENT_SCIENCE,
)
from ..domains.kinetics.cstr.independent_solver import (
    SOLVER_ID as INDEPENDENT_SOLVER_ID,
    SOLVER_VERSION as INDEPENDENT_SOLVER_VERSION,
)
from ..scientific.results.validation import ValidationLevel
from ..scientific.units.quantity import Quantity
from ..sria.uncertainty import UncertaintyChannel

CSTR_CAPABILITY_ID = "kinetics.cstr.production"

_ALIAS = {
    CA_FINAL_METRIC: "final_concentration",
    T_FINAL_METRIC: "final_temperature",
    T_MAX_METRIC: "peak_temperature",
    T_AT_MAX_METRIC: "peak_temperature_time",
    CONVERSION_METRIC: "conversion",
}


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _q(section: Mapping[str, Any], key: str) -> Quantity:
    value = section.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be unit-bearing quantity text")
    return Quantity.parse(value)


def build_cstr_case(case: Mapping[str, Any]) -> ReactorRun:
    chemistry = _mapping(case.get("chemistry"), "chemistry")
    operation = _mapping(case.get("operation"), "operation")
    initial = _mapping(case.get("initial"), "initial")

    return ReactorRun(
        run_label=str(case.get("run_label", "production")).strip() or "production",
        chemistry=ReactorChemistry(
            k0=_q(chemistry, "k0"),
            activation_energy=_q(chemistry, "activation_energy"),
            heat_of_reaction=_q(chemistry, "heat_of_reaction"),
            density=_q(chemistry, "density"),
            heat_capacity=_q(chemistry, "heat_capacity"),
            boiling_temperature=(
                _q(chemistry, "boiling_temperature")
                if "boiling_temperature" in chemistry else None
            ),
            freezing_temperature=(
                _q(chemistry, "freezing_temperature")
                if "freezing_temperature" in chemistry else None
            ),
        ),
        operation=ReactorOperation(
            volume=_q(operation, "volume"),
            flow_rate=_q(operation, "flow_rate"),
            feed_concentration=_q(operation, "feed_concentration"),
            feed_temperature=_q(operation, "feed_temperature"),
            coolant_temperature=_q(operation, "coolant_temperature"),
            ua=_q(operation, "ua"),
            end_time=_q(operation, "end_time"),
        ),
        initial_concentration=_q(initial, "concentration"),
        initial_temperature=_q(initial, "temperature"),
        integration=IntegrationSettings(),
    )


def run_cstr_case(case: Mapping[str, Any], *, run_id: str) -> CapabilityRun:
    run = build_cstr_case(case)
    problem = build_cstr_problem(run)
    result = solve_reactor(
        run,
        run_id=run_id,
        solver=CSTRSolver(),
        problem=problem,
    )
    verification = run_verification_gate(
        run,
        run_id_prefix=f"{run_id}-verification",
    )
    verification_report = verification.to_report()

    report = CredibilityEvidenceReport.from_result(
        result,
        validation=verification_report.checks,
        problem=problem,
        notes=(
            "CSTR production report includes the per-solve checks plus the "
            "declared tolerance-ladder/analytic-reference verification gate. "
            "The BDF-vs-Radau arm is retained as corroboration and earns no "
            "cross-solver level because the implementations share the RHS, "
            "Jacobian and SciPy infrastructure."
        ),
    )

    values = {
        _ALIAS.get(name, name): value for name, value in report.values.items()
    }
    uncertainty = {
        _ALIAS.get(name, name): value
        for name, value in report.uncertainty.items()
    }
    report = replace(report, values=values, uncertainty=uncertainty)
    return CapabilityRun(
        reports=(InstanceReport(None, report),),
        native={"run": run, "verification": verification, "result": result},
    )


def _input(
    path: str,
    unit: str,
    role: InputRole,
    *,
    required: bool = True,
    model_input: str | None = None,
    unlocks: tuple[str, ...] = (),
) -> InputDeclaration:
    return InputDeclaration(
        path=path,
        kind=InputKind.QUANTITY,
        role=role,
        required=required,
        unit_exemplar=unit,
        model_id=CSTR_MODEL.model_id if model_input else None,
        model_input=model_input,
        unlocks_conditions=unlocks,
    )


def cstr_capability() -> CapabilityDeclaration:
    inputs = (
        _input("chemistry.k0", "1/second", InputRole.PARAMETER, model_input="k0"),
        _input(
            "chemistry.activation_energy",
            "joule/mol",
            InputRole.PARAMETER,
            model_input="activation_energy",
        ),
        _input(
            "chemistry.heat_of_reaction",
            "joule/mol",
            InputRole.PARAMETER,
            model_input="heat_of_reaction",
        ),
        _input("chemistry.density", "kg/meter**3", InputRole.PARAMETER, model_input="density"),
        _input(
            "chemistry.heat_capacity",
            "joule/kg/kelvin",
            InputRole.PARAMETER,
            model_input="heat_capacity",
        ),
        _input(
            "chemistry.boiling_temperature",
            "kelvin",
            InputRole.APPLICABILITY,
            required=False,
            model_input="boiling_temperature",
        ),
        _input(
            "chemistry.freezing_temperature",
            "kelvin",
            InputRole.APPLICABILITY,
            required=False,
            model_input="freezing_temperature",
        ),
        _input("operation.volume", "meter**3", InputRole.PARAMETER),
        _input("operation.flow_rate", "meter**3/second", InputRole.OPERATING_CONDITION),
        _input(
            "operation.feed_concentration",
            CONCENTRATION_UNIT,
            InputRole.BOUNDARY_CONDITION,
            model_input="feed_concentration",
        ),
        _input(
            "operation.feed_temperature",
            TEMPERATURE_UNIT,
            InputRole.BOUNDARY_CONDITION,
            model_input="feed_temperature",
        ),
        _input(
            "operation.coolant_temperature",
            TEMPERATURE_UNIT,
            InputRole.BOUNDARY_CONDITION,
            model_input="coolant_temperature",
        ),
        _input("operation.ua", "watt/kelvin", InputRole.PARAMETER, model_input="ua"),
        _input(
            "operation.end_time",
            TIME_UNIT,
            InputRole.OPERATING_CONDITION,
            model_input="end_time",
        ),
        _input(
            "initial.concentration",
            CONCENTRATION_UNIT,
            InputRole.INITIAL_CONDITION,
            model_input="initial_concentration",
        ),
        _input(
            "initial.temperature",
            TEMPERATURE_UNIT,
            InputRole.INITIAL_CONDITION,
            model_input="initial_temperature",
        ),
    )

    return CapabilityDeclaration(
        capability_id=CSTR_CAPABILITY_ID,
        version="2",
        domain="kinetics",
        summary=(
            "Transient non-isothermal first-order CSTR with Arrhenius kinetics, "
            "production BDF integration, tolerance-ladder numerical verification "
            "and an exact adiabatic-invariant verification route when applicable."
        ),
        provides=(
            ProvidedCapability(
                CSTR_TRANSIENT_SCIENCE,
                f"realization:{CSTR_REALIZATION.realization_id}@{CSTR_REALIZATION.version}",
            ),
        ),
        inputs=inputs,
        produces=(
            ProducedQuantity("final_concentration", CONCENTRATION_UNIT, CSTR_MODEL.model_id),
            ProducedQuantity("final_temperature", TEMPERATURE_UNIT, CSTR_MODEL.model_id),
            ProducedQuantity("peak_temperature", TEMPERATURE_UNIT, CSTR_MODEL.model_id),
            ProducedQuantity("peak_temperature_time", TIME_UNIT, CSTR_MODEL.model_id),
            ProducedQuantity("conversion", DIMENSIONLESS, CSTR_MODEL.model_id),
        ),
        models=(ModelUse.of(CSTR_MODEL),),
        solvers=(
            SolverUse(
                SOLVER_ID,
                SOLVER_VERSION,
                ("core:ode", "kinetics:cstr_nonisothermal_transient"),
            ),
            SolverUse(
                INDEPENDENT_SOLVER_ID,
                INDEPENDENT_SOLVER_VERSION,
                ("core:ode", "kinetics:cstr_nonisothermal_transient"),
            ),
        ),
        claim_shapes=frozenset({ClaimKind.THRESHOLD, ClaimKind.TOLERANCE_BAND}),
        attainable_levels=(
            AttainableLevel(
                ValidationLevel.DIMENSIONALLY_VALID,
                check_name="dimensional_consistency",
                route_id=None,
                condition="produced CSTR metrics match the model's declared dimensions",
            ),
            AttainableLevel(
                ValidationLevel.NUMERICALLY_CONVERGED,
                check_name="tolerance_independence",
                route_id="kinetics.cstr.integration:BDF",
                condition="the declared tolerance ladder is complete and the QOIs stop moving",
            ),
            AttainableLevel(
                ValidationLevel.ANALYTICALLY_VERIFIED,
                check_name="analytic_invariant_agreement",
                route_id="kinetics.cstr.adiabatic_reaction_free_invariant",
                condition="the adiabatic trajectory reproduces the exact reaction-free invariant",
            ),
            AttainableLevel(
                ValidationLevel.CROSS_SOLVER_VALIDATED,
                check_name="independent_solver_agreement",
                route_id="kinetics.cstr.independent:LSODA",
                condition=(
                    "the tolerance-independent production solve agrees with the "
                    "pinned separately translated ODEPACK/LSODA implementation "
                    "on every required quantity"
                ),
            ),
        ),
        uncertainty=UncertaintyCapability(
            quantified={
                name: (
                    UncertaintyChannel.ALEATORIC,
                    UncertaintyChannel.MODEL_FORM,
                )
                for name in (
                    "final_concentration",
                    "final_temperature",
                    "peak_temperature",
                    "peak_temperature_time",
                    "conversion",
                )
            },
            basis=(
                "ALEATORIC is quantifiable only from curated independent physical "
                "replicates at one exact context. MODEL_FORM is quantifiable only "
                "from calibration/held-out DatasetObservation groups whose prediction "
                "runs are usable and whose discrepancy estimate is promoted by an "
                "independently reviewed ProducerQualification. Missing evidence leaves "
                "the channel UNKNOWN; the tolerance gate is verification and is not "
                "silently converted into scientific uncertainty."
            ),
        ),
        routes=(
            RouteDeclaration(
                route_id="kinetics.cstr.integration:BDF",
                kind=RouteKind.PRIMARY_SIMULATION,
                pinned_route="kinetics.cstr.integration:BDF",
                description="production implicit BDF integration",
            ),
            RouteDeclaration(
                route_id="kinetics.cstr.independent:LSODA",
                kind=RouteKind.SOLVER_ROUTE,
                pinned_route="kinetics.cstr.independent:LSODA",
                check_name="independent_solver_agreement",
                description=(
                    "separately translated CSTR equations through scipy.integrate."
                    "odeint/ODEPACK LSODA; independent preprocessing, implementation, "
                    "numerical method and backend"
                ),
            ),
            RouteDeclaration(
                route_id="kinetics.cstr.integration:Radau",
                kind=RouteKind.SOLVER_ROUTE,
                pinned_route="kinetics.cstr.integration:Radau",
                check_name="cross_method_agreement",
                description=(
                    "Radau cross-method corroboration. It shares the RHS/Jacobian/"
                    "SciPy infrastructure with BDF and therefore earns no independent-solver level."
                ),
            ),
            RouteDeclaration(
                route_id="kinetics.cstr.adiabatic_reaction_free_invariant",
                kind=RouteKind.ANALYTIC_REFERENCE,
                analytic_reference="kinetics.cstr.adiabatic_reaction_free_invariant",
                check_name="analytic_invariant_agreement",
                description="exact reaction-free invariant for an adiabatic CSTR",
            ),
        ),
        executor=lambda case, run_id: run_cstr_case(case, run_id=run_id),
    )


__all__ = [
    "CSTR_CAPABILITY_ID",
    "build_cstr_case",
    "cstr_capability",
    "run_cstr_case",
]
