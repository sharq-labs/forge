"""Built-in battery electrothermal Composition Pack — the Sprint 3 flagship.

The topology is a genuine cycle::

    cell temperature -> R0(T), R1(T) -> I^2 R0 + I v_p -> cell temperature

with the load current entering from outside as a measured, time-varying
schedule. That is what makes this different from the battery domain's existing
self-heating helper, which is honestly declared one-way because its resistance
does not depend on temperature.

What the pack declares, and what it refuses
--------------------------------------------
The applicability rules are the guardrail this campaign tests: discharge and
rest only, an ambient band the model's evidence covers, and positive thermal
and electrical parameters. A scenario outside them is refused at preflight,
before any state is advanced, and the refusal is the pack's -- not a harness's
opinion about where the model should be trusted.
"""

from __future__ import annotations

import hashlib
import json

from ..claims.capabilities import (
    CapabilityDeclaration,
    InputDeclaration,
    InputKind,
    InputRole,
    ModelUse,
    PerturbableInput,
    ProducedQuantity,
    ProvidedCapability,
    RouteDeclaration,
    RouteKind,
    UncertaintyCapability,
)
from ..claims.contract import ClaimKind
from ..domainpacks.builtin_battery_electrothermal import (
    MANIFEST as BATTERY_ELECTROTHERMAL_MANIFEST,
)
from ..domainpacks.builtin_thermal_lumped import (
    MANIFEST as THERMAL_LUMPED_MANIFEST,
)
from ..domainpacks.frozen import implementation_fingerprint
from ..domainpacks.manifest import ArtifactRef
from ..domains.battery import context as bctx
from ..domains.battery import electrothermal as et
from ..domains.battery import flagship as fl
from ..domains.thermal_models import lumped
from ..scientific.composition import EnergyConversion
from ..scientific.multiphysics import (
    CouplingEdge,
    CouplingScheme,
    IterationSemantics,
    PortDefinition,
    PortDirection,
    PortKind,
    PortRef,
)
from ..scientific.units.quantity import Quantity
from ..scientific.verification.dependencies import (
    DependencyComponent,
    DependencyRole,
    RouteDependencyManifest,
)
from ..scientific.verification.independence import IndependenceLevel
from ..scientific.verification.ladder import VerificationLevel
from ..scientific.verification.observations import VerificationObservation
from ..scientific.verification.planning import (
    VerificationCandidate,
    VerificationPolicy,
)
from ..scientific.verification.route import (
    VerificationRoute,
    VerificationRouteKind,
)
from ..scientific.verification.run_record import VerificationRunRecord
from ..sria.uncertainty import UncertaintyChannel
from .applicability import ApplicabilityPredicate, ApplicabilityPredicateKind
from .blueprint import (
    CouplingPolicyTemplate,
    CouplingWindowRule,
    CouplingWindowRuleKind,
    SystemGraphBlueprint,
)
from .contracts import (
    ProvidedCompositionValidation,
    SystemApplicabilityRule,
    SystemValidationCheck,
    SystemValidationResult,
    UncertaintyCompositionRule,
    UncertaintyCompositionStrategy,
    system_contract_digest,
)
from .inputs import ExternalInputBinding
from .manifest import (
    BlueprintRef,
    COMPOSITION_PACK_API,
    CompositionPackManifest,
    DomainPackDependency,
    PolicyTemplateRef,
)
from .participant import ParticipantBlueprint
from .references.battery_electrothermal import (
    LOAD_CURRENT_INPUT,
    battery_electrothermal_reference,
    battery_electrothermal_reference_evidence_digest,
    propagate_battery_parameter_uncertainty,
)
from .semantics import (
    CouplingSemantic,
    CouplingSignConvention,
    PortSemanticBinding,
)
from .uncertainty import ProvidedCompositionUncertainty, SystemUncertaintyResult
from .verification import ProvidedCompositionVerification

PACK_ID = "system.battery_electrothermal"
PACK_VERSION = "1"
CAPABILITY_ID = "system.battery_electrothermal"
BLUEPRINT_ID = "system.battery_electrothermal.graph"
BLUEPRINT_VERSION = "1"
POLICY_ID = "system.battery_electrothermal.staggered"
POLICY_VERSION = "1"

CELL_PARTICIPANT = "cell"
THERMAL_PARTICIPANT = "thermal"

CELL_ADAPTER_ID = "engcore.adapter.battery_electrothermal_1rc"
#: Its own adapter identity, not the thermal-resistance pack's. The physics is
#: the same lumped body, but this adapter also carries the cumulative energy
#: accounting the composition's balance check reads, and two implementations
#: behind one adapter id is exactly what the factory registry refuses.
THERMAL_ADAPTER_ID = "engcore.adapter.battery_thermal_lumped"
ADAPTER_VERSION = "1"

# -- quantity paths ---------------------------------------------------------
Q_TEMPERATURE = "thermodynamics.temperature"
Q_POWER = "electrical.dissipated_power"
Q_VOLTAGE = "electrical.terminal_voltage"
Q_CURRENT = "electrical.load_current"
Q_STATE_OF_CHARGE = "battery.state_of_charge"
Q_RESISTANCE_REFERENCE = "battery.resistance_reference"
Q_ACTIVATION_ENERGY = "battery.activation_energy"
Q_CAPACITANCE = "battery.polarization_capacitance"
Q_REFERENCE_TEMPERATURE = "battery.reference_temperature"
Q_CHARGE_BASIS = "battery.charge_state_basis"
Q_EFFICIENCY = "battery.coulombic_efficiency"
Q_POLARIZATION_VOLTAGE = "battery.polarization_voltage"
Q_HEAT_CAPACITY = "thermal.heat_capacity"
Q_AMBIENT_CONDUCTANCE = "thermal.ambient_conductance"
Q_AMBIENT_TEMPERATURE = "thermal.ambient_temperature"
Q_INITIAL_TEMPERATURE = "thermal.initial_temperature"

