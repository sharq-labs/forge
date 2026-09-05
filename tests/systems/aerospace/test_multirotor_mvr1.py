from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import os
import subprocess
import sys
from pathlib import Path

import pytest

from engcore.design import SelectionEligibility
from engcore.scientific.errors import ScientificCoreError
from engcore.scientific.units.quantity import Quantity
from engcore.systems.aerospace.multirotor.study import (
    MULTIROTOR_STUDY_BINDING_METADATA_KEY,
    MULTIROTOR_STUDY_ID_PREFIX,
    MultirotorStudyBinding,
    MultirotorStudyEvaluation,
    MultirotorStudySpecification,
    evaluate_study_candidate,
    generate_mvr1_candidate_universe,
    require_study_binding,
    require_study_physical_consistency,
    run_multirotor_study,
    study_a_specification,
    study_b_specification,
    study_identity,
    study_identity_payload,
)


EXPECTED_STUDY_A_ID = (
    "multirotor-study-v0.1:sha256:"
    "591616a4da0649b0894fa816c2dbe1d3741dd8ee3f02b73330d3a607a3e92279"
)
EXPECTED_STUDY_B_ID = (
    "multirotor-study-v0.1:sha256:"
    "11493992e8da46864897d570759b91b181b748902da7a6773cd6a2be1f69c2e7"
)


def _small_study_pair() -> tuple[MultirotorStudyEvaluation, MultirotorStudyEvaluation]:
    design_space, batch = generate_mvr1_candidate_universe(count=4, attempt_budget=20)
    candidate = batch.candidates[0]
    twin = {item.reference.key: item for item in batch.twins}[candidate.twin.key]
    return (
        evaluate_study_candidate(
            candidate=candidate,
            twin=twin,
            design_space=design_space,
            specification=study_a_specification(),
            count=4,
            attempt_budget=20,
        ),
        evaluate_study_candidate(
            candidate=candidate,
            twin=twin,
            design_space=design_space,
            specification=study_b_specification(),
            count=4,
            attempt_budget=20,
        ),
    )


def _digest_prefix(study_id: str) -> str:
    return study_id.removeprefix(MULTIROTOR_STUDY_ID_PREFIX)[:16]


def _with_all_binding_metadata(evaluation, binding_payload):
    metadata = dict(evaluation.metadata)
    result_metadata = dict(evaluation.result.metadata)
    provenance_metadata = dict(evaluation.result.provenance.metadata)
    for target in (metadata, result_metadata, provenance_metadata):
        target[MULTIROTOR_STUDY_BINDING_METADATA_KEY] = deepcopy(binding_payload)
        target["study_identity"] = binding_payload["study_identity"]
    provenance = replace(evaluation.result.provenance, metadata=provenance_metadata)
    result = replace(evaluation.result, metadata=result_metadata, provenance=provenance)
    return replace(evaluation, metadata=metadata, result=result)


def _with_mvr1_ids(evaluation, study_id: str):
    candidate_id = evaluation.candidate.candidate_id
    digest = _digest_prefix(study_id)
    provenance = replace(
        evaluation.result.provenance,
        run_id=f"mvr1:{study_id}:{candidate_id}",
    )
    result = replace(
        evaluation.result,
        result_id=f"mvr1-result:{candidate_id}:{digest}",
        provenance=provenance,
    )
    return replace(
        evaluation,
        evaluation_id=f"mvr1-eval:{candidate_id}:{digest}",
        result=result,
    )


def _binding_for_spec(
    specification: MultirotorStudySpecification,
    *,
    count: int = 4,
    attempt_budget: int = 20,
) -> dict:
    payload = study_identity_payload(
        specification, count=count, attempt_budget=attempt_budget
    )
    return MultirotorStudyBinding(
        study_identity=study_identity(
            specification, count=count, attempt_budget=attempt_budget
        ),
        study_payload=payload,
    ).to_dict()


