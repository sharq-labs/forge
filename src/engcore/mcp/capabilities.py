"""The production capability declarations, over the systems this runtime executes.

:mod:`engcore.mcp.systems` names the system boundaries a caller may pose a case
to by name. This module declares the same boundaries -- plus the executable
NAFEMS T3 vertical -- as :class:`~engcore.claims.capabilities.CapabilityDeclaration`
records, so a structured claim can be routed to them by what they *produce and
provide* rather than by a name the caller had to know.

What is derived, and what is written here
-----------------------------------------
**Derived** from records that already exist, at registry build time:

* every input -- path, kind, requiredness, unit, the model input it feeds, the
  validity conditions it unlocks, its alternatives and its description -- from
  the system's own ``CaseDescription`` (which itself reads the model
  registries and measures ``unlocks`` by omission);
* every model's id, version, type, assumptions, exclusions, condition names
  and reserved derived quantities, from the live ``ScientificModelDefinition``;
* every provided scientific capability, from the realization records the
  system actually binds (``provided_capabilities``);
* every produced quantity's unit, from the model's own ``ModelOutputSpec``;
* every route's pin, from ``engcore.domains`` and the trusted oracle registry.

**Written here**, because no record states them, each checked by
``tests/claims/test_claims_production_capabilities.py`` against a real run:

* which of a model's outputs the credibility report carries;
* the role of each input (initial or boundary condition, applicability
  evidence, numerics, identity) -- by exact path or section prefix;
* which input block activates a conditional model;
* which check earns which level on this path;
* which model conditions a system never assembles the context for;
* one requiredness correction, stated where it is made.

Nothing here selects, ranks or executes on a caller's behalf. The executors
are the system run functions, called with a case built only from inputs the
claim stated.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping

from ..claims.capabilities import (
    AttainableLevel,
    CapabilityDeclaration,
    CapabilityRegistry,
    CapabilityRun,
    InputDeclaration,
    InputKind,
    InputRole,
    InstanceReport,
    ModelUse,
    PerturbableInput,
    ProducedQuantity,
    ProvidedCapability,
    RefinementStudy,
    RouteDeclaration,
    RouteKind,
    SolverUse,
    UnassessableCondition,
    UncertaintyCapability,
)
from ..claims.contract import ClaimKind
from ..claims.errors import CapabilityDeclarationError, CapabilityExecutionRefused
from ..scientific.results.validation import ValidationLevel
from ..scientific.units.quantity import Quantity
from ..sria.uncertainty import UncertaintyChannel

__all__ = [
    "BATTERY_CAPABILITY_ID",
    "ELECTROTHERMAL_CAPABILITY_ID",
    "NAFEMS_T3_CAPABILITY_ID",
    "battery_capability",
    "electrothermal_capability",
    "nafems_t3_capability",
    "production_registry",
]

ELECTROTHERMAL_CAPABILITY_ID = "system.electrothermal"
BATTERY_CAPABILITY_ID = "system.battery"
NAFEMS_T3_CAPABILITY_ID = "benchmark.nafems_t3"

_BOTH_SHAPES = frozenset({ClaimKind.THRESHOLD, ClaimKind.TOLERANCE_BAND})

_NO_UQ = (
    "every reported value carries Uncertainty.unknown: this path performs no "
    "numerical, parameter, measurement or model-form uncertainty quantification"
)

#: Phase 2B: the electrothermal inputs a propagation or sensitivity study may re-run the case at.
#: Parameters and boundary conditions of the declared physics; never numerics, identities or routes.
_ET_PERTURBABLE = (
    ("source_voltage", "the ideal source's voltage, a boundary condition of the circuit"),
    ("stages[].body.ambient_temperature", "the ambient each body exchanges heat with"),
    ("stages[].body.ambient_conductance", "the body's lumped heat-transfer conductance to ambient"),
    ("stages[].body.heat_capacity", "the body's lumped heat capacity"),
    ("stages[].conductor.reference_resistance", "the conductor's resistance at its reference temperature"),
    ("stages[].conductor.temperature_coefficient", "the conductor's linear temperature coefficient of resistance"),
)

_ET_PARAMETER_UQ = (
    "EPISTEMIC_PARAMETER is quantified only when the claim declares input distributions over the "
    "perturbable inputs: every draw is a real run, and Wilks' two-sided tolerance interval over those runs "
    "is reported (no normality or linearity assumed). NUMERICAL, ALEATORIC and MODEL_FORM are not quantified"
)

#: Battery inputs whose declared uncertainty can be propagated by real reruns.
#: Applicability limits are intentionally absent: uncertainty in a validity
#: threshold is not uncertainty in the simulated physical state.
_BATTERY_PERTURBABLE = (
    ("cell.nominal_capacity", "cell capacity entering charge removal and state-of-charge evolution"),
    ("cell.internal_resistance", "series resistance setting terminal voltage and I^2 R heat"),
    ("cell.open_circuit_voltage_at_full", "upper endpoint of the production OCV chord"),
    ("cell.open_circuit_voltage_at_empty", "lower endpoint of the production OCV chord"),
    ("cell.limits.cell_thermal_conductance", "the physical heat-transfer conductance shared by cell and body"),
    ("load.discharge_current", "the imposed continuous-current operating condition"),
    ("load.state_of_charge", "the declared initial state of charge"),
    ("load.cell_temperature", "the declared initial cell/body temperature"),
    ("thermal.heat_capacity", "the lumped body's total heat capacity"),
    ("thermal.ambient_temperature", "the imposed ambient boundary temperature"),
)

_BATTERY_PARAMETER_UQ = (
    "EPISTEMIC_PARAMETER is quantified when the claim supplies distributions over declared "
    "battery or thermal perturbable inputs. Each draw rebuilds and executes the complete marched "
    "battery/thermal case, invalid draws or scientifically unusable runs are not silently retained, "
    "and the reported interval is the runtime's Wilks two-sided tolerance interval over the usable "
    "reruns. NUMERICAL, ALEATORIC, MEASUREMENT and MODEL_FORM remain UNKNOWN unless separate evidence "
    "quantifies them."
)

_KIND = {
    "quantity": InputKind.QUANTITY,
    "fraction": InputKind.FRACTION,
    "identifier": InputKind.IDENTIFIER,
    "category": InputKind.CATEGORY,
    "count": InputKind.COUNT,
}


def _role(path: str, exact: Mapping[str, InputRole], prefixes: Mapping[str, InputRole]) -> InputRole:
    if path in exact:
        return exact[path]
    for prefix, role in prefixes.items():
        if path.startswith(prefix):
            return role
    return InputRole.PARAMETER


def _inputs_from_description(
    description: Any,
    *,
    exact: Mapping[str, InputRole],
    prefixes: Mapping[str, InputRole],
    required_overrides: Mapping[str, str] = {},
) -> tuple[InputDeclaration, ...]:
    """One InputDeclaration per FieldDescription. The role tables must all be used."""
    paths = {f.path for f in description.fields}
    stale = sorted(set(exact) - paths) + sorted(
        p for p in prefixes if not any(path.startswith(p) for path in paths)
    ) + sorted(set(required_overrides) - paths)
    if stale:
        raise CapabilityDeclarationError(f"role/requiredness tables name nothing declared: {stale}")
    out = []
    for f in description.fields:
        out.append(
            InputDeclaration(
                path=f.path,
                kind=_KIND[f.kind],
                role=_role(f.path, exact, prefixes),
                required=bool(f.required) or f.path in required_overrides,
                unit_exemplar=f.unit_exemplar if f.kind == "quantity" else None,
                model_id=f.model_id,
                model_input=f.model_input,
                unlocks_conditions=tuple(f.unlocks),
                alternative_to=tuple(
                    f"{f.section}.{key}" if f.section else key for key in f.alternative_to
                ),
                description=f.description
                + (f" REQUIRED by the run: {required_overrides[f.path]}" if f.path in required_overrides else ""),
            )
        )
    return tuple(out)


def _produced(model: Any, names: tuple[str, ...], **instance: str) -> tuple[ProducedQuantity, ...]:
    """Produced quantities read off a model's own output specs."""
    specs = {o.metric: o for o in model.outputs}
    missing = sorted(set(names) - set(specs))
    if missing:
        raise CapabilityDeclarationError(f"{model.model_id} declares no output {missing}")
    return tuple(
        ProducedQuantity(
            name=name,
            unit_exemplar=specs[name].unit_exemplar,
            model_id=model.model_id,
            description=specs[name].description,
            **instance,
        )
        for name in names
    )