# -- produced quantity ids --------------------------------------------------
TERMINAL_VOLTAGE = "terminal_voltage"
CELL_TEMPERATURE = "cell_temperature"
STATE_OF_CHARGE = "state_of_charge"
HEAT_GENERATION = "heat_generation"

# -- fact paths -------------------------------------------------------------
F_R0 = "battery.ohmic_resistance_reference"
F_EA0 = "battery.ohmic_activation_energy"
F_R1 = "battery.polarization_resistance_reference"
F_EA1 = "battery.polarization_activation_energy"
F_C1 = "battery.polarization_capacitance"
F_TREF = "battery.reference_temperature"
F_QBASIS = "battery.charge_state_basis"
F_ETA = "battery.coulombic_efficiency"
F_Z0 = "battery.initial_state_of_charge"
F_VP0 = "battery.initial_polarization_voltage"
F_CURRENT = LOAD_CURRENT_INPUT
F_CTH = "thermal.heat_capacity"
F_HA = "thermal.ambient_conductance"
F_TAMB = "thermal.ambient_temperature"
F_T0 = "thermal.initial_temperature"

#: The system-level tolerance on what explicit staggered splitting costs. Not an
#: accuracy claim about the cell: the independent monolithic route measures the
#: actual coupled error of every executed run and this is the band the
#: composition declares it will accept for its own consistency checks.
COUPLING_RELATIVE_TOLERANCE = 5e-3
VERIFICATION_RELATIVE_TOLERANCE = 5e-3

#: The ambient band the pack's evidence covers, and the guardrail this campaign
#: tests. Outside it the composition refuses at preflight.
AMBIENT_LOWER = Quantity(293.15, bctx.TEMPERATURE_UNIT)
AMBIENT_UPPER = Quantity(303.15, bctx.TEMPERATURE_UNIT)

#: How negative a sampled current may be before the pack calls it charge.
#:
#: Not zero, and the reason is a measurement one. A current channel resting at
#: no load scatters about its own zero, so a profile of a pure discharge with a
#: rest contains samples of both signs at the milliamp level. A strict
#: non-negative predicate would read that scatter as a charge event and refuse a
#: discharge, which is a guardrail firing on instrument noise rather than on
#: physics.
#:
#: The floor is 50 mA: an order of magnitude above the few-milliamp scatter
#: these sources show at rest, and one eightieth of the smallest load this pack
#: is calibrated over. A genuine charge current of any consequence is far below
#: it and is refused; a charge below it would be a C/40 trickle, which this
#: model would not distinguish from rest anyway.
CHARGE_CURRENT_FLOOR = Quantity(-0.05, bctx.CURRENT_UNIT)