def test_study_specification_is_unit_safe_and_semantically_separated() -> None:
    spec = MultirotorStudySpecification(
        payload_mass=Quantity(500.0, "g"),
        minimum_hover_endurance=Quantity(25.0, "min"),
        maximum_takeoff_mass=Quantity(3000.0, "g"),
        maximum_disk_loading=Quantity(0.12, "kN/m^2"),
    )

    assert spec.payload_mass.magnitude_in("kg") == pytest.approx(0.5)
    assert spec.minimum_hover_endurance.magnitude_in("s") == pytest.approx(1500.0)
    assert spec.maximum_takeoff_mass.magnitude_in("kg") == pytest.approx(3.0)
    assert spec.maximum_disk_loading.magnitude_in("N/m^2") == pytest.approx(120.0)
    assert set(spec.operating_conditions) == {"payload_mass"}
    assert set(spec.target_requirements) == {
        "minimum_hover_endurance",
        "maximum_takeoff_mass",
        "maximum_disk_loading",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("payload_mass", Quantity(0.0, "kg")),
        ("minimum_hover_endurance", Quantity(-1.0, "s")),
        ("maximum_takeoff_mass", Quantity(0.0, "kg")),
        ("maximum_disk_loading", Quantity(-2.0, "N/m^2")),
        ("payload_mass", Quantity(1.0, "s")),
    ),
)
def test_study_specification_fails_closed_for_invalid_inputs(
    field: str, value: Quantity
) -> None:
    kwargs = {
        "payload_mass": Quantity(0.5, "kg"),
        "minimum_hover_endurance": Quantity(900.0, "s"),
        "maximum_takeoff_mass": Quantity(3.0, "kg"),
        "maximum_disk_loading": Quantity(120.0, "N/m^2"),
    }
    kwargs[field] = value
    with pytest.raises(ScientificCoreError):
        MultirotorStudySpecification(**kwargs)

    kwargs[field] = 1.0
    with pytest.raises(ScientificCoreError):
        MultirotorStudySpecification(**kwargs)


def test_study_identity_is_deterministic_unit_normalized_and_field_sensitive() -> None:
    canonical = MultirotorStudySpecification(
        payload_mass=Quantity(0.5, "kg"),
        minimum_hover_endurance=Quantity(1500.0, "s"),
        maximum_takeoff_mass=Quantity(3.0, "kg"),
        maximum_disk_loading=Quantity(120.0, "N/m^2"),
    )
    equivalent = MultirotorStudySpecification(
        payload_mass=Quantity(500.0, "g"),
        minimum_hover_endurance=Quantity(25.0, "min"),
        maximum_takeoff_mass=Quantity(3000.0, "g"),
        maximum_disk_loading=Quantity(0.12, "kN/m^2"),
    )
    changed = MultirotorStudySpecification(
        payload_mass=Quantity(1.0, "kg"),
        minimum_hover_endurance=Quantity(1500.0, "s"),
        maximum_takeoff_mass=Quantity(3.0, "kg"),
        maximum_disk_loading=Quantity(120.0, "N/m^2"),
    )

    assert study_identity(canonical) == study_identity(equivalent)
    assert study_identity(canonical) == study_identity(canonical)
    assert study_identity(canonical) != study_identity(changed)
    assert study_identity(study_a_specification()) != study_identity(study_b_specification())
    assert study_identity(study_a_specification()) == EXPECTED_STUDY_A_ID
    assert study_identity(study_b_specification()) == EXPECTED_STUDY_B_ID