def _provided(*realizations: Any) -> tuple[ProvidedCapability, ...]:
    out: dict[str, ProvidedCapability] = {}
    for realization in realizations:
        basis = f"realization:{realization.realization_id}@{realization.version}"
        for capability in realization.provided_capabilities:
            out.setdefault(capability.identifier, ProvidedCapability(capability, basis))
    return tuple(out.values())


def _models_by_id(*registries: Any) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for registry in registries:
        for model in registry:
            found[model.model_id] = model
    return found


# ---------------------------------------------------------------------------
# Electro-thermal
# ---------------------------------------------------------------------------


def _run_electrothermal(case: Mapping[str, Any], *, run_id: str) -> CapabilityRun:
    from .problem import run_electrothermal_case

    run = run_electrothermal_case(dict(case), run_id=run_id)
    stages = case.get("stages", [])
    ids = [stage.get("component_id") for stage in stages]
    if len(run.reports) == len(ids):
        instances = ids
    elif len(run.reports) == 1:
        # The coupling transfer was refused: one report stands for the case.
        instances = [None]
    else:  # pragma: no cover - the system emits one report per stage or one refusal
        raise CapabilityExecutionRefused(
            f"electrothermal returned {len(run.reports)} reports for {len(ids)} stages"
        )
    reports = tuple(InstanceReport(i, r) for i, r in zip(instances, run.reports))
    repairs = tuple(
        (instance, repair.to_dict())
        for instance, group in zip(instances, run.repairs)
        for repair in group
    )
    return CapabilityRun(reports=reports, condition_repairs=repairs, native=run)


