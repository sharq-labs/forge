"""Built-in cross-domain thermal -> material resistance composition."""

from __future__ import annotations

from ..claims.capabilities import (
    CapabilityDeclaration,
    InputDeclaration,
    InputKind,
    InputRole,
    ModelUse,
    ProducedQuantity,
    ProvidedCapability,
    RouteDeclaration,
    RouteKind,
    UncertaintyCapability,
)
from ..claims.contract import ClaimKind
from ..domainpacks.builtin_electrical_material import (
    MANIFEST as ELECTRICAL_MATERIAL_MANIFEST,
)
from ..domainpacks.builtin_thermal_lumped import (
    MANIFEST as THERMAL_LUMPED_MANIFEST,
)
from ..domainpacks.manifest import ArtifactRef
from ..domains.electrical import material
from ..domains.thermal_models import lumped
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
from .applicability import (
    ApplicabilityPredicate,
    ApplicabilityPredicateKind,
)
from .blueprint import CouplingPolicyTemplate, SystemGraphBlueprint
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
from .semantics import (
    CouplingSemantic,
    CouplingSignConvention,
    PortSemanticBinding,
)

PACK_ID = "system.thermal_resistance"
PACK_VERSION = "1"
CAPABILITY_ID = "system.thermal_resistance_property"
BLUEPRINT_ID = "system.thermal_resistance.graph"
BLUEPRINT_VERSION = "1"
POLICY_ID = "system.thermal_resistance.explicit"
POLICY_VERSION = "1"
VALIDATION_ID = "system.thermal_resistance.validation"
VALIDATION_VERSION = "1"

THERMAL_PARTICIPANT = "thermal"
MATERIAL_PARTICIPANT = "material"
THERMAL_ADAPTER_ID = "engcore.adapter.thermal_lumped"
MATERIAL_ADAPTER_ID = "engcore.adapter.linear_tcr"
ADAPTER_VERSION = "1"

Q_TEMPERATURE = "thermodynamics.temperature"
Q_RESISTANCE = "electrical.resistance"
Q_HEAT_INPUT = "thermal.heat_input"
Q_HEAT_CAPACITY = "thermal.heat_capacity"
Q_AMBIENT_CONDUCTANCE = "thermal.ambient_conductance"
Q_AMBIENT_TEMPERATURE = "thermal.ambient_temperature"
Q_INITIAL_TEMPERATURE = "thermal.initial_temperature"
Q_REFERENCE_RESISTANCE = "electrical.reference_resistance"
Q_TCR = "electrical.temperature_coefficient"
Q_REFERENCE_TEMPERATURE = "electrical.reference_temperature"


def thermal_resistance_capability() -> CapabilityDeclaration:
    return CapabilityDeclaration(
        capability_id=CAPABILITY_ID,
        version="1",
        domain="thermal.resistance",
        summary=(
            "Advance one lumped thermal body under an imposed heat input and "
            "evaluate a linear-TCR conductor resistance at the resulting "
            "body temperature."
        ),
        provides=(
            ProvidedCapability(
                lumped.BODY_TEMPERATURE,
                (
                    "domain-pack:"
                    f"{THERMAL_LUMPED_MANIFEST.pack_id}@"
                    f"{THERMAL_LUMPED_MANIFEST.pack_version}"
                ),
            ),
            ProvidedCapability(
                material.TEMPERATURE_DEPENDENT_RESISTANCE,
                (
                    "domain-pack:"
                    f"{ELECTRICAL_MATERIAL_MANIFEST.pack_id}@"
                    f"{ELECTRICAL_MATERIAL_MANIFEST.pack_version}"
                ),
            ),
        ),
        inputs=(
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
                path="thermal.heat_input",
                kind=InputKind.QUANTITY,
                role=InputRole.BOUNDARY_CONDITION,
                required=True,
                unit_exemplar=lumped.POWER_UNIT,
                model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
                model_input=lumped.HEAT_INPUT,
            ),
            InputDeclaration(
                path="conductor.reference_resistance",
                kind=InputKind.QUANTITY,
                role=InputRole.PARAMETER,
                required=True,
                unit_exemplar=material.RESISTANCE_UNIT,
                model_id=material.LINEAR_TCR_MODEL.model_id,
                model_input=material.REFERENCE_RESISTANCE,
            ),
            InputDeclaration(
                path="conductor.temperature_coefficient",
                kind=InputKind.QUANTITY,
                role=InputRole.PARAMETER,
                required=True,
                unit_exemplar=material.TCR_UNIT,
                model_id=material.LINEAR_TCR_MODEL.model_id,
                model_input=material.TEMPERATURE_COEFFICIENT,
            ),
            InputDeclaration(
                path="conductor.reference_temperature",
                kind=InputKind.QUANTITY,
                role=InputRole.PARAMETER,
                required=True,
                unit_exemplar=material.TEMPERATURE_UNIT,
                model_id=material.LINEAR_TCR_MODEL.model_id,
                model_input=material.REFERENCE_TEMPERATURE,
            ),
        ),
        produces=(
            ProducedQuantity(
                name=material.RESISTANCE_METRIC,
                unit_exemplar=material.RESISTANCE_UNIT,
                model_id=material.LINEAR_TCR_MODEL.model_id,
                description=(
                    "Linear-TCR resistance evaluated at the final body "
                    "temperature of the requested simulation horizon."
                ),
            ),
        ),
        models=(
            ModelUse.of(lumped.LUMPED_CAPACITY_MODEL),
            ModelUse.of(material.LINEAR_TCR_MODEL),
        ),
        solvers=(),
        claim_shapes=frozenset(
            {ClaimKind.THRESHOLD, ClaimKind.TOLERANCE_BAND}
        ),
        attainable_levels=(),
        uncertainty=UncertaintyCapability(
            quantified={},
            basis=(
                "The composition records uncertainty propagation explicitly "
                "as unknown until a system-level producer is qualified."
            ),
        ),
        routes=(
            RouteDeclaration(
                route_id="thermal_resistance.generic_multiphysics",
                kind=RouteKind.PRIMARY_SIMULATION,
                description=(
                    "Generic multiphysics execution of the registered thermal "
                    "and material participants."
                ),
            ),
        ),
        executor=None,
        case_builder=None,
    )