def test_ordinary_study_a_and_b_bindings_validate() -> None:
    design_space, batch = generate_mvr1_candidate_universe(count=4, attempt_budget=20)
    candidate = batch.candidates[0]
    twin = {item.reference.key: item for item in batch.twins}[candidate.twin.key]
    eval_a = evaluate_study_candidate(
        candidate=candidate,
        twin=twin,
        design_space=design_space,
        specification=study_a_specification(),
        count=4,
        attempt_budget=20,
    )
    eval_b = evaluate_study_candidate(
        candidate=candidate,
        twin=twin,
        design_space=design_space,
        specification=study_b_specification(),
        count=4,
        attempt_budget=20,
    )

    assert require_study_binding(eval_a.evaluation, eval_a.study_identity).study_identity == (
        eval_a.study_identity
    )
    assert require_study_binding(eval_b.evaluation, eval_b.study_identity).study_identity == (
        eval_b.study_identity
    )
    assert (
        require_study_physical_consistency(
            eval_a.evaluation,
            eval_a.study_identity,
            candidate=candidate,
            twin=twin,
            design_space=design_space,
        ).study_identity
        == eval_a.study_identity
    )
    assert (
        require_study_physical_consistency(
            eval_b.evaluation,
            eval_b.study_identity,
            candidate=candidate,
            twin=twin,
            design_space=design_space,
        ).study_identity
        == eval_b.study_identity
    )


def test_cross_study_validation_and_coherent_rebind_fail_closed() -> None:
    eval_a, eval_b = _small_study_pair()

    with pytest.raises(ScientificCoreError):
        require_study_binding(eval_a.evaluation, eval_b.study_identity)

    forged = _with_all_binding_metadata(
        eval_a.evaluation,
        eval_b.evaluation.metadata[MULTIROTOR_STUDY_BINDING_METADATA_KEY],
    )
    with pytest.raises(ScientificCoreError):
        require_study_binding(forged, eval_b.study_identity)


@pytest.mark.parametrize(
    "mutator",
    (
        lambda evaluation: replace(evaluation, evaluation_id="mvr1-eval:forged"),
        lambda evaluation: replace(
            evaluation,
            result=replace(evaluation.result, result_id="mvr1-result:forged"),
        ),
        lambda evaluation: replace(
            evaluation,
            result=replace(
                evaluation.result,
                provenance=replace(
                    evaluation.result.provenance,
                    run_id="mvr1:forged",
                ),
            ),
        ),
    ),
)
def test_forged_bound_identifiers_fail_closed(mutator) -> None:
    eval_a, _eval_b = _small_study_pair()

    with pytest.raises(ScientificCoreError):
        require_study_binding(mutator(eval_a.evaluation), eval_a.study_identity)


def test_missing_binding_location_and_mismatching_study_marker_fail_closed() -> None:
    eval_a, _eval_b = _small_study_pair()

    result_metadata = dict(eval_a.evaluation.result.metadata)
    result_metadata.pop(MULTIROTOR_STUDY_BINDING_METADATA_KEY)
    missing_result = replace(
        eval_a.evaluation,
        result=replace(eval_a.evaluation.result, metadata=result_metadata),
    )
    with pytest.raises(ScientificCoreError):
        require_study_binding(missing_result, eval_a.study_identity)

    provenance_metadata = dict(eval_a.evaluation.result.provenance.metadata)
    provenance_metadata["study_identity"] = "not-the-bound-study"
    mismatched_marker = replace(
        eval_a.evaluation,
        result=replace(
            eval_a.evaluation.result,
            provenance=replace(
                eval_a.evaluation.result.provenance,
                metadata=provenance_metadata,
            ),
        ),
    )
    with pytest.raises(ScientificCoreError):
        require_study_binding(mismatched_marker, eval_a.study_identity)


def test_study_b_payload_with_study_a_provenance_inputs_fails_closed() -> None:
    eval_a, eval_b = _small_study_pair()
    forged = _with_mvr1_ids(
        _with_all_binding_metadata(
            eval_a.evaluation,
            eval_b.evaluation.metadata[MULTIROTOR_STUDY_BINDING_METADATA_KEY],
        ),
        eval_b.study_identity,
    )

    with pytest.raises(ScientificCoreError):
        require_study_binding(forged, eval_b.study_identity)