def battery_electrothermal_capability() -> CapabilityDeclaration:
    inputs = (
        InputDeclaration(
            path=F_R0,
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=bctx.RESISTANCE_UNIT,
            model_id=fl.MODEL_ID,
            model_input=fl.OHMIC_RESISTANCE_REFERENCE,
        ),
        InputDeclaration(
            path=F_EA0,
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=et.ACTIVATION_ENERGY_UNIT,
            model_id=fl.MODEL_ID,
            model_input=fl.OHMIC_ACTIVATION_ENERGY,
        ),
        InputDeclaration(
            path=F_R1,
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=bctx.RESISTANCE_UNIT,
            model_id=fl.MODEL_ID,
            model_input=fl.POLARIZATION_RESISTANCE_REFERENCE,
        ),
        InputDeclaration(
            path=F_EA1,
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=et.ACTIVATION_ENERGY_UNIT,
            model_id=fl.MODEL_ID,
            model_input=fl.POLARIZATION_ACTIVATION_ENERGY,
        ),
        InputDeclaration(
            path=F_C1,
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=et.CAPACITANCE_UNIT,
            model_id=fl.MODEL_ID,
            model_input=fl.POLARIZATION_CAPACITANCE,
        ),
        InputDeclaration(
            path=F_TREF,
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=bctx.TEMPERATURE_UNIT,
            model_id=fl.MODEL_ID,
            model_input=fl.REFERENCE_TEMPERATURE,
        ),
        InputDeclaration(
            path=F_QBASIS,
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=bctx.CAPACITY_UNIT,
            model_id=fl.MODEL_ID,
            model_input=fl.CHARGE_STATE_BASIS,
        ),
        InputDeclaration(
            path=F_ETA,
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=bctx.DIMENSIONLESS,
            model_id=fl.MODEL_ID,
            model_input=bctx.COULOMBIC_EFFICIENCY,
        ),
        InputDeclaration(
            path=F_Z0,
            kind=InputKind.QUANTITY,
            role=InputRole.INITIAL_CONDITION,
            required=True,
            unit_exemplar=bctx.DIMENSIONLESS,
            model_id=fl.MODEL_ID,
            model_input=bctx.STATE_OF_CHARGE,
        ),
        InputDeclaration(
            path=F_VP0,
            kind=InputKind.QUANTITY,
            role=InputRole.INITIAL_CONDITION,
            required=True,
            unit_exemplar=bctx.VOLTAGE_UNIT,
            model_id=fl.MODEL_ID,
            model_input=et.POLARIZATION_VOLTAGE,
        ),
        InputDeclaration(
            path=F_CURRENT,
            kind=InputKind.QUANTITY,
            role=InputRole.BOUNDARY_CONDITION,
            required=True,
            unit_exemplar=bctx.CURRENT_UNIT,
            model_id=fl.MODEL_ID,
            model_input=fl.LOAD_CURRENT,
        ),
        InputDeclaration(
            path=F_CTH,
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=lumped.CAPACITY_UNIT,
            model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
            model_input=lumped.HEAT_CAPACITY,
        ),
        InputDeclaration(
            path=F_HA,
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=lumped.CONDUCTANCE_UNIT,
            model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
            model_input=lumped.AMBIENT_CONDUCTANCE,
        ),
        InputDeclaration(
            path=F_TAMB,
            kind=InputKind.QUANTITY,
            role=InputRole.BOUNDARY_CONDITION,
            required=True,
            unit_exemplar=lumped.TEMPERATURE_UNIT,
            model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
            model_input=lumped.AMBIENT_TEMPERATURE,
        ),
        InputDeclaration(
            path=F_T0,
            kind=InputKind.QUANTITY,
            role=InputRole.INITIAL_CONDITION,
            required=True,
            unit_exemplar=lumped.TEMPERATURE_UNIT,
            model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
            model_input=lumped.TEMPERATURE,
        ),
    )
    return CapabilityDeclaration(
        capability_id=CAPABILITY_ID,
        version="1",
        domain="battery.electrothermal",
        summary=(
            "Closed-loop electrothermal discharge of one 1-RC Thevenin cell "
            "with Arrhenius resistances and a declared open-circuit voltage "
            "curve, thermally represented by one first-order lumped body, "
            "driven by a measured load-current schedule."
        ),
        provides=(
            ProvidedCapability(
                fl.ELECTROTHERMAL_CELL_STATE,
                f"domain-pack:{BATTERY_ELECTROTHERMAL_MANIFEST.pack_id}@"
                f"{BATTERY_ELECTROTHERMAL_MANIFEST.pack_version}",
            ),
            ProvidedCapability(
                lumped.BODY_TEMPERATURE,
                f"domain-pack:{THERMAL_LUMPED_MANIFEST.pack_id}@"
                f"{THERMAL_LUMPED_MANIFEST.pack_version}",
            ),
        ),
        inputs=inputs,
        produces=(
            ProducedQuantity(
                TERMINAL_VOLTAGE,
                bctx.VOLTAGE_UNIT,
                model_id=fl.MODEL_ID,
                description="Terminal voltage at the end of the horizon.",
            ),
            ProducedQuantity(
                CELL_TEMPERATURE,
                lumped.TEMPERATURE_UNIT,
                model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
                description="Lumped cell temperature at the end of the horizon.",
            ),
            ProducedQuantity(
                STATE_OF_CHARGE,
                bctx.DIMENSIONLESS,
                model_id=fl.MODEL_ID,
                description=(
                    "Charge state on the declared basis. Coulomb-counted; this "
                    "campaign validates it against no independent reference."
                ),
            ),
            ProducedQuantity(
                HEAT_GENERATION,
                bctx.POWER_UNIT,
                model_id=fl.MODEL_ID,
                description=(
                    "Mean irreversible dissipation over the last interval. "
                    "The reversible entropic term is excluded."
                ),
            ),
        ),
        models=(
            ModelUse.of(fl.ELECTROTHERMAL_1RC_MODEL),
            ModelUse.of(lumped.LUMPED_CAPACITY_MODEL),
        ),
        solvers=(),
        claim_shapes=frozenset({ClaimKind.THRESHOLD, ClaimKind.TOLERANCE_BAND}),
        attainable_levels=(),
        uncertainty=UncertaintyCapability(
            quantified={
                TERMINAL_VOLTAGE: frozenset({UncertaintyChannel.EPISTEMIC_PARAMETER}),
                CELL_TEMPERATURE: frozenset({UncertaintyChannel.EPISTEMIC_PARAMETER}),
            },
            basis=(
                "Independent STANDARD/PARAMETER external-input uncertainties "
                "are propagated by finite-difference sensitivities around an "
                "independent monolithic DOP853 integration of the coupled "
                "system. The measurement and model-form channels are not "
                "produced here and are reported as gaps."
            ),
        ),
        routes=(
            RouteDeclaration(
                route_id="battery_electrothermal.generic_multiphysics",
                kind=RouteKind.PRIMARY_SIMULATION,
                description=(
                    "Staggered cyclic generic multiphysics execution across the "
                    "cell and thermal participants, driven by a measured "
                    "load-current schedule."
                ),
            ),
        ),
        perturbable=tuple(
            PerturbableInput(
                item.path,
                "independent system-level parameter-UQ reference accepts "
                "perturbations of this external quantity",
            )
            for item in inputs
            if item.path != F_CURRENT
        ),
        executor=None,
        case_builder=None,
    )


