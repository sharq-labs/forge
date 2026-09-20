"""Built-in closed-loop electrothermal feedback Composition Pack.

The topology is deliberately small but scientifically complete:
temperature -> linear-TCR resistance -> DC Joule heating -> thermal state.
It exercises cyclic multiphysics, a multi-model electrical subsystem, typed
applicability, parameter UQ, quantitative system validation and an independent
ODE verification route.
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
from ..domainpacks.builtin_electrical_dc import (
    MANIFEST as ELECTRICAL_DC_MANIFEST,
)
from ..domainpacks.builtin_electrical_material import (
    MANIFEST as ELECTRICAL_MATERIAL_MANIFEST,
)
from ..domainpacks.builtin_thermal_lumped import (
    MANIFEST as THERMAL_LUMPED_MANIFEST,
)
from ..domainpacks.frozen import implementation_fingerprint
from ..domainpacks.manifest import ArtifactRef
from ..domains.electrical import material
from ..domains.electrical.dc import models as dc_models
from ..domains.electrical.dc.realizations import DC_NETWORK_STATE
from ..domains.thermal_models import lumped
from ..scientific.composition import EnergyConversion
from ..scientific.multiphysics import (
    CouplingEdge,
    CouplingScheme,
    IterationSemantics,
    ParticipantModelRef,
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
from .applicability import (
    ApplicabilityPredicate,
    ApplicabilityPredicateKind,
)
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
from .references.electrothermal_feedback import (
    feedback_reference,
    feedback_reference_evidence_digest,
    propagate_feedback_parameter_uncertainty,
)
from .semantics import (
    CouplingSemantic,
    CouplingSignConvention,
    PortSemanticBinding,
)
from .uncertainty import (
    ProvidedCompositionUncertainty,
    SystemUncertaintyResult,
)
from .verification import ProvidedCompositionVerification

PACK_ID = "system.electrothermal_feedback"
PACK_VERSION = "1"
CAPABILITY_ID = "system.electrothermal_feedback"
BLUEPRINT_ID = "system.electrothermal_feedback.graph"
BLUEPRINT_VERSION = "1"
POLICY_ID = "system.electrothermal_feedback.staggered"
POLICY_VERSION = "1"

THERMAL_PARTICIPANT = "thermal"
MATERIAL_PARTICIPANT = "material"
ELECTRICAL_PARTICIPANT = "electrical"

THERMAL_ADAPTER_ID = "engcore.adapter.thermal_lumped"
MATERIAL_ADAPTER_ID = "engcore.adapter.linear_tcr"
ELECTRICAL_ADAPTER_ID = "engcore.adapter.electrical_dc_network"
ADAPTER_VERSION = "1"

Q_TEMPERATURE = "thermodynamics.temperature"
Q_RESISTANCE = "electrical.resistance"
Q_POWER = "electrical.dissipated_power"
Q_HEAT_CAPACITY = "thermal.heat_capacity"
Q_AMBIENT_CONDUCTANCE = "thermal.ambient_conductance"
Q_AMBIENT_TEMPERATURE = "thermal.ambient_temperature"
Q_INITIAL_TEMPERATURE = "thermal.initial_temperature"
Q_REFERENCE_RESISTANCE = "electrical.reference_resistance"
Q_TCR = "electrical.temperature_coefficient"
Q_REFERENCE_TEMPERATURE = "electrical.reference_temperature"
Q_SOURCE_VOLTAGE = "electrical.source_voltage"

FINAL_TEMPERATURE = "final_temperature"
RESISTANCE = "resistance"
HEAT_GENERATION = "heat_generation"

COUPLING_RELATIVE_TOLERANCE = 5e-3
VERIFICATION_RELATIVE_TOLERANCE = 5e-3


def electrothermal_feedback_capability() -> CapabilityDeclaration:
    inputs = (
        InputDeclaration(
            path="thermal.heat_capacity",
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=lumped.CAPACITY_UNIT,
            model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
            model_input=lumped.HEAT_CAPACITY,
        ),
        InputDeclaration(
            path="thermal.ambient_conductance",
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=lumped.CONDUCTANCE_UNIT,
            model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
            model_input=lumped.AMBIENT_CONDUCTANCE,
        ),
        InputDeclaration(
            path="thermal.ambient_temperature",
            kind=InputKind.QUANTITY,
            role=InputRole.BOUNDARY_CONDITION,
            required=True,
            unit_exemplar=lumped.TEMPERATURE_UNIT,
            model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
            model_input=lumped.AMBIENT_TEMPERATURE,
        ),
        InputDeclaration(
            path="thermal.initial_temperature",
            kind=InputKind.QUANTITY,
            role=InputRole.INITIAL_CONDITION,
            required=True,
            unit_exemplar=lumped.TEMPERATURE_UNIT,
            model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
            model_input=lumped.TEMPERATURE,
        ),
        InputDeclaration(
            path="material.reference_resistance",
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=material.RESISTANCE_UNIT,
            model_id=material.LINEAR_TCR_MODEL.model_id,
            model_input=material.REFERENCE_RESISTANCE,
        ),
        InputDeclaration(
            path="material.temperature_coefficient",
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=material.TCR_UNIT,
            model_id=material.LINEAR_TCR_MODEL.model_id,
            model_input=material.TEMPERATURE_COEFFICIENT,
        ),
        InputDeclaration(
            path="material.reference_temperature",
            kind=InputKind.QUANTITY,
            role=InputRole.PARAMETER,
            required=True,
            unit_exemplar=material.TEMPERATURE_UNIT,
            model_id=material.LINEAR_TCR_MODEL.model_id,
            model_input=material.REFERENCE_TEMPERATURE,
        ),
        InputDeclaration(
            path="electrical.source_voltage",
            kind=InputKind.QUANTITY,
            role=InputRole.BOUNDARY_CONDITION,
            required=True,
            unit_exemplar=dc_models.VOLTAGE_UNIT,
            model_id=dc_models.IDEAL_VOLTAGE_SOURCE_MODEL.model_id,
            model_input="source_voltage",
        ),
    )
    return CapabilityDeclaration(
        capability_id=CAPABILITY_ID,
        version="1",
        domain="electrothermal.feedback",
        summary=(
            "Closed-loop self-heating of one linear-TCR resistor driven by "
            "one ideal DC voltage source and thermally represented by one "
            "first-order lumped body."
        ),
        provides=(
            ProvidedCapability(
                lumped.BODY_TEMPERATURE,
                f"domain-pack:{THERMAL_LUMPED_MANIFEST.pack_id}@"
                f"{THERMAL_LUMPED_MANIFEST.pack_version}",
            ),
            ProvidedCapability(
                material.TEMPERATURE_DEPENDENT_RESISTANCE,
                f"domain-pack:{ELECTRICAL_MATERIAL_MANIFEST.pack_id}@"
                f"{ELECTRICAL_MATERIAL_MANIFEST.pack_version}",
            ),
            ProvidedCapability(
                DC_NETWORK_STATE,
                f"domain-pack:{ELECTRICAL_DC_MANIFEST.pack_id}@"
                f"{ELECTRICAL_DC_MANIFEST.pack_version}",
            ),
        ),
        inputs=inputs,
        produces=(
            ProducedQuantity(
                FINAL_TEMPERATURE,
                lumped.TEMPERATURE_UNIT,
                model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
                description="Terminal lumped-body temperature.",
            ),
            ProducedQuantity(
                RESISTANCE,
                material.RESISTANCE_UNIT,
                model_id=material.LINEAR_TCR_MODEL.model_id,
                description="Terminal linear-TCR resistance.",
            ),
            ProducedQuantity(
                HEAT_GENERATION,
                dc_models.POWER_UNIT,
                model_id=dc_models.RESISTOR_OHM_MODEL.model_id,
                description="Terminal resistor Joule dissipation V^2/R.",
            ),
        ),
        models=(
            ModelUse.of(lumped.LUMPED_CAPACITY_MODEL),
            ModelUse.of(material.LINEAR_TCR_MODEL),
            ModelUse.of(dc_models.KCL_MODEL),
            ModelUse.of(dc_models.RESISTOR_OHM_MODEL),
            ModelUse.of(dc_models.IDEAL_VOLTAGE_SOURCE_MODEL),
        ),
        solvers=(),
        claim_shapes=frozenset(
            {ClaimKind.THRESHOLD, ClaimKind.TOLERANCE_BAND}
        ),
        attainable_levels=(),
        uncertainty=UncertaintyCapability(
            quantified={
                FINAL_TEMPERATURE: frozenset(
                    {UncertaintyChannel.EPISTEMIC_PARAMETER}
                ),
                RESISTANCE: frozenset(
                    {UncertaintyChannel.EPISTEMIC_PARAMETER}
                ),
                HEAT_GENERATION: frozenset(
                    {UncertaintyChannel.EPISTEMIC_PARAMETER}
                ),
            },
            basis=(
                "Independent STANDARD/PARAMETER external-input uncertainties "
                "are propagated by finite-difference sensitivities around an "
                "independent high-accuracy electrothermal ODE reference."
            ),
        ),
        routes=(
            RouteDeclaration(
                route_id="electrothermal_feedback.generic_multiphysics",
                kind=RouteKind.PRIMARY_SIMULATION,
                description=(
                    "Staggered cyclic generic multiphysics execution across "
                    "material, DC-network and thermal participants."
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
        ),
        executor=None,
        case_builder=None,
    )


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
        Q_POWER, dc_models.POWER_UNIT,
    ),
    PortDefinition(
        "temperature", PortDirection.OUTPUT, PortKind.SCALAR,
        Q_TEMPERATURE, lumped.TEMPERATURE_UNIT,
    ),
)

MATERIAL_PORTS = (
    PortDefinition(
        "reference_resistance", PortDirection.INPUT, PortKind.SCALAR,
        Q_REFERENCE_RESISTANCE, material.RESISTANCE_UNIT,
    ),
    PortDefinition(
        "temperature_coefficient", PortDirection.INPUT, PortKind.SCALAR,
        Q_TCR, material.TCR_UNIT,
    ),
    PortDefinition(
        "reference_temperature", PortDirection.INPUT, PortKind.SCALAR,
        Q_REFERENCE_TEMPERATURE, material.TEMPERATURE_UNIT,
    ),
    PortDefinition(
        "temperature", PortDirection.INPUT, PortKind.SCALAR,
        Q_TEMPERATURE, material.TEMPERATURE_UNIT,
    ),
    PortDefinition(
        "resistance", PortDirection.OUTPUT, PortKind.SCALAR,
        Q_RESISTANCE, material.RESISTANCE_UNIT,
    ),
)

ELECTRICAL_PORTS = (
    PortDefinition(
        "source_voltage", PortDirection.INPUT, PortKind.SCALAR,
        Q_SOURCE_VOLTAGE, dc_models.VOLTAGE_UNIT,
    ),
    PortDefinition(
        "resistance", PortDirection.INPUT, PortKind.SCALAR,
        Q_RESISTANCE, dc_models.RESISTANCE_UNIT,
    ),
    PortDefinition(
        "heat_generation", PortDirection.OUTPUT, PortKind.SCALAR,
        Q_POWER, dc_models.POWER_UNIT,
    ),
)

ELECTRICAL_MODELS = (
    ParticipantModelRef(
        dc_models.KCL_MODEL.model_id,
        dc_models.KCL_MODEL.version,
    ),
    ParticipantModelRef(
        dc_models.RESISTOR_OHM_MODEL.model_id,
        dc_models.RESISTOR_OHM_MODEL.version,
    ),
    ParticipantModelRef(
        dc_models.IDEAL_VOLTAGE_SOURCE_MODEL.model_id,
        dc_models.IDEAL_VOLTAGE_SOURCE_MODEL.version,
    ),
)

BLUEPRINT = SystemGraphBlueprint(
    blueprint_id=BLUEPRINT_ID,
    version=BLUEPRINT_VERSION,
    capability_id=CAPABILITY_ID,
    participants=(
        ParticipantBlueprint(
            participant_id=MATERIAL_PARTICIPANT,
            model_id=material.LINEAR_TCR_MODEL.model_id,
            model_version=material.LINEAR_TCR_MODEL.version,
            adapter_id=MATERIAL_ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            ports=MATERIAL_PORTS,
        ),
        ParticipantBlueprint(
            participant_id=ELECTRICAL_PARTICIPANT,
            model_id=dc_models.KCL_MODEL.model_id,
            model_version=dc_models.KCL_MODEL.version,
            models=ELECTRICAL_MODELS,
            adapter_id=ELECTRICAL_ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            ports=ELECTRICAL_PORTS,
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
            edge_id="thermal_temperature_to_material",
            source=PortRef(THERMAL_PARTICIPANT, "temperature"),
            target=PortRef(MATERIAL_PARTICIPANT, "temperature"),
            description="Body temperature drives the TCR relation.",
        ),
        CouplingEdge(
            edge_id="material_resistance_to_electrical",
            source=PortRef(MATERIAL_PARTICIPANT, "resistance"),
            target=PortRef(ELECTRICAL_PARTICIPANT, "resistance"),
            description="Temperature-dependent resistance enters the DC network.",
        ),
        CouplingEdge(
            edge_id="electrical_power_to_thermal",
            source=PortRef(ELECTRICAL_PARTICIPANT, "heat_generation"),
            target=PortRef(THERMAL_PARTICIPANT, "heat_input"),
            conversion=EnergyConversion(
                name="resistor_dissipation_to_body_heat",
                input_form="resistor_joule_dissipation",
                output_form="body_heat_input",
                unit_exemplar=dc_models.POWER_UNIT,
                efficiency=1.0,
                description=(
                    "The represented system has no intermediate thermal "
                    "storage or loss path: all resistor Joule dissipation is "
                    "deposited in the single lumped body."
                ),
            ),
            description="Resistor Joule dissipation is deposited as body heat.",
        ),
    ),
    description=(
        "Closed electrothermal feedback cycle T -> R(T) -> V^2/R -> T."
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
        numerator_path="thermal.heat_capacity",
        denominator_path="thermal.ambient_conductance",
        factor=0.01,
        justification=(
            "Use one percent of the first-order thermal time constant C/G. "
            "This is an explicit splitting policy, not an accuracy claim; "
            "system validation and the independent ODE route measure the "
            "actual coupled error of every executed run."
        ),
    ),
    align_events=False,
    max_windows=100000,
    participant_order=(
        MATERIAL_PARTICIPANT,
        ELECTRICAL_PARTICIPANT,
        THERMAL_PARTICIPANT,
    ),
    criteria=(),
    max_iterations=1,
    fail_on_nonconvergence=True,
)

PORT_SEMANTICS = tuple(
    PortSemanticBinding(
        BLUEPRINT_ID,
        participant_id,
        port.port_id,
        port.quantity,
    )
    for participant_id, ports in (
        (THERMAL_PARTICIPANT, THERMAL_PORTS),
        (MATERIAL_PARTICIPANT, MATERIAL_PORTS),
        (ELECTRICAL_PARTICIPANT, ELECTRICAL_PORTS),
    )
    for port in ports
)

COUPLING_SEMANTICS = (
    CouplingSemantic(
        BLUEPRINT_ID,
        "thermal_temperature_to_material",
        Q_TEMPERATURE,
        Q_TEMPERATURE,
        "identity.temperature",
        CouplingSignConvention.SOURCE_TO_TARGET_POSITIVE,
        reference="No transformation: material receives body temperature.",
    ),
    CouplingSemantic(
        BLUEPRINT_ID,
        "material_resistance_to_electrical",
        Q_RESISTANCE,
        Q_RESISTANCE,
        "identity.resistance",
        CouplingSignConvention.SOURCE_TO_TARGET_POSITIVE,
        reference="No transformation: DC resistor receives material resistance.",
    ),
    CouplingSemantic(
        BLUEPRINT_ID,
        "electrical_power_to_thermal",
        Q_POWER,
        Q_POWER,
        "identity.dissipated_power_to_heat",
        CouplingSignConvention.SOURCE_TO_TARGET_POSITIVE,
        reference=(
            "Positive resistor dissipation is deposited as positive thermal "
            "heat input; no storage exists between the participants."
        ),
    ),
)

EXTERNAL_INPUT_BINDINGS = (
    ExternalInputBinding(
        BLUEPRINT_ID, THERMAL_PARTICIPANT,
        "heat_capacity", "thermal.heat_capacity",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID, THERMAL_PARTICIPANT,
        "ambient_conductance", "thermal.ambient_conductance",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID, THERMAL_PARTICIPANT,
        "ambient_temperature", "thermal.ambient_temperature",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID, THERMAL_PARTICIPANT,
        "initial_temperature", "thermal.initial_temperature",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID, MATERIAL_PARTICIPANT,
        "reference_resistance", "material.reference_resistance",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID, MATERIAL_PARTICIPANT,
        "temperature_coefficient", "material.temperature_coefficient",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID, MATERIAL_PARTICIPANT,
        "reference_temperature", "material.reference_temperature",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID, ELECTRICAL_PARTICIPANT,
        "source_voltage", "electrical.source_voltage",
    ),
)

APPLICABILITY_RULES = (
    SystemApplicabilityRule(
        blueprint_id=BLUEPRINT_ID,
        rule_id="electrothermal_feedback.single_resistor_voltage_drive",
        predicates=(
            ApplicabilityPredicate(
                "electrothermal_feedback.static_external_inputs",
                ApplicabilityPredicateKind.STATIC_EXTERNAL_INPUTS,
                description=(
                    "External material, thermal and source parameters remain "
                    "constant during the requested run horizon."
                ),
            ),
            ApplicabilityPredicate(
                "electrothermal_feedback.positive_heat_capacity",
                ApplicabilityPredicateKind.FACT_GT,
                path="thermal.heat_capacity",
                expected=Quantity(0.0, lumped.CAPACITY_UNIT),
            ),
            ApplicabilityPredicate(
                "electrothermal_feedback.positive_ambient_conductance",
                ApplicabilityPredicateKind.FACT_GT,
                path="thermal.ambient_conductance",
                expected=Quantity(0.0, lumped.CONDUCTANCE_UNIT),
            ),
            ApplicabilityPredicate(
                "electrothermal_feedback.positive_reference_resistance",
                ApplicabilityPredicateKind.FACT_GT,
                path="material.reference_resistance",
                expected=Quantity(0.0, material.RESISTANCE_UNIT),
            ),
        ),
        required_evidence=(),
        description=(
            "The pack owns exactly one ideal voltage source, one TCR resistor "
            "and one lumped thermal body; typed predicates gate the additional "
            "system assumptions needed by its coupling policy."
        ),
    ),
)

UNCERTAINTY_RULES = (
    UncertaintyCompositionRule(
        blueprint_id=BLUEPRINT_ID,
        rule_id="electrothermal_feedback.parameter_uq",
        strategy=UncertaintyCompositionStrategy.INDEPENDENT,
        channels=(UncertaintyChannel.EPISTEMIC_PARAMETER,),
        description=(
            "Independent STANDARD/PARAMETER external uncertainties are "
            "propagated through a separately integrated electrothermal ODE."
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


def _relative_check(
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
        abs((converted - expected).magnitude_in(expected.units)),
        expected.units,
    )
    scale = max(
        abs(expected.magnitude),
        abs(converted.magnitude),
        1e-15,
    )
    tolerance = Quantity(relative_tolerance * scale, expected.units)
    relative_error = error.magnitude_in(expected.units) / scale
    return SystemValidationCheck(
        check_id=check_id,
        passed=error.magnitude_in(expected.units) <= tolerance.magnitude,
        observed=converted,
        expected=expected,
        tolerance=tolerance,
        absolute_error=error,
        relative_error=relative_error,
        evidence=evidence,
        detail=detail,
    )


def validate_electrothermal_feedback_run(record) -> SystemValidationResult:
    final_temperature = _qdict(
        record.final_outputs[f"{THERMAL_PARTICIPANT}.temperature"]
    )
    final_resistance = _qdict(
        record.final_outputs[f"{MATERIAL_PARTICIPANT}.resistance"]
    )
    final_power = _qdict(
        record.final_outputs[f"{ELECTRICAL_PARTICIPANT}.heat_generation"]
    )
    material_diag = _step_diagnostics(record, MATERIAL_PARTICIPANT)
    electrical_diag = _step_diagnostics(record, ELECTRICAL_PARTICIPANT)
    thermal_diag = _step_diagnostics(record, THERMAL_PARTICIPANT)

    operating_temperature = _qdict(
        material_diag["operating_temperature"]
    )
    rref = _qdict(material_diag["reference_resistance"])
    alpha = _qdict(material_diag["temperature_coefficient"])
    tref = _qdict(material_diag["reference_temperature"])
    resistance_used = _qdict(electrical_diag["resistance"])
    source_voltage = _qdict(electrical_diag["source_voltage"])
    power_used = _qdict(electrical_diag["heat_generation"])
    thermal_heat_input = _qdict(thermal_diag["heat_input"])

    expected_operating_resistance = rref * (
        Quantity(1.0, "dimensionless")
        + alpha * (operating_temperature - tref)
    )
    expected_power = source_voltage * source_voltage / resistance_used
    expected_final_resistance = rref * (
        Quantity(1.0, "dimensionless")
        + alpha * (final_temperature - tref)
    )

    checks = (
        _relative_check(
            "material_tcr_relation",
            final_resistance,
            expected_operating_resistance,
            relative_tolerance=1e-11,
            evidence=(
                "material participant operating temperature",
                "R = R_ref * (1 + alpha * (T - T_ref))",
            ),
            detail="Material participant output satisfies its TCR relation.",
        ),
        _relative_check(
            "electrical_joule_relation",
            power_used,
            expected_power,
            relative_tolerance=1e-11,
            evidence=(
                "DC-network participant operating resistance",
                "single ideal voltage source gives P = V^2/R",
            ),
            detail="Electrical participant dissipation matches V^2/R.",
        ),
        _relative_check(
            "power_transfer_conservation",
            thermal_heat_input,
            power_used,
            relative_tolerance=1e-12,
            evidence=(
                "electrical heat_generation output",
                "thermal heat_input consumed in same serial window",
            ),
            detail="Electrical dissipation is conserved into thermal input.",
        ),
        _relative_check(
            "staggered_terminal_resistance_lag",
            final_resistance,
            expected_final_resistance,
            relative_tolerance=COUPLING_RELATIVE_TOLERANCE,
            evidence=(
                "terminal thermal state",
                "terminal material state",
                "declared explicit staggered coupling tolerance",
            ),
            detail=(
                "Terminal lag caused by explicit staggered splitting remains "
                "inside the declared system-level tolerance."
            ),
        ),
        _relative_check(
            "terminal_power_self_consistency",
            final_power,
            source_voltage * source_voltage / final_resistance,
            relative_tolerance=1e-11,
            evidence=(
                "terminal electrical output",
                "terminal material output",
            ),
            detail="Terminal electrical output is self-consistent with R.",
        ),
    )
    return SystemValidationResult(
        valid=all(item.passed for item in checks),
        checks=checks,
        findings=tuple(
            item.detail for item in checks if not item.passed
        ),
        evidence=(
            "typed participant diagnostics from final coupling window",
            "explicit cross-domain conservation and constitutive checks",
        ),
    )


def produce_electrothermal_feedback_uncertainty(record):
    propagated = propagate_feedback_parameter_uncertainty(record)
    return tuple(
        SystemUncertaintyResult(
            quantity=name,
            channel=UncertaintyChannel.EPISTEMIC_PARAMETER,
            uncertainty=uncertainty,
            method_id="electrothermal_feedback.independent_ode_sensitivity",
            evidence=(
                "independent DOP853 reference integration",
                "finite-difference parameter sensitivities",
                "independent STANDARD/PARAMETER inputs only",
            ),
        )
        for name, uncertainty in sorted(propagated.items())
    )


def _digest(payload) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


_REFERENCE_DIGEST = implementation_fingerprint(feedback_reference)[0]

REFERENCE_VERIFICATION_ROUTE = VerificationRoute(
    "electrothermal_feedback.independent_dop853",
    VerificationRouteKind.DIFFERENT_ALGORITHM,
    _REFERENCE_DIGEST,
)

REFERENCE_DEPENDENCIES = RouteDependencyManifest(
    REFERENCE_VERIFICATION_ROUTE.route_id,
    (
        DependencyComponent(
            "reference_model.electrothermal_feedback.monolithic_ode",
            _REFERENCE_DIGEST,
            DependencyRole.MODEL,
        ),
        DependencyComponent(
            "reference_solver.electrothermal_feedback.dop853",
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


def _verification_run(record, plan, quantity: str) -> VerificationRunRecord:
    mapping = {
        FINAL_TEMPERATURE: (
            f"{THERMAL_PARTICIPANT}.temperature",
            "kelvin",
        ),
        RESISTANCE: (
            f"{MATERIAL_PARTICIPANT}.resistance",
            "ohm",
        ),
        HEAT_GENERATION: (
            f"{ELECTRICAL_PARTICIPANT}.heat_generation",
            "watt",
        ),
    }
    output_key, unit = mapping[quantity]
    primary_value = _qdict(record.final_outputs[output_key]).to(unit)
    reference_value = feedback_reference(record)[quantity].to(unit)
    scale = max(
        abs(primary_value.magnitude),
        abs(reference_value.magnitude),
        1e-15,
    )
    tolerance = Quantity(
        VERIFICATION_RELATIVE_TOLERANCE * scale,
        unit,
    )
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
                feedback_reference_evidence_digest(record),
                True,
            ),
        ),
        tolerance=tolerance,
    )


def verify_feedback_temperature(record, plan):
    return _verification_run(record, plan, FINAL_TEMPERATURE)


def verify_feedback_resistance(record, plan):
    return _verification_run(record, plan, RESISTANCE)


def verify_feedback_power(record, plan):
    return _verification_run(record, plan, HEAT_GENERATION)


VALIDATION_REF = ArtifactRef(
    "system.electrothermal_feedback.validation", "1"
)
VALIDATION_PROTOCOLS = (
    ProvidedCompositionValidation(
        BLUEPRINT_ID,
        VALIDATION_REF,
        validate_electrothermal_feedback_run,
    ),
)

UNCERTAINTY_REF = ArtifactRef(
    "system.electrothermal_feedback.parameter_uq", "1"
)
UNCERTAINTY_PRODUCERS = (
    ProvidedCompositionUncertainty(
        BLUEPRINT_ID,
        UNCERTAINTY_REF,
        "electrothermal_feedback.parameter_uq",
        (FINAL_TEMPERATURE, RESISTANCE, HEAT_GENERATION),
        (UncertaintyChannel.EPISTEMIC_PARAMETER,),
        produce_electrothermal_feedback_uncertainty,
    ),
)

_VERIFICATION_SPECS = (
    (
        ArtifactRef(
            "system.electrothermal_feedback.verify_temperature", "1"
        ),
        FINAL_TEMPERATURE,
        verify_feedback_temperature,
    ),
    (
        ArtifactRef(
            "system.electrothermal_feedback.verify_resistance", "1"
        ),
        RESISTANCE,
        verify_feedback_resistance,
    ),
    (
        ArtifactRef(
            "system.electrothermal_feedback.verify_power", "1"
        ),
        HEAT_GENERATION,
        verify_feedback_power,
    ),
)
VERIFICATION_PROTOCOLS = tuple(
    ProvidedCompositionVerification(
        blueprint_id=BLUEPRINT_ID,
        ref=ref,
        quantity=quantity,
        candidates=(
            VerificationCandidate(
                REFERENCE_VERIFICATION_ROUTE,
                REFERENCE_DEPENDENCIES,
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
            THERMAL_LUMPED_MANIFEST.pack_id,
            THERMAL_LUMPED_MANIFEST.pack_version,
            THERMAL_LUMPED_MANIFEST.digest,
        ),
        DomainPackDependency(
            ELECTRICAL_MATERIAL_MANIFEST.pack_id,
            ELECTRICAL_MATERIAL_MANIFEST.pack_version,
            ELECTRICAL_MATERIAL_MANIFEST.digest,
        ),
        DomainPackDependency(
            ELECTRICAL_DC_MANIFEST.pack_id,
            ELECTRICAL_DC_MANIFEST.pack_version,
            ELECTRICAL_DC_MANIFEST.digest,
        ),
    ),
    capabilities=(CAPABILITY_ID,),
    blueprints=(BlueprintRef.from_blueprint(BLUEPRINT),),
    coupling_policies=(PolicyTemplateRef.from_template(COUPLING_POLICY),),
    system_contract_digest=SYSTEM_CONTRACT_DIGEST,
    validation_protocols=(VALIDATION_REF,),
    uncertainty_protocols=(UNCERTAINTY_REF,),
    verification_protocols=tuple(
        ref for ref, _quantity, _implementation in _VERIFICATION_SPECS
    ),
)


class ElectrothermalFeedbackCompositionPack:
    manifest = MANIFEST

    def claim_capabilities(self):
        return (electrothermal_feedback_capability(),)

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


BUILTIN_ELECTROTHERMAL_FEEDBACK_COMPOSITION = (
    ElectrothermalFeedbackCompositionPack()
)

__all__ = [
    "ADAPTER_VERSION",
    "BLUEPRINT",
    "BLUEPRINT_ID",
    "BUILTIN_ELECTROTHERMAL_FEEDBACK_COMPOSITION",
    "CAPABILITY_ID",
    "COUPLING_POLICY",
    "ELECTRICAL_ADAPTER_ID",
    "ELECTRICAL_MODELS",
    "ELECTRICAL_PARTICIPANT",
    "HEAT_GENERATION",
    "MANIFEST",
    "MATERIAL_ADAPTER_ID",
    "MATERIAL_PARTICIPANT",
    "PACK_ID",
    "PACK_VERSION",
    "RESISTANCE",
    "THERMAL_ADAPTER_ID",
    "THERMAL_PARTICIPANT",
    "FINAL_TEMPERATURE",
    "ElectrothermalFeedbackCompositionPack",
    "electrothermal_feedback_capability",
    "validate_electrothermal_feedback_run",
]
