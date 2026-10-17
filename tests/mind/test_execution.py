"""Closed-loop dispatch and belief revision.

These fixtures do not name the scored A3 packets. NAFEMS is not executed here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from engcore.mind.handlers import dispatch
from engcore.mind.loop import run_investigation
from engcore.mind.transition import (
    NAFEMS_CAPABILITY,
    NAFEMS_MODULE,
    NAFEMS_SUBJECT,
    ActionResult,
    ActionType,
    CandidateAction,
    Dependency,
    DependencyKind,
    DependencyStatus,
    HypothesisStatus,
    MindHypothesis,
    MindProblem,
    MindRefusal,
    MindState,
    ResultKind,
    apply_result,
    canonical_digest,
    select_next_action,
)

REVISION = "b" * 40
RUN = "mind-execution-test"
CATALOG = {"available_keys": [], "unavailable_keys": ["needed"]}


def _problem(question: str) -> MindProblem:
    return MindProblem(
        problem_id="problem-exec",
        question_hypothesis_id=question,
        statement="which admissible action is next",
        source_revision=REVISION,
        run_id=RUN,
    )


def _stop() -> CandidateAction:
    return CandidateAction("stop", ActionType.STOP, "stop", None)


def _evidence_state() -> MindState:
    return MindState(
        problem=_problem("q"),
        hypotheses=(
            MindHypothesis("q", HypothesisStatus.UNRESOLVED, "question"),
            MindHypothesis("other", HypothesisStatus.ACTIVE, "unrelated"),
            MindHypothesis(
                "kept",
                HypothesisStatus.SUPPORTED_BY_AUTHORITY,
                "already supported",
                "auth-kept",
                authority_token="supported",
            ),
        ),
        dependencies=(
            Dependency(
                "need",
                DependencyKind.OPERATING_POINT_EVIDENCE,
                DependencyStatus.OPEN,
                blocks=("q",),
            ),
            Dependency(
                "side",
                DependencyKind.EVIDENCE_REQUEST,
                DependencyStatus.OPEN,
                blocks=("other",),
            ),
        ),
        actions=(
            CandidateAction(
                "ask-need",
                ActionType.REQUEST_EVIDENCE,
                "blocking evidence",
                "need",
                capability_id="evidence:needed",
            ),
            CandidateAction(
                "ask-side",
                ActionType.REQUEST_EVIDENCE,
                "optional evidence",
                "side",
                capability_id="evidence:side",
            ),
            _stop(),
        ),
    )


def test_an_unknown_handler_is_refused():
    state = _evidence_state()
    action = CandidateAction(
        "ask-need",
        ActionType.REQUEST_EVIDENCE,
        "blocking evidence",
        "need",
        capability_id="shell:rm",
    )
    with pytest.raises(MindRefusal, match="REFUSE ACTION"):
        dispatch(state, action, CATALOG)


def test_ledger_identifiability_is_missing_and_not_unidentifiable():
    state = MindState(
        problem=_problem("q"),
        hypotheses=(MindHypothesis("q", HypothesisStatus.UNRESOLVED, "can this be calibrated"),),
        dependencies=(
            Dependency(
                "ident",
                DependencyKind.IDENTIFIABILITY,
                DependencyStatus.OPEN,
                blocks=("q",),
            ),
        ),
        actions=(
            CandidateAction(
                "check-ident",
                ActionType.CHECK_IDENTIFIABILITY,
                "inspect the identifiability path",
                "ident",
                capability_id="ledger:battery.thevenin_1rc#identifiability",
            ),
            _stop(),
        ),
    )
    result = dispatch(state, state.action("check-ident"), CATALOG)
    assert result.kind is ResultKind.AUTHORITY_STATUS
    assert result.authority_token == "missing"
    assert result.producing_module == "engcore.domains.battery.thevenin"
    assert "unidentifiable" not in result.to_dict().values()
    updated = apply_result(state, result)
    assert updated.hypothesis("q").status is HypothesisStatus.UNRESOLVED
    assert updated.hypothesis("q").authority_token is None
    assert updated.dependency("ident").status is DependencyStatus.BLOCKED


def test_failed_evidence_changes_only_the_dependent_branch():
    state = _evidence_state()
    before_other = state.hypothesis("other")
    before_kept = state.hypothesis("kept")
    record = run_investigation(state, CATALOG)
    assert record.action_ids == ("ask-need", "stop")
    final = record.final_state
    assert final.dependency("need").status is DependencyStatus.BLOCKED
    assert final.dependency("side").status is DependencyStatus.OPEN
    assert final.hypothesis("other") == before_other
    assert final.hypothesis("kept") == before_kept
    assert final.hypothesis("q").status is HypothesisStatus.UNRESOLVED
    again = run_investigation(MindState.from_dict(state.to_dict()), CATALOG)
    assert again.action_ids == record.action_ids
    assert canonical_digest(again.final_state.to_dict()) == canonical_digest(
        record.final_state.to_dict()
    )


def test_a_support_token_cannot_resurrect_a_refuted_hypothesis():
    state = MindState(
        problem=_problem("q"),
        hypotheses=(
            MindHypothesis("q", HypothesisStatus.UNRESOLVED, "open"),
            MindHypothesis(
                "refuted",
                HypothesisStatus.REFUTED_BY_AUTHORITY,
                "refused",
                "auth-no",
                subject_id=NAFEMS_SUBJECT,
            ),
        ),
        dependencies=(
            Dependency(
                "again",
                DependencyKind.CAPABILITY_EXECUTION,
                DependencyStatus.OPEN,
                blocks=("q", "refuted"),
            ),
        ),
        actions=(
            CandidateAction(
                "recheck",
                ActionType.RUN_CAPABILITY,
                "run the bound benchmark capability",
                "again",
                capability_id=NAFEMS_CAPABILITY,
            ),
            _stop(),
        ),
    )
    result = ActionResult(
        result_id="new-support",
        action_id="recheck",
        kind=ResultKind.AUTHORITY_STATUS,
        target_dependency_id="again",
        observation_id="new-support",
        problem_id=state.problem.problem_id,
        run_id=state.problem.run_id,
        source_revision=state.problem.source_revision,
        state_digest=canonical_digest(state.to_dict()),
        physical_infeasibility_claimed=False,
        authority_token="benchmark_validated",
        authority_result_id="new-support",
        target_hypothesis_id="refuted",
        producing_module=NAFEMS_MODULE,
    )
    with pytest.raises(MindRefusal, match="cannot be resurrected"):
        apply_result(state, result)
    assert state.hypothesis("refuted").status is HypothesisStatus.REFUTED_BY_AUTHORITY


def test_a_refute_token_cannot_clear_a_supported_hypothesis():
    state = MindState(
        problem=_problem("q"),
        hypotheses=(
            MindHypothesis("q", HypothesisStatus.UNRESOLVED, "open"),
            MindHypothesis(
                "kept",
                HypothesisStatus.SUPPORTED_BY_AUTHORITY,
                "supported",
                "auth-kept",
                authority_token="benchmark_validated",
            ),
        ),
        dependencies=(
            Dependency(
                "again",
                DependencyKind.APPLICABILITY,
                DependencyStatus.OPEN,
                blocks=("q", "kept"),
            ),
        ),
        actions=(
            CandidateAction(
                "recheck",
                ActionType.CHECK_APPLICABILITY,
                "inspect applicability",
                "again",
            ),
            _stop(),
        ),
    )
    result = ActionResult(
        result_id="new-refute",
        action_id="recheck",
        kind=ResultKind.AUTHORITY_STATUS,
        target_dependency_id="again",
        observation_id="new-refute",
        problem_id=state.problem.problem_id,
        run_id=state.problem.run_id,
        source_revision=state.problem.source_revision,
        state_digest=canonical_digest(state.to_dict()),
        physical_infeasibility_claimed=False,
        authority_token="not_supported",
        authority_result_id="new-refute",
        target_hypothesis_id="kept",
        producing_module="engcore.product.nafems_t3",
    )
    with pytest.raises(MindRefusal, match="cannot become unsupported"):
        apply_result(state, result)
    assert state.hypothesis("kept").authority_result_id == "auth-kept"
    assert state.hypothesis("kept").status is HypothesisStatus.SUPPORTED_BY_AUTHORITY


def test_a_new_authority_result_marks_supported_reasoning_stale_without_deleting_it():
    state = MindState(
        problem=_problem("q"),
        hypotheses=(
            MindHypothesis("q", HypothesisStatus.UNRESOLVED, "open"),
            MindHypothesis(
                "kept",
                HypothesisStatus.SUPPORTED_BY_AUTHORITY,
                "supported",
                "auth-kept",
                authority_token="benchmark_validated",
                subject_id=NAFEMS_SUBJECT,
            ),
        ),
        dependencies=(
            Dependency(
                "again",
                DependencyKind.CAPABILITY_EXECUTION,
                DependencyStatus.OPEN,
                blocks=("q", "kept"),
            ),
        ),
        actions=(
            CandidateAction(
                "recheck",
                ActionType.RUN_CAPABILITY,
                "run the bound benchmark capability",
                "again",
                capability_id=NAFEMS_CAPABILITY,
            ),
            _stop(),
        ),
    )
    result = ActionResult(
        result_id="later-support",
        action_id="recheck",
        kind=ResultKind.AUTHORITY_STATUS,
        target_dependency_id="again",
        observation_id="later-support",
        problem_id=state.problem.problem_id,
        run_id=state.problem.run_id,
        source_revision=state.problem.source_revision,
        state_digest=canonical_digest(state.to_dict()),
        physical_infeasibility_claimed=False,
        authority_token="benchmark_validated",
        authority_result_id="later-support",
        target_hypothesis_id="kept",
        producing_module=NAFEMS_MODULE,
    )
    updated = apply_result(state, result)
    kept = updated.hypothesis("kept")
    assert kept.status is HypothesisStatus.STALE
    assert kept.authority_result_id == "auth-kept"
    assert kept.authority_token == "benchmark_validated"
    assert kept.prior_authority_result_ids == ("auth-kept",)
    assert kept.stale_result_id == "later-support"
    assert updated.hypothesis("q").status is HypothesisStatus.UNRESOLVED
    assert "auth-kept" in updated.to_dict()["hypotheses"][0]["prior_authority_result_ids"] or (
        "auth-kept" in kept.prior_authority_result_ids
    )


def test_handlers_do_not_execute_a_shell():
    source = Path(__file__).resolve().parents[2] / "src" / "engcore" / "mind" / "handlers.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert "subprocess" not in imported
    assert "engcore.mind" not in imported


def test_downstream_calibration_is_not_selected_ahead_of_an_open_gate():
    state = MindState(
        problem=_problem("q"),
        hypotheses=(MindHypothesis("q", HypothesisStatus.UNRESOLVED, "open"),),
        dependencies=(
            Dependency(
                "ident",
                DependencyKind.IDENTIFIABILITY,
                DependencyStatus.OPEN,
                blocks=("q",),
            ),
            Dependency(
                "trace",
                DependencyKind.EVIDENCE_REQUEST,
                DependencyStatus.OPEN,
                blocks=("q",),
                prerequisite_ids=("ident",),
            ),
            Dependency(
                "calibrate",
                DependencyKind.CAPABILITY_EXECUTION,
                DependencyStatus.OPEN,
                blocks=("q",),
                prerequisite_ids=("ident", "trace"),
            ),
        ),
        actions=(
            CandidateAction(
                "z-calibrate",
                ActionType.RUN_CAPABILITY,
                "attempt calibration",
                "calibrate",
                capability_id="ledger:battery.thevenin_1rc#calibration",
            ),
            CandidateAction(
                "a-trace",
                ActionType.REQUEST_EVIDENCE,
                "inspect the dataset trace",
                "trace",
                capability_id="ledger:battery.thevenin_1rc#real_data",
            ),
            CandidateAction(
                "z-ident",
                ActionType.CHECK_IDENTIFIABILITY,
                "inspect identifiability",
                "ident",
                capability_id="ledger:battery.thevenin_1rc#identifiability",
            ),
            _stop(),
        ),
    )
    selected = select_next_action(state)
    assert selected.action_id == "z-ident"
    record = run_investigation(state, CATALOG, max_steps=4)
    assert record.action_ids == ("z-ident", "stop")
    assert record.results[0].authority_token == "missing"
    assert record.final_state.hypothesis("q").status is HypothesisStatus.UNRESOLVED


def test_an_unbound_question_cannot_receive_the_benchmark_result():
    state = MindState(
        problem=_problem("q"),
        hypotheses=(
            MindHypothesis(
                "q",
                HypothesisStatus.UNRESOLVED,
                "this cell and duty cycle are experimentally validated",
            ),
        ),
        dependencies=(
            Dependency(
                "benchmark",
                DependencyKind.CAPABILITY_EXECUTION,
                DependencyStatus.OPEN,
                blocks=("q",),
            ),
        ),
        actions=(
            CandidateAction(
                "run-benchmark",
                ActionType.RUN_CAPABILITY,
                "run the thermal benchmark capability",
                "benchmark",
                capability_id=NAFEMS_CAPABILITY,
            ),
            _stop(),
        ),
    )
    with pytest.raises(MindRefusal, match="REFUSE ACTION"):
        dispatch(state, state.action("run-benchmark"), CATALOG)
    assert state.hypothesis("q").status is HypothesisStatus.UNRESOLVED


def test_an_open_applicability_gate_is_not_dispatched_as_a_capability():
    state = MindState(
        problem=_problem("q"),
        hypotheses=(
            MindHypothesis("q", HypothesisStatus.UNRESOLVED, "open", subject_id=NAFEMS_SUBJECT),
        ),
        dependencies=(
            Dependency(
                "applicability",
                DependencyKind.APPLICABILITY,
                DependencyStatus.OPEN,
                blocks=("q",),
            ),
            Dependency(
                "benchmark",
                DependencyKind.CAPABILITY_EXECUTION,
                DependencyStatus.OPEN,
                blocks=("q",),
            ),
        ),
        actions=(
            CandidateAction(
                "check-applicability",
                ActionType.CHECK_APPLICABILITY,
                "inspect applicability",
                "applicability",
            ),
            CandidateAction(
                "run-benchmark",
                ActionType.RUN_CAPABILITY,
                "run the thermal benchmark capability",
                "benchmark",
                capability_id=NAFEMS_CAPABILITY,
            ),
            _stop(),
        ),
    )
    with pytest.raises(MindRefusal, match="REFUSE ACTION"):
        dispatch(state, state.action("run-benchmark"), CATALOG)


def test_a_ledger_pass_does_not_resolve_the_scientific_dependency():
    state = MindState(
        problem=_problem("q"),
        hypotheses=(MindHypothesis("q", HypothesisStatus.UNRESOLVED, "open"),),
        dependencies=(
            Dependency(
                "measurement",
                DependencyKind.EVIDENCE_REQUEST,
                DependencyStatus.OPEN,
                blocks=("q",),
            ),
        ),
        actions=(
            CandidateAction(
                "inspect-measurement",
                ActionType.REQUEST_EVIDENCE,
                "inspect measurement metadata",
                "measurement",
                capability_id="ledger:claims.model_form_discrepancy#measurement_uq",
            ),
            _stop(),
        ),
    )
    result = dispatch(state, state.action("inspect-measurement"), CATALOG)
    assert result.authority_token == "ledger_observed"
    updated = apply_result(state, result)
    assert updated.hypothesis("q").status is HypothesisStatus.UNRESOLVED
    assert updated.hypothesis("q").authority_token is None
    assert updated.dependency("measurement").status is DependencyStatus.OPEN


def test_not_applicable_is_not_recorded_as_missing_evidence():
    state = MindState(
        problem=_problem("q"),
        hypotheses=(MindHypothesis("q", HypothesisStatus.ACTIVE, "open"),),
        dependencies=(
            Dependency(
                "calibration",
                DependencyKind.CAPABILITY_EXECUTION,
                DependencyStatus.OPEN,
                blocks=("q",),
            ),
        ),
        actions=(
            CandidateAction(
                "calibrate",
                ActionType.RUN_CAPABILITY,
                "attempt calibration",
                "calibration",
                capability_id="ledger:battery.rint#calibration",
            ),
            _stop(),
        ),
    )
    result = dispatch(state, state.action("calibrate"), CATALOG)
    assert result.authority_token == "not_applicable"
    updated = apply_result(state, result)
    assert updated.hypothesis("q").status is HypothesisStatus.ACTIVE
    assert updated.dependency("calibration").status is DependencyStatus.OPEN


def test_a_caller_supplied_support_token_is_refused():
    state = _evidence_state()
    with pytest.raises(MindRefusal, match="unknown authority token"):
        ActionResult(
            result_id="forged",
            action_id="ask-need",
            kind=ResultKind.AUTHORITY_STATUS,
            target_dependency_id="need",
            observation_id="forged",
            problem_id=state.problem.problem_id,
            run_id=state.problem.run_id,
            source_revision=state.problem.source_revision,
            state_digest=canonical_digest(state.to_dict()),
            physical_infeasibility_claimed=False,
            authority_token="supported",
            authority_result_id="forged",
            target_hypothesis_id="q",
            producing_module=NAFEMS_MODULE,
        )


def test_an_unknown_evidence_key_is_refused():
    state = _evidence_state()
    with pytest.raises(MindRefusal, match="REFUSE ACTION"):
        dispatch(state, state.action("ask-need"), {"available_keys": [], "unavailable_keys": []})


def test_an_identify_name_does_not_close_the_gate(monkeypatch):
    monkeypatch.setattr(
        "engcore.mind.handlers._identify_callables",
        lambda capability_id: ("identify_placeholder",),
    )
    state = MindState(
        problem=_problem("q"),
        hypotheses=(MindHypothesis("q", HypothesisStatus.UNRESOLVED, "open"),),
        dependencies=(
            Dependency(
                "ident",
                DependencyKind.IDENTIFIABILITY,
                DependencyStatus.OPEN,
                blocks=("q",),
            ),
        ),
        actions=(
            CandidateAction(
                "check-ident",
                ActionType.CHECK_IDENTIFIABILITY,
                "inspect identifiability",
                "ident",
                capability_id="ledger:battery.thevenin_1rc#identifiability",
            ),
            _stop(),
        ),
    )
    with pytest.raises(MindRefusal, match="REFUSE ACTION"):
        dispatch(state, state.action("check-ident"), CATALOG)