CELL_PORTS = (
    PortDefinition(
        "ohmic_resistance_reference", PortDirection.INPUT, PortKind.SCALAR,
        Q_RESISTANCE_REFERENCE, bctx.RESISTANCE_UNIT,
    ),
    PortDefinition(
        "ohmic_activation_energy", PortDirection.INPUT, PortKind.SCALAR,
        Q_ACTIVATION_ENERGY, et.ACTIVATION_ENERGY_UNIT,
    ),
    PortDefinition(
        "polarization_resistance_reference", PortDirection.INPUT, PortKind.SCALAR,
        Q_RESISTANCE_REFERENCE, bctx.RESISTANCE_UNIT,
    ),
    PortDefinition(
        "polarization_activation_energy", PortDirection.INPUT, PortKind.SCALAR,
        Q_ACTIVATION_ENERGY, et.ACTIVATION_ENERGY_UNIT,
    ),
    PortDefinition(
        "polarization_capacitance", PortDirection.INPUT, PortKind.SCALAR,
        Q_CAPACITANCE, et.CAPACITANCE_UNIT,
    ),
    PortDefinition(
        "reference_temperature", PortDirection.INPUT, PortKind.SCALAR,
        Q_REFERENCE_TEMPERATURE, bctx.TEMPERATURE_UNIT,
    ),
    PortDefinition(
        "charge_state_basis", PortDirection.INPUT, PortKind.SCALAR,
        Q_CHARGE_BASIS, bctx.CAPACITY_UNIT,
    ),
    PortDefinition(
        "coulombic_efficiency", PortDirection.INPUT, PortKind.SCALAR,
        Q_EFFICIENCY, bctx.DIMENSIONLESS,
    ),
    PortDefinition(
        "initial_state_of_charge", PortDirection.INPUT, PortKind.SCALAR,
        Q_STATE_OF_CHARGE, bctx.DIMENSIONLESS,
    ),
    PortDefinition(
        "initial_polarization_voltage", PortDirection.INPUT, PortKind.SCALAR,
        Q_POLARIZATION_VOLTAGE, bctx.VOLTAGE_UNIT,
    ),
    PortDefinition(
        "load_current", PortDirection.INPUT, PortKind.SCALAR,
        Q_CURRENT, bctx.CURRENT_UNIT,
    ),
    PortDefinition(
        "cell_temperature", PortDirection.INPUT, PortKind.SCALAR,
        Q_TEMPERATURE, bctx.TEMPERATURE_UNIT,
    ),
    PortDefinition(
        "heat_generation", PortDirection.OUTPUT, PortKind.SCALAR,
        Q_POWER, bctx.POWER_UNIT,
    ),
    PortDefinition(
        "terminal_voltage", PortDirection.OUTPUT, PortKind.SCALAR,
        Q_VOLTAGE, bctx.VOLTAGE_UNIT,
    ),
    PortDefinition(
        "state_of_charge", PortDirection.OUTPUT, PortKind.SCALAR,
        Q_STATE_OF_CHARGE, bctx.DIMENSIONLESS,
    ),
    PortDefinition(
        "polarization_voltage", PortDirection.OUTPUT, PortKind.SCALAR,
        Q_POLARIZATION_VOLTAGE, bctx.VOLTAGE_UNIT,
    ),
)

#: The thermal participant's ports are the lumped body's own, unchanged, so the
#: existing thermal adapter serves this blueprint without a second copy of it.
THERMAL_PORTS = (
    PortDefinition(
        "heat_capacity", PortDirection.INPUT, PortKind.SCALAR,
        Q_HEAT_CAPACITY, lumped.CAPACITY_UNIT,
    ),
    PortDefinition(
        "ambient_conductance", PortDirection.INPUT, PortKind.SCALAR,
        Q_AMBIENT_CONDUCTANCE, lumped.CONDUCTANCE_UNIT,
    ),
    PortDefinition(
        "ambient_temperature", PortDirection.INPUT, PortKind.SCALAR,
        Q_AMBIENT_TEMPERATURE, lumped.TEMPERATURE_UNIT,
    ),
    PortDefinition(
        "initial_temperature", PortDirection.INPUT, PortKind.SCALAR,
        Q_INITIAL_TEMPERATURE, lumped.TEMPERATURE_UNIT,
    ),
    PortDefinition(
        "heat_input", PortDirection.INPUT, PortKind.SCALAR,
        Q_POWER, lumped.POWER_UNIT,
    ),
    PortDefinition(
        "temperature", PortDirection.OUTPUT, PortKind.SCALAR,
        Q_TEMPERATURE, lumped.TEMPERATURE_UNIT,
    ),
)

BLUEPRINT = SystemGraphBlueprint(
    blueprint_id=BLUEPRINT_ID,
    version=BLUEPRINT_VERSION,
    capability_id=CAPABILITY_ID,
    participants=(
        ParticipantBlueprint(
            participant_id=CELL_PARTICIPANT,
            model_id=fl.ELECTROTHERMAL_1RC_MODEL.model_id,
            model_version=fl.ELECTROTHERMAL_1RC_MODEL.version,
            adapter_id=CELL_ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            ports=CELL_PORTS,
            transient=True,
        ),
        ParticipantBlueprint(
            participant_id=THERMAL_PARTICIPANT,
            model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
            model_version=lumped.LUMPED_CAPACITY_MODEL.version,
            adapter_id=THERMAL_ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            ports=THERMAL_PORTS,
            transient=True,
        ),
    ),
    edges=(
        CouplingEdge(
            edge_id="thermal_temperature_to_cell",
            source=PortRef(THERMAL_PARTICIPANT, "temperature"),
            target=PortRef(CELL_PARTICIPANT, "cell_temperature"),
            description=(
                "Cell temperature drives both Arrhenius resistances. This is "
                "the edge that makes the coupling a cycle rather than a "
                "one-way march."
            ),
        ),
        CouplingEdge(
            edge_id="cell_heat_to_thermal",
            source=PortRef(CELL_PARTICIPANT, "heat_generation"),
            target=PortRef(THERMAL_PARTICIPANT, "heat_input"),
            conversion=EnergyConversion(
                name="cell_dissipation_to_body_heat",
                input_form="cell_irreversible_dissipation",
                output_form="body_heat_input",
                unit_exemplar=bctx.POWER_UNIT,
                efficiency=1.0,
                description=(
                    "The represented system has no intermediate thermal "
                    "storage and no loss path between the cell's dissipation "
                    "and the lumped body: all of it is deposited. The "
                    "reversible entropic term is not in this stream because "
                    "the cell model does not produce it."
                ),
            ),
            description="Cell irreversible dissipation is deposited as body heat.",
        ),
    ),
    description=(
        "Closed electrothermal cycle T -> R(T) -> I^2 R0 + I v_p -> T, driven "
        "by a measured load-current schedule."
    ),
)

