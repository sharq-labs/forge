from __future__ import annotations

from pathlib import Path

import pytest

from engcore.design import SelectionEligibility
from engcore.systems.aerospace.multirotor.rotor_hover import (
    disk_loading,
    ideal_induced_hover_power,
)
from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.solvers.protocol import ConvergenceState
from engcore.scientific.units.quantity import Quantity
from engcore.systems.aerospace.multirotor import (
    MULTIROTOR_CONSTRAINT_REF,
    MultirotorProposalGate,
    MultirotorTargetSpec,
    build_reference_design_space,
    run_reference_study,
)


def test_reusable_rotor_hover_reference_is_unit_aware_and_fails_closed() -> None:
    power = ideal_induced_hover_power(
        thrust=Quantity(20.0, "N"),
        disk_area=Quantity(0.4, "m^2"),
        air_density=Quantity(1.225, "kg/m^3"),
    )
    loading = disk_loading(
        thrust=Quantity(20.0, "N"),
        disk_area=Quantity(0.4, "m^2"),
    )
    assert power.magnitude_in("W") > 0.0
    assert loading.magnitude_in("N/m^2") == pytest.approx(50.0)

    with pytest.raises(InvalidScientificProblem):
        ideal_induced_hover_power(
            thrust=Quantity(0.0, "N"),
            disk_area=Quantity(0.4, "m^2"),
            air_density=Quantity(1.225, "kg/m^3"),
        )
    with pytest.raises(InvalidScientificProblem):
        disk_loading(
            thrust=Quantity(20.0, "N"),
            disk_area=Quantity(0.0, "m^2"),
        )


def test_multirotor_design_space_and_gate_are_system_owned() -> None:
    space = build_reference_design_space()
    assert space.constraint_refs == (MULTIROTOR_CONSTRAINT_REF,)
    assert {variable.name for variable in space.variables} == {
        "rotor_count",
        "rotor_radius",
        "battery_energy",
        "battery_specific_energy_class",
        "frame_class",
        "prop_guards",
    }
    assert MultirotorProposalGate.constraint_refs == (MULTIROTOR_CONSTRAINT_REF,)


def test_small_reference_study_preserves_identity_and_scientific_boundaries() -> None:
    run = run_reference_study(
        count=32,
        attempt_budget=120,
        source_revision="mvr0-test-revision",
    )
    assert len(run.batch.candidates) == 32
    assert len(run.evaluations) == 32
    assert len(run.assessments) == 32
    assert set(run.batch.accepted_sequence_indices)

    twin_keys = {twin.reference.key for twin in run.batch.twins}
    assert len(twin_keys) == 32
    for candidate, evaluation in zip(run.batch.candidates, run.evaluations):
        assert candidate.twin.key in twin_keys
        assert evaluation.candidate.candidate_id == candidate.candidate_id
        assert evaluation.twin.key == candidate.twin.key
        assert evaluation.eligibility is SelectionEligibility.ELIGIBLE
        assert evaluation.result.convergence is ConvergenceState.NOT_APPLICABLE
        assert not evaluation.result.attained_levels
        assert evaluation.result.value("total_mass").magnitude_in("kg") > 0.0
        assert evaluation.result.value("hover_electrical_power").magnitude_in("W") > 0.0
        assert evaluation.result.value("hover_endurance").magnitude_in("s") > 0.0
        evaluation.result_binding

    assessment_by_id = {item.candidate_id: item for item in run.assessments}
    for evaluation in run.evaluations:
        assessment = assessment_by_id[evaluation.candidate.candidate_id]
        margins = (
            evaluation.result.value("mass_margin").magnitude_in("kg"),
            evaluation.result.value("endurance_margin").magnitude_in("s"),
            evaluation.result.value("disk_loading_margin").magnitude_in("N/m^2"),
        )
        assert assessment.meets_target == all(margin >= 0.0 for margin in margins)


def test_reference_target_normalizes_units_without_changing_benchmark_meaning() -> None:
    target = MultirotorTargetSpec(
        payload_mass=Quantity(500.0, "g"),
        minimum_hover_endurance=Quantity(900.0, "s"),
        maximum_takeoff_mass=Quantity(3000.0, "g"),
        maximum_disk_loading=Quantity(0.12, "kN/m^2"),
    )
    assert target.payload_mass.magnitude_in("kg") == pytest.approx(0.5)
    assert target.minimum_hover_endurance.magnitude_in("min") == pytest.approx(15.0)
    assert target.maximum_takeoff_mass.magnitude_in("kg") == pytest.approx(3.0)
    assert target.maximum_disk_loading.magnitude_in("N/m^2") == pytest.approx(120.0)


def test_reference_study_is_deterministic_for_same_declared_inputs() -> None:
    first = run_reference_study(count=48, attempt_budget=180, source_revision="same")
    second = run_reference_study(count=48, attempt_budget=180, source_revision="same")

    assert first.summary() == second.summary()
    assert [item.to_dict() for item in first.batch.proposals] == [
        item.to_dict() for item in second.batch.proposals
    ]
    assert [member.evaluation_id for member in first.pareto.members] == [
        member.evaluation_id for member in second.pareto.members
    ]
    assert [
        (archive.scope_ref, tuple(member.evaluation_id for member in archive.members))
        for archive in first.scoped_archives
    ] == [
        (archive.scope_ref, tuple(member.evaluation_id for member in archive.members))
        for archive in second.scoped_archives
    ]


def test_1000_candidate_vertical_slice_runs_end_to_end() -> None:
    run = run_reference_study(
        count=1000,
        attempt_budget=3000,
        source_revision="mvr0-targeted-test",
    )
    summary = run.summary()

    assert summary["generated_candidates"] == 1000
    assert sum(summary["rotor_count_counts"].values()) == 1000
    assert set(summary["rotor_count_counts"]) <= {4, 6, 8}
    assert 0 <= summary["reference_target_pass_count"] <= 1000
    assert summary["pareto_member_count"] >= 1
    assert set(summary["scoped_member_counts"]) == {
        "multirotor:mass",
        "multirotor:endurance",
        "multirotor:hover-power",
    }
    assert all(count >= 1 for count in summary["scoped_member_counts"].values())
    assert len(run.pareto.source_evaluations) == 1000
    assert all(len(archive.source_evaluations) == 1000 for archive in run.scoped_archives)

    for low, high in summary["metric_ranges"].values():
        assert low > 0.0
        assert high >= low


def test_multirotor_logic_does_not_leak_into_frozen_general_design_layer() -> None:
    root = Path(__file__).resolve().parents[3] / "src" / "engcore" / "design"
    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in root.glob("*.py"))
    assert "multirotor" not in source
    assert "rotor_count" not in source
