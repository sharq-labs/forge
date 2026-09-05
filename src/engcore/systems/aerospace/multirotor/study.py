"""MVR1 target-driven multirotor study layer.

This module is system-owned glue around the frozen MVR0 reference benchmark.
It separates caller-supplied operating conditions from target requirements,
adds deterministic study identity, and binds every payload-dependent result to
the exact study that produced it.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Mapping

from ....design import (
    CandidateGenerationBatch,
    CandidateGenerationPlan,
    DesignCandidate,
    DesignSpace,
    DesignEvaluation,
    GenerationStrategy,
    ParetoArchive,
    ScopedEliteArchive,
    SelectionEligibility,
    generate_initial_population,
)
from ....design.evaluation import RESULT_BINDING_METADATA_KEY
from ....scientific.errors import InvalidScientificProblem
from ....scientific.results.provenance import ProvenanceRecord
from ....scientific.results.result import ScientificResult
from ....scientific.twins.definition import ScientificTwin
from ....scientific.units.quantity import Quantity
from .reference import (
    MODEL_IDENTITIES,
    MODEL_VERSION,
    MVR0_ASSUMPTIONS,
    MultirotorProposalGate,
    MultirotorTargetSpec,
    MultirotorTwinMaterializer,
    build_reference_design_space,
    evaluate_reference_candidate,
    global_objectives,
)

MULTIROTOR_STUDY_SCHEMA = "multirotor_study_specification"
MULTIROTOR_STUDY_VERSION = "0.1"
MULTIROTOR_STUDY_ID_PREFIX = "multirotor-study-v0.1:sha256:"
MULTIROTOR_STUDY_BINDING_METADATA_KEY = "engcore.multirotor.mvr1.study_binding"
MVR1_DEFAULT_COUNT = 1000
MVR1_DEFAULT_ATTEMPT_BUDGET = 3000
MVR1_GENERATION = 0
MVR1_SEQUENCE_START = 1
MVR1_POPULATION_ID = "mvr0-reference-population"
MVR1_CANDIDATE_PREFIX = "mvr0"
MVR1_PHYSICAL_OUTPUT_UNITS = {
    "total_mass": "kg",
    "battery_mass": "kg",
    "total_disk_area": "m^2",
    "disk_loading": "N/m^2",
    "ideal_induced_power": "W",
    "hover_electrical_power": "W",
    "hover_endurance": "s",
}


def _positive_quantity(value: Quantity, unit: str, field_name: str) -> Quantity:
    if not isinstance(value, Quantity):
        raise InvalidScientificProblem(f"{field_name} must be a Quantity")
    normalized = value.to(unit)
    if not normalized.magnitude > 0.0:
        raise InvalidScientificProblem(f"{field_name} must be strictly positive")
    return normalized


def _quantity_payload(value: Quantity, unit: str) -> dict[str, Any]:
    normalized = value.to(unit)
    return {"magnitude": normalized.magnitude, "units": unit}


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _study_digest_prefix(study_identity_value: str) -> str:
    study_id = str(study_identity_value).strip()
    if not study_id.startswith(MULTIROTOR_STUDY_ID_PREFIX):
        raise InvalidScientificProblem("malformed MVR1 study identity")
    digest = study_id.removeprefix(MULTIROTOR_STUDY_ID_PREFIX)
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise InvalidScientificProblem("malformed MVR1 study identity digest")
    return digest[:16]


def _study_bound_evaluation_id(candidate_id: str, study_identity_value: str) -> str:
    return f"mvr1-eval:{candidate_id}:{_study_digest_prefix(study_identity_value)}"


def _study_bound_result_id(candidate_id: str, study_identity_value: str) -> str:
    return f"mvr1-result:{candidate_id}:{_study_digest_prefix(study_identity_value)}"


def _study_bound_run_id(candidate_id: str, study_identity_value: str) -> str:
    return f"mvr1:{study_identity_value}:{candidate_id}"


def _quantity_from_payload(payload: Mapping[str, Any], *, context: str) -> Quantity:
    try:
        magnitude = payload["magnitude"]
        units = payload["units"]
    except KeyError as exc:
        raise InvalidScientificProblem(
            f"malformed MVR1 study quantity in {context}"
        ) from exc
    return Quantity(magnitude, units)


def _require_quantity_equal(
    actual: Quantity,
    expected: Quantity,
    unit: str,
    *,
    context: str,
) -> None:
    if not isinstance(actual, Quantity):
        raise InvalidScientificProblem(f"{context} must be a Quantity")
    if actual.magnitude_in(unit) != expected.magnitude_in(unit):
        raise InvalidScientificProblem(f"MVR1 {context} mismatch")


@dataclass(frozen=True)
class MultirotorStudySpecification:
    """Typed MVR1 study specification.

    ``payload_mass`` is an operating condition and enters the frozen reference
    computation. The other fields are target requirements used only for margin
    assessment after evaluation.
    """

    payload_mass: Quantity
    minimum_hover_endurance: Quantity
    maximum_takeoff_mass: Quantity
    maximum_disk_loading: Quantity

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "payload_mass",
            _positive_quantity(self.payload_mass, "kg", "payload_mass"),
        )
        object.__setattr__(
            self,
            "minimum_hover_endurance",
            _positive_quantity(
                self.minimum_hover_endurance, "s", "minimum_hover_endurance"
            ),
        )
        object.__setattr__(
            self,
            "maximum_takeoff_mass",
            _positive_quantity(self.maximum_takeoff_mass, "kg", "maximum_takeoff_mass"),
        )
        object.__setattr__(
            self,
            "maximum_disk_loading",
            _positive_quantity(
                self.maximum_disk_loading, "N/m^2", "maximum_disk_loading"
            ),
        )

    @property
    def operating_conditions(self) -> Mapping[str, Quantity]:
        return MappingProxyType({"payload_mass": self.payload_mass})

    @property
    def target_requirements(self) -> Mapping[str, Quantity]:
        return MappingProxyType(
            {
                "minimum_hover_endurance": self.minimum_hover_endurance,
                "maximum_takeoff_mass": self.maximum_takeoff_mass,
                "maximum_disk_loading": self.maximum_disk_loading,
            }
        )

    def to_reference_target(self) -> MultirotorTargetSpec:
        """Adapt MVR1 study semantics into the frozen MVR0 execution contract."""

        return MultirotorTargetSpec(
            payload_mass=self.payload_mass,
            minimum_hover_endurance=self.minimum_hover_endurance,
            maximum_takeoff_mass=self.maximum_takeoff_mass,
            maximum_disk_loading=self.maximum_disk_loading,
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema": MULTIROTOR_STUDY_SCHEMA,
            "schema_version": MULTIROTOR_STUDY_VERSION,
            "operating_conditions": {
                "payload_mass": _quantity_payload(self.payload_mass, "kg"),
            },
            "target_requirements": {
                "minimum_hover_endurance": _quantity_payload(
                    self.minimum_hover_endurance, "s"
                ),
                "maximum_takeoff_mass": _quantity_payload(
                    self.maximum_takeoff_mass, "kg"
                ),
                "maximum_disk_loading": _quantity_payload(
                    self.maximum_disk_loading, "N/m^2"
                ),
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return self.canonical_payload()


def study_identity_payload(
    specification: MultirotorStudySpecification,
    *,
    count: int = MVR1_DEFAULT_COUNT,
    attempt_budget: int = MVR1_DEFAULT_ATTEMPT_BUDGET,
) -> dict[str, Any]:
    if not isinstance(specification, MultirotorStudySpecification):
        raise InvalidScientificProblem(
            "MVR1 study identity requires MultirotorStudySpecification"
        )
    design_space = build_reference_design_space()
    plan = CandidateGenerationPlan(
        population_id=MVR1_POPULATION_ID,
        design_space=design_space.reference,
        count=count,
        generation=MVR1_GENERATION,
        sequence_start=MVR1_SEQUENCE_START,
        attempt_budget=attempt_budget,
        strategy=GenerationStrategy.HALTON_V1,
        candidate_prefix=MVR1_CANDIDATE_PREFIX,
    )
    return {
        "schema": "multirotor_study_identity",
        "schema_version": MULTIROTOR_STUDY_VERSION,
        "study_specification": specification.canonical_payload(),
        "frozen_reference_model": {
            "model_version": MODEL_VERSION,
            "models": [list(item) for item in MODEL_IDENTITIES],
            "assumptions_family": "mvr0_reference",
        },
        "frozen_design_space": design_space.reference.to_dict(),
        "frozen_generation_plan": plan.to_dict(),
    }


def study_identity(
    specification: MultirotorStudySpecification,
    *,
    count: int = MVR1_DEFAULT_COUNT,
    attempt_budget: int = MVR1_DEFAULT_ATTEMPT_BUDGET,
) -> str:
    payload = study_identity_payload(
        specification, count=count, attempt_budget=attempt_budget
    )
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"{MULTIROTOR_STUDY_ID_PREFIX}{digest}"


@dataclass(frozen=True)
class MultirotorStudyBinding:
    study_identity: str
    study_payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        study_id = str(self.study_identity).strip()
        if not study_id.startswith(MULTIROTOR_STUDY_ID_PREFIX):
            raise InvalidScientificProblem("malformed MVR1 study identity")
        try:
            payload = json.loads(_canonical_json(self.study_payload))
        except TypeError as exc:
            raise InvalidScientificProblem("malformed MVR1 study binding payload") from exc
        expected = f"{MULTIROTOR_STUDY_ID_PREFIX}{hashlib.sha256(_canonical_json(payload).encode('utf-8')).hexdigest()}"
        if expected != study_id:
            raise InvalidScientificProblem("MVR1 study binding digest mismatch")
        object.__setattr__(self, "study_identity", study_id)
        object.__setattr__(self, "study_payload", payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "multirotor_study_binding",
            "schema_version": MULTIROTOR_STUDY_VERSION,
            "study_identity": self.study_identity,
            "study_payload": json.loads(_canonical_json(self.study_payload)),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MultirotorStudyBinding":
        if payload.get("schema") != "multirotor_study_binding":
            raise InvalidScientificProblem("malformed MVR1 study binding schema")
        if payload.get("schema_version") != MULTIROTOR_STUDY_VERSION:
            raise InvalidScientificProblem("malformed MVR1 study binding version")
        if "study_identity" not in payload or "study_payload" not in payload:
            raise InvalidScientificProblem("malformed MVR1 study binding payload")
        return cls(
            study_identity=payload["study_identity"],
            study_payload=payload["study_payload"],
        )


def _binding_for(
    specification: MultirotorStudySpecification,
    *,
    count: int,
    attempt_budget: int,
) -> MultirotorStudyBinding:
    payload = study_identity_payload(
        specification, count=count, attempt_budget=attempt_budget
    )
    return MultirotorStudyBinding(
        study_identity=study_identity(
            specification, count=count, attempt_budget=attempt_budget
        ),
        study_payload=payload,
    )


def _binding_specification_payload(
    binding: MultirotorStudyBinding,
) -> Mapping[str, Mapping[str, Mapping[str, Any]]]:
    try:
        spec = binding.study_payload["study_specification"]
        operating = spec["operating_conditions"]
        targets = spec["target_requirements"]
    except KeyError as exc:
        raise InvalidScientificProblem("malformed MVR1 study identity payload") from exc
    if spec.get("schema") != MULTIROTOR_STUDY_SCHEMA:
        raise InvalidScientificProblem("malformed MVR1 study specification schema")
    if spec.get("schema_version") != MULTIROTOR_STUDY_VERSION:
        raise InvalidScientificProblem("malformed MVR1 study specification version")
    if not isinstance(operating, Mapping) or not isinstance(targets, Mapping):
        raise InvalidScientificProblem("malformed MVR1 study specification payload")
    return {
        "operating_conditions": operating,
        "target_requirements": targets,
    }


def _specification_from_binding(
    binding: MultirotorStudyBinding,
) -> MultirotorStudySpecification:
    spec = _binding_specification_payload(binding)
    operating = spec["operating_conditions"]
    targets = spec["target_requirements"]
    return MultirotorStudySpecification(
        payload_mass=_quantity_from_payload(
            operating["payload_mass"], context="payload_mass"
        ),
        minimum_hover_endurance=_quantity_from_payload(
            targets["minimum_hover_endurance"], context="minimum_hover_endurance"
        ),
        maximum_takeoff_mass=_quantity_from_payload(
            targets["maximum_takeoff_mass"], context="maximum_takeoff_mass"
        ),
        maximum_disk_loading=_quantity_from_payload(
            targets["maximum_disk_loading"], context="maximum_disk_loading"
        ),
    )


def _require_study_identity_marker(
    source: Mapping[str, Any],
    expected_study_identity: str,
    *,
    context: str,
) -> None:
    if source.get("study_identity") != expected_study_identity:
        raise InvalidScientificProblem(f"MVR1 {context} study identity marker mismatch")


def _require_expected_bound_ids(
    evaluation: DesignEvaluation,
    expected_study_identity: str,
) -> None:
    candidate_id = evaluation.candidate.candidate_id
    if evaluation.evaluation_id != _study_bound_evaluation_id(
        candidate_id, expected_study_identity
    ):
        raise InvalidScientificProblem("MVR1 evaluation_id study binding mismatch")
    if evaluation.result.result_id != _study_bound_result_id(
        candidate_id, expected_study_identity
    ):
        raise InvalidScientificProblem("MVR1 result_id study binding mismatch")
    if evaluation.result.provenance.run_id != _study_bound_run_id(
        candidate_id, expected_study_identity
    ):
        raise InvalidScientificProblem("MVR1 provenance run_id study binding mismatch")


def _require_binding_consistency(
    evaluation: DesignEvaluation,
    expected_study_identity: str,
) -> MultirotorStudyBinding:
    raw_sources = (
        ("evaluation metadata", evaluation.metadata),
        ("result metadata", evaluation.result.metadata),
        ("provenance metadata", evaluation.result.provenance.metadata),
    )
    bindings: list[MultirotorStudyBinding] = []
    canonical_raw: str | None = None
    for source_name, source in raw_sources:
        _require_study_identity_marker(
            source, expected_study_identity, context=source_name
        )
        raw = source.get(MULTIROTOR_STUDY_BINDING_METADATA_KEY)
        if not isinstance(raw, Mapping):
            raise InvalidScientificProblem(f"MVR1 {source_name} is missing study binding")
        binding = MultirotorStudyBinding.from_dict(raw)
        if binding.study_identity != expected_study_identity:
            raise InvalidScientificProblem(f"MVR1 {source_name} study binding mismatch")
        raw_json = _canonical_json(binding.to_dict())
        if canonical_raw is None:
            canonical_raw = raw_json
        elif raw_json != canonical_raw:
            raise InvalidScientificProblem(
                f"MVR1 {source_name} study binding payload mismatch"
            )
        bindings.append(binding)
    return bindings[0]


def _require_provenance_inputs_match_binding(
    evaluation: DesignEvaluation,
    binding: MultirotorStudyBinding,
) -> None:
    spec = _binding_specification_payload(binding)
    provenance_inputs = evaluation.result.provenance.inputs
    required = (
        (
            "payload_mass",
            "kg",
            spec["operating_conditions"],
        ),
        (
            "minimum_hover_endurance",
            "s",
            spec["target_requirements"],
        ),
        (
            "maximum_takeoff_mass",
            "kg",
            spec["target_requirements"],
        ),
        (
            "maximum_disk_loading",
            "N/m^2",
            spec["target_requirements"],
        ),
    )
    for name, unit, source in required:
        if name not in source:
            raise InvalidScientificProblem(
                f"MVR1 study binding is missing {name}"
            )
        if name not in provenance_inputs:
            raise InvalidScientificProblem(
                f"MVR1 provenance inputs are missing {name}"
            )
        expected = _quantity_from_payload(source[name], context=name)
        _require_quantity_equal(
            provenance_inputs[name],
            expected,
            unit,
            context=f"provenance input {name}",
        )


def _require_target_margins_match_binding(
    evaluation: DesignEvaluation,
    binding: MultirotorStudyBinding,
) -> None:
    spec = _binding_specification_payload(binding)
    targets = spec["target_requirements"]
    maximum_takeoff_mass = _quantity_from_payload(
        targets["maximum_takeoff_mass"], context="maximum_takeoff_mass"
    )
    minimum_hover_endurance = _quantity_from_payload(
        targets["minimum_hover_endurance"], context="minimum_hover_endurance"
    )
    maximum_disk_loading = _quantity_from_payload(
        targets["maximum_disk_loading"], context="maximum_disk_loading"
    )
    result = evaluation.result
    _require_quantity_equal(
        result.value("mass_margin"),
        maximum_takeoff_mass - result.value("total_mass"),
        "kg",
        context="mass_margin",
    )
    _require_quantity_equal(
        result.value("endurance_margin"),
        result.value("hover_endurance") - minimum_hover_endurance,
        "s",
        context="endurance_margin",
    )
    _require_quantity_equal(
        result.value("disk_loading_margin"),
        maximum_disk_loading - result.value("disk_loading"),
        "N/m^2",
        context="disk_loading_margin",
    )


def _require_assessment_matches_evaluation(
    assessment: "MultirotorStudyTargetAssessment",
    evaluation: DesignEvaluation,
) -> None:
    _require_quantity_equal(
        assessment.mass_margin,
        evaluation.result.value("mass_margin"),
        "kg",
        context="target assessment mass_margin",
    )
    _require_quantity_equal(
        assessment.endurance_margin,
        evaluation.result.value("endurance_margin"),
        "s",
        context="target assessment endurance_margin",
    )
    _require_quantity_equal(
        assessment.disk_loading_margin,
        evaluation.result.value("disk_loading_margin"),
        "N/m^2",
        context="target assessment disk_loading_margin",
    )


def require_study_binding(
    evaluation: DesignEvaluation,
    expected_study_identity: str,
) -> MultirotorStudyBinding:
    if not isinstance(evaluation, DesignEvaluation):
        raise InvalidScientificProblem(
            "MVR1 study binding validation requires DesignEvaluation"
        )
    expected = str(expected_study_identity).strip()
    if not expected:
        raise InvalidScientificProblem("expected MVR1 study identity is required")
    _study_digest_prefix(expected)
    _require_expected_bound_ids(evaluation, expected)
    binding = _require_binding_consistency(evaluation, expected)
    _require_provenance_inputs_match_binding(evaluation, binding)
    _require_target_margins_match_binding(evaluation, binding)
    return binding


def require_study_physical_consistency(
    evaluation: DesignEvaluation,
    expected_study_identity: str,
    *,
    candidate: DesignCandidate,
    twin: ScientificTwin,
    design_space: DesignSpace,
) -> MultirotorStudyBinding:
    """Require MVR1 attribution to match recomputed frozen-reference physics."""

    binding = require_study_binding(evaluation, expected_study_identity)
    if not isinstance(candidate, DesignCandidate):
        raise InvalidScientificProblem(
            "MVR1 physical validation requires DesignCandidate"
        )
    if not isinstance(twin, ScientificTwin):
        raise InvalidScientificProblem("MVR1 physical validation requires ScientificTwin")
    if not isinstance(design_space, DesignSpace):
        raise InvalidScientificProblem("MVR1 physical validation requires DesignSpace")
    candidate.validate_against(design_space)
    evaluation.validate_candidate(candidate)
    if twin.reference.key != evaluation.twin.key:
        raise InvalidScientificProblem("MVR1 physical validation Twin mismatch")

    specification = _specification_from_binding(binding)
    expected_evaluation, _expected_assessment = evaluate_reference_candidate(
        candidate=candidate,
        twin=twin,
        design_space=design_space,
        target=specification.to_reference_target(),
    )
    for metric, unit in MVR1_PHYSICAL_OUTPUT_UNITS.items():
        submitted = evaluation.result.value(metric).magnitude_in(unit)
        expected = expected_evaluation.result.value(metric).magnitude_in(unit)
        if not math.isclose(submitted, expected, rel_tol=0.0, abs_tol=1e-12):
            raise InvalidScientificProblem(
                f"MVR1 physical output {metric} mismatch"
            )
    _require_target_margins_match_binding(evaluation, binding)
    return binding


@dataclass(frozen=True)
class MultirotorStudyTargetAssessment:
    candidate_id: str
    study_identity: str
    reference_target_pass: bool
    mass_margin: Quantity
    endurance_margin: Quantity
    disk_loading_margin: Quantity
    failed_requirements: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        candidate_id = str(self.candidate_id).strip()
        study_id = str(self.study_identity).strip()
        if not candidate_id:
            raise InvalidScientificProblem("MVR1 target assessment requires candidate_id")
        if not study_id.startswith(MULTIROTOR_STUDY_ID_PREFIX):
            raise InvalidScientificProblem("MVR1 target assessment requires study identity")
        margins = {
            "mass_margin": self.mass_margin.to("kg"),
            "endurance_margin": self.endurance_margin.to("s"),
            "disk_loading_margin": self.disk_loading_margin.to("N/m^2"),
        }
        failures = tuple(str(item).strip() for item in self.failed_requirements)
        if any(not item for item in failures):
            raise InvalidScientificProblem("MVR1 target failures must be non-empty")
        expected_pass = all(value.magnitude >= 0.0 for value in margins.values())
        if bool(self.reference_target_pass) is not expected_pass:
            raise InvalidScientificProblem("MVR1 target pass does not match margins")
        if expected_pass and failures:
            raise InvalidScientificProblem("passing MVR1 target cannot list failures")
        if not expected_pass and not failures:
            raise InvalidScientificProblem("failing MVR1 target requires reasons")
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "study_identity", study_id)
        object.__setattr__(self, "reference_target_pass", expected_pass)
        object.__setattr__(self, "mass_margin", margins["mass_margin"])
        object.__setattr__(self, "endurance_margin", margins["endurance_margin"])
        object.__setattr__(self, "disk_loading_margin", margins["disk_loading_margin"])
        object.__setattr__(self, "failed_requirements", failures)


@dataclass(frozen=True)
class MultirotorStudyEvaluation:
    evaluation: DesignEvaluation
    assessment: MultirotorStudyTargetAssessment
    study_identity: str

    def __post_init__(self) -> None:
        if not isinstance(self.evaluation, DesignEvaluation):
            raise InvalidScientificProblem(
                "MVR1 study evaluation requires DesignEvaluation"
            )
        if not isinstance(self.assessment, MultirotorStudyTargetAssessment):
            raise InvalidScientificProblem(
                "MVR1 study evaluation requires target assessment"
            )
        if self.assessment.candidate_id != self.evaluation.candidate.candidate_id:
            raise InvalidScientificProblem("MVR1 assessment/evaluation candidate mismatch")
        if self.assessment.study_identity != self.study_identity:
            raise InvalidScientificProblem("MVR1 assessment/evaluation study mismatch")
        require_study_binding(self.evaluation, self.study_identity)
        _require_assessment_matches_evaluation(self.assessment, self.evaluation)


def _study_bound_result(
    *,
    base: ScientificResult,
    candidate_id: str,
    binding: MultirotorStudyBinding,
    source_revision: str,
) -> ScientificResult:
    provenance_metadata = dict(base.provenance.metadata)
    provenance_metadata[MULTIROTOR_STUDY_BINDING_METADATA_KEY] = binding.to_dict()
    provenance_metadata["study_identity"] = binding.study_identity
    provenance = ProvenanceRecord(
        run_id=_study_bound_run_id(candidate_id, binding.study_identity),
        software_version="mvr1-v0.1",
        git_commit=str(source_revision).strip() or base.provenance.git_commit,
        models=base.provenance.models,
        solvers=base.provenance.solvers,
        # Carried like models and solvers. This record is a re-binding of the
        # same computation to a study, not a different computation.
        bindings=base.provenance.bindings,
        inputs=base.provenance.inputs,
        assumptions=base.provenance.assumptions,
        tolerances=base.provenance.tolerances,
        environment=base.provenance.environment,
        timestamp=None,
        parent_run_id=base.provenance.run_id,
        metadata=provenance_metadata,
    )
    metadata = dict(base.metadata)
    metadata[MULTIROTOR_STUDY_BINDING_METADATA_KEY] = binding.to_dict()
    metadata["study_identity"] = binding.study_identity
    return replace(
        base,
        result_id=_study_bound_result_id(candidate_id, binding.study_identity),
        problem_id="mvr1-study-bound-reference-hover",
        provenance=provenance,
        metadata=metadata,
        warnings=(
            "MVR1 is a reference analytic benchmark under a typed study specification; it is not physical validation, certification or a flight-readiness claim",
        ),
    )


def evaluate_study_candidate(
    *,
    candidate: DesignCandidate,
    twin: ScientificTwin,
    design_space: Any,
    specification: MultirotorStudySpecification,
    count: int = MVR1_DEFAULT_COUNT,
    attempt_budget: int = MVR1_DEFAULT_ATTEMPT_BUDGET,
    source_revision: str = "",
) -> MultirotorStudyEvaluation:
    binding = _binding_for(specification, count=count, attempt_budget=attempt_budget)
    base_evaluation, _base_assessment = evaluate_reference_candidate(
        candidate=candidate,
        twin=twin,
        design_space=design_space,
        target=specification.to_reference_target(),
        source_revision=source_revision,
    )
    result = _study_bound_result(
        base=base_evaluation.result,
        candidate_id=candidate.candidate_id,
        binding=binding,
        source_revision=source_revision,
    )
    metadata = dict(base_evaluation.metadata)
    metadata[MULTIROTOR_STUDY_BINDING_METADATA_KEY] = binding.to_dict()
    metadata["study_identity"] = binding.study_identity
    evaluation = DesignEvaluation(
        evaluation_id=_study_bound_evaluation_id(
            candidate.candidate_id, binding.study_identity
        ),
        candidate=base_evaluation.candidate,
        twin=base_evaluation.twin,
        design_space=base_evaluation.design_space,
        result=result,
        fidelity=base_evaluation.fidelity,
        eligibility=SelectionEligibility.ELIGIBLE,
        eligibility_reasons=base_evaluation.eligibility_reasons,
        metadata=metadata,
    ).validate_candidate(candidate)

    failed: list[str] = []
    if result.value("mass_margin").magnitude_in("kg") < 0.0:
        failed.append("maximum_takeoff_mass")
    if result.value("endurance_margin").magnitude_in("s") < 0.0:
        failed.append("minimum_hover_endurance")
    if result.value("disk_loading_margin").magnitude_in("N/m^2") < 0.0:
        failed.append("maximum_disk_loading")
    assessment = MultirotorStudyTargetAssessment(
        candidate_id=candidate.candidate_id,
        study_identity=binding.study_identity,
        reference_target_pass=not failed,
        mass_margin=result.value("mass_margin"),
        endurance_margin=result.value("endurance_margin"),
        disk_loading_margin=result.value("disk_loading_margin"),
        failed_requirements=tuple(failed),
    )
    return MultirotorStudyEvaluation(
        evaluation=evaluation,
        assessment=assessment,
        study_identity=binding.study_identity,
    )


@dataclass(frozen=True)
class MultirotorStudyRun:
    specification: MultirotorStudySpecification
    study_identity: str
    design_space: Any
    batch: CandidateGenerationBatch
    evaluations: tuple[DesignEvaluation, ...]
    assessments: tuple[MultirotorStudyTargetAssessment, ...]
    pareto: ParetoArchive
    scoped_archives: tuple[ScopedEliteArchive, ...]
    runtime_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.study_identity != study_identity(
            self.specification,
            count=self.batch.plan.count,
            attempt_budget=self.batch.plan.attempt_budget,
        ):
            raise InvalidScientificProblem("MVR1 run study identity mismatch")
        if len(self.evaluations) != len(self.batch.candidates):
            raise InvalidScientificProblem("MVR1 run evaluation count mismatch")
        if len(self.assessments) != len(self.batch.candidates):
            raise InvalidScientificProblem("MVR1 run assessment count mismatch")
        candidate_ids = {item.candidate_id for item in self.batch.candidates}
        if {item.candidate.candidate_id for item in self.evaluations} != candidate_ids:
            raise InvalidScientificProblem("MVR1 run evaluation identities mismatch")
        if {item.candidate_id for item in self.assessments} != candidate_ids:
            raise InvalidScientificProblem("MVR1 run assessment identities mismatch")
        candidates_by_id = {
            item.candidate_id: item for item in self.batch.candidates
        }
        twins_by_key = {item.reference.key: item for item in self.batch.twins}
        for evaluation in self.evaluations:
            try:
                candidate = candidates_by_id[evaluation.candidate.candidate_id]
                twin = twins_by_key[evaluation.twin.key]
            except KeyError as exc:
                raise InvalidScientificProblem(
                    "MVR1 run is missing concrete candidate/Twin for evaluation"
                ) from exc
            require_study_physical_consistency(
                evaluation,
                self.study_identity,
                candidate=candidate,
                twin=twin,
                design_space=self.design_space,
            )
            if evaluation.eligibility is not SelectionEligibility.ELIGIBLE:
                raise InvalidScientificProblem(
                    "MVR1 successful evaluations must remain D1 eligible"
                )
        for assessment in self.assessments:
            if assessment.study_identity != self.study_identity:
                raise InvalidScientificProblem("MVR1 assessment study identity mismatch")
        self.pareto.validate_against(self.evaluations)
        for archive in self.scoped_archives:
            archive.validate_against(self.evaluations)
        object.__setattr__(self, "runtime_metadata", MappingProxyType(dict(self.runtime_metadata)))

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
            values = [
                evaluation.result.value(metric).magnitude_in(unit)
                for evaluation in self.evaluations
            ]
            metrics[metric] = (min(values), max(values))
        return {
            "study_specification": self.specification.to_dict(),
            "study_identity": self.study_identity,
            "generated_candidates": len(self.batch.candidates),
            "rejected_proposals": len(self.batch.rejected),
            "rotor_count_counts": dict(sorted(rotor_counts.items())),
            "reference_target_pass_count": sum(
                assessment.reference_target_pass for assessment in self.assessments
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
            "runtime_metadata": dict(self.runtime_metadata),
        }


def generate_mvr1_candidate_universe(
    *,
    count: int = MVR1_DEFAULT_COUNT,
    attempt_budget: int = MVR1_DEFAULT_ATTEMPT_BUDGET,
) -> tuple[Any, CandidateGenerationBatch]:
    design_space = build_reference_design_space()
    plan = CandidateGenerationPlan(
        population_id=MVR1_POPULATION_ID,
        design_space=design_space.reference,
        count=count,
        generation=MVR1_GENERATION,
        sequence_start=MVR1_SEQUENCE_START,
        attempt_budget=attempt_budget,
        strategy=GenerationStrategy.HALTON_V1,
        candidate_prefix=MVR1_CANDIDATE_PREFIX,
    )
    batch = generate_initial_population(
        design_space=design_space,
        plan=plan,
        materializer=MultirotorTwinMaterializer(),
        gate=MultirotorProposalGate(),
    )
    return design_space, batch


def run_multirotor_study(
    specification: MultirotorStudySpecification,
    *,
    count: int = MVR1_DEFAULT_COUNT,
    attempt_budget: int = MVR1_DEFAULT_ATTEMPT_BUDGET,
    source_revision: str = "",
) -> MultirotorStudyRun:
    if not isinstance(specification, MultirotorStudySpecification):
        raise InvalidScientificProblem(
            "MVR1 run requires MultirotorStudySpecification"
        )
    start = time.perf_counter()
    design_space, batch = generate_mvr1_candidate_universe(
        count=count,
        attempt_budget=attempt_budget,
    )
    study_id = study_identity(
        specification, count=count, attempt_budget=attempt_budget
    )
    twins_by_key = {twin.reference.key: twin for twin in batch.twins}
    study_evaluations: list[MultirotorStudyEvaluation] = []
    for candidate in batch.candidates:
        study_evaluations.append(
            evaluate_study_candidate(
                candidate=candidate,
                twin=twins_by_key[candidate.twin.key],
                design_space=design_space,
                specification=specification,
                count=count,
                attempt_budget=attempt_budget,
                source_revision=source_revision,
            )
        )

    evaluations = tuple(item.evaluation for item in study_evaluations)
    assessments = tuple(item.assessment for item in study_evaluations)
    objectives = global_objectives()
    pareto = ParetoArchive.build(
        archive_id=f"mvr1-global-pareto:{study_id.removeprefix(MULTIROTOR_STUDY_ID_PREFIX)[:16]}",
        design_space=design_space.reference,
        objectives=objectives,
        evaluations=evaluations,
    )
    scoped = (
        ScopedEliteArchive.build(
            archive_id=f"mvr1-elite-mass:{study_id.removeprefix(MULTIROTOR_STUDY_ID_PREFIX)[:16]}",
            scope_ref="multirotor:mass",
            design_space=design_space.reference,
            objectives=(objectives[0],),
            evaluations=evaluations,
        ),
        ScopedEliteArchive.build(
            archive_id=f"mvr1-elite-endurance:{study_id.removeprefix(MULTIROTOR_STUDY_ID_PREFIX)[:16]}",
            scope_ref="multirotor:endurance",
            design_space=design_space.reference,
            objectives=(objectives[1],),
            evaluations=evaluations,
        ),
        ScopedEliteArchive.build(
            archive_id=f"mvr1-elite-hover-power:{study_id.removeprefix(MULTIROTOR_STUDY_ID_PREFIX)[:16]}",
            scope_ref="multirotor:hover-power",
            design_space=design_space.reference,
            objectives=(objectives[2],),
            evaluations=evaluations,
        ),
    )
    return MultirotorStudyRun(
        specification=specification,
        study_identity=study_id,
        design_space=design_space,
        batch=batch,
        evaluations=evaluations,
        assessments=assessments,
        pareto=pareto,
        scoped_archives=scoped,
        runtime_metadata={
            "runtime_seconds": time.perf_counter() - start,
            "runtime_is_not_part_of_study_identity": True,
        },
    )


def study_a_specification() -> MultirotorStudySpecification:
    return MultirotorStudySpecification(
        payload_mass=Quantity(0.50, "kg"),
        minimum_hover_endurance=Quantity(900.0, "s"),
        maximum_takeoff_mass=Quantity(3.00, "kg"),
        maximum_disk_loading=Quantity(120.0, "N/m^2"),
    )


def study_b_specification() -> MultirotorStudySpecification:
    return MultirotorStudySpecification(
        payload_mass=Quantity(1.00, "kg"),
        minimum_hover_endurance=Quantity(1500.0, "s"),
        maximum_takeoff_mass=Quantity(4.00, "kg"),
        maximum_disk_loading=Quantity(120.0, "N/m^2"),
    )


__all__ = [
    "MULTIROTOR_STUDY_BINDING_METADATA_KEY",
    "MULTIROTOR_STUDY_ID_PREFIX",
    "MultirotorStudyBinding",
    "MultirotorStudyEvaluation",
    "MultirotorStudyRun",
    "MultirotorStudySpecification",
    "MultirotorStudyTargetAssessment",
    "evaluate_study_candidate",
    "generate_mvr1_candidate_universe",
    "require_study_binding",
    "require_study_physical_consistency",
    "run_multirotor_study",
    "study_a_specification",
    "study_b_specification",
    "study_identity",
    "study_identity_payload",
]