def electrothermal_capability() -> CapabilityDeclaration:
    from ..domains.electrical.dc import models as dc_models
    from ..domains.electrical import dc_applicability, material
    from ..domains.electrical.dc import solver as dc_solver
    from ..domains.thermal_models import lumped
    from .problem import describe_electrothermal_case

    description = describe_electrothermal_case()
    by_id = _models_by_id(
        lumped.lumped_model_registry(),
        material.resistance_model_registry(),
        dc_models.build_dc_model_registry(),
        dc_applicability.build_dc_applicability_registry(),
    )
    missing = sorted(set(description.models) - set(by_id))
    if missing:
        raise CapabilityDeclarationError(f"electrothermal runs models no registry defines: {missing}")

    # Which block activates a conditional model, and which models exist once
    # per stage. Measured, not guessed: tests/claims/test_claims_production_capabilities.py
    # runs the example with and without each block and compares with the
    # report's validity records.
    activation = {
        "electrical.material.rated_linear_tcr_resistance": ("stages[].conductor.limits",),
        "electrical.dc.self_heated_resistor": ("stages[].conductor.element",),
        "electrical.dc.regulated_voltage_source": ("source_regulation",),
    }
    per_stage = {
        "thermal.lumped.first_order_capacity",
        "electrical.material.linear_tcr_resistance",
        "electrical.material.rated_linear_tcr_resistance",
        "electrical.dc.resistor_ohm",
        "electrical.dc.self_heated_resistor",
    }
    models = tuple(
        ModelUse.of(
            by_id[model_id],
            activation=activation.get(model_id, ()),
            instance_section="stages[]" if model_id in per_stage else None,
        )
        for model_id in description.models
    )

    inputs = _inputs_from_description(
        description,
        exact={
            "source_voltage": InputRole.BOUNDARY_CONDITION,
            "stages[].component_id": InputRole.IDENTITY,
            "stages[].body.initial_temperature": InputRole.INITIAL_CONDITION,
            "stages[].body.ambient_temperature": InputRole.BOUNDARY_CONDITION,
            "stages[].body.duration": InputRole.OPERATING_CONDITION,
        },
        prefixes={
            "stages[].body.applicability.": InputRole.APPLICABILITY,
            "stages[].conductor.limits.": InputRole.APPLICABILITY,
            "stages[].conductor.ratings.": InputRole.APPLICABILITY,
            "stages[].conductor.element.": InputRole.APPLICABILITY,
            "source_ratings.": InputRole.APPLICABILITY,
            "source_regulation.": InputRole.PARAMETER,
            "coupling.": InputRole.NUMERICS,
            "cross_solver_check.": InputRole.NUMERICS,
        },
    )

    return CapabilityDeclaration(
        capability_id=ELECTROTHERMAL_CAPABILITY_ID,
        version="1",
        domain="electrothermal",
        summary=(
            "Self-heating conductors in series across one ideal DC voltage source, "
            "each paired one-to-one with a first-order lumped thermal body, run to a "
            "quasi-static end-of-interval fixed point. One credibility report per stage."
        ),
        provides=_provided(material.LINEAR_TCR_REALIZATION, lumped.LUMPED_CLOSED_FORM_REALIZATION),
        inputs=inputs,
        produces=_produced(
            lumped.LUMPED_CAPACITY_MODEL,
            ("final_temperature", "steady_state_temperature", "time_constant"),
            instance_key="component_id",
            instance_path="stages[].component_id",
        ),
        models=models,
        solvers=(
            SolverUse(lumped.SOLVER_ID, lumped.SOLVER_VERSION, ("thermal:lumped_capacity_transient",)),
            SolverUse(material.SOLVER_ID, material.SOLVER_VERSION),
            SolverUse(dc_solver.SOLVER_ID, dc_solver.SOLVER_VERSION, ("electrical:dc_linear", "core:linear_system")),
        ),
        claim_shapes=_BOTH_SHAPES,
        attainable_levels=(
            AttainableLevel(
                ValidationLevel.ANALYTICALLY_VERIFIED,
                check_name="analytic_reference_agreement",
                route_id="thermal.lumped.series_recurrence",
                condition="the lumped body's closed form agrees with the pinned series-recurrence reference",
            ),
        ),
        uncertainty=UncertaintyCapability(
            quantified={
                name: (UncertaintyChannel.EPISTEMIC_PARAMETER,)
                for name in ("final_temperature", "steady_state_temperature", "time_constant")
            },
            basis=_ET_PARAMETER_UQ,
        ),
        perturbable=tuple(PerturbableInput(path, why) for path, why in _ET_PERTURBABLE),
        routes=(
            RouteDeclaration(
                route_id="electrothermal.fixed_point",
                kind=RouteKind.PRIMARY_SIMULATION,
                pinned_route="electrical.dc.native_mna",
                description="Gauss-Seidel fixed point over the native MNA solve, the TCR evaluator and the lumped closed form",
            ),
            RouteDeclaration(
                route_id="thermal.lumped.series_recurrence",
                kind=RouteKind.ANALYTIC_REFERENCE,
                analytic_reference="thermal_models.lumped.series_recurrence",
                check_name="analytic_reference_agreement",
                description="the pinned series-recurrence reference for the lumped body",
            ),
            RouteDeclaration(
                route_id="electrical.dc.external_simulator",
                kind=RouteKind.SOLVER_ROUTE,
                pinned_route="electrical.dc.external_simulator",
                check_name="cross_solver_agreement",
                activation=("cross_solver_check.external_provider",),
                description=(
                    "a second DC solve by an external program, requested per case. On this path "
                    "its level is always withheld (no artifact-verified independence evidence), "
                    "so it attains nothing here"
                ),
            ),
        ),
        executor=_run_electrothermal,
    )


