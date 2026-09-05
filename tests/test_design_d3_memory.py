from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from engcore.design import (
    AssessmentContext,
    CandidateGenerationPlan,
    CandidateProposal,
    DesignCandidate,
    DesignCandidateReference,
    DesignEvaluation,
    DesignMemoryEntry,
    DesignMemoryLayerA,
    DesignMemoryPolicy,
    DesignMemoryRecord,
    DesignMemoryScope,
    DesignSpace,
    ExplicitRetention,
    ParetoArchive,
    ResultBinding,
    RetentionReason,
    ScopedEliteArchive,
    SelectionEligibility,
    compare_entries,
    generate_initial_population,
    merge_layer_a_records,
    reason_overlaps,
    verify_layer_a_attribution,
)
from engcore.design.evaluation import RESULT_BINDING_METADATA_KEY
from engcore.scientific.errors import InvalidScientificProblem, UnitCompatibilityError
from engcore.scientific.ir.objectives import ObjectiveDefinition, ObjectiveDirection
from engcore.scientific.ir.problem import ModelReference
from engcore.scientific.ir.values import BooleanValue, CategoricalValue, IntegerValue
from engcore.scientific.ir.variables import ScientificVariable, VariableKind, VariableRole
from engcore.scientific.results.provenance import ProvenanceRecord
from engcore.scientific.results.result import ScientificResult
from engcore.scientific.twins.definition import ScientificTwin, TwinDatum, TwinKind
from engcore.scientific.units.quantity import Quantity


GAIN = ObjectiveDefinition(
    name="gain",
    metric="gain",
    direction=ObjectiveDirection.MAXIMIZE,
    unit="dimensionless",
)
LOSS = ObjectiveDefinition(
    name="loss",
    metric="loss",
    direction=ObjectiveDirection.MINIMIZE,
    unit="dimensionless",
)


class _Materializer:
    def materialize(self, proposal: CandidateProposal) -> ScientificTwin:
        return ScientificTwin(
            twin_id=f"twin:{proposal.candidate_id}",
            version="1",
            kind=TwinKind.CANDIDATE,
            models=(ModelReference("d3-synthetic", "1"),),
            declarations=tuple(
                TwinDatum(name=name, value=value)
                for name, value in proposal.assignments.items()
            ),
        )


def _space() -> DesignSpace:
    return DesignSpace(
        space_id="d3-synthetic",
        version="1",
        variables=(
            ScientificVariable(
                name="x",
                unit="dimensionless",
                kind=VariableKind.CONTINUOUS,
                role=VariableRole.DESIGN,
                lower=Quantity(0.0, "dimensionless"),
                upper=Quantity(1.0, "dimensionless"),
            ),
            ScientificVariable(
                name="y",
                unit="dimensionless",
                kind=VariableKind.CONTINUOUS,
                role=VariableRole.DESIGN,
                lower=Quantity(0.0, "dimensionless"),
                upper=Quantity(1.0, "dimensionless"),
            ),
            ScientificVariable(
                name="level",
                unit="dimensionless",
                kind=VariableKind.INTEGER,
                role=VariableRole.DESIGN,
                lower=Quantity(0, "dimensionless"),
                upper=Quantity(3, "dimensionless"),
            ),
            ScientificVariable(
                name="family",
                unit="dimensionless",
                kind=VariableKind.CATEGORICAL,
                role=VariableRole.DESIGN,
                categories=("a", "b"),
            ),
            ScientificVariable(
                name="flag",
                unit="dimensionless",
                kind=VariableKind.BOOLEAN,
                role=VariableRole.DESIGN,
            ),
        ),
    )


def _partitioner(assignments) -> bytes:
    family = assignments["family"].value
    flag = "1" if assignments["flag"].value else "0"
    return f"{family}:{flag}".encode("utf-8")