COUPLING_POLICY = CouplingPolicyTemplate(
    template_id=POLICY_ID,
    version=POLICY_VERSION,
    blueprint_id=BLUEPRINT_ID,
    scheme=CouplingScheme.EXPLICIT,
    iteration_semantics=IterationSemantics.SERIAL,
    window_rule=CouplingWindowRule(
        kind=CouplingWindowRuleKind.FACT_RATIO,
        numerator_path=F_CTH,
        denominator_path=F_HA,
        factor=1.0,
        justification=(
            "One thermal time constant C_th / hA. The scenario's measurement "
            "instants are declared as scheduled events and cut every window "
            "well inside that, so this rule is an upper bound the sampling "
            "grid dominates rather than the step size in use. It is an "
            "explicit splitting policy and not an accuracy claim: the "
            "refinement study and the independent monolithic route measure "
            "what the splitting actually cost."
        ),
    ),
    align_events=False,
    max_windows=100000,
    participant_order=(CELL_PARTICIPANT, THERMAL_PARTICIPANT),
    criteria=(),
    max_iterations=1,
    fail_on_nonconvergence=True,
)

PORT_SEMANTICS = tuple(
    PortSemanticBinding(BLUEPRINT_ID, participant_id, port.port_id, port.quantity)
    for participant_id, ports in (
        (CELL_PARTICIPANT, CELL_PORTS),
        (THERMAL_PARTICIPANT, THERMAL_PORTS),
    )
    for port in ports
)

COUPLING_SEMANTICS = (
    CouplingSemantic(
        BLUEPRINT_ID,
        "thermal_temperature_to_cell",
        Q_TEMPERATURE,
        Q_TEMPERATURE,
        "identity.temperature",
        CouplingSignConvention.SOURCE_TO_TARGET_POSITIVE,
        reference="No transformation: the cell receives the body temperature.",
    ),
    CouplingSemantic(
        BLUEPRINT_ID,
        "cell_heat_to_thermal",
        Q_POWER,
        Q_POWER,
        "identity.dissipated_power_to_heat",
        CouplingSignConvention.SOURCE_TO_TARGET_POSITIVE,
        reference=(
            "Positive cell dissipation is deposited as positive thermal heat "
            "input; no storage exists between the participants."
        ),
    ),
)

EXTERNAL_INPUT_BINDINGS = (
    ExternalInputBinding(BLUEPRINT_ID, CELL_PARTICIPANT, "ohmic_resistance_reference", F_R0),
    ExternalInputBinding(BLUEPRINT_ID, CELL_PARTICIPANT, "ohmic_activation_energy", F_EA0),
    ExternalInputBinding(
        BLUEPRINT_ID, CELL_PARTICIPANT, "polarization_resistance_reference", F_R1
    ),
    ExternalInputBinding(
        BLUEPRINT_ID, CELL_PARTICIPANT, "polarization_activation_energy", F_EA1
    ),
    ExternalInputBinding(BLUEPRINT_ID, CELL_PARTICIPANT, "polarization_capacitance", F_C1),
    ExternalInputBinding(BLUEPRINT_ID, CELL_PARTICIPANT, "reference_temperature", F_TREF),
    ExternalInputBinding(BLUEPRINT_ID, CELL_PARTICIPANT, "charge_state_basis", F_QBASIS),
    ExternalInputBinding(BLUEPRINT_ID, CELL_PARTICIPANT, "coulombic_efficiency", F_ETA),
    ExternalInputBinding(BLUEPRINT_ID, CELL_PARTICIPANT, "initial_state_of_charge", F_Z0),
    ExternalInputBinding(
        BLUEPRINT_ID, CELL_PARTICIPANT, "initial_polarization_voltage", F_VP0
    ),
    ExternalInputBinding(BLUEPRINT_ID, CELL_PARTICIPANT, "load_current", F_CURRENT),
    ExternalInputBinding(BLUEPRINT_ID, THERMAL_PARTICIPANT, "heat_capacity", F_CTH),
    ExternalInputBinding(BLUEPRINT_ID, THERMAL_PARTICIPANT, "ambient_conductance", F_HA),
    ExternalInputBinding(BLUEPRINT_ID, THERMAL_PARTICIPANT, "ambient_temperature", F_TAMB),
    ExternalInputBinding(BLUEPRINT_ID, THERMAL_PARTICIPANT, "initial_temperature", F_T0),
)