def test_altered_target_thresholds_inconsistent_with_provenance_fail_closed() -> None:
    eval_a, _eval_b = _small_study_pair()
    altered_spec = MultirotorStudySpecification(
        payload_mass=Quantity(0.5, "kg"),
        minimum_hover_endurance=Quantity(25.0, "min"),
        maximum_takeoff_mass=Quantity(3.0, "kg"),
        maximum_disk_loading=Quantity(120.0, "N/m^2"),
    )
    altered_binding = _binding_for_spec(altered_spec)
    forged = _with_mvr1_ids(
        _with_all_binding_metadata(eval_a.evaluation, altered_binding),
        altered_binding["study_identity"],
    )

    with pytest.raises(ScientificCoreError):
        require_study_binding(forged, altered_binding["study_identity"])


def test_target_margins_inconsistent_with_bound_target_fail_closed() -> None:
    eval_a, _eval_b = _small_study_pair()
    values = dict(eval_a.evaluation.result.values)
    values["mass_margin"] = Quantity(999.0, "kg")
    forged = replace(
        eval_a.evaluation,
        result=replace(eval_a.evaluation.result, values=values),
    )

    with pytest.raises(ScientificCoreError):
        require_study_binding(forged, eval_a.study_identity)


def test_fully_rebound_study_a_physics_as_study_b_fails_physical_gate() -> None:
    design_space, batch = generate_mvr1_candidate_universe(count=4, attempt_budget=20)
    candidate = batch.candidates[0]
    twin = {item.reference.key: item for item in batch.twins}[candidate.twin.key]
    eval_a = evaluate_study_candidate(
        candidate=candidate,
        twin=twin,
        design_space=design_space,
        specification=study_a_specification(),
        count=4,
        attempt_budget=20,
    )
    eval_b = evaluate_study_candidate(
        candidate=candidate,
        twin=twin,
        design_space=design_space,
        specification=study_b_specification(),
        count=4,
        attempt_budget=20,
    )

    forged = _with_mvr1_ids(
        _with_all_binding_metadata(
            eval_a.evaluation,
            eval_b.evaluation.metadata[MULTIROTOR_STUDY_BINDING_METADATA_KEY],
        ),
        eval_b.study_identity,
    )
    provenance_inputs = dict(forged.result.provenance.inputs)
    for name in (
        "payload_mass",
        "minimum_hover_endurance",
        "maximum_takeoff_mass",
        "maximum_disk_loading",
    ):
        provenance_inputs[name] = eval_b.evaluation.result.provenance.inputs[name]
    provenance = replace(forged.result.provenance, inputs=provenance_inputs)
    forged = replace(forged, result=replace(forged.result, provenance=provenance))

    values = dict(forged.result.values)
    values["mass_margin"] = Quantity(4.0, "kg") - values["total_mass"]
    values["endurance_margin"] = values["hover_endurance"] - Quantity(1500.0, "s")
    values["disk_loading_margin"] = Quantity(120.0, "N/m^2") - values["disk_loading"]
    forged = replace(forged, result=replace(forged.result, values=values))

    require_study_binding(forged, eval_b.study_identity)
    with pytest.raises(ScientificCoreError, match="physical output total_mass mismatch"):
        require_study_physical_consistency(
            forged,
            eval_b.study_identity,
            candidate=candidate,
            twin=twin,
            design_space=design_space,
        )


def test_nested_binding_payload_mutation_fails_closed() -> None:
    eval_a, _eval_b = _small_study_pair()
    raw = eval_a.evaluation.metadata[MULTIROTOR_STUDY_BINDING_METADATA_KEY]
    raw["study_payload"]["study_specification"]["operating_conditions"][
        "payload_mass"
    ]["magnitude"] = 0.75

    with pytest.raises(ScientificCoreError):
        require_study_binding(eval_a.evaluation, eval_a.study_identity)