THERMAL_PORTS = (
    PortDefinition(
        "heat_capacity",
        PortDirection.INPUT,
        PortKind.SCALAR,
        Q_HEAT_CAPACITY,
        lumped.CAPACITY_UNIT,
    ),
    PortDefinition(
        "ambient_conductance",
        PortDirection.INPUT,
        PortKind.SCALAR,
        Q_AMBIENT_CONDUCTANCE,
        lumped.CONDUCTANCE_UNIT,
    ),
    PortDefinition(
        "ambient_temperature",
        PortDirection.INPUT,
        PortKind.SCALAR,
        Q_AMBIENT_TEMPERATURE,
        lumped.TEMPERATURE_UNIT,
    ),
    PortDefinition(
        "initial_temperature",
        PortDirection.INPUT,
        PortKind.SCALAR,
        Q_INITIAL_TEMPERATURE,
        lumped.TEMPERATURE_UNIT,
    ),
    PortDefinition(
        "heat_input",
        PortDirection.INPUT,
        PortKind.SCALAR,
        Q_HEAT_INPUT,
        lumped.POWER_UNIT,
    ),
    PortDefinition(
        "temperature",
        PortDirection.OUTPUT,
        PortKind.SCALAR,
        Q_TEMPERATURE,
        lumped.TEMPERATURE_UNIT,
    ),
)

MATERIAL_PORTS = (
    PortDefinition(
        "reference_resistance",
        PortDirection.INPUT,
        PortKind.SCALAR,
        Q_REFERENCE_RESISTANCE,
        material.RESISTANCE_UNIT,
    ),
    PortDefinition(
        "temperature_coefficient",
        PortDirection.INPUT,
        PortKind.SCALAR,
        Q_TCR,
        material.TCR_UNIT,
    ),
    PortDefinition(
        "reference_temperature",
        PortDirection.INPUT,
        PortKind.SCALAR,
        Q_REFERENCE_TEMPERATURE,
        material.TEMPERATURE_UNIT,
    ),
    PortDefinition(
        "temperature",
        PortDirection.INPUT,
        PortKind.SCALAR,
        Q_TEMPERATURE,
        material.TEMPERATURE_UNIT,
    ),
    PortDefinition(
        "resistance",
        PortDirection.OUTPUT,
        PortKind.SCALAR,
        Q_RESISTANCE,
        material.RESISTANCE_UNIT,
    ),
)