def _make_evaluation(
    candidate: DesignCandidate,
    gain: float,
    loss: float,
    *,
    suffix: str,
    eligible: bool = True,
) -> DesignEvaluation:
    binding = ResultBinding(
        candidate=candidate.reference,
        twin=candidate.twin,
        design_space=candidate.design_space,
    )
    result = ScientificResult(
        result_id=f"result:{suffix}:{candidate.candidate_id}",
        values={
            "gain": Quantity(gain, "dimensionless"),
            "loss": Quantity(loss, "dimensionless"),
        },
        provenance=ProvenanceRecord(
            run_id=f"run:{suffix}:{candidate.candidate_id}",
            metadata={RESULT_BINDING_METADATA_KEY: binding.to_dict()},
        ),
    )
    eligibility = (
        SelectionEligibility.ELIGIBLE
        if eligible
        else SelectionEligibility.INELIGIBLE
    )
    return DesignEvaluation(
        evaluation_id=f"eval:{suffix}:{candidate.candidate_id}",
        candidate=candidate.reference,
        twin=candidate.twin,
        design_space=candidate.design_space,
        result=result,
        eligibility=eligibility,
        eligibility_reasons=("declared eligible",)
        if eligible
        else ("declared outside evidence set",),
    )


def _batch(count: int = 8, *, context: str = "ctx-a", shift: float = 0.0):
    space = _space()
    batch = generate_initial_population(
        design_space=space,
        plan=CandidateGenerationPlan(
            population_id=f"population:{context}",
            design_space=space.reference,
            count=count,
            attempt_budget=count,
            candidate_prefix=f"cand:{context}",
        ),
        materializer=_Materializer(),
    )
    evaluations = []
    for candidate in batch.candidates:
        x = candidate.assignments["x"].magnitude
        y = candidate.assignments["y"].magnitude
        level = candidate.assignments["level"].value
        flag = 1.0 if candidate.assignments["flag"].value else 0.0
        family = 0.03 if candidate.assignments["family"].value == "b" else 0.0
        gain = 1.0 - (x - 0.72) ** 2 - 0.35 * (y - 0.22) ** 2 + 0.02 * level + 0.01 * flag + shift
        loss = (x - 0.18) ** 2 + 0.55 * (y - 0.78) ** 2 + family + 0.01 * level + shift
        evaluations.append(_make_evaluation(candidate, gain, loss, suffix=context))
    scope = DesignMemoryScope(
        design_space=space.reference,
        objectives=(GAIN, LOSS),
        context_reference=context,
    )
    layer_a = DesignMemoryLayerA.build(
        scope=scope,
        candidates=batch.candidates,
        evaluations=tuple(evaluations),
        partitioner=_partitioner,
    )
    return space, batch.candidates, tuple(evaluations), layer_a


def _policy(layer_a: DesignMemoryLayerA, *, cap: int = 250) -> DesignMemoryPolicy:
    explicit = layer_a.entries[-1]
    return DesignMemoryPolicy(
        policy_id="policy-a",
        elite_scopes=(("gain",), ("loss",)),
        extreme_tolerances={
            "gain": Quantity(0.0, "dimensionless"),
            "loss": Quantity(0.0, "dimensionless"),
        },
        assessment_contexts=(
            AssessmentContext(
                assessment_id="assessment-a",
                thresholds={"gain": Quantity(0.91, "dimensionless")},
                threshold_tolerances={"gain": Quantity(0.0, "dimensionless")},
            ),
        ),
        explicit_retention=(
            ExplicitRetention(
                candidate=explicit.candidate,
                evaluation=explicit.evaluation,
                reason="declared holdout",
            ),
        ),
        cap=cap,
    )


def _manual_layer():
    space = _space()
    candidates = generate_initial_population(
        design_space=space,
        plan=CandidateGenerationPlan(
            population_id="manual-pop",
            design_space=space.reference,
            count=4,
            attempt_budget=4,
            candidate_prefix="manual",
        ),
        materializer=_Materializer(),
    ).candidates
    values = ((10.0, 5.0), (9.0, 4.0), (8.0, 6.0), (7.0, 7.0))
    evaluations = tuple(
        _make_evaluation(candidate, gain, loss, suffix="manual")
        for candidate, (gain, loss) in zip(candidates, values)
    )
    scope = DesignMemoryScope(space.reference, (GAIN, LOSS), "manual-scope")
    layer_a = DesignMemoryLayerA.build(
        scope=scope,
        candidates=candidates,
        evaluations=evaluations,
        partitioner=lambda assignments: b"one-partition",
    )
    return candidates, evaluations, layer_a


