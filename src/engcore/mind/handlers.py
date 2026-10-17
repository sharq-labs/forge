"""Dispatch one already selected action to an existing FORGE authority.

An unknown capability prefix is refused. This module returns the authority's
typed result. It does not choose the next action and it does not mint a
support or refutation token.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any, Mapping

from .transition import (
    NAFEMS_CAPABILITY,
    NAFEMS_MODULE,
    NAFEMS_SUBJECT,
    POLICY_VERSION,
    SOFTWARE_VERSION,
    ActionResult,
    ActionType,
    CandidateAction,
    MindRefusal,
    MindState,
    ResultKind,
    canonical_digest,
    select_next_action,
)

_LEDGER_SCHEMA = "forge.scientific_capability_completion/1"
_LEDGER_GATES = {
    "identifiability": ActionType.CHECK_IDENTIFIABILITY,
    "real_data": ActionType.REQUEST_EVIDENCE,
    "measurement_uq": ActionType.REQUEST_EVIDENCE,
    "calibration": ActionType.RUN_CAPABILITY,
}
_IDENTIFY_MODULES = {
    "battery.thevenin_1rc": "engcore.domains.battery.thevenin",
}
_NAFEMS_CAPABILITY = NAFEMS_CAPABILITY

_REGISTRY = (
    {
        "action_type": ActionType.REQUEST_EVIDENCE.value,
        "handler_id": "evidence",
        "prefix": "evidence:",
        "producing_module": "frozen-evidence-catalog",
    },
    {
        "action_type": "ledger-gate",
        "handler_id": "ledger",
        "prefix": "ledger:",
        "producing_module": "tools.capability_maturity",
    },
    {
        "action_type": ActionType.RUN_CAPABILITY.value,
        "handler_id": "nafems-t3",
        "prefix": _NAFEMS_CAPABILITY,
        "producing_module": "engcore.product.nafems_t3",
    },
)


def handler_registry_digest(catalog_digest: str) -> str:
    """Identity of the registered handlers, policy, and evidence catalog."""
    return canonical_digest(
        {
            "catalog_digest": catalog_digest,
            "handlers": list(_REGISTRY),
            "policy_version": POLICY_VERSION,
            "software_version": SOFTWARE_VERSION,
        }
    )


def catalog_digest(catalog: Mapping[str, Any]) -> str:
    return canonical_digest(dict(catalog))


def dispatch(
    state: MindState,
    action: CandidateAction,
    catalog: Mapping[str, Any],
) -> ActionResult:
    """Return the typed result of one registered handler."""
    capability = action.capability_id or ""
    if action.action_type is ActionType.STOP or not capability:
        raise MindRefusal("REFUSE ACTION")
    selected = select_next_action(state)
    if selected.action_id != action.action_id:
        raise MindRefusal("REFUSE ACTION")
    if capability.startswith("evidence:"):
        if action.action_type is not ActionType.REQUEST_EVIDENCE:
            raise MindRefusal("REFUSE ACTION")
        return _evidence(state, action, catalog)
    if capability.startswith("ledger:"):
        return _ledger(state, action)
    if capability == _NAFEMS_CAPABILITY:
        if action.action_type is not ActionType.RUN_CAPABILITY:
            raise MindRefusal("REFUSE ACTION")
        return _nafems(state, action)
    raise MindRefusal("REFUSE ACTION")


def _evidence(
    state: MindState,
    action: CandidateAction,
    catalog: Mapping[str, Any],
) -> ActionResult:
    key = (action.capability_id or "")[len("evidence:") :]
    if not key:
        raise MindRefusal("REFUSE ACTION")
    if "available_keys" not in catalog or "unavailable_keys" not in catalog:
        raise MindRefusal("REFUSE ACTION")
    available = catalog["available_keys"]
    unavailable = catalog["unavailable_keys"]
    if (
        not isinstance(available, list)
        or not isinstance(unavailable, list)
        or any(type(item) is not str for item in [*available, *unavailable])
    ):
        raise MindRefusal("REFUSE ACTION")
    if key in available or key not in unavailable:
        raise MindRefusal("REFUSE ACTION")
    observation = canonical_digest(
        {"catalog_digest": catalog_digest(catalog), "key": key, "status": "absent"}
    )
    return _availability(state, action, observation)


def _availability(state: MindState, action: CandidateAction, observation: str) -> ActionResult:
    result_id = canonical_digest(
        {
            "action_id": action.action_id,
            "kind": ResultKind.EVIDENCE_UNAVAILABLE.value,
            "observation_id": observation,
        }
    )
    return ActionResult(
        result_id=result_id,
        action_id=action.action_id,
        kind=ResultKind.EVIDENCE_UNAVAILABLE,
        target_dependency_id=action.dependency_id or "",
        observation_id=observation,
        problem_id=state.problem.problem_id,
        run_id=state.problem.run_id,
        source_revision=state.problem.source_revision,
        state_digest=canonical_digest(state.to_dict()),
        physical_infeasibility_claimed=False,
    )


def _ledger(state: MindState, action: CandidateAction) -> ActionResult:
    body = (action.capability_id or "")[len("ledger:") :]
    if "#" not in body:
        raise MindRefusal("REFUSE ACTION")
    capability_id, gate = body.split("#", 1)
    expected = _LEDGER_GATES.get(gate)
    if expected is None or action.action_type is not expected:
        raise MindRefusal("REFUSE ACTION")
    raw, data = _load_ledger()
    names: tuple[str, ...] = ()
    if gate == "identifiability":
        names = _identify_callables(capability_id)
        if names:
            raise MindRefusal("REFUSE ACTION")
        token = "missing"
        module = _IDENTIFY_MODULES[capability_id]
    else:
        token = _gate_token(data, capability_id, gate)
        module = "tools.capability_maturity"
    if "unidentifiable" in token:
        raise MindRefusal("REFUSE ACTION")
    authority_id = canonical_digest(
        {
            "capability_id": capability_id,
            "gate": gate,
            "identify_names": list(names),
            "ledger_sha256": hashlib.sha256(raw).hexdigest(),
            "token": token,
        }
    )
    return _authority(state, action, token, authority_id, module)


def _load_ledger() -> tuple[bytes, dict[str, Any]]:
    import engcore

    path = (
        Path(engcore.__file__).resolve().parents[2]
        / "docs"
        / "project"
        / "scientific_capability_completion.json"
    )
    raw = path.read_bytes()
    try:
        from tools.capability_maturity import load_ledger
    except ImportError:
        data = json.loads(raw)
        if data.get("schema") != _LEDGER_SCHEMA:
            raise MindRefusal("REFUSE ACTION")
        return raw, data
    loaded = load_ledger(path)
    return raw, loaded


def _identify_callables(capability_id: str) -> tuple[str, ...]:
    module_name = _IDENTIFY_MODULES.get(capability_id)
    if module_name is None:
        raise MindRefusal("REFUSE ACTION")
    module = importlib.import_module(module_name)
    return tuple(
        sorted(
            name
            for name in dir(module)
            if name.startswith("identify") and callable(getattr(module, name))
        )
    )


def _gate_token(data: Mapping[str, Any], capability_id: str, gate: str) -> str:
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list):
        raise MindRefusal("REFUSE ACTION")
    matches = [item for item in capabilities if item.get("id") == capability_id]
    if len(matches) != 1:
        raise MindRefusal("REFUSE ACTION")
    gates = matches[0].get("gates")
    if not isinstance(gates, dict) or gate not in gates:
        raise MindRefusal("REFUSE ACTION")
    status = gates[gate].get("status")
    if status == "PASS":
        return "ledger_observed"
    if status == "MISSING":
        return "missing"
    if status == "NOT_APPLICABLE":
        return "not_applicable"
    raise MindRefusal("REFUSE ACTION")


def _nafems(state: MindState, action: CandidateAction) -> ActionResult:
    question = state.hypothesis(state.problem.question_hypothesis_id)
    if question.subject_id != NAFEMS_SUBJECT:
        raise MindRefusal("REFUSE ACTION")
    from engcore.product.nafems_t3 import run_nafems_t3_credibility

    report = run_nafems_t3_credibility(run_id=state.problem.run_id)
    attained = sorted(level.value for level in report.attained_levels)
    missing = sorted(level.value for level in report.missing_required_levels)
    verdict = report.verdict.value
    if "benchmark_validated" in attained and not missing and verdict == "supported":
        token = "benchmark_validated"
    elif verdict == "not_supported":
        token = "not_supported"
    else:
        token = "insufficient_evidence"
    authority_id = canonical_digest(
        {
            "attained": attained,
            "hypothesis_id": question.hypothesis_id,
            "missing_required": missing,
            "run_id": state.problem.run_id,
            "subject_id": question.subject_id,
            "token": token,
            "verdict": verdict,
        }
    )
    return _authority(
        state,
        action,
        token,
        authority_id,
        NAFEMS_MODULE,
    )


def _authority(
    state: MindState,
    action: CandidateAction,
    token: str,
    authority_id: str,
    module: str,
) -> ActionResult:
    dependency = state.dependency(action.dependency_id or "")
    target = state.problem.question_hypothesis_id
    if target not in dependency.blocks:
        raise MindRefusal("REFUSE ACTION")
    return ActionResult(
        result_id=authority_id,
        action_id=action.action_id,
        kind=ResultKind.AUTHORITY_STATUS,
        target_dependency_id=dependency.dependency_id,
        observation_id=authority_id,
        problem_id=state.problem.problem_id,
        run_id=state.problem.run_id,
        source_revision=state.problem.source_revision,
        state_digest=canonical_digest(state.to_dict()),
        physical_infeasibility_claimed=False,
        authority_token=token,
        authority_result_id=authority_id,
        target_hypothesis_id=target,
        producing_module=module,
    )