BLUEPRINT = SystemGraphBlueprint(
    blueprint_id=BLUEPRINT_ID,
    version=BLUEPRINT_VERSION,
    capability_id=CAPABILITY_ID,
    participants=(
        ParticipantBlueprint(
            participant_id=THERMAL_PARTICIPANT,
            model_id=lumped.LUMPED_CAPACITY_MODEL.model_id,
            model_version=lumped.LUMPED_CAPACITY_MODEL.version,
            adapter_id=THERMAL_ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            ports=THERMAL_PORTS,
            transient=True,
            checkpointable=False,
            deterministic_restore=False,
            event_capable=False,
        ),
        ParticipantBlueprint(
            participant_id=MATERIAL_PARTICIPANT,
            model_id=material.LINEAR_TCR_MODEL.model_id,
            model_version=material.LINEAR_TCR_MODEL.version,
            adapter_id=MATERIAL_ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            ports=MATERIAL_PORTS,
            transient=False,
            checkpointable=False,
            deterministic_restore=False,
            event_capable=False,
        ),
    ),
    edges=(
        CouplingEdge(
            edge_id="thermal_temperature_to_material",
            source=PortRef(THERMAL_PARTICIPANT, "temperature"),
            target=PortRef(MATERIAL_PARTICIPANT, "temperature"),
            description=(
                "Final lumped-body temperature is the state coordinate at "
                "which the material resistance is evaluated."
            ),
        ),
    ),
    description=(
        "One-way cross-domain composition: transient lumped thermal state "
        "feeds the linear-TCR electrical material property."
    ),
)

COUPLING_POLICY = CouplingPolicyTemplate(
    template_id=POLICY_ID,
    version=POLICY_VERSION,
    blueprint_id=BLUEPRINT_ID,
    scheme=CouplingScheme.EXPLICIT,
    iteration_semantics=IterationSemantics.SERIAL,
    coupling_window=Quantity(1.0, "second"),
    align_events=False,
    participant_order=(THERMAL_PARTICIPANT, MATERIAL_PARTICIPANT),
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
    )
    for port in ports
)

COUPLING_SEMANTICS = (
    CouplingSemantic(
        blueprint_id=BLUEPRINT_ID,
        edge_id="thermal_temperature_to_material",
        source_quantity_id=Q_TEMPERATURE,
        target_quantity_id=Q_TEMPERATURE,
        transfer_law_id="identity.temperature",
        sign_convention=CouplingSignConvention.SOURCE_TO_TARGET_POSITIVE,
        reference=(
            "The material model declares temperature as an externally supplied "
            "state coordinate; no conversion is applied."
        ),
    ),
)

EXTERNAL_INPUT_BINDINGS = (
    ExternalInputBinding(
        BLUEPRINT_ID,
        THERMAL_PARTICIPANT,
        "heat_capacity",
        "thermal.heat_capacity",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID,
        THERMAL_PARTICIPANT,
        "ambient_conductance",
        "thermal.ambient_conductance",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID,
        THERMAL_PARTICIPANT,
        "ambient_temperature",
        "thermal.ambient_temperature",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID,
        THERMAL_PARTICIPANT,
        "initial_temperature",
        "thermal.initial_temperature",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID,
        THERMAL_PARTICIPANT,
        "heat_input",
        "thermal.heat_input",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID,
        MATERIAL_PARTICIPANT,
        "reference_resistance",
        "conductor.reference_resistance",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID,
        MATERIAL_PARTICIPANT,
        "temperature_coefficient",
        "conductor.temperature_coefficient",
    ),
    ExternalInputBinding(
        BLUEPRINT_ID,
        MATERIAL_PARTICIPANT,
        "reference_temperature",
        "conductor.reference_temperature",
    ),
)

APPLICABILITY_RULES = (
    SystemApplicabilityRule(
        blueprint_id=BLUEPRINT_ID,
        rule_id="thermal_resistance.one_way_state_transfer",
        predicates=(
            ApplicabilityPredicate(
                predicate_id=(
                    "thermal_resistance.static_external_inputs"
                ),
                kind=(
                    ApplicabilityPredicateKind.STATIC_EXTERNAL_INPUTS
                ),
                description=(
                    "This composition is admitted only when external "
                    "parameters are constant over the run horizon."
                ),
            ),
        ),
        required_evidence=(),
        description=(
            "System-level applicability adds only the declared cross-domain "
            "identity; model-level validity remains owned by the two Domain "
            "Packs."
        ),
    ),
)

UNCERTAINTY_RULES = (
    UncertaintyCompositionRule(
        blueprint_id=BLUEPRINT_ID,
        rule_id="thermal_resistance.uncertainty",
        strategy=UncertaintyCompositionStrategy.UNKNOWN,
        channels=(),
        description=(
            "No system-level uncertainty producer is qualified for this "
            "composition yet; the unknown state is explicit."
        ),
    ),
)