# ---------------------------------------------------------------------------
# Battery
# ---------------------------------------------------------------------------


def _run_battery(case: Mapping[str, Any], *, run_id: str) -> CapabilityRun:
    from .battery import run_battery_case

    run = run_battery_case(dict(case), run_id=run_id)
    return CapabilityRun(reports=(InstanceReport(None, run.report),), native=run)


def battery_capability() -> CapabilityDeclaration:
    from ..domains.battery import models as battery_models
    from ..domains.battery import solver as battery_solver
    from ..domains.thermal_models import lumped
    from .battery import describe_battery_case

    description = describe_battery_case()
    by_id = _models_by_id(battery_models.battery_model_registry(), lumped.lumped_model_registry())
    missing = sorted(set(description.models) - set(by_id))
    if missing:
        raise CapabilityDeclarationError(f"battery runs models no registry defines: {missing}")

    inputs = _inputs_from_description(
        description,
        exact={
            "cell.cell_id": InputRole.IDENTITY,
            "load.load_id": InputRole.IDENTITY,
            "load.state_of_charge": InputRole.INITIAL_CONDITION,
            "load.cell_temperature": InputRole.INITIAL_CONDITION,
            "thermal.ambient_temperature": InputRole.BOUNDARY_CONDITION,
        },
        prefixes={
            "cell.limits.": InputRole.APPLICABILITY,
            "thermal.applicability.": InputRole.APPLICABILITY,
            "load.": InputRole.OPERATING_CONDITION,
            "march.": InputRole.NUMERICS,
        },
        # The case description lists this limit as optional, and a coupled run
        # refuses without it (engcore.mcp.battery: "cell_thermal_conductance is
        # required for a coupled run"). Routing a claim on the description would
        # produce a READY case the system refuses; the declaration states what
        # the run needs.
        required_overrides={
            "cell.limits.cell_thermal_conductance": (
                "the self-heating condition and the thermal body's exchange are both stated over it"
            ),
        },
    )
    produced = (
        _produced(
            battery_models.RINT_OCV_MODEL,
            ("terminal_voltage", "open_circuit_voltage", "heat_generation"),
        )
        + _produced(battery_models.COULOMB_COUNTING_MODEL, ("final_state_of_charge",))
        + _produced(lumped.LUMPED_CAPACITY_MODEL, ("final_temperature",))
    )
    return CapabilityDeclaration(
        capability_id=BATTERY_CAPABILITY_ID,
        version="2",
        domain="battery",
        summary=(
            "One equivalent-circuit cell discharged over a marched interval, heating "
            "itself against a lumped thermal body. One-way coupling; one credibility "
            "report. load.duration is the length of ONE march step."
        ),
        provides=_provided(battery_models.RINT_OCV_REALIZATION, lumped.LUMPED_CLOSED_FORM_REALIZATION),
        inputs=inputs,
        produces=produced,
        models=tuple(ModelUse.of(by_id[model_id]) for model_id in description.models),
        solvers=(
            SolverUse(battery_solver.SOLVER_ID, battery_solver.SOLVER_VERSION, ("battery:cell_discharge_step", "core:algebraic")),
            SolverUse(lumped.SOLVER_ID, lumped.SOLVER_VERSION, ("thermal:lumped_capacity_transient",)),
        ),
        claim_shapes=_BOTH_SHAPES,
        attainable_levels=(
            AttainableLevel(
                ValidationLevel.DIMENSIONALLY_VALID,
                check_name="metric_dimensions",
                route_id=None,
                condition="every reported metric carries its declared dimension",
            ),
            AttainableLevel(
                ValidationLevel.ANALYTICALLY_VERIFIED,
                check_name="analytic_reference_agreement",
                route_id="thermal.lumped.series_recurrence",
                condition="the lumped body's closed form agrees with the pinned series-recurrence reference",
            ),
        ),
        uncertainty=UncertaintyCapability(
            quantified={
                name: (UncertaintyChannel.EPISTEMIC_PARAMETER,)
                for name in (
                    "terminal_voltage",
                    "open_circuit_voltage",
                    "heat_generation",
                    "final_state_of_charge",
                    "final_temperature",
                )
            },
            basis=_BATTERY_PARAMETER_UQ,
        ),
        perturbable=tuple(
            PerturbableInput(path, rationale)
            for path, rationale in _BATTERY_PERTURBABLE
        ),
        routes=(
            RouteDeclaration(
                route_id="battery.march",
                kind=RouteKind.PRIMARY_SIMULATION,
                description="closed-form cell steps marched one-way into the lumped thermal body",
            ),
            RouteDeclaration(
                route_id="thermal.lumped.series_recurrence",
                kind=RouteKind.ANALYTIC_REFERENCE,
                analytic_reference="thermal_models.lumped.series_recurrence",
                check_name="analytic_reference_agreement",
                description="the pinned series-recurrence reference for the lumped body",
            ),
        ),
        executor=_run_battery,
    )