APPLICABILITY_RULES = (
    SystemApplicabilityRule(
        blueprint_id=BLUEPRINT_ID,
        rule_id="battery_electrothermal.declared_envelope",
        predicates=(
            ApplicabilityPredicate(
                "battery_electrothermal.discharge_and_rest_only",
                ApplicabilityPredicateKind.FACT_GE,
                path=F_CURRENT,
                expected=CHARGE_CURRENT_FLOOR,
                description=(
                    "Positive current is discharge. A value below the declared "
                    "charge-current floor is charge, and no charge-direction "
                    "evidence supports these parameters or this open-circuit "
                    "voltage curve. The floor is a measurement noise band and "
                    "not a permission to charge."
                ),
            ),
            ApplicabilityPredicate(
                "battery_electrothermal.ambient_at_or_above_declared_floor",
                ApplicabilityPredicateKind.FACT_GE,
                path=F_TAMB,
                expected=AMBIENT_LOWER,
                description=(
                    "The model carries no temperature-dependent capacity, and "
                    "below this band the cell delivers visibly less charge than "
                    "the declared basis represents."
                ),
            ),
            ApplicabilityPredicate(
                "battery_electrothermal.ambient_at_or_below_declared_ceiling",
                ApplicabilityPredicateKind.FACT_LE,
                path=F_TAMB,
                expected=AMBIENT_UPPER,
                description=(
                    "Above this band the evidence behind the open-circuit "
                    "voltage authority and the thermal parameters does not "
                    "reach."
                ),
            ),
            ApplicabilityPredicate(
                "battery_electrothermal.positive_thermal_capacitance",
                ApplicabilityPredicateKind.FACT_GT,
                path=F_CTH,
                expected=Quantity(0.0, lumped.CAPACITY_UNIT),
            ),
            ApplicabilityPredicate(
                "battery_electrothermal.positive_thermal_conductance",
                ApplicabilityPredicateKind.FACT_GT,
                path=F_HA,
                expected=Quantity(0.0, lumped.CONDUCTANCE_UNIT),
            ),
            ApplicabilityPredicate(
                "battery_electrothermal.positive_ohmic_resistance",
                ApplicabilityPredicateKind.FACT_GT,
                path=F_R0,
                expected=Quantity(0.0, bctx.RESISTANCE_UNIT),
            ),
            ApplicabilityPredicate(
                "battery_electrothermal.positive_polarization_resistance",
                ApplicabilityPredicateKind.FACT_GT,
                path=F_R1,
                expected=Quantity(0.0, bctx.RESISTANCE_UNIT),
            ),
        ),
        required_evidence=(),
        description=(
            "The pack owns exactly one cell and one lumped body. The current "
            "and ambient predicates are the declared applicability boundary of "
            "the flagship, and the scenario preflight evaluates them at every "
            "sample of the load schedule, not only at its first value."
        ),
    ),
)

UNCERTAINTY_RULES = (
    UncertaintyCompositionRule(
        blueprint_id=BLUEPRINT_ID,
        rule_id="battery_electrothermal.parameter_uq",
        strategy=UncertaintyCompositionStrategy.INDEPENDENT,
        channels=(UncertaintyChannel.EPISTEMIC_PARAMETER,),
        description=(
            "Independent STANDARD/PARAMETER external uncertainties are "
            "propagated through a separately integrated monolithic "
            "electrothermal ODE."
        ),
    ),
)


def _qdict(payload) -> Quantity:
    return Quantity.from_dict(payload)


def _step_diagnostics(record, participant_id: str):
    step = next(
        item
        for item in record.windows[-1].iterations[-1].participant_steps
        if item.participant_id == participant_id
    )
    return {} if step.diagnostics is None else dict(step.diagnostics)


def _check(
    check_id: str,
    observed: Quantity,
    expected: Quantity,
    *,
    relative_tolerance: float,
    evidence: tuple[str, ...],
    detail: str,
) -> SystemValidationCheck:
    converted = observed.to(expected.units)
    error = Quantity(
        abs((converted - expected).magnitude_in(expected.units)), expected.units
    )
    scale = max(abs(expected.magnitude), abs(converted.magnitude), 1e-15)
    tolerance = Quantity(relative_tolerance * scale, expected.units)
    return SystemValidationCheck(
        check_id=check_id,
        passed=error.magnitude_in(expected.units) <= tolerance.magnitude,
        observed=converted,
        expected=expected,
        tolerance=tolerance,
        absolute_error=error,
        relative_error=error.magnitude_in(expected.units) / scale,
        evidence=evidence,
        detail=detail,
    )


def validate_battery_electrothermal_run(record) -> SystemValidationResult:
    """Cross-domain consistency of the executed coupling, not of the cell.

    Every check below compares two things the run itself produced. None of them
    is evidence that the cell behaves this way; that question belongs to the
    validation campaign against measured trajectories, and conflating the two is
    exactly the verification-as-validation confusion the core refuses.
    """
    cell_diagnostics = _step_diagnostics(record, CELL_PARTICIPANT)
    thermal_diagnostics = _step_diagnostics(record, THERMAL_PARTICIPANT)

    step = cell_diagnostics["step"]
    ocv = _qdict(step[et.OPEN_CIRCUIT_VOLTAGE])
    ohmic = _qdict(step[et.OHMIC_DROP])
    polarization = _qdict(step[et.POLARIZATION_VOLTAGE])
    terminal = _qdict(step[et.TERMINAL_VOLTAGE])
    heat = _qdict(step[et.HEAT_GENERATION])
    thermal_heat = _qdict(thermal_diagnostics["heat_input"])

    final_temperature = _qdict(record.final_outputs[f"{THERMAL_PARTICIPANT}.temperature"])
    final_voltage = _qdict(record.final_outputs[f"{CELL_PARTICIPANT}.terminal_voltage"])
    operating_temperature = _qdict(cell_diagnostics["operating_temperature"])

    # Energy over the whole run: what was dissipated equals what the body
    # stored plus what it rejected to ambient.
    deposited = float(cell_diagnostics["cumulative_dissipated_joule"])
    stored = float(thermal_diagnostics["cumulative_stored_joule"])
    rejected = float(thermal_diagnostics["cumulative_rejected_joule"])

    checks = (
        _check(
            "cell_terminal_relation",
            terminal,
            ocv - ohmic - polarization,
            relative_tolerance=1e-11,
            evidence=("cell participant step diagnostics", "V = OCV(z) - I R0 - v_p"),
            detail="Cell participant output satisfies its own circuit relation.",
        ),
        _check(
            "power_transfer_conservation",
            thermal_heat,
            heat,
            relative_tolerance=1e-12,
            evidence=(
                "cell heat_generation output",
                "thermal heat_input consumed in the same serial window",
            ),
            detail="Cell dissipation is conserved into the thermal input.",
        ),
        _check(
            "coupled_energy_balance",
            Quantity(deposited, "joule"),
            Quantity(stored + rejected, "joule"),
            relative_tolerance=COUPLING_RELATIVE_TOLERANCE,
            evidence=(
                "cumulative cell dissipation over every window",
                "thermal stored energy plus energy rejected to ambient",
            ),
            detail=(
                "Energy deposited over the run equals the body's change in "
                "stored energy plus what it rejected, inside the declared "
                "staggered-splitting band."
            ),
        ),
        _check(
            "staggered_temperature_lag",
            operating_temperature,
            final_temperature,
            relative_tolerance=COUPLING_RELATIVE_TOLERANCE,
            evidence=(
                "temperature the cell was evaluated at in the last window",
                "terminal thermal state",
                "declared explicit staggered coupling tolerance",
            ),
            detail=(
                "The lag caused by evaluating the cell at the previous "
                "window's temperature stays inside the declared band."
            ),
        ),
        _check(
            "terminal_voltage_self_consistency",
            final_voltage,
            terminal,
            relative_tolerance=1e-12,
            evidence=("terminal cell output", "last window's step record"),
            detail="The run's terminal output is the last step's own value.",
        ),
    )
    return SystemValidationResult(
        valid=all(item.passed for item in checks),
        checks=checks,
        findings=tuple(item.detail for item in checks if not item.passed),
        evidence=(
            "typed participant diagnostics from the final coupling window",
            "cumulative energy accounting over every window",
        ),
    )