def test_all_six_predicates_multiple_reasons_boundaries_and_zero_tolerance() -> None:
    _, _, layer_a = _manual_layer()
    second = layer_a.entries[1]
    policy = DesignMemoryPolicy(
        policy_id="manual-policy",
        elite_scopes=(("gain",), ("loss",)),
        extreme_tolerances={
            "gain": Quantity(0.0, "dimensionless"),
            "loss": Quantity(0.0, "dimensionless"),
        },
        assessment_contexts=(
            AssessmentContext(
                "threshold-exact",
                thresholds={"gain": Quantity(9.0, "dimensionless")},
                threshold_tolerances={"gain": Quantity(0.0, "dimensionless")},
            ),
        ),
        explicit_retention=(
            ExplicitRetention(second.candidate, second.evaluation, "caller reason"),
        ),
        cap=4,
    )
    record = DesignMemoryRecord.build(layer_a=layer_a, policy=policy)
    by_eval = {item.evaluation_id: item for item in record.classification.classifications}
    reasons = by_eval[second.evaluation.evaluation_id].reasons

    assert RetentionReason.PARETO_MEMBER in reasons
    assert RetentionReason.SCOPED_ELITE in reasons
    assert RetentionReason.NEAR_EXTREME in reasons
    assert RetentionReason.NEAR_THRESHOLD in reasons
    assert RetentionReason.EXPLICIT in reasons
    first = by_eval[layer_a.entries[0].evaluation.evaluation_id]
    assert RetentionReason.DIVERSITY_REPRESENTATIVE in first.reasons
    assert by_eval[second.evaluation.evaluation_id].near_threshold_margins[
        "threshold-exact"
    ]["gain"] == 0.0
    assert record.classification.summary["per_reason_census"] == {
        "PARETO_MEMBER": 2,
        "SCOPED_ELITE": 2,
        "NEAR_EXTREME": 2,
        "NEAR_THRESHOLD": 1,
        "DIVERSITY_REPRESENTATIVE": 1,
        "EXPLICIT": 1,
    }
    assert reason_overlaps(record.classification)["PARETO_MEMBER&SCOPED_ELITE"] == 2


def test_tolerance_validation_failures_are_closed() -> None:
    _, _, layer_a = _manual_layer()
    with pytest.raises(InvalidScientificProblem, match=">= 0"):
        DesignMemoryPolicy(
            policy_id="bad-negative",
            extreme_tolerances={"gain": Quantity(-1.0, "dimensionless")},
        )
    with pytest.raises(UnitCompatibilityError):
        Quantity(float("nan"), "dimensionless")
    with pytest.raises((InvalidScientificProblem, UnitCompatibilityError)):
        DesignMemoryRecord.build(
            layer_a=layer_a,
            policy=DesignMemoryPolicy(
                policy_id="bad-units",
                extreme_tolerances={"gain": Quantity(1.0, "m")},
            ),
        )
    with pytest.raises(InvalidScientificProblem):
        AssessmentContext(
            "bad-threshold-maps",
            thresholds={"gain": Quantity(1.0, "dimensionless")},
            threshold_tolerances={},
        )
    with pytest.raises(InvalidScientificProblem):
        DesignMemoryRecord.build(
            layer_a=layer_a,
            policy=DesignMemoryPolicy(
                policy_id="bad-assessment-objective",
                assessment_contexts=(
                    AssessmentContext(
                        "bad",
                        thresholds={"absent": Quantity(1.0, "dimensionless")},
                        threshold_tolerances={
                            "absent": Quantity(0.0, "dimensionless")
                        },
                    ),
                ),
            ),
        )


def test_cap_binding_tier1_overflow_and_identity_ordering() -> None:
    _, _, layer_a = _manual_layer()
    policy = DesignMemoryPolicy(
        policy_id="cap-policy",
        elite_scopes=(("gain",), ("loss",)),
        assessment_contexts=(
            AssessmentContext(
                "wide",
                thresholds={"gain": Quantity(8.5, "dimensionless")},
                threshold_tolerances={"gain": Quantity(100.0, "dimensionless")},
            ),
        ),
        cap=3,
    )
    record = DesignMemoryRecord.build(layer_a=layer_a, policy=policy)
    assert record.classification.summary["with_at_least_one_reason_count"] == 4
    assert record.classification.summary["retained_after_cap_count"] == 3
    assert record.classification.summary["classified_discarded_by_cap_count"] == 1
    assert all(
        item.reasons
        for item in record.classification.classifications
        if item.identity in record.classification.discarded_classified_identities
    )
    with pytest.raises(InvalidScientificProblem, match="tier-1"):
        DesignMemoryRecord.build(
            layer_a=layer_a,
            policy=replace(policy, cap=1),
        )