def validate_temperature_resistance_run(
    record,
) -> SystemValidationResult:
    """Verify terminal outputs against the declared linear-TCR relation."""

    final_outputs = getattr(record, "final_outputs", {})
    temperature = final_outputs.get(
        f"{THERMAL_PARTICIPANT}.temperature"
    )
    resistance = final_outputs.get(
        f"{MATERIAL_PARTICIPANT}.resistance"
    )
    external = {
        item.port.key: item.value
        for item in getattr(record, "external_inputs", ())
    }
    r_ref = external.get(
        f"{MATERIAL_PARTICIPANT}.reference_resistance"
    )
    alpha = external.get(
        f"{MATERIAL_PARTICIPANT}.temperature_coefficient"
    )
    t_ref = external.get(
        f"{MATERIAL_PARTICIPANT}.reference_temperature"
    )

    checks: list[SystemValidationCheck] = []
    complete = all(
        item is not None
        for item in (temperature, resistance, r_ref, alpha, t_ref)
    )
    checks.append(
        SystemValidationCheck(
            check_id="terminal_contract_complete",
            passed=complete,
            evidence=(
                "thermal.temperature",
                "material.resistance",
                "material.reference_resistance",
                "material.temperature_coefficient",
                "material.reference_temperature",
            ),
            detail=(
                "all quantities required to independently evaluate R(T) "
                "are present"
                if complete
                else "one or more quantities required for R(T) are absent"
            ),
        )
    )

    if complete:
        expected = r_ref * (
            Quantity(1.0, "dimensionless")
            + alpha * (temperature - t_ref)
        )
        error = abs(resistance - expected)
        scale = max(
            1.0,
            abs(expected.magnitude_in(material.RESISTANCE_UNIT)),
        )
        tolerance = Quantity(
            1e-12 * scale,
            material.RESISTANCE_UNIT,
        )
        relative_error = (
            error.magnitude_in(material.RESISTANCE_UNIT) / scale
        )
        relation_ok = (
            error.magnitude_in(material.RESISTANCE_UNIT)
            <= tolerance.magnitude_in(material.RESISTANCE_UNIT)
        )
        checks.append(
            SystemValidationCheck(
                check_id="linear_tcr_relation",
                passed=relation_ok,
                observed=resistance,
                expected=expected,
                tolerance=tolerance,
                absolute_error=error,
                relative_error=relative_error,
                evidence=(
                    "R = R_ref * (1 + alpha * (T - T_ref))",
                    "temperature sourced from terminal thermal output",
                ),
                detail=(
                    "terminal material resistance agrees with the "
                    "declared linear-TCR relation"
                    if relation_ok
                    else "terminal material resistance disagrees with R(T)"
                ),
            )
        )
        positive = (
            resistance.magnitude_in(material.RESISTANCE_UNIT) > 0.0
        )
        checks.append(
            SystemValidationCheck(
                check_id="positive_resistance",
                passed=positive,
                observed=resistance,
                expected=Quantity(0.0, material.RESISTANCE_UNIT),
                evidence=("electrical DC admissibility requires R > 0",),
                detail=(
                    "resistance is physically admissible"
                    if positive
                    else "non-positive resistance is outside DC scope"
                ),
            )
        )

    valid = bool(checks) and all(item.passed for item in checks)
    return SystemValidationResult(
        valid=valid,
        checks=tuple(checks),
        findings=tuple(
            item.detail for item in checks if not item.passed
        ),
        evidence=(
            "independent composition-level evaluation of the TCR equation",
        ),
    )


VALIDATION_REF = ArtifactRef(VALIDATION_ID, VALIDATION_VERSION)
VALIDATION_PROTOCOLS = (
    ProvidedCompositionValidation(
        blueprint_id=BLUEPRINT_ID,
        ref=VALIDATION_REF,
        implementation=validate_temperature_resistance_run,
    ),
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
    ),
    capabilities=(CAPABILITY_ID,),
    blueprints=(BlueprintRef.from_blueprint(BLUEPRINT),),
    coupling_policies=(
        PolicyTemplateRef.from_template(COUPLING_POLICY),
    ),
    system_contract_digest=SYSTEM_CONTRACT_DIGEST,
    validation_protocols=(VALIDATION_REF,),
)


class ThermalResistanceCompositionPack:
    manifest = MANIFEST

    def claim_capabilities(self):
        return (thermal_resistance_capability(),)

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


BUILTIN_THERMAL_RESISTANCE_COMPOSITION = ThermalResistanceCompositionPack()

__all__ = [
    "ADAPTER_VERSION",
    "BLUEPRINT",
    "BLUEPRINT_ID",
    "BUILTIN_THERMAL_RESISTANCE_COMPOSITION",
    "CAPABILITY_ID",
    "COUPLING_POLICY",
    "MANIFEST",
    "MATERIAL_ADAPTER_ID",
    "MATERIAL_PARTICIPANT",
    "PACK_ID",
    "PACK_VERSION",
    "THERMAL_ADAPTER_ID",
    "THERMAL_PARTICIPANT",
    "ThermalResistanceCompositionPack",
    "thermal_resistance_capability",
    "validate_temperature_resistance_run",
]