def test_same_candidate_and_twin_can_be_bound_to_distinct_studies() -> None:
    design_space, batch = generate_mvr1_candidate_universe(count=4, attempt_budget=20)
    candidate = batch.candidates[0]
    twin = {item.reference.key: item for item in batch.twins}[candidate.twin.key]

    eval_a = evaluate_study_candidate(
        candidate=candidate,
        twin=twin,
        design_space=design_space,
        specification=study_a_specification(),
        count=4,
        attempt_budget=20,
    )
    eval_b = evaluate_study_candidate(
        candidate=candidate,
        twin=twin,
        design_space=design_space,
        specification=study_b_specification(),
        count=4,
        attempt_budget=20,
    )

    assert eval_a.evaluation.candidate.candidate_id == eval_b.evaluation.candidate.candidate_id
    assert eval_a.evaluation.twin.key == eval_b.evaluation.twin.key
    assert eval_a.study_identity != eval_b.study_identity
    assert eval_a.evaluation.result.result_id != eval_b.evaluation.result.result_id
    assert (
        eval_a.evaluation.result.value("total_mass").magnitude_in("kg")
        != eval_b.evaluation.result.value("total_mass").magnitude_in("kg")
    )
    require_study_physical_consistency(
        eval_a.evaluation,
        eval_a.study_identity,
        candidate=candidate,
        twin=twin,
        design_space=design_space,
    )
    require_study_physical_consistency(
        eval_b.evaluation,
        eval_b.study_identity,
        candidate=candidate,
        twin=twin,
        design_space=design_space,
    )
    with pytest.raises(ScientificCoreError):
        require_study_binding(eval_a.evaluation, eval_b.study_identity)
    with pytest.raises(ScientificCoreError):
        MultirotorStudyEvaluation(
            evaluation=eval_a.evaluation,
            assessment=eval_a.assessment,
            study_identity=eval_b.study_identity,
        )


def test_payload_changes_physics_but_threshold_only_change_does_not() -> None:
    design_space, batch = generate_mvr1_candidate_universe(count=1, attempt_budget=10)
    candidate = batch.candidates[0]
    twin = batch.twins[0]
    base = MultirotorStudySpecification(
        payload_mass=Quantity(0.5, "kg"),
        minimum_hover_endurance=Quantity(900.0, "s"),
        maximum_takeoff_mass=Quantity(3.0, "kg"),
        maximum_disk_loading=Quantity(120.0, "N/m^2"),
    )
    payload_changed = MultirotorStudySpecification(
        payload_mass=Quantity(1.0, "kg"),
        minimum_hover_endurance=Quantity(900.0, "s"),
        maximum_takeoff_mass=Quantity(3.0, "kg"),
        maximum_disk_loading=Quantity(120.0, "N/m^2"),
    )
    threshold_changed = MultirotorStudySpecification(
        payload_mass=Quantity(0.5, "kg"),
        minimum_hover_endurance=Quantity(100000.0, "s"),
        maximum_takeoff_mass=Quantity(3.0, "kg"),
        maximum_disk_loading=Quantity(120.0, "N/m^2"),
    )

    base_eval = evaluate_study_candidate(
        candidate=candidate,
        twin=twin,
        design_space=design_space,
        specification=base,
        count=1,
        attempt_budget=10,
    ).evaluation
    payload_eval = evaluate_study_candidate(
        candidate=candidate,
        twin=twin,
        design_space=design_space,
        specification=payload_changed,
        count=1,
        attempt_budget=10,
    ).evaluation
    threshold_eval = evaluate_study_candidate(
        candidate=candidate,
        twin=twin,
        design_space=design_space,
        specification=threshold_changed,
        count=1,
        attempt_budget=10,
    ).evaluation

    for metric, unit in (
        ("total_mass", "kg"),
        ("ideal_induced_power", "W"),
        ("hover_electrical_power", "W"),
        ("hover_endurance", "s"),
        ("disk_loading", "N/m^2"),
    ):
        assert base_eval.result.value(metric).magnitude_in(unit) != pytest.approx(
            payload_eval.result.value(metric).magnitude_in(unit)
        )
        assert base_eval.result.value(metric).magnitude_in(unit) == pytest.approx(
            threshold_eval.result.value(metric).magnitude_in(unit)
        )

    assert base_eval.result.value("endurance_margin").magnitude_in("s") != pytest.approx(
        threshold_eval.result.value("endurance_margin").magnitude_in("s")
    )
    assert base_eval.eligibility is SelectionEligibility.ELIGIBLE
    assert threshold_eval.eligibility is SelectionEligibility.ELIGIBLE