def test_offer_order_permutation_invariance_and_round_trip_reconstruction() -> None:
    space, candidates, evaluations, layer_a = _batch(32)
    policy = _policy(layer_a)
    baseline = DesignMemoryRecord.build(layer_a=layer_a, policy=policy)
    variants = (
        evaluations,
        tuple(reversed(evaluations)),
        tuple(evaluations[::2] + evaluations[1::2]),
    )
    for offered in variants:
        rebuilt = DesignMemoryLayerA.build(
            scope=layer_a.scope,
            candidates=candidates,
            evaluations=offered,
            partitioner=_partitioner,
        )
        record = DesignMemoryRecord.build(layer_a=rebuilt, policy=policy)
        assert record.to_json() == baseline.to_json()
        assert DesignMemoryRecord.from_dict(json.loads(record.to_json())).to_json() == record.to_json()
        assert record.reconstruct().to_json() == record.to_json()
    assert space.reference.key == layer_a.scope.design_space.key


def test_assessment_change_preserves_layer_a_and_adds_attributable_context() -> None:
    _, _, _, layer_a = _batch(24)
    original = _policy(layer_a)
    record_a = DesignMemoryRecord.build(layer_a=layer_a, policy=original)
    digests = [entry.entry_digest for entry in layer_a.entries]
    extended = DesignMemoryPolicy(
        policy_id="policy-with-second-assessment",
        elite_scopes=original.elite_scopes,
        extreme_tolerances=original.extreme_tolerances,
        assessment_contexts=original.assessment_contexts
        + (
            AssessmentContext(
                "assessment-b",
                thresholds={"loss": Quantity(0.22, "dimensionless")},
                threshold_tolerances={"loss": Quantity(0.03, "dimensionless")},
            ),
        ),
        explicit_retention=original.explicit_retention,
        cap=original.cap,
    )
    record_b = DesignMemoryRecord.build(layer_a=layer_a, policy=extended)

    assert [entry.entry_digest for entry in layer_a.entries] == digests
    assert record_b.layer_a.scope.scope_identity == record_a.layer_a.scope.scope_identity
    assert record_b.layer_a.to_dict() == record_a.layer_a.to_dict()
    for item in record_b.classification.classifications:
        if "assessment-b" in item.near_threshold_margins:
            assert item.near_threshold_margins["assessment-b"]


def test_scope_separation_and_cross_scope_operations_fail_closed() -> None:
    _, candidates_a, evaluations_a, layer_a = _batch(12, context="scope-a")
    _, candidates_b, evaluations_b, layer_b = _batch(
        12, context="scope-b", shift=0.07
    )
    assert layer_a.scope.scope_identity != layer_b.scope.scope_identity
    assert [entry.candidate.candidate_id for entry in layer_a.entries] != [
        entry.candidate.candidate_id for entry in layer_b.entries
    ]
    with pytest.raises(InvalidScientificProblem, match="cross-scope"):
        compare_entries(layer_a.entries[0], layer_b.entries[0], (GAIN, LOSS))
    with pytest.raises(InvalidScientificProblem, match="cross-scope"):
        merge_layer_a_records(layer_a, layer_b)
    with pytest.raises(InvalidScientificProblem):
        DesignMemoryLayerA(
            scope=layer_a.scope,
            entries=(layer_a.entries[0], layer_b.entries[0]),
            partition_keys={
                layer_a.entries[0].identity: layer_a.partition_keys[
                    layer_a.entries[0].identity
                ],
                layer_b.entries[0].identity: layer_b.partition_keys[
                    layer_b.entries[0].identity
                ],
            },
        )
    verify_layer_a_attribution(
        layer_a=layer_a, candidates=candidates_a, evaluations=evaluations_a
    )
    verify_layer_a_attribution(
        layer_a=layer_b, candidates=candidates_b, evaluations=evaluations_b
    )


