"""MVR0 multirotor reference system-pack vertical slice.

The model is intentionally explicit and limited. It couples a benchmark mass
model to reusable ideal actuator-disk hover physics, then exercises frozen D0,
D1 and D2 contracts. Nothing here is a flight-certification or physical-
validation claim.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ....design import (
    CandidateGenerationBatch,
    CandidateGenerationPlan,
    CandidateProposal,
    DesignCandidate,
    DesignEvaluation,
    DesignSpace,
    GenerationStrategy,
    ParetoArchive,
    ProposalDecision,
    ResultBinding,
    ScopedEliteArchive,
    SelectionEligibility,
    generate_initial_population,
)
from ....design.evaluation import RESULT_BINDING_METADATA_KEY
from .rotor_hover import disk_loading, ideal_induced_hover_power
from ....scientific.errors import InvalidScientificProblem
from ....scientific.ir.objectives import ObjectiveDefinition, ObjectiveDirection
from ....scientific.ir.problem import ModelReference
from ....scientific.ir.values import BooleanValue, CategoricalValue, IntegerValue
from ....scientific.ir.variables import ScientificVariable, VariableKind, VariableRole
from ....scientific.results.provenance import ProvenanceRecord
from ....scientific.results.result import ScientificResult
from ....scientific.solvers.protocol import ConvergenceState
from ....scientific.twins.definition import ScientificTwin, TwinDatum, TwinKind
from ....scientific.units.quantity import Quantity

MULTIROTOR_CONSTRAINT_REF = "multirotor:even-rotor-count:v1"
ROTOR_HOVER_MODEL_ID = "ideal-actuator-disk-hover"
SYSTEM_MODEL_ID = "mvr0-multirotor-mass-endurance-reference"
MODEL_VERSION = "0.1"
MODEL_IDENTITIES = (
    (ROTOR_HOVER_MODEL_ID, MODEL_VERSION),
    (SYSTEM_MODEL_ID, MODEL_VERSION),
)

SPECIFIC_ENERGY_WH_PER_KG = {
    "conservative": 160.0,
    "standard": 220.0,
    "high": 280.0,
}
FRAME_BASE_MASS_KG = {
    "light": 0.35,
    "standard": 0.55,
    "rugged": 0.80,
}
FRAME_RADIUS_COEFF_KG_PER_M_PER_ROTOR = 0.35
FIXED_AVIONICS_MASS_KG = 0.18
MOTOR_ESC_MASS_KG_PER_ROTOR = 0.085
ROTOR_PROP_MASS_KG_PER_ROTOR = 0.025
PROP_GUARD_MASS_KG_PER_ROTOR = 0.035
PROP_GUARD_EFFICIENCY_MULTIPLIER = 0.94

MVR0_ASSUMPTIONS = (
    "steady hover only",
    "uniform actuator-disk momentum-theory approximation",
    "no forward-flight aerodynamics",
    "no rotor-rotor interference correction",
    "no propeller blade-element map",
    "no motor/ESC efficiency map",
    "no battery voltage sag or thermal model",
    "no structural stress, buckling or fatigue analysis",
    "no flight-control or stability analysis",
    "no acoustic model",
    "no propeller tip-Mach constraint",
    "benchmark mass and efficiency coefficients are reference coefficients, not catalog evidence",
    "target satisfaction is meaningful only under the frozen MVR0 reference model",
    "air density defaults to ISA sea level (1.225 kg/m^3); altitude is not modelled and is not asked for",
    "usable battery fraction defaults to 0.80, a reference depth of discharge and not a property of any pack",
    "hover efficiency defaults to 0.72, one lumped figure for the whole motor/ESC/propeller chain",
    "auxiliary power defaults to 25 W, fixed and independent of airframe, payload and flight time",
    "a result computed from those four defaults is a result about this benchmark, not about a vehicle",
)


@dataclass(frozen=True)
class MultirotorTargetSpec:
    """The hover target, and FOUR VALUES THAT DEFAULT RATHER THAN BEING ASKED.

    ``air_density``, ``usable_battery_fraction``, ``base_hover_efficiency`` and
    ``auxiliary_power`` all carry defaults, so ``MultirotorTargetSpec()``
    constructs and answers without the caller stating any of them. **The answer
    then reads as general and is not.** What those defaults commit to:

    * ``air_density = 1.225 kg/m^3`` -- ISA sea level, 15 degC, dry. A design
      that hovers at sea level does not hover at 2000 m on this number.
    * ``usable_battery_fraction = 0.80`` -- a reference depth of discharge, not
      a property of any pack, and not derived from a cell record.
    * ``base_hover_efficiency = 0.72`` -- one lumped figure standing for the
      whole motor/ESC/propeller chain. There is no efficiency map behind it;
      ``MVR0_ASSUMPTIONS`` says so twice.
    * ``auxiliary_power = 25 W`` -- a fixed avionics draw, independent of the
      airframe, the payload and the flight time.

    Each is a REFERENCE COEFFICIENT of the frozen MVR0/MVR1 benchmark, not a
    measurement and not a catalogue value. A result computed from the defaults
    is a result about that benchmark. Supplying your own is the supported way
    to ask about a real vehicle, and doing so is what makes the answer yours
    rather than the benchmark's.
    """

    payload_mass: Quantity = field(default_factory=lambda: Quantity(0.50, "kg"))
    minimum_hover_endurance: Quantity = field(
        default_factory=lambda: Quantity(15.0, "min")
    )
    maximum_takeoff_mass: Quantity = field(default_factory=lambda: Quantity(3.0, "kg"))
    maximum_disk_loading: Quantity = field(
        default_factory=lambda: Quantity(120.0, "N/m^2")
    )
    air_density: Quantity = field(default_factory=lambda: Quantity(1.225, "kg/m^3"))
    gravity: Quantity = field(default_factory=lambda: Quantity(9.80665, "m/s^2"))
    usable_battery_fraction: float = 0.80
    base_hover_efficiency: float = 0.72
    auxiliary_power: Quantity = field(default_factory=lambda: Quantity(25.0, "W"))

    def __post_init__(self) -> None:
        normalized = {
            "payload_mass": self.payload_mass.to("kg"),
            "minimum_hover_endurance": self.minimum_hover_endurance.to("s"),
            "maximum_takeoff_mass": self.maximum_takeoff_mass.to("kg"),
            "maximum_disk_loading": self.maximum_disk_loading.to("N/m^2"),
            "air_density": self.air_density.to("kg/m^3"),
            "gravity": self.gravity.to("m/s^2"),
            "auxiliary_power": self.auxiliary_power.to("W"),
        }
        for name, value in normalized.items():
            if name == "auxiliary_power":
                if value.magnitude < 0.0:
                    raise InvalidScientificProblem("auxiliary_power cannot be negative")
            elif not value.magnitude > 0.0:
                raise InvalidScientificProblem(f"{name} must be positive")
            object.__setattr__(self, name, value)

        usable = float(self.usable_battery_fraction)
        efficiency = float(self.base_hover_efficiency)
        if not 0.0 < usable <= 1.0:
            raise InvalidScientificProblem("usable_battery_fraction must be in (0, 1]")
        if not 0.0 < efficiency <= 1.0:
            raise InvalidScientificProblem("base_hover_efficiency must be in (0, 1]")
        object.__setattr__(self, "usable_battery_fraction", usable)
        object.__setattr__(self, "base_hover_efficiency", efficiency)


@dataclass(frozen=True)
class MultirotorTargetAssessment:
    candidate_id: str
    meets_target: bool
    failed_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        candidate_id = str(self.candidate_id).strip()
        if not candidate_id:
            raise InvalidScientificProblem("target assessment requires candidate_id")
        failures = tuple(str(item).strip() for item in self.failed_requirements)
        if any(not item for item in failures):
            raise InvalidScientificProblem("target assessment failures must be non-empty")
        if self.meets_target and failures:
            raise InvalidScientificProblem("passing target assessment cannot list failures")
        if not self.meets_target and not failures:
            raise InvalidScientificProblem("failing target assessment requires reasons")
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "failed_requirements", failures)


def build_reference_design_space() -> DesignSpace:
    """Frozen MVR0 mixed design-space declaration."""

    return DesignSpace(
        space_id="multirotor-mvr0-reference",
        version="1",
        name="MVR0 multirotor reference design space",
        description="Reference mixed-variable hover benchmark; not certified aircraft design.",
        variables=(
            ScientificVariable(
                name="rotor_count",
                unit="dimensionless",
                kind=VariableKind.INTEGER,
                role=VariableRole.DESIGN,
                lower=Quantity(4, "dimensionless"),
                upper=Quantity(8, "dimensionless"),
            ),
            ScientificVariable(
                name="rotor_radius",
                unit="m",
                kind=VariableKind.CONTINUOUS,
                role=VariableRole.DESIGN,
                lower=Quantity(0.09, "m"),
                upper=Quantity(0.20, "m"),
            ),
            ScientificVariable(
                name="battery_energy",
                unit="Wh",
                kind=VariableKind.CONTINUOUS,
                role=VariableRole.DESIGN,
                lower=Quantity(120.0, "Wh"),
                upper=Quantity(450.0, "Wh"),
            ),
            ScientificVariable(
                name="battery_specific_energy_class",
                unit="dimensionless",
                kind=VariableKind.CATEGORICAL,
                role=VariableRole.DESIGN,
                categories=("conservative", "standard", "high"),
            ),
            ScientificVariable(
                name="frame_class",
                unit="dimensionless",
                kind=VariableKind.CATEGORICAL,
                role=VariableRole.DESIGN,
                categories=("light", "standard", "rugged"),
            ),
            ScientificVariable(
                name="prop_guards",
                unit="dimensionless",
                kind=VariableKind.BOOLEAN,
                role=VariableRole.DESIGN,
            ),
        ),
        constraint_refs=(MULTIROTOR_CONSTRAINT_REF,),
        metadata={"scientific_role": "reference_vertical_slice"},
    )


class MultirotorProposalGate:
    """System-owned topology gate; D2 sees only the opaque constraint id."""

    constraint_refs = (MULTIROTOR_CONSTRAINT_REF,)

    def decide(self, proposal: CandidateProposal) -> ProposalDecision:
        value = proposal.assignments.get("rotor_count")
        if not isinstance(value, IntegerValue):
            raise InvalidScientificProblem("multirotor rotor_count must be IntegerValue")
        if value.value in (4, 6, 8):
            return ProposalDecision(True, ("MVR0 even-rotor topology admitted",))
        return ProposalDecision(False, ("MVR0 benchmark admits rotor_count in {4, 6, 8}",))


class MultirotorTwinMaterializer:
    """Materialize exact candidate design declarations into a candidate Twin."""

    def materialize(self, proposal: CandidateProposal) -> ScientificTwin:
        return ScientificTwin(
            twin_id=f"mvr0:twin:{proposal.candidate_id}",
            version="1",
            kind=TwinKind.CANDIDATE,
            models=tuple(ModelReference(model_id, version) for model_id, version in MODEL_IDENTITIES),
            declarations=tuple(
                TwinDatum(name=name, value=value)
                for name, value in sorted(proposal.assignments.items())
            ),
            metadata={"system_pack": "multirotor_mvr0_reference"},
        )


def _require_assignments(candidate: DesignCandidate) -> tuple[int, float, float, str, str, bool]:
    rotor_count = candidate.assignments["rotor_count"]
    rotor_radius = candidate.assignments["rotor_radius"]
    battery_energy = candidate.assignments["battery_energy"]
    specific_class = candidate.assignments["battery_specific_energy_class"]
    frame_class = candidate.assignments["frame_class"]
    prop_guards = candidate.assignments["prop_guards"]

    if not isinstance(rotor_count, IntegerValue):
        raise InvalidScientificProblem("rotor_count assignment must be IntegerValue")
    if not isinstance(rotor_radius, Quantity):
        raise InvalidScientificProblem("rotor_radius assignment must be Quantity")
    if not isinstance(battery_energy, Quantity):
        raise InvalidScientificProblem("battery_energy assignment must be Quantity")
    if not isinstance(specific_class, CategoricalValue):
        raise InvalidScientificProblem(
            "battery_specific_energy_class assignment must be CategoricalValue"
        )
    if not isinstance(frame_class, CategoricalValue):
        raise InvalidScientificProblem("frame_class assignment must be CategoricalValue")
    if not isinstance(prop_guards, BooleanValue):
        raise InvalidScientificProblem("prop_guards assignment must be BooleanValue")

    if rotor_count.value not in (4, 6, 8):
        raise InvalidScientificProblem("evaluated MVR0 candidate violates topology gate")
    if specific_class.value not in SPECIFIC_ENERGY_WH_PER_KG:
        raise InvalidScientificProblem("unknown MVR0 battery specific-energy class")
    if frame_class.value not in FRAME_BASE_MASS_KG:
        raise InvalidScientificProblem("unknown MVR0 frame class")

    return (
        rotor_count.value,
        rotor_radius.magnitude_in("m"),
        battery_energy.magnitude_in("Wh"),
        specific_class.value,
        frame_class.value,
        prop_guards.value,
    )


def evaluate_reference_candidate(
    *,
    candidate: DesignCandidate,
    twin: ScientificTwin,
    design_space: DesignSpace,
    target: MultirotorTargetSpec,
    source_revision: str = "",
) -> tuple[DesignEvaluation, MultirotorTargetAssessment]:
    """Evaluate one candidate under the frozen MVR0 analytic benchmark."""

    candidate.validate_against(design_space)
    if not isinstance(twin, ScientificTwin) or twin.kind is not TwinKind.CANDIDATE:
        raise InvalidScientificProblem("MVR0 evaluation requires candidate ScientificTwin")
    if candidate.twin.key != twin.reference.key:
        raise InvalidScientificProblem("MVR0 candidate/Twin identity mismatch")
    if not isinstance(target, MultirotorTargetSpec):
        raise InvalidScientificProblem("MVR0 evaluation requires MultirotorTargetSpec")

    rotor_count, radius_m, energy_wh, specific_class, frame_class, guards = _require_assignments(candidate)

    battery_mass_kg = energy_wh / SPECIFIC_ENERGY_WH_PER_KG[specific_class]
    frame_mass_kg = (
        FRAME_BASE_MASS_KG[frame_class]
        + FRAME_RADIUS_COEFF_KG_PER_M_PER_ROTOR * radius_m * rotor_count
    )
    guard_mass_kg = PROP_GUARD_MASS_KG_PER_ROTOR * rotor_count if guards else 0.0
    total_mass_kg = (
        target.payload_mass.magnitude_in("kg")
        + FIXED_AVIONICS_MASS_KG
        + battery_mass_kg
        + MOTOR_ESC_MASS_KG_PER_ROTOR * rotor_count
        + ROTOR_PROP_MASS_KG_PER_ROTOR * rotor_count
        + frame_mass_kg
        + guard_mass_kg
    )
    if not total_mass_kg > 0.0:
        raise InvalidScientificProblem("MVR0 computed non-positive total mass")

    total_disk_area_m2 = rotor_count * math.pi * radius_m**2
    if not total_disk_area_m2 > 0.0:
        raise InvalidScientificProblem("MVR0 computed non-positive disk area")

    thrust_n = total_mass_kg * target.gravity.magnitude_in("m/s^2")
    thrust = Quantity(thrust_n, "N")
    area = Quantity(total_disk_area_m2, "m^2")
    ideal_power = ideal_induced_hover_power(
        thrust=thrust,
        disk_area=area,
        air_density=target.air_density,
    )
    loading = disk_loading(thrust=thrust, disk_area=area)

    efficiency = target.base_hover_efficiency * (
        PROP_GUARD_EFFICIENCY_MULTIPLIER if guards else 1.0
    )
    if not 0.0 < efficiency <= 1.0:
        raise InvalidScientificProblem("MVR0 computed nonphysical hover efficiency")

    electrical_power_w = (
        ideal_power.magnitude_in("W") / efficiency
        + target.auxiliary_power.magnitude_in("W")
    )
    if not electrical_power_w > 0.0:
        raise InvalidScientificProblem("MVR0 computed non-positive electrical power")

    usable_energy_wh = target.usable_battery_fraction * energy_wh
    endurance_s = usable_energy_wh * 3600.0 / electrical_power_w

    mass_margin_kg = target.maximum_takeoff_mass.magnitude_in("kg") - total_mass_kg
    endurance_margin_s = (
        endurance_s - target.minimum_hover_endurance.magnitude_in("s")
    )
    disk_loading_margin = (
        target.maximum_disk_loading.magnitude_in("N/m^2")
        - loading.magnitude_in("N/m^2")
    )

    failures: list[str] = []
    if mass_margin_kg < 0.0:
        failures.append("maximum_takeoff_mass")
    if endurance_margin_s < 0.0:
        failures.append("minimum_hover_endurance")
    if disk_loading_margin < 0.0:
        failures.append("maximum_disk_loading")
    assessment = MultirotorTargetAssessment(
        candidate_id=candidate.candidate_id,
        meets_target=not failures,
        failed_requirements=tuple(failures),
    )

    binding = ResultBinding(
        candidate=candidate.reference,
        twin=twin.reference,
        design_space=design_space.reference,
    )
    provenance = ProvenanceRecord(
        run_id=f"mvr0:{candidate.candidate_id}",
        software_version="mvr0-v0.1",
        git_commit=str(source_revision).strip() or None,
        models=MODEL_IDENTITIES,
        inputs={
            "payload_mass": target.payload_mass,
            "minimum_hover_endurance": target.minimum_hover_endurance,
            "maximum_takeoff_mass": target.maximum_takeoff_mass,
            "maximum_disk_loading": target.maximum_disk_loading,
            "air_density": target.air_density,
            "gravity": target.gravity,
            "auxiliary_power": target.auxiliary_power,
            "rotor_radius": candidate.assignments["rotor_radius"],
            "battery_energy": candidate.assignments["battery_energy"],
        },
        assumptions=MVR0_ASSUMPTIONS,
        metadata={
            RESULT_BINDING_METADATA_KEY: binding.to_dict(),
            "system_pack": "multirotor_mvr0_reference",
        },
    )
    result = ScientificResult(
        result_id=f"mvr0-result:{candidate.candidate_id}",
        problem_id="mvr0-reference-hover",
        values={
            "total_mass": Quantity(total_mass_kg, "kg"),
            "battery_mass": Quantity(battery_mass_kg, "kg"),
            "total_disk_area": area,
            "disk_loading": loading,
            "ideal_induced_power": ideal_power,
            "hover_electrical_power": Quantity(electrical_power_w, "W"),
            "hover_endurance": Quantity(endurance_s, "s"),
            "mass_margin": Quantity(mass_margin_kg, "kg"),
            "endurance_margin": Quantity(endurance_margin_s, "s"),
            "disk_loading_margin": Quantity(disk_loading_margin, "N/m^2"),
        },
        provenance=provenance,
        models=MODEL_IDENTITIES,
        # MVR0's two models are reference identities: neither is a
        # `ScientificModelDefinition` and neither declares a validity domain,
        # so there is no envelope to assess this candidate against. That is a
        # real gap and it is now recorded as one, on every result, rather than
        # being indistinguishable from a domain that simply did not bother.
        validity_not_assessed={
            model_id: (
                "not assessed: MVR0 declares this model as a reference "
                "identity with no ValidityDomain, so there is no envelope to "
                "assess against. Declaring one is MVR1's work"
            )
            for model_id, _version in MODEL_IDENTITIES
        },
        convergence=ConvergenceState.NOT_APPLICABLE,
        assumptions=MVR0_ASSUMPTIONS,
        warnings=(
            "MVR0 is a reference analytic benchmark; it is not physical validation, certification or a flight-readiness claim",
        ),
        metadata={"reference_target_pass": assessment.meets_target},
    )
    evaluation = DesignEvaluation(
        evaluation_id=f"mvr0-eval:{candidate.candidate_id}",
        candidate=candidate.reference,
        twin=twin.reference,
        design_space=design_space.reference,
        result=result,
        eligibility=SelectionEligibility.ELIGIBLE,
        eligibility_reasons=(
            "reference analytic evaluation is available for D1 comparison; eligibility does not imply target satisfaction or physical feasibility",
        ),
        metadata={
            "reference_target_pass": assessment.meets_target,
            "reference_target_failed_requirements": list(assessment.failed_requirements),
        },
    ).validate_candidate(candidate)
    return evaluation, assessment


def global_objectives() -> tuple[ObjectiveDefinition, ...]:
    return (
        ObjectiveDefinition(
            name="total_mass",
            metric="total_mass",
            direction=ObjectiveDirection.MINIMIZE,
            unit="kg",
        ),
        ObjectiveDefinition(
            name="hover_endurance",
            metric="hover_endurance",
            direction=ObjectiveDirection.MAXIMIZE,
            unit="s",
        ),
        ObjectiveDefinition(
            name="hover_electrical_power",
            metric="hover_electrical_power",
            direction=ObjectiveDirection.MINIMIZE,
            unit="W",
        ),
    )


@dataclass(frozen=True)
class MultirotorReferenceRun:
    design_space: DesignSpace
    target: MultirotorTargetSpec
    batch: CandidateGenerationBatch
    evaluations: tuple[DesignEvaluation, ...]
    assessments: tuple[MultirotorTargetAssessment, ...]
    pareto: ParetoArchive
    scoped_archives: tuple[ScopedEliteArchive, ...]

    def __post_init__(self) -> None:
        if len(self.evaluations) != len(self.batch.candidates):
            raise InvalidScientificProblem("MVR0 run evaluation count mismatch")
        if len(self.assessments) != len(self.batch.candidates):
            raise InvalidScientificProblem("MVR0 run target-assessment count mismatch")
        candidate_ids = {item.candidate_id for item in self.batch.candidates}
        if {item.candidate.candidate_id for item in self.evaluations} != candidate_ids:
            raise InvalidScientificProblem("MVR0 run evaluation identities mismatch")
        if {item.candidate_id for item in self.assessments} != candidate_ids:
            raise InvalidScientificProblem("MVR0 run assessment identities mismatch")
        self.pareto.validate_against(self.evaluations)
        for archive in self.scoped_archives:
            archive.validate_against(self.evaluations)

    def summary(self) -> dict[str, Any]:
        rotor_counts = Counter(
            candidate.assignments["rotor_count"].value
            for candidate in self.batch.candidates
        )
        metrics: dict[str, tuple[float, float]] = {}
        for metric, unit in (
            ("total_mass", "kg"),
            ("hover_endurance", "s"),
            ("hover_electrical_power", "W"),
            ("disk_loading", "N/m^2"),
        ):
            values = [evaluation.result.value(metric).magnitude_in(unit) for evaluation in self.evaluations]
            metrics[metric] = (min(values), max(values))

        return {
            "generated_candidates": len(self.batch.candidates),
            "rejected_proposals": len(self.batch.rejected),
            "rotor_count_counts": dict(sorted(rotor_counts.items())),
            "reference_target_pass_count": sum(
                assessment.meets_target for assessment in self.assessments
            ),
            "pareto_member_count": len(self.pareto.members),
            "scoped_member_counts": {
                archive.scope_ref: len(archive.members)
                for archive in sorted(self.scoped_archives, key=lambda item: item.scope_ref)
            },
            "metric_ranges": metrics,
            "pareto_member_ids": tuple(
                member.evaluation_id for member in self.pareto.members
            ),
        }


def run_reference_study(
    *,
    count: int = 1000,
    attempt_budget: int = 3000,
    target: MultirotorTargetSpec | None = None,
    source_revision: str = "",
) -> MultirotorReferenceRun:
    """Run the deterministic MVR0 generation → evaluation → archive slice."""

    design_space = build_reference_design_space()
    target = target or MultirotorTargetSpec()
    plan = CandidateGenerationPlan(
        population_id="mvr0-reference-population",
        design_space=design_space.reference,
        count=count,
        generation=0,
        sequence_start=1,
        attempt_budget=attempt_budget,
        strategy=GenerationStrategy.HALTON_V1,
        candidate_prefix="mvr0",
    )
    batch = generate_initial_population(
        design_space=design_space,
        plan=plan,
        materializer=MultirotorTwinMaterializer(),
        gate=MultirotorProposalGate(),
    )

    twins_by_key = {twin.reference.key: twin for twin in batch.twins}
    evaluations: list[DesignEvaluation] = []
    assessments: list[MultirotorTargetAssessment] = []
    for candidate in batch.candidates:
        twin = twins_by_key[candidate.twin.key]
        evaluation, assessment = evaluate_reference_candidate(
            candidate=candidate,
            twin=twin,
            design_space=design_space,
            target=target,
            source_revision=source_revision,
        )
        evaluations.append(evaluation)
        assessments.append(assessment)

    evaluation_tuple = tuple(evaluations)
    objectives = global_objectives()
    pareto = ParetoArchive.build(
        archive_id="mvr0-global-pareto",
        design_space=design_space.reference,
        objectives=objectives,
        evaluations=evaluation_tuple,
    )
    scoped = (
        ScopedEliteArchive.build(
            archive_id="mvr0-elite-mass",
            scope_ref="multirotor:mass",
            design_space=design_space.reference,
            objectives=(objectives[0],),
            evaluations=evaluation_tuple,
        ),
        ScopedEliteArchive.build(
            archive_id="mvr0-elite-endurance",
            scope_ref="multirotor:endurance",
            design_space=design_space.reference,
            objectives=(objectives[1],),
            evaluations=evaluation_tuple,
        ),
        ScopedEliteArchive.build(
            archive_id="mvr0-elite-hover-power",
            scope_ref="multirotor:hover-power",
            design_space=design_space.reference,
            objectives=(objectives[2],),
            evaluations=evaluation_tuple,
        ),
    )
    return MultirotorReferenceRun(
        design_space=design_space,
        target=target,
        batch=batch,
        evaluations=evaluation_tuple,
        assessments=tuple(assessments),
        pareto=pareto,
        scoped_archives=scoped,
    )