# ---------------------------------------------------------------------------
# NAFEMS T3
# ---------------------------------------------------------------------------

#: Scientific role of each T3 model input. The model is restricted to one exact
#: operating point, so every one of these is also validity evidence: a claim
#: that does not state it leaves the model's applicability UNKNOWN.
_T3_ROLES = {
    "length": InputRole.PARAMETER,
    "width": InputRole.PARAMETER,
    "depth": InputRole.PARAMETER,
    "conductivity": InputRole.PARAMETER,
    "density": InputRole.PARAMETER,
    "specific_heat": InputRole.PARAMETER,
    "internal_heat_generation": InputRole.PARAMETER,
    "initial_temperature": InputRole.INITIAL_CONDITION,
    "left_boundary_temperature": InputRole.BOUNDARY_CONDITION,
    "right_boundary_offset": InputRole.BOUNDARY_CONDITION,
    "right_boundary_amplitude": InputRole.BOUNDARY_CONDITION,
    "right_boundary_sine_time_scale": InputRole.BOUNDARY_CONDITION,
    "lateral_heat_flux": InputRole.BOUNDARY_CONDITION,
    "end_time": InputRole.OPERATING_CONDITION,
    "probe_position": InputRole.OPERATING_CONDITION,
}


def _run_nafems_t3(case: Mapping[str, Any], *, run_id: str) -> CapabilityRun:
    from ..domains.thermal_models.nafems_t3 import NAFEMST3Numerics
    from ..domains.thermal_models.nafems_t3_oracle import CONDITIONS
    from .nafems_t3 import run_nafems_t3_credibility

    stated = {key: value for key, value in case.items() if key != "numerics"}
    unknown = sorted(set(stated) - set(CONDITIONS))
    if unknown:
        raise CapabilityExecutionRefused(f"NAFEMS T3 has no operating-point input {unknown}")
    # The physics is fixed. A case stating another operating point is refused
    # here, before anything runs, so a T3 report can never be read as the answer
    # to a question about a different bar.
    for name, text in stated.items():
        value = Quantity.parse(text)
        fixed = CONDITIONS[name]
        if value.to(fixed.units).magnitude != fixed.magnitude:
            raise CapabilityExecutionRefused(
                f"NAFEMS T3 runs only at its declared operating point; {name}={value} is not {fixed}"
            )
    numerics = dict(case.get("numerics", {}))
    report = run_nafems_t3_credibility(run_id=run_id, numerics=NAFEMST3Numerics(**numerics))
    return CapabilityRun(reports=(InstanceReport(None, report),), native=report)