def test_attribution_spoof_attempts_fail_closed() -> None:
    candidates, evaluations, layer_a = _manual_layer()
    wrong_twin = replace(candidates[0], twin=candidates[1].twin)
    with pytest.raises(InvalidScientificProblem, match="Twin identity mismatch"):
        DesignMemoryLayerA.build(
            scope=layer_a.scope,
            candidates=(wrong_twin,),
            evaluations=(evaluations[0],),
            partitioner=_partitioner,
        )
    forged_scope = replace(layer_a.entries[0], scope_identity="0" * 64)
    with pytest.raises(InvalidScientificProblem, match="scope mismatch"):
        DesignMemoryLayerA(
            scope=layer_a.scope,
            entries=(forged_scope,),
            partition_keys={forged_scope.identity: "00"},
        )
    forged_objective = DesignMemoryEntry(
        candidate=layer_a.entries[0].candidate,
        design_space=layer_a.entries[0].design_space,
        evaluation=layer_a.entries[0].evaluation,
        result_binding=layer_a.entries[0].result_binding,
        scope_identity=layer_a.entries[0].scope_identity,
        assignments=layer_a.entries[0].assignments,
        objective_values={
            **dict(layer_a.entries[0].objective_values),
            "gain": Quantity(999.0, "dimensionless"),
        },
    )
    forged_layer = DesignMemoryLayerA(
        scope=layer_a.scope,
        entries=(forged_objective,),
        partition_keys={forged_objective.identity: "00"},
    )
    with pytest.raises(InvalidScientificProblem, match="disagrees with D1 source"):
        verify_layer_a_attribution(
            layer_a=forged_layer,
            candidates=candidates,
            evaluations=evaluations,
        )
    with pytest.raises(InvalidScientificProblem, match="reference absent"):
        DesignMemoryRecord.build(
            layer_a=layer_a,
            policy=DesignMemoryPolicy(
                policy_id="bad-explicit",
                explicit_retention=(
                    ExplicitRetention(
                        DesignCandidateReference("absent"),
                        evaluations[0].reference,
                        "bad",
                    ),
                ),
            ),
        )


def test_no_status_inflation_terms_in_serialized_record() -> None:
    _, _, _, layer_a = _batch(8)
    record = DesignMemoryRecord.build(layer_a=layer_a, policy=_policy(layer_a))
    payload = record.to_json()
    forbidden = (
        "feasible",
        "validated",
        "adequate",
        "safe",
        "optimal",
        "promising",
        "recommended",
        "refuted",
        "infeasible",
    )
    lowered = payload.lower()
    for token in forbidden:
        assert token not in lowered


def test_frozen_d1_compatibility_for_pareto_and_scoped_elite() -> None:
    _, evaluations, layer_a = _manual_layer()
    policy = DesignMemoryPolicy(
        policy_id="d1-compat",
        elite_scopes=(("gain",), ("loss",)),
    )
    record = DesignMemoryRecord.build(layer_a=layer_a, policy=policy)
    pareto = ParetoArchive.build(
        archive_id="pareto",
        design_space=layer_a.scope.design_space,
        objectives=(GAIN, LOSS),
        evaluations=evaluations,
    )
    gain_elite = ScopedEliteArchive.build(
        archive_id="gain-elite",
        scope_ref="gain",
        design_space=layer_a.scope.design_space,
        objectives=(GAIN,),
        evaluations=evaluations,
    )
    loss_elite = ScopedEliteArchive.build(
        archive_id="loss-elite",
        scope_ref="loss",
        design_space=layer_a.scope.design_space,
        objectives=(LOSS,),
        evaluations=evaluations,
    )
    by_eval = {item.evaluation_id: item for item in record.classification.classifications}

    assert {
        item.evaluation_id
        for item in pareto.members
    } == {
        item.evaluation_id
        for item in by_eval.values()
        if RetentionReason.PARETO_MEMBER in item.reasons
    }
    assert {
        item.evaluation_id for item in gain_elite.members + loss_elite.members
    } == {
        item.evaluation_id
        for item in by_eval.values()
        if RetentionReason.SCOPED_ELITE in item.reasons
    }


def test_d3_source_remains_domain_neutral() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "engcore"
        / "design"
        / "memory.py"
    ).read_text(encoding="utf-8").lower()
    forbidden = (
        "engcore.domains",
        "engcore.systems",
        "multirotor",
        "battery",
        "motor",
        "propeller",
        "reactor",
        "hvac",
        "llm",
        "redis",
        "s3",
    )
    for token in forbidden:
        assert token not in source