def test_full_studies_a_and_b_use_same_universe_and_a_reproduces_mvr0() -> None:
    study_a = run_multirotor_study(study_a_specification())
    study_b = run_multirotor_study(study_b_specification())
    summary_a = study_a.summary()
    summary_b = study_b.summary()

    assert summary_a["generated_candidates"] == 1000
    assert summary_a["rejected_proposals"] == 671
    assert summary_a["reference_target_pass_count"] == 93
    assert summary_a["pareto_member_count"] == 26
    assert summary_a["rotor_count_counts"] == {4: 335, 6: 333, 8: 332}
    assert summary_b["generated_candidates"] == 1000
    assert summary_b["rejected_proposals"] == 671
    assert summary_b["reference_target_pass_count"] == 163
    assert summary_b["pareto_member_count"] == 28
    assert summary_b["rotor_count_counts"] == {4: 335, 6: 333, 8: 332}
    assert study_b.study_identity != study_a.study_identity
    assert [item.candidate_id for item in study_a.batch.candidates] == [
        item.candidate_id for item in study_b.batch.candidates
    ]
    assert [item.twin.key for item in study_a.batch.candidates] == [
        item.twin.key for item in study_b.batch.candidates
    ]
    assert [item.reference.key for item in study_a.batch.twins] == [
        item.reference.key for item in study_b.batch.twins
    ]


def test_deterministic_rerun_for_identical_study() -> None:
    first_b = run_multirotor_study(
        study_b_specification(), count=32, attempt_budget=120
    )
    second_b = run_multirotor_study(
        study_b_specification(), count=32, attempt_budget=120
    )
    left = dict(first_b.summary())
    right = dict(second_b.summary())
    left.pop("runtime_metadata")
    right.pop("runtime_metadata")
    assert left == right


def test_target_failures_remain_eligible_and_pareto_uses_full_universe() -> None:
    spec = MultirotorStudySpecification(
        payload_mass=Quantity(0.5, "kg"),
        minimum_hover_endurance=Quantity(100000.0, "s"),
        maximum_takeoff_mass=Quantity(0.1, "kg"),
        maximum_disk_loading=Quantity(1.0, "N/m^2"),
    )
    run = run_multirotor_study(spec, count=32, attempt_budget=120)

    assert run.summary()["reference_target_pass_count"] == 0
    assert all(item.eligibility is SelectionEligibility.ELIGIBLE for item in run.evaluations)
    assert len(run.pareto.source_evaluations) == len(run.evaluations)
    assert all(
        len(archive.source_evaluations) == len(run.evaluations)
        for archive in run.scoped_archives
    )


def test_no_mvr1_logic_leaks_into_frozen_general_design_layer() -> None:
    root = Path(__file__).resolve().parents[3] / "src" / "engcore" / "design"
    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in root.glob("*.py"))
    assert "multirotor" not in source
    assert "mvr1" not in source
    assert MULTIROTOR_STUDY_BINDING_METADATA_KEY.lower() not in source


def test_cli_exposes_only_study_fields_and_uses_non_validation_language() -> None:
    root = Path(__file__).resolve().parents[3]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{root / 'src'}{os.pathsep}{root}"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "experiments.multirotor_mvr1.run",
            "--help",
        ],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--payload-kg" in completed.stdout
    assert "--min-endurance-min" in completed.stdout
    assert "--max-mass-kg" in completed.stdout
    assert "--max-disk-loading" in completed.stdout
    assert "--count" not in completed.stdout
    assert "--attempt-budget" not in completed.stdout

    lowered = completed.stdout.lower()
    forbidden = (
        "flight ready",
        "safe",
        "certified",
        "physically validated",
        "real-world proven",
        "globally optimal aircraft",
    )
    assert not any(term in lowered for term in forbidden)
