"""Focused tests for the minimal next-action transition.

The fixtures use arbitrary ids. None of the assertions depend on a motor,
battery, or benchmark name.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from engcore.mind.transition import (
    SOFTWARE_VERSION,
    ActionResult,
    ActionType,
    BoundaryRequest,
    CandidateAction,
    Dependency,
    DependencyKind,
    DependencyStatus,
    HypothesisStatus,
    InformationGain,
    LlmActionProposal,
    MindHypothesis,
    MindProblem,
    MindRefusal,
    MindState,
    ResultKind,
    apply_result,
    canonical_digest,
    review_proposal,
    select_next_action,
)


REVISION = "a" * 40
RUN = "mind-transition-test"


def _availability(state: MindState, **overrides) -> ActionResult:
    payload = {
        "result_id": "availability",
        "action_id": "request-point",
        "kind": ResultKind.EVIDENCE_UNAVAILABLE,
        "target_dependency_id": "point-dep",
        "observation_id": "obs-point-unavailable",
        "problem_id": state.problem.problem_id,
        "run_id": state.problem.run_id,
        "source_revision": state.problem.source_revision,
        "state_digest": canonical_digest(state.to_dict()),
        "physical_infeasibility_claimed": False,
    }
    payload.update(overrides)
    return ActionResult(**payload)


def _problem(question: str) -> MindProblem:
    return MindProblem(
        problem_id="problem-1",
        question_hypothesis_id=question,
        statement="which admissible action is next",
        source_revision=REVISION,
        run_id=RUN,
    )


def _stop() -> CandidateAction:
    return CandidateAction(
        action_id="stop",
        action_type=ActionType.STOP,
        reason="stop when no admissible action remains",
        dependency_id=None,
    )


def _state_with_open_evidence() -> MindState:
    return MindState(
        problem=_problem("mission"),
        hypotheses=(
            MindHypothesis("dead-branch", HypothesisStatus.REFUTED_BY_AUTHORITY, "refused", "auth-dead"),
            MindHypothesis("duration", HypothesisStatus.SUPPORTED_BY_AUTHORITY, "duration contained", "auth-duration"),
            MindHypothesis("mission", HypothesisStatus.UNRESOLVED, "question open"),
            MindHypothesis("point", HypothesisStatus.UNRESOLVED, "operating point missing"),
            MindHypothesis("unrelated", HypothesisStatus.ACTIVE, "not on this question"),
        ),
        dependencies=(
            Dependency(
                "dead-dep",
                DependencyKind.APPLICABILITY,
                DependencyStatus.DEAD,
                blocks=("dead-branch",),
                upstream_result_ids=("auth-dead",),
            ),
            Dependency(
                "point-dep",
                DependencyKind.OPERATING_POINT_EVIDENCE,
                DependencyStatus.OPEN,
                blocks=("mission", "point"),
                upstream_result_ids=("auth-duration",),
            ),
            Dependency(
                "unrelated-dep",
                DependencyKind.OPERATING_POINT_EVIDENCE,
                DependencyStatus.OPEN,
                blocks=("unrelated",),
            ),
            Dependency(
                "resolved-dep",
                DependencyKind.CAPABILITY_EXECUTION,
                DependencyStatus.RESOLVED,
                blocks=("mission",),
                upstream_result_ids=("auth-old-run",),
            ),
        ),
        actions=(
            CandidateAction(
                "again",
                ActionType.CHECK_APPLICABILITY,
                "repeat the refused branch; the reason text must not revive it",
                "dead-dep",
            ),
            CandidateAction(
                "infeasible",
                ActionType.CHECK_APPLICABILITY,
                "declare the mission impossible",
                "point-dep",
                boundary_request=BoundaryRequest.DECLARE_PHYSICAL_INFEASIBILITY,
            ),
            CandidateAction(
                "relax",
                ActionType.REQUEST_EVIDENCE,
                "shorten the requirement",
                "point-dep",
                boundary_request=BoundaryRequest.CHANGE_THRESHOLD,
            ),
            CandidateAction(
                "request-point",
                ActionType.REQUEST_EVIDENCE,
                "request the missing operating-point evidence",
                "point-dep",
            ),
            CandidateAction(
                "rerun",
                ActionType.RUN_CAPABILITY,
                "repeat a finished capability",
                "resolved-dep",
                capability_id="old-capability",
            ),
            CandidateAction(
                "search-other",
                ActionType.REQUEST_EVIDENCE,
                "search a branch that does not block the question",
                "unrelated-dep",
            ),
            _stop(),
        ),
    )


def _state_needing_identifiability() -> MindState:
    return MindState(
        problem=_problem("identification"),
        hypotheses=(
            MindHypothesis("identification", HypothesisStatus.UNRESOLVED, "parameters are not identified"),
        ),
        dependencies=(
            Dependency(
                "identifiability",
                DependencyKind.IDENTIFIABILITY,
                DependencyStatus.OPEN,
                blocks=("identification",),
                upstream_result_ids=("gate-real-data-missing", "gate-calibration-missing"),
            ),
            Dependency(
                "fit",
                DependencyKind.CAPABILITY_EXECUTION,
                DependencyStatus.OPEN,
                blocks=("identification",),
                prerequisite_ids=("identifiability",),
            ),
        ),
        actions=(
            CandidateAction(
                "assume",
                ActionType.CHECK_IDENTIFIABILITY,
                "treat an unknown state as known",
                "identifiability",
                boundary_request=BoundaryRequest.CONVERT_UNKNOWN_TO_ZERO,
            ),
            CandidateAction(
                "check",
                ActionType.CHECK_IDENTIFIABILITY,
                "establish the identifiability dependency",
                "identifiability",
            ),
            CandidateAction(
                "fit-now",
                ActionType.RUN_CAPABILITY,
                "fit parameters immediately",
                "fit",
                capability_id="parameter-fit",
            ),
            CandidateAction(
                "more-iterations",
                ActionType.RUN_CAPABILITY,
                "increase optimizer iterations",
                "fit",
                capability_id="parameter-fit",
            ),
            CandidateAction(
                "unidentifiable",
                ActionType.CHECK_IDENTIFIABILITY,
                "declare the dataset inherently unidentifiable",
                "identifiability",
                boundary_request=BoundaryRequest.DECLARE_TRUTH,
            ),
            _stop(),
        ),
    )


def _resolved_question() -> MindState:
    return MindState(
        problem=_problem("benchmark"),
        hypotheses=(
            MindHypothesis(
                "benchmark",
                HypothesisStatus.SUPPORTED_BY_AUTHORITY,
                "benchmark comparison already supported",
                "auth-benchmark",
            ),
            MindHypothesis("experiment", HypothesisStatus.UNRESOLVED, "experimental validation was not the question"),
            MindHypothesis("uncertainty", HypothesisStatus.UNRESOLVED, "uncertainty was not quantified"),
        ),
        dependencies=(
            Dependency(
                "benchmark-dep",
                DependencyKind.CAPABILITY_EXECUTION,
                DependencyStatus.RESOLVED,
                blocks=("benchmark",),
                upstream_result_ids=("auth-benchmark",),
            ),
            Dependency(
                "experiment-dep",
                DependencyKind.APPLICABILITY,
                DependencyStatus.OPEN,
                blocks=("experiment",),
            ),
            Dependency(
                "uncertainty-dep",
                DependencyKind.IDENTIFIABILITY,
                DependencyStatus.OPEN,
                blocks=("uncertainty",),
            ),
        ),
        actions=(
            CandidateAction(
                "invent",
                ActionType.CHECK_IDENTIFIABILITY,
                "invent an uncertainty from refinement",
                "uncertainty-dep",
                boundary_request=BoundaryRequest.INVENT_UNCERTAINTY,
            ),
            CandidateAction(
                "promote",
                ActionType.CHECK_APPLICABILITY,
                "promote the result to experimental validation",
                "experiment-dep",
                boundary_request=BoundaryRequest.DECLARE_VALIDATION,
            ),
            CandidateAction(
                "rerun",
                ActionType.RUN_CAPABILITY,
                "run the solver again",
                "benchmark-dep",
                capability_id="benchmark-solver",
            ),
            CandidateAction(
                "search",
                ActionType.CHECK_APPLICABILITY,
                "search evidence that does not block the question",
                "experiment-dep",
            ),
            _stop(),
        ),
    )


def test_the_same_state_selects_one_action_and_one_digest():
    state = _state_with_open_evidence()
    first = select_next_action(state)
    second = select_next_action(state)
    assert first == second
    assert first.action_id == "request-point"
    assert first.action_type is ActionType.REQUEST_EVIDENCE
    assert first.dependency_id == "point-dep"
    assert first.information_gain is InformationGain.OPEN_DEPENDENCY
    assert first.state_digest == second.state_digest
    assert state.to_dict() == _state_with_open_evidence().to_dict()


def test_a_forged_verdict_cannot_overwrite_a_refusal():
    state = _state_with_open_evidence()
    with pytest.raises(MindRefusal, match="physical infeasibility"):
        _availability(state, result_id="forged", observation_id="obs-1", physical_infeasibility_claimed=True)
    payload = state.to_dict()
    dead = next(item for item in payload["hypotheses"] if item["hypothesis_id"] == "dead-branch")
    dead["status"] = HypothesisStatus.SUPPORTED_BY_AUTHORITY.value
    dead["authority_result_id"] = None
    with pytest.raises(MindRefusal, match="without an authority result id"):
        MindState.from_dict(payload)
    updated = apply_result(state, _availability(state))
    refused = updated.hypothesis("dead-branch")
    assert refused.status is HypothesisStatus.REFUTED_BY_AUTHORITY
    assert refused.authority_result_id == "auth-dead"
    assert updated.hypothesis("duration").status is HypothesisStatus.SUPPORTED_BY_AUTHORITY
    assert updated.hypothesis("duration").authority_result_id == "auth-duration"


def test_a_dead_branch_stays_dead_and_is_not_selected():
    state = _state_with_open_evidence()
    updated = apply_result(state, _availability(state))
    assert updated.dependency("dead-dep").status is DependencyStatus.DEAD
    assert updated.hypothesis("dead-branch").status is HypothesisStatus.REFUTED_BY_AUTHORITY
    selected = select_next_action(updated)
    assert selected.action_id == "stop"
    gains = {item.action_id: item.information_gain for item in selected.decisions}
    assert gains["again"] is InformationGain.DEAD_BRANCH


def test_an_unrelated_branch_survives_revision():
    state = _state_with_open_evidence()
    before = state.hypothesis("unrelated").to_dict()
    before_dependency = state.dependency("unrelated-dep").to_dict()
    updated = apply_result(state, _availability(state))
    assert updated.hypothesis("unrelated").to_dict() == before
    assert updated.dependency("unrelated-dep").to_dict() == before_dependency
    assert updated.hypothesis("mission").status is HypothesisStatus.UNRESOLVED
    assert updated.dependency("point-dep").status is DependencyStatus.BLOCKED
    assert (
        updated.dependency("point-dep").upstream_result_ids
        == state.dependency("point-dep").upstream_result_ids
    )
    assert updated.dependency("point-dep").availability_observation_id == "obs-point-unavailable"
    assert updated.dependency("point-dep").availability_result_id == "availability"


def test_a_missing_dependency_keeps_the_hypothesis_unresolved():
    state = MindState(
        problem=_problem("mission"),
        hypotheses=(
            MindHypothesis("mission", HypothesisStatus.UNRESOLVED, "still open"),
        ),
        dependencies=(
            Dependency(
                "elsewhere",
                DependencyKind.OPERATING_POINT_EVIDENCE,
                DependencyStatus.OPEN,
                blocks=("mission",),
            ),
        ),
        actions=(
            CandidateAction(
                "request",
                ActionType.REQUEST_EVIDENCE,
                "request evidence for a dependency this result will not name",
                "elsewhere",
            ),
            _stop(),
        ),
    )
    with pytest.raises(MindRefusal, match="unknown dependency"):
        apply_result(
            state,
            _availability(
                state,
                result_id="missing",
                action_id="request",
                target_dependency_id="not-a-dependency",
                observation_id="obs-missing",
            ),
        )
    assert state.hypothesis("mission").status is HypothesisStatus.UNRESOLVED
    assert select_next_action(state).action_type is not ActionType.STOP


def test_an_unknown_or_boundary_llm_action_is_rejected_without_changing_state():
    state = _state_with_open_evidence()
    digest = select_next_action(state).state_digest
    unknown = review_proposal(
        state,
        LlmActionProposal(
            model_identity="fixture-model",
            prompt_identity="prompt-1",
            proposed_action_id="not-a-candidate",
            output_payload={"action": "not-a-candidate"},
        ),
    )
    override = review_proposal(
        state,
        LlmActionProposal(
            model_identity="fixture-model",
            prompt_identity="prompt-1",
            proposed_action_id="infeasible",
            output_payload={"action": "infeasible"},
        ),
    )
    assert unknown.matches_selected_action is False
    assert unknown.payload_interpreted is False
    assert override.matches_selected_action is False
    assert unknown.model_identity == "fixture-model"
    assert unknown.prompt_identity == "prompt-1"
    assert unknown.input_digest == digest
    assert unknown.output_digest != override.output_digest
    assert select_next_action(state).state_digest == digest
    matching = review_proposal(
        state,
        LlmActionProposal(
            model_identity="fixture-model",
            prompt_identity="prompt-1",
            proposed_action_id="request-point",
            output_payload={"action": "request-point"},
        ),
    )
    assert matching.matches_selected_action is True
    assert matching.payload_interpreted is False
    assert select_next_action(state).action_id == "request-point"


def test_stop_is_admissible_and_selected_when_the_question_is_resolved():
    state = _resolved_question()
    selected = select_next_action(state)
    assert selected.action_type is ActionType.STOP
    assert selected.information_gain is InformationGain.STOP
    stop = next(item for item in selected.decisions if item.action_id == "stop")
    assert stop.admissible is True
    assert state.hypothesis("experiment").status is HypothesisStatus.UNRESOLVED
    assert state.hypothesis("uncertainty").status is HypothesisStatus.UNRESOLVED
    record = review_proposal(
        state,
        LlmActionProposal(
            model_identity="fixture-model",
            prompt_identity="prompt-stop",
            proposed_action_id="stop",
            output_payload={"action": "stop"},
        ),
    )
    assert record.matches_selected_action is True
    assert record.payload_interpreted is False


def test_stop_is_not_selected_while_relevant_work_remains():
    selected = select_next_action(_state_needing_identifiability())
    assert selected.action_id == "check"
    assert selected.action_type is ActionType.CHECK_IDENTIFIABILITY
    gains = {item.action_id: item.information_gain for item in selected.decisions}
    assert gains["fit-now"] is InformationGain.PREREQUISITE_OPEN
    assert gains["more-iterations"] is InformationGain.PREREQUISITE_OPEN
    assert gains["assume"] is InformationGain.AUTHORITY_OVERRIDE
    assert gains["unidentifiable"] is InformationGain.AUTHORITY_OVERRIDE
    assert gains["stop"] is InformationGain.STOP


def test_replay_is_deterministic_across_order_and_round_trip():
    state = _state_with_open_evidence()
    shuffled = MindState(
        problem=state.problem,
        hypotheses=tuple(reversed(state.hypotheses)),
        dependencies=tuple(reversed(state.dependencies)),
        actions=tuple(reversed(state.actions)),
        attempted_action_ids=(),
    )
    assert shuffled.to_dict() == state.to_dict()
    restored = MindState.from_dict(state.to_dict())
    assert restored.to_dict() == state.to_dict()
    assert select_next_action(restored) == select_next_action(state)
    updated = apply_result(state, _availability(state))
    restored = MindState.from_dict(state.to_dict())
    again = apply_result(restored, _availability(restored))
    assert updated.to_dict() == again.to_dict()
    assert select_next_action(updated) == select_next_action(again)


def test_the_module_does_not_import_scientific_authority():
    source = Path(__file__).resolve().parents[2] / "src" / "engcore" / "mind" / "transition.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert imported == [] or all(not name.startswith("engcore") for name in imported)
    assert SOFTWARE_VERSION == "engcore.mind.transition/1.0.0"


def test_a_resolved_refusal_is_not_reopened_by_a_new_authority_status_field():
    payload = _state_with_open_evidence().to_dict()
    payload["expected_action"] = "request-point"
    with pytest.raises(MindRefusal, match="fields mismatch"):
        MindState.from_dict(payload)


def test_capability_execution_waits_while_a_question_gate_is_unresolved():
    state = MindState(
        problem=_problem("q"),
        hypotheses=(MindHypothesis("q", HypothesisStatus.UNRESOLVED, "open question"),),
        dependencies=(
            Dependency(
                "a-exec",
                DependencyKind.CAPABILITY_EXECUTION,
                DependencyStatus.OPEN,
                blocks=("q",),
            ),
            Dependency(
                "b-app",
                DependencyKind.APPLICABILITY,
                DependencyStatus.OPEN,
                blocks=("q",),
            ),
        ),
        actions=(
            CandidateAction("check-app", ActionType.CHECK_APPLICABILITY, "check applicability", "b-app"),
            CandidateAction("run-exec", ActionType.RUN_CAPABILITY, "run the capability", "a-exec", capability_id="solver"),
            _stop(),
        ),
    )
    selected = select_next_action(state)
    assert selected.action_id == "check-app"
    blocked = apply_result(
        state,
        _availability(
            state,
            action_id="check-app",
            target_dependency_id="b-app",
            observation_id="obs-app-unavailable",
            result_id="app-unavailable",
        ),
    )
    assert blocked.dependency("b-app").status is DependencyStatus.BLOCKED
    assert select_next_action(blocked).action_type is ActionType.STOP
    assert state.hypothesis("q").status is HypothesisStatus.UNRESOLVED


def test_an_availability_result_from_another_context_is_refused():
    state = _state_with_open_evidence()
    with pytest.raises(MindRefusal, match="different problem"):
        apply_result(state, _availability(state, problem_id="other-problem"))
    with pytest.raises(MindRefusal, match="different run"):
        apply_result(state, _availability(state, run_id="other-run"))
    with pytest.raises(MindRefusal, match="different source revision"):
        apply_result(state, _availability(state, source_revision="b" * 40))
    with pytest.raises(MindRefusal, match="does not match this state"):
        apply_result(state, _availability(state, state_digest="c" * 64))
    assert state.dependency("point-dep").status is DependencyStatus.OPEN


def test_an_inadmissible_action_cannot_record_an_observation():
    state = _state_needing_identifiability()
    with pytest.raises(MindRefusal, match="not an admissible"):
        apply_result(
            state,
            _availability(
                state,
                action_id="fit-now",
                target_dependency_id="fit",
                observation_id="obs-fit",
                result_id="fit-unavailable",
            ),
        )
    assert state.dependency("fit").status is DependencyStatus.OPEN
    assert state.hypothesis("identification").status is HypothesisStatus.UNRESOLVED


def test_evidence_unavailable_does_not_rewrite_descendant_status():
    state = MindState(
        problem=_problem("q"),
        hypotheses=(
            MindHypothesis("q", HypothesisStatus.UNRESOLVED, "open"),
            MindHypothesis("live", HypothesisStatus.ACTIVE, "still active"),
            MindHypothesis("held", HypothesisStatus.SUPPORTED_BY_AUTHORITY, "already supported", "auth-held"),
        ),
        dependencies=(
            Dependency(
                "point",
                DependencyKind.OPERATING_POINT_EVIDENCE,
                DependencyStatus.OPEN,
                blocks=("q", "live", "held"),
            ),
        ),
        actions=(
            CandidateAction("request", ActionType.REQUEST_EVIDENCE, "request the missing point", "point"),
            _stop(),
        ),
    )
    updated = apply_result(
        state,
        _availability(state, action_id="request", target_dependency_id="point", result_id="point-result"),
    )
    assert updated.hypothesis("live").status is HypothesisStatus.ACTIVE
    assert updated.hypothesis("held").status is HypothesisStatus.SUPPORTED_BY_AUTHORITY
    assert updated.hypothesis("held").authority_result_id == "auth-held"
    assert updated.hypothesis("q").status is HypothesisStatus.UNRESOLVED


def test_a_refuted_question_selects_stop():
    state = MindState(
        problem=_problem("q"),
        hypotheses=(
            MindHypothesis("q", HypothesisStatus.REFUTED_BY_AUTHORITY, "refused by authority", "auth-q"),
        ),
        dependencies=(
            Dependency(
                "again",
                DependencyKind.APPLICABILITY,
                DependencyStatus.OPEN,
                blocks=("q",),
            ),
        ),
        actions=(
            CandidateAction("recheck", ActionType.CHECK_APPLICABILITY, "check the refused question again", "again"),
            _stop(),
        ),
    )
    selected = select_next_action(state)
    assert selected.action_type is ActionType.STOP
    assert state.hypothesis("q").status is HypothesisStatus.REFUTED_BY_AUTHORITY


def test_same_kind_actions_tie_break_on_action_id():
    state = MindState(
        problem=_problem("q"),
        hypotheses=(MindHypothesis("q", HypothesisStatus.UNRESOLVED, "open"),),
        dependencies=(
            Dependency(
                "point",
                DependencyKind.OPERATING_POINT_EVIDENCE,
                DependencyStatus.OPEN,
                blocks=("q",),
            ),
        ),
        actions=(
            CandidateAction("b-request", ActionType.REQUEST_EVIDENCE, "second request", "point"),
            CandidateAction("a-request", ActionType.REQUEST_EVIDENCE, "first request", "point"),
            _stop(),
        ),
    )
    assert select_next_action(state).action_id == "a-request"


def test_a_matching_proposal_payload_is_not_interpreted():
    state = _state_with_open_evidence()
    record = review_proposal(
        state,
        LlmActionProposal(
            model_identity="fixture-model",
            prompt_identity="prompt-poison",
            proposed_action_id="request-point",
            output_payload={"boundary_request": "set_claim", "uncertainty": 0},
        ),
    )
    assert record.matches_selected_action is True
    assert record.payload_interpreted is False
    assert select_next_action(state).action_id == "request-point"
    assert state.hypothesis("mission").status is HypothesisStatus.UNRESOLVED
