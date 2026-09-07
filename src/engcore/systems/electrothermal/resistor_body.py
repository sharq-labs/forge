"""One resistor, its thermal body, and the environment they sit in.

MIN-FOUNDATION-ET. The minimum two-way electro-thermal consumer::

              ┌────────────────────────────────────────────┐
    temperature│                                           │resistance
              ↓                                            │
    [ lumped thermal body ]                [ R(T) property model ]
              ↑                                            │
    heat input│                                            ↓
              │        [ DC circuit: V1, R1 ]──────────────┘
              └─────────── dissipated power ───────────────┘

Three separately posed problems, three directed quantity dependencies, one
twin. The electrical side is the **existing, unmodified** Electrical DC V0
domain, written long before coupling was contemplated — which is the only
reason anything here counts as evidence about the contracts rather than about
this module.

What this module executes
-------------------------
Exactly **one open-loop pass**::

    T0 -> R(T0) -> electrical solve -> P0 -> thermal step -> T1 -> R(T1)

and stops. There is no fixed-point iteration, no coupling convergence
criterion, no relaxation, no rollback and no second electrical solve. ``R(T1)``
is computed to demonstrate that the feedback path exists and is evaluable; it
is not fed back. A coupled solve is the next milestone.

What this module is not
-----------------------
Not a coupling runtime, not a scheduler, not a planner, not a solver. It builds
records, and runs one pass through published contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from ...domains.electrical import material as mat
from ...domains.electrical.dc import (
    DCCircuit,
    DCVoltageSource,
    ElectricalNode,
    Resistor,
    build_dc_problem,
    models_for_circuit,
    solve_circuit,
)
from ...domains.electrical.dc.problem import resistance_name
from ...domains.thermal_models import lumped as lump
from ...scientific.composition import QuantityDependency
from ...scientific.errors import InvalidScientificProblem
from ...scientific.ir.problem import ModelReference, ScientificProblem
from ...scientific.realizations.definition import ModelRealizationDefinition
from ...scientific.results.provenance import ExecutionBinding, ProvenanceRecord
from ...scientific.results.result import ScientificResult
from ...scientific.results.uncertainty import Uncertainty
from ...scientific.twins.definition import (
    ScientificTwin,
    TwinDatum,
    TwinDatumRole,
    TwinKind,
)
from ...scientific.units.quantity import Quantity, dimensionality

__all__ = [
    "DEPENDENCY_HEAT",
    "DEPENDENCY_RESISTANCE",
    "DEPENDENCY_TEMPERATURE",
    "ElectroThermalResistor",
    "OpenLoopPass",
    "build_electrical_problem",
    "build_twin",
    "candidate_sources",
    "electrothermal_dependencies",
    "electrothermal_problems",
    "run_open_loop_pass",
]

#: Names of the three declared dependencies. Prose labels for humans reading a
#: record; nothing branches on them.
DEPENDENCY_HEAT = "joule-dissipation-heats-body"
DEPENDENCY_TEMPERATURE = "body-temperature-sets-property-state"
DEPENDENCY_RESISTANCE = "property-resistance-sets-circuit-element"

#: The electrical result metric carrying the resistor's absorbed power. Read
#: from the domain's published metric namespace; never parsed.
RESISTOR_POWER_METRIC = "resistor_power:{component_id}"

SOURCE_ID = "V1"
NODE_HOT = "n1"
NODE_REFERENCE = "gnd"


@dataclass(frozen=True)
class ElectroThermalResistor:
    """One declared instance: a conductor, its thermal body, its supply.

    The conductor and the body deliberately share a ``component_id``. That
    co-identity is a **convention of this system pack**, not a contract: no
    universal record states that this conductor and this body are one object.
    Introducing a component-instance identity to state it was tested and
    deferred — with one of each, nothing becomes impossible, duplicated or
    ambiguous. It would stop being deferrable at two.
    """

    conductor: mat.TemperatureDependentConductor
    body: lump.ThermalBody
    source_voltage: Quantity
    system_id: str = "electrothermal-resistor-body"

    def __post_init__(self) -> None:
        if not isinstance(self.conductor, mat.TemperatureDependentConductor):
            raise InvalidScientificProblem(
                "conductor must be a TemperatureDependentConductor"
            )
        if not isinstance(self.body, lump.ThermalBody):
            raise InvalidScientificProblem("body must be a ThermalBody")
        if not isinstance(self.source_voltage, Quantity):
            raise InvalidScientificProblem("source_voltage must be a Quantity")
        self.source_voltage.require_compatible(
            "volt", context="electro-thermal source voltage"
        )
        if self.conductor.component_id != self.body.body_id:
            raise InvalidScientificProblem(
                f"conductor {self.conductor.component_id!r} and body "
                f"{self.body.body_id!r} must share an id in this system pack; "
                f"no universal record states that two declarations describe "
                f"one physical object, so this pack keeps them aligned by "
                f"construction"
            )

    @property
    def component_id(self) -> str:
        return self.conductor.component_id

    @property
    def power_metric(self) -> str:
        return RESISTOR_POWER_METRIC.format(component_id=self.component_id)

    @property
    def circuit_id(self) -> str:
        return f"{self.system_id}-{self.component_id}"

    def circuit_at(self, resistance: Quantity) -> DCCircuit:
        """The DC circuit with the resistor set to one evaluated resistance."""
        return DCCircuit(
            circuit_id=self.circuit_id,
            nodes=(
                ElectricalNode(NODE_HOT),
                ElectricalNode(NODE_REFERENCE, is_reference=True),
            ),
            resistors=(
                Resistor(
                    self.component_id, NODE_HOT, NODE_REFERENCE, resistance
                ),
            ),
            voltage_sources=(
                DCVoltageSource(
                    SOURCE_ID, NODE_HOT, NODE_REFERENCE, self.source_voltage
                ),
            ),
        )


# =====================================================================
# Representation
# =====================================================================

def build_electrical_problem(
    system: ElectroThermalResistor, resistance: Quantity
) -> ScientificProblem:
    """The electrical problem at one evaluated resistance.

    The resistance has to be supplied to *build* the problem, because the
    Electrical DC domain carries it as a configured ``ScientificParameter`` and
    folds it into the circuit's canonical identity. That is the configuration/
    state conflation this milestone measures rather than repairs — see
    :func:`electrothermal_dependencies` and the milestone evidence.
    """
    return build_dc_problem(system.circuit_at(resistance))


def electrothermal_problems(
    system: ElectroThermalResistor, resistance: Quantity
) -> tuple[ScientificProblem, ScientificProblem, ScientificProblem]:
    """``(electrical, property, thermal)`` — three separately posed problems.

    Three, not one. A single merged "electro-thermal problem" would have to
    carry a single merged model spanning both sciences, and cross-domain
    composition exists precisely so that the electrical claim and the thermal
    claim stay separately statable, separately valid and separately reusable.
    """
    return (
        build_electrical_problem(system, resistance),
        mat.build_resistance_problem(system.conductor),
        lump.build_lumped_thermal_problem(system.body),
    )


def build_twin(
    system: ElectroThermalResistor,
    *,
    twin_id: str | None = None,
    version: str = "0.1.0",
) -> ScientificTwin:
    """The instance authority for this system. **The only one.**

    Every declared number of the instance lives here once, with a typed role.
    No ``SystemInstance``, ``ComponentInstance`` or ``AssemblyInstance`` is
    created: each would restate what these declarations already say, and a
    second authority for instance state is worse than none.

    Note the two role vocabularies in play. ``TwinDatumRole`` offers
    ``OPERATING_CONDITION``, which is the honest home for an ambient; the
    problem-level ``VariableRole`` has no such member and the same quantity is
    a ``CONTROL`` there. Nothing maps the two sets, and this pack does not
    invent a mapping.
    """
    conductor = system.conductor
    body = system.body
    return ScientificTwin(
        twin_id=twin_id or system.system_id,
        version=version,
        kind=TwinKind.CONCEPT,
        name="Self-heating resistor with a lumped thermal body",
        description=(
            "One conductor whose resistance depends on its temperature, "
            "thermally represented as a lumped body exchanging with an "
            "ambient, supplied by an ideal DC voltage source."
        ),
        models=(
            ModelReference(
                mat.LINEAR_TCR_MODEL.model_id, mat.LINEAR_TCR_MODEL.version
            ),
            ModelReference(
                lump.LUMPED_CAPACITY_MODEL.model_id,
                lump.LUMPED_CAPACITY_MODEL.version,
            ),
        ),
        declarations=(
            TwinDatum(
                name=f"reference_resistance:{system.component_id}",
                value=conductor.reference_resistance,
                role=TwinDatumRole.PARAMETER,
            ),
            TwinDatum(
                name=f"temperature_coefficient:{system.component_id}",
                value=conductor.temperature_coefficient,
                role=TwinDatumRole.PARAMETER,
            ),
            TwinDatum(
                name=f"reference_temperature:{system.component_id}",
                value=conductor.reference_temperature,
                role=TwinDatumRole.PARAMETER,
            ),
            TwinDatum(
                name=f"heat_capacity:{system.component_id}",
                value=body.heat_capacity,
                role=TwinDatumRole.PARAMETER,
            ),
            TwinDatum(
                name=f"ambient_conductance:{system.component_id}",
                value=body.ambient_conductance,
                role=TwinDatumRole.PARAMETER,
            ),
            # An imposed external condition, not a property of the system.
            TwinDatum(
                name="ambient_temperature",
                value=body.ambient_temperature,
                role=TwinDatumRole.OPERATING_CONDITION,
            ),
            TwinDatum(
                name=f"source_voltage:{SOURCE_ID}",
                value=system.source_voltage,
                role=TwinDatumRole.CONTROL,
            ),
            # The one evolving quantity, declared as state at t0.
            TwinDatum(
                name=f"temperature:{system.component_id}",
                value=body.initial_temperature,
                role=TwinDatumRole.STATE,
                description="Body temperature at the start of the interval.",
            ),
        ),
        assumptions=(
            "the conductor and its thermal body are the same physical object",
            "the whole dissipated power of the resistor enters the body",
            "one open-loop pass only; no coupled steady state is claimed",
        ),
    )


def electrothermal_dependencies(
    system: ElectroThermalResistor,
    problems: tuple[ScientificProblem, ScientificProblem, ScientificProblem],
) -> tuple[QuantityDependency, ...]:
    """The three directed dependencies that close the electro-thermal loop.

    Read as a set they say: electrical dissipation heats the body; the body's
    temperature is the state at which the property is evaluated; the evaluated
    resistance is the circuit element's value. Both directions are present, and
    the thermal-to-electrical direction goes *through a material property*,
    which is the scientifically correct route rather than a shortcut.

    ``ambient_temperature`` deliberately has **no** record here. It is imposed
    by the environment, and :func:`externally_imposed` reports it as such —
    absence is the answer, not a gap.
    """
    electrical, prop, thermal = problems
    return (
        QuantityDependency(
            source_problem_id=electrical.problem_id,
            source_quantity=system.power_metric,
            target_problem_id=thermal.problem_id,
            target_quantity=lump.HEAT_INPUT,
            unit_exemplar=lump.POWER_UNIT,
            name=DEPENDENCY_HEAT,
            description=(
                "The power absorbed by the resistor is the heat delivered to "
                "the body it is thermally represented by."
            ),
        ),
        QuantityDependency(
            source_problem_id=thermal.problem_id,
            source_quantity=lump.TEMPERATURE_METRIC,
            target_problem_id=prop.problem_id,
            target_quantity=mat.TEMPERATURE,
            unit_exemplar=mat.TEMPERATURE_UNIT,
            name=DEPENDENCY_TEMPERATURE,
            description=(
                "The body temperature is the state coordinate at which the "
                "conductor's resistance is evaluated."
            ),
        ),
        # The one that a reader could not otherwise even detect: its target is
        # a configured PARAMETER of the electrical problem, indistinguishable
        # from a genuinely fixed value.
        QuantityDependency(
            source_problem_id=prop.problem_id,
            source_quantity=mat.RESISTANCE_METRIC,
            target_problem_id=electrical.problem_id,
            target_quantity=resistance_name(system.component_id),
            unit_exemplar=mat.RESISTANCE_UNIT,
            name=DEPENDENCY_RESISTANCE,
            description=(
                "The evaluated resistance is the value the circuit element "
                "takes. The electrical domain models it as configuration, so "
                "nothing but this record says it is computed."
            ),
        ),
    )


def candidate_sources(
    target_unit: str,
    problems: Iterable[ScientificProblem],
    results: Mapping[str, Mapping[str, Quantity]] = (),
    *,
    exclude: tuple[str, str] | None = None,
) -> tuple[tuple[str, str, str], ...]:
    """Every declared quantity of a matching dimension, from records alone.

    The measurement behind the milestone's central claim. Given a target's
    dimension, it returns everything in the system that could supply it on
    dimensional grounds — which is what a reader without a
    :class:`QuantityDependency` is reduced to guessing between.

    It reads only what a record enumerates: problem variables, quantity-valued
    parameters and result metrics. It never parses a name.
    """
    wanted = dimensionality(target_unit)
    found: list[tuple[str, str, str]] = []
    for problem in problems:
        for variable in problem.variables:
            found.append((problem.problem_id, variable.name, variable.unit))
        for parameter in problem.parameters:
            if isinstance(parameter.value, Quantity):
                found.append(
                    (problem.problem_id, parameter.name, parameter.value.units)
                )
    for problem_id, values in dict(results).items():
        for name, quantity in values.items():
            found.append((problem_id, name, quantity.units))
    return tuple(
        entry
        for entry in found
        if dimensionality(entry[2]) == wanted
        and (exclude is None or (entry[0], entry[1]) != exclude)
    )


# =====================================================================
# One open-loop pass
# =====================================================================

@dataclass(frozen=True)
class OpenLoopPass:
    """What one pass produced. **Not** a coupled solution.

    ``resistance_after`` is the demonstration that the feedback path is
    evaluable. It was not fed back into a second electrical solve, and no
    coupled convergence is claimed anywhere in this record.
    """

    system: ElectroThermalResistor
    problems: tuple[ScientificProblem, ScientificProblem, ScientificProblem]
    dependencies: tuple[QuantityDependency, ...]
    twin: ScientificTwin
    resistance_before: Quantity
    dissipated_power: Quantity
    temperature_after: Quantity
    resistance_after: Quantity
    property_result: ScientificResult
    electrical_result: ScientificResult
    thermal_result: ScientificResult
    provenance: ProvenanceRecord

    @property
    def coupled_convergence_claimed(self) -> bool:
        """Always ``False``, and asserted by a test.

        One pass converges nothing. A property that can only answer ``False``
        is here so that the claim is checkable rather than merely absent.
        """
        return False


def _property_result(
    *,
    run_id: str,
    problem: ScientificProblem,
    solver: mat.ResistancePropertySolver,
    prepared,
    raw,
    realization: ModelRealizationDefinition,
) -> ScientificResult:
    metrics = solver.extract_metrics(prepared, raw)
    model = ModelReference(
        mat.LINEAR_TCR_MODEL.model_id, mat.LINEAR_TCR_MODEL.version
    )
    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version="engcore.domains.electrical.material/0.1.0",
        bindings=(
            ExecutionBinding(
                model=model,
                realization=realization.reference(),
                solver=solver.identity,
            ),
        ),
        inputs=dict(problem.quantity_parameters())
        | {
            mat.TEMPERATURE: Quantity(
                prepared.payload.temperature_k, mat.TEMPERATURE_UNIT
            )
        },
        assumptions=mat.LINEAR_TCR_MODEL.assumptions,
    )
    return ScientificResult(
        result_id=run_id,
        problem_id=problem.problem_id,
        values=metrics,
        models=((model.model_id, model.version),),
        # See `coupled.py`: the applicability question about this model is
        # asked where the declaration lives, not here, and this path says so
        # rather than leaving an empty mapping to be read as either.
        validity_not_assessed={
            model.model_id: (
                "not assessed by this element solve: the conditions are about "
                "the declared validity span and the element's ratings, which "
                "this solve does not hold. The assessment is made by the "
                "applicability layer that holds the declaration, and reaches "
                "the reader through the evidence report"
            )
        },
        solver=solver.identity,
        convergence=raw.convergence,
        validation=solver.validate(prepared, raw),
        uncertainty={
            name: Uncertainty.unknown(
                "no uncertainty quantification is performed on the declared "
                "temperature coefficient"
            )
            for name in metrics
        },
        assumptions=mat.LINEAR_TCR_MODEL.assumptions,
        provenance=provenance,
    )


def _thermal_result(
    *,
    run_id: str,
    problem: ScientificProblem,
    solver: lump.LumpedThermalSolver,
    prepared,
    raw,
    realization: ModelRealizationDefinition,
    heat_input: Quantity,
) -> ScientificResult:
    metrics = solver.extract_metrics(prepared, raw)
    model = ModelReference(
        lump.LUMPED_CAPACITY_MODEL.model_id, lump.LUMPED_CAPACITY_MODEL.version
    )
    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version="engcore.domains.thermal_models.lumped/0.1.0",
        bindings=(
            ExecutionBinding(
                model=model,
                realization=realization.reference(),
                solver=solver.identity,
            ),
        ),
        inputs=dict(problem.quantity_parameters())
        | {
            lump.HEAT_INPUT: heat_input,
            lump.AMBIENT_TEMPERATURE: prepared.payload.body.ambient_temperature,
            lump.TEMPERATURE: prepared.payload.body.initial_temperature,
        },
        assumptions=lump.LUMPED_CAPACITY_MODEL.assumptions,
    )
    return ScientificResult(
        result_id=run_id,
        problem_id=problem.problem_id,
        values=metrics,
        models=((model.model_id, model.version),),
        # See `coupled.py`: the applicability question about this model is
        # asked where the declaration lives, not here, and this path says so
        # rather than leaving an empty mapping to be read as either.
        validity_not_assessed={
            model.model_id: (
                "not assessed by this element solve: the conditions are about "
                "the declared validity span and the element's ratings, which "
                "this solve does not hold. The assessment is made by the "
                "applicability layer that holds the declaration, and reaches "
                "the reader through the evidence report"
            )
        },
        solver=solver.identity,
        convergence=raw.convergence,
        validation=solver.validate(prepared, raw),
        uncertainty={
            name: Uncertainty.unknown(
                "no uncertainty quantification is performed on the lumped "
                "thermal declaration"
            )
            for name in metrics
        },
        assumptions=lump.LUMPED_CAPACITY_MODEL.assumptions,
        provenance=provenance,
    )


def run_open_loop_pass(
    system: ElectroThermalResistor, *, run_id: str = "et-open-loop"
) -> OpenLoopPass:
    """Evaluate R(T0), solve the circuit, advance the body, evaluate R(T1).

    One electrical solve and one thermal step. The final resistance is not fed
    back: a second electrical solve is where a coupled iteration would begin,
    and that begins in the next milestone.
    """
    body = system.body

    # 1. Property at the initial state.
    property_problem = mat.build_resistance_problem(system.conductor)
    property_solver = mat.ResistancePropertySolver()
    property_solver.bind_conductor(
        system.conductor,
        property_problem.problem_id,
        temperature=body.initial_temperature,
    )
    prepared_property = property_solver.prepare(property_problem)
    raw_property = property_solver.solve(prepared_property)
    resistance_before = property_solver.extract_metrics(
        prepared_property, raw_property
    )[mat.RESISTANCE_METRIC]
    property_result = _property_result(
        run_id=f"{run_id}-property-1",
        problem=property_problem,
        solver=property_solver,
        prepared=prepared_property,
        raw=raw_property,
        realization=prepared_property.payload.realization,
    )

    # 2. The one electrical solve, at that resistance.
    circuit = system.circuit_at(resistance_before)
    electrical_problem = build_dc_problem(circuit)
    electrical_result = solve_circuit(
        circuit,
        run_id=f"{run_id}-electrical-1",
        problem=electrical_problem,
        parent_run_id=property_result.result_id,
    )
    dissipated_power = electrical_result.values[system.power_metric]

    # 3. The one thermal step, under that dissipation.
    thermal_problem = lump.build_lumped_thermal_problem(body)
    thermal_solver = lump.LumpedThermalSolver()
    thermal_solver.bind_body(
        body, thermal_problem.problem_id, heat_input=dissipated_power
    )
    prepared_thermal = thermal_solver.prepare(thermal_problem)
    raw_thermal = thermal_solver.solve(prepared_thermal)
    temperature_after = thermal_solver.extract_metrics(
        prepared_thermal, raw_thermal
    )[lump.TEMPERATURE_METRIC]
    thermal_result = _thermal_result(
        run_id=f"{run_id}-thermal-1",
        problem=thermal_problem,
        solver=thermal_solver,
        prepared=prepared_thermal,
        raw=raw_thermal,
        realization=prepared_thermal.payload.realization,
        heat_input=dissipated_power,
    )

    # 4. The feedback path, demonstrated and NOT closed.
    property_solver.bind_conductor(
        system.conductor,
        property_problem.problem_id,
        temperature=temperature_after,
    )
    prepared_feedback = property_solver.prepare(property_problem)
    resistance_after = property_solver.extract_metrics(
        prepared_feedback, property_solver.solve(prepared_feedback)
    )[mat.RESISTANCE_METRIC]

    problems = (electrical_problem, property_problem, thermal_problem)

    # One provenance record for the pass, carrying every model -> realization
    # -> solver association across both domains. This is the first record in
    # the repository with bindings at arity > 1 over more than one solver.
    bindings = (
        tuple(
            ExecutionBinding(
                model=ModelReference(model.model_id, model.version),
                realization=None,
                solver=electrical_result.solver,
            )
            for model in models_for_circuit(circuit)
        )
        + property_result.provenance.bindings
        + thermal_result.provenance.bindings
    )
    provenance = ProvenanceRecord(
        run_id=run_id,
        software_version="engcore.systems.electrothermal/0.1.0",
        bindings=bindings,
        inputs={
            "resistance_before": resistance_before,
            "dissipated_power": dissipated_power,
            "temperature_after": temperature_after,
            "resistance_after": resistance_after,
        },
        assumptions=(
            "one open-loop pass: one electrical solve and one thermal step",
            "the resistance evaluated at the final temperature was NOT fed "
            "back; no coupled steady state is computed or claimed",
        ),
    )

    return OpenLoopPass(
        system=system,
        problems=problems,
        dependencies=electrothermal_dependencies(system, problems),
        twin=build_twin(system),
        resistance_before=resistance_before,
        dissipated_power=dissipated_power,
        temperature_after=temperature_after,
        resistance_after=resistance_after,
        property_result=property_result,
        electrical_result=electrical_result,
        thermal_result=thermal_result,
        provenance=provenance,
    )