def nafems_t3_capability() -> CapabilityDeclaration:
    from ..domains.thermal_models import nafems_t3
    from ..domains.thermal_models.nafems_t3_oracle import ORACLE_ID, ORACLE_VERSION, nafems_t3_evidence

    model = nafems_t3.MODEL
    specs = {spec.name: spec for spec in model.inputs}
    if set(specs) != set(_T3_ROLES):
        raise CapabilityDeclarationError(
            f"T3 role table {sorted(_T3_ROLES)} does not match the model's inputs {sorted(specs)}"
        )
    inputs = tuple(
        InputDeclaration(
            path=name,
            kind=InputKind.QUANTITY,
            role=_T3_ROLES[name],
            required=False,
            unit_exemplar=specs[name].unit_exemplar,
            model_id=model.model_id,
            model_input=name,
            unlocks_conditions=(name,),
            description=(
                f"{specs[name].description} The run is fixed at the benchmark value; stating it "
                f"is what lets the model's applicability to the claim be assessed."
            ),
        )
        for name in sorted(specs)
    ) + (
        InputDeclaration(
            path="numerics.n_cells",
            kind=InputKind.COUNT,
            role=InputRole.NUMERICS,
            required=False,
            description="spatial cells of the fine grid; divisible by 5, at least 20",
        ),
        InputDeclaration(
            path="numerics.n_steps",
            kind=InputKind.COUNT,
            role=InputRole.NUMERICS,
            required=False,
            description="time steps of the fine grid",
        ),
    )
    return CapabilityDeclaration(
        capability_id=NAFEMS_T3_CAPABILITY_ID,
        version="1",
        domain="thermal",
        summary=(
            "The NAFEMS P18.T3 one-dimensional transient conduction benchmark, executed by "
            "Crank-Nicolson at its single declared operating point and compared with the "
            "repository-pinned external benchmark target."
        ),
        provides=(
            ProvidedCapability(
                "thermal:transient_conduction_1d",
                basis=(
                    f"stated: {model.model_id}@{model.version} is a one-dimensional transient "
                    f"heat-conduction model restricted to one operating point; no realization "
                    f"record exists for it"
                ),
            ),
        ),
        inputs=inputs,
        produces=_produced(model, (nafems_t3.QOI,)),
        models=(ModelUse.of(model),),
        solvers=(SolverUse(nafems_t3.SOLVER_ID, nafems_t3.SOLVER_VERSION, ("core:pde",)),),
        claim_shapes=_BOTH_SHAPES,
        attainable_levels=(
            AttainableLevel(
                ValidationLevel.BENCHMARK_VALIDATED,
                check_name="nafems_t3_external_benchmark",
                route_id="nafems.p18.t3.oracle",
                condition="the probe temperature agrees with the trusted NAFEMS T3 target at the exact benchmark point",
            ),
        ),
        uncertainty=UncertaintyCapability(
            quantified={nafems_t3.QOI: (UncertaintyChannel.NUMERICAL,)},
            basis=(
                "NUMERICAL is quantified by a declared three-level space-and-time refinement of the "
                "Crank-Nicolson solve (Richardson extrapolation with the observed order, reported as a GCI "
                "interval, or UNKNOWN when the levels are not in the asymptotic range). Parameter, measurement "
                "and model-form uncertainty are not quantified"
            ),
        ),
        refinement=RefinementStudy(
            quantities=frozenset({nafems_t3.QOI}),
            refined_inputs={
                "numerics.n_cells": nafems_t3.NAFEMST3Numerics().n_cells,
                "numerics.n_steps": nafems_t3.NAFEMST3Numerics().n_steps,
            },
            ratio=2,
            levels=3,
            formal_order=2.0,
            order_tolerance=0.25,
            basis=(
                "second-order central differences in space and Crank-Nicolson in time, refined together by 2 "
                "so the leading error scales as h**2; the coarsest level keeps the probe on a node and its own "
                "2x-coarser companion valid"
            ),
            accuracy_checks=frozenset({"nafems_t3_refinement_sensitivity", "nafems_t3_external_benchmark"}),
        ),
        routes=(
            RouteDeclaration(
                route_id="nafems_t3.crank_nicolson",
                kind=RouteKind.PRIMARY_SIMULATION,
                description="second-order finite differences in space, Crank-Nicolson in time",
            ),
            RouteDeclaration(
                route_id="nafems.p18.t3.oracle",
                kind=RouteKind.BENCHMARK,
                oracle=(ORACLE_ID, ORACLE_VERSION),
                oracle_provider=nafems_t3_evidence,
                check_name="nafems_t3_external_benchmark",
                description="the repository-pinned NAFEMS P18.T3 target temperature",
            ),
        ),
        executor=_run_nafems_t3,
    )


@lru_cache(maxsize=1)
def _builtin_production_capabilities() -> tuple[CapabilityDeclaration, ...]:
    """Built-in declarations are immutable for the life of this process."""
    return (
        electrothermal_capability(),
        battery_capability(),
        nafems_t3_capability(),
    )


def production_registry() -> CapabilityRegistry:
    """Every capability the production claim router may execute.

    Built-ins are cached because deriving their field unlocks is relatively
    expensive. Enabled Domain Packs are read on every registry build so an
    explicitly registered pack cannot be hidden by a singleton created before
    it was enabled. CapabilityRegistry itself rejects duplicate ids.
    """
    from .production_packs import production_pack_capabilities

    return CapabilityRegistry(
        (*_builtin_production_capabilities(), *production_pack_capabilities())
    )