def produce_battery_electrothermal_uncertainty(record):
    propagated = propagate_battery_parameter_uncertainty(record)
    return tuple(
        SystemUncertaintyResult(
            quantity=name,
            channel=UncertaintyChannel.EPISTEMIC_PARAMETER,
            uncertainty=uncertainty,
            method_id="battery_electrothermal.independent_ode_sensitivity",
            evidence=(
                "independent monolithic DOP853 reference integration",
                "finite-difference parameter sensitivities",
                "independent STANDARD/PARAMETER inputs only",
            ),
        )
        for name, uncertainty in sorted(propagated.items())
    )


def _digest(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


_REFERENCE_DIGEST = implementation_fingerprint(battery_electrothermal_reference)[0]

REFERENCE_VERIFICATION_ROUTE = VerificationRoute(
    "battery_electrothermal.independent_dop853",
    VerificationRouteKind.DIFFERENT_ALGORITHM,
    _REFERENCE_DIGEST,
)

REFERENCE_DEPENDENCIES = RouteDependencyManifest(
    REFERENCE_VERIFICATION_ROUTE.route_id,
    (
        DependencyComponent(
            "reference_model.battery_electrothermal.monolithic_ode",
            _REFERENCE_DIGEST,
            DependencyRole.MODEL,
        ),
        DependencyComponent(
            "reference_solver.battery_electrothermal.dop853",
            _REFERENCE_DIGEST,
            DependencyRole.SOLVER,
        ),
    ),
    "forge.reference",
)

VERIFICATION_POLICY = VerificationPolicy(
    minimum_level=VerificationLevel.V1,
    minimum_independence=IndependenceLevel.STRONG,
    minimum_routes=1,
    require_external=False,
)

_VERIFIED = {
    TERMINAL_VOLTAGE: (f"{CELL_PARTICIPANT}.terminal_voltage", bctx.VOLTAGE_UNIT),
    CELL_TEMPERATURE: (f"{THERMAL_PARTICIPANT}.temperature", lumped.TEMPERATURE_UNIT),
    STATE_OF_CHARGE: (f"{CELL_PARTICIPANT}.state_of_charge", bctx.DIMENSIONLESS),
}

_REFERENCE_KEY = {
    TERMINAL_VOLTAGE: fl.TERMINAL_VOLTAGE_METRIC,
    CELL_TEMPERATURE: bctx.CELL_TEMPERATURE,
    STATE_OF_CHARGE: fl.STATE_OF_CHARGE_METRIC,
}


def _verification_run(record, plan, quantity: str) -> VerificationRunRecord:
    output_key, unit = _VERIFIED[quantity]
    primary_value = _qdict(record.final_outputs[output_key]).to(unit)
    reference_value = battery_electrothermal_reference(record)[
        _REFERENCE_KEY[quantity]
    ].to(unit)
    scale = max(abs(primary_value.magnitude), abs(reference_value.magnitude), 1e-15)
    return VerificationRunRecord(
        plan=plan,
        primary=VerificationObservation(
            plan.primary_route.route_id,
            primary_value,
            _digest(record.to_dict()),
            True,
        ),
        observations=(
            VerificationObservation(
                REFERENCE_VERIFICATION_ROUTE.route_id,
                reference_value,
                battery_electrothermal_reference_evidence_digest(record),
                True,
            ),
        ),
        tolerance=Quantity(VERIFICATION_RELATIVE_TOLERANCE * scale, unit),
    )


def verify_terminal_voltage(record, plan):
    return _verification_run(record, plan, TERMINAL_VOLTAGE)


def verify_cell_temperature(record, plan):
    return _verification_run(record, plan, CELL_TEMPERATURE)


def verify_state_of_charge(record, plan):
    return _verification_run(record, plan, STATE_OF_CHARGE)


VALIDATION_REF = ArtifactRef("system.battery_electrothermal.validation", "1")
VALIDATION_PROTOCOLS = (
    ProvidedCompositionValidation(
        BLUEPRINT_ID, VALIDATION_REF, validate_battery_electrothermal_run
    ),
)

UNCERTAINTY_REF = ArtifactRef("system.battery_electrothermal.parameter_uq", "1")
UNCERTAINTY_PRODUCERS = (
    ProvidedCompositionUncertainty(
        BLUEPRINT_ID,
        UNCERTAINTY_REF,
        "battery_electrothermal.parameter_uq",
        (TERMINAL_VOLTAGE, CELL_TEMPERATURE),
        (UncertaintyChannel.EPISTEMIC_PARAMETER,),
        produce_battery_electrothermal_uncertainty,
    ),
)

_VERIFICATION_SPECS = (
    (
        ArtifactRef("system.battery_electrothermal.verify_terminal_voltage", "1"),
        TERMINAL_VOLTAGE,
        verify_terminal_voltage,
    ),
    (
        ArtifactRef("system.battery_electrothermal.verify_cell_temperature", "1"),
        CELL_TEMPERATURE,
        verify_cell_temperature,
    ),
    (
        ArtifactRef("system.battery_electrothermal.verify_state_of_charge", "1"),
        STATE_OF_CHARGE,
        verify_state_of_charge,
    ),
)

VERIFICATION_PROTOCOLS = tuple(
    ProvidedCompositionVerification(
        blueprint_id=BLUEPRINT_ID,
        ref=ref,
        quantity=quantity,
        candidates=(
            VerificationCandidate(
                REFERENCE_VERIFICATION_ROUTE, REFERENCE_DEPENDENCIES
            ),
        ),
        policy=VERIFICATION_POLICY,
        implementation=implementation,
    )
    for ref, quantity, implementation in _VERIFICATION_SPECS
)

SYSTEM_CONTRACT_DIGEST = system_contract_digest(
    port_semantics=PORT_SEMANTICS,
    coupling_semantics=COUPLING_SEMANTICS,
    external_input_bindings=EXTERNAL_INPUT_BINDINGS,
    applicability_rules=APPLICABILITY_RULES,
    uncertainty_rules=UNCERTAINTY_RULES,
)

MANIFEST = CompositionPackManifest(
    pack_id=PACK_ID,
    pack_version=PACK_VERSION,
    compatible_core_apis=(COMPOSITION_PACK_API,),
    requires_domain_packs=(
        DomainPackDependency(
            BATTERY_ELECTROTHERMAL_MANIFEST.pack_id,
            BATTERY_ELECTROTHERMAL_MANIFEST.pack_version,
            BATTERY_ELECTROTHERMAL_MANIFEST.digest,
        ),
        DomainPackDependency(
            THERMAL_LUMPED_MANIFEST.pack_id,
            THERMAL_LUMPED_MANIFEST.pack_version,
            THERMAL_LUMPED_MANIFEST.digest,
        ),
    ),
    capabilities=(CAPABILITY_ID,),
    blueprints=(BlueprintRef.from_blueprint(BLUEPRINT),),
    coupling_policies=(PolicyTemplateRef.from_template(COUPLING_POLICY),),
    system_contract_digest=SYSTEM_CONTRACT_DIGEST,
    validation_protocols=(VALIDATION_REF,),
    uncertainty_protocols=(UNCERTAINTY_REF,),
    verification_protocols=tuple(ref for ref, _q, _i in _VERIFICATION_SPECS),
)


class BatteryElectrothermalCompositionPack:
    manifest = MANIFEST

    def claim_capabilities(self):
        return (battery_electrothermal_capability(),)

    def blueprints(self):
        return (BLUEPRINT,)

    def coupling_policy_templates(self):
        return (COUPLING_POLICY,)

    def port_semantics(self):
        return PORT_SEMANTICS

    def coupling_semantics(self):
        return COUPLING_SEMANTICS

    def external_input_bindings(self):
        return EXTERNAL_INPUT_BINDINGS

    def applicability_rules(self):
        return APPLICABILITY_RULES

    def uncertainty_rules(self):
        return UNCERTAINTY_RULES

    def validation_protocols(self):
        return VALIDATION_PROTOCOLS

    def uncertainty_producers(self):
        return UNCERTAINTY_PRODUCERS

    def verification_protocols(self):
        return VERIFICATION_PROTOCOLS


BUILTIN_BATTERY_ELECTROTHERMAL_COMPOSITION = BatteryElectrothermalCompositionPack()

__all__ = [
    "ADAPTER_VERSION",
    "AMBIENT_LOWER",
    "AMBIENT_UPPER",
    "CHARGE_CURRENT_FLOOR",
    "BLUEPRINT",
    "BLUEPRINT_ID",
    "BUILTIN_BATTERY_ELECTROTHERMAL_COMPOSITION",
    "CAPABILITY_ID",
    "CELL_ADAPTER_ID",
    "CELL_PARTICIPANT",
    "CELL_TEMPERATURE",
    "COUPLING_POLICY",
    "F_C1",
    "F_CTH",
    "F_CURRENT",
    "F_EA0",
    "F_EA1",
    "F_ETA",
    "F_HA",
    "F_QBASIS",
    "F_R0",
    "F_R1",
    "F_T0",
    "F_TAMB",
    "F_TREF",
    "F_VP0",
    "F_Z0",
    "HEAT_GENERATION",
    "MANIFEST",
    "PACK_ID",
    "PACK_VERSION",
    "STATE_OF_CHARGE",
    "TERMINAL_VOLTAGE",
    "THERMAL_ADAPTER_ID",
    "THERMAL_PARTICIPANT",
    "BatteryElectrothermalCompositionPack",
    "battery_electrothermal_capability",
    "validate_battery_electrothermal_run",
]
