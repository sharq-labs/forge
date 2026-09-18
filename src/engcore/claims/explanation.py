"""CORE-13 -- the structured scientific explanation of an assessment.

Forge already produces reasons: fired verdict rules, unmet obligations, UNKNOWN
conditions with typed reasons, repair records. They live in five records with
five shapes. An :class:`ExplanationItem` is one of them, typed by what it *is*
for a reader -- a finding, a missing piece of evidence, a model limitation, a
numerical failure, a validity failure, an uncertainty or validation gap, a
caller assumption, a contradiction, a repair action.

**The explanation never creates a fact.** :func:`explain` is a pure function of
the serialized assessment record, and every item carries ``source``: a JSON
pointer into that record at the value it restates. A test resolves every
pointer, so an item that is not backed by a recorded value cannot exist. Prose
in ``message`` is assembled from the pointed-at values and fixed phrases; it
adds no number and no judgement the record does not hold.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping


class ExplanationKind(str, Enum):
    FINDING = "finding"
    MISSING_EVIDENCE = "missing_evidence"
    MODEL_LIMITATION = "model_limitation"
    NUMERICAL_FAILURE = "numerical_failure"
    VALIDITY_FAILURE = "validity_failure"
    UNCERTAINTY_GAP = "uncertainty_gap"
    VALIDATION_GAP = "validation_gap"
    ASSUMPTION = "assumption"
    CONTRADICTION = "contradiction"
    REPAIR_ACTION = "repair_action"


@dataclass(frozen=True)
class ExplanationItem:
    kind: ExplanationKind
    code: str
    message: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "code": self.code, "message": self.message, "source": self.source}


def resolve(record: Mapping[str, Any], pointer: str) -> Any:
    """Follow a JSON pointer (``/a/b/0``) into ``record``. Raises KeyError when it points nowhere."""
    node: Any = record
    if pointer in ("", "/"):
        return node
    for part in pointer.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, Mapping):
            if part not in node:
                raise KeyError(pointer)
            node = node[part]
        elif isinstance(node, (list, tuple)):
            index = int(part)
            if index >= len(node):
                raise KeyError(pointer)
            node = node[index]
        else:
            raise KeyError(pointer)
    return node


_GAP_KIND = {
    "level_unattainable": ExplanationKind.VALIDATION_GAP,
    "channel_unquantified": ExplanationKind.UNCERTAINTY_GAP,
    "discrepancy_unsupported": ExplanationKind.UNCERTAINTY_GAP,
    "applicability_pending": ExplanationKind.FINDING,
    "applicability_at_risk": ExplanationKind.MISSING_EVIDENCE,
}

_STATUS_KIND = {
    "needs_input": ExplanationKind.MISSING_EVIDENCE,
    "ambiguous": ExplanationKind.MISSING_EVIDENCE,
    "unsupported_capability": ExplanationKind.MODEL_LIMITATION,
    "refused": ExplanationKind.FINDING,
}


def _each(items: Iterable[Any]) -> Iterable[tuple[int, Any]]:
    return enumerate(items or ())


def explain(record: Mapping[str, Any]) -> tuple[ExplanationItem, ...]:
    """Organize what an assessment record already says. Deterministic, record order."""
    out: list[ExplanationItem] = []

    def add(kind: ExplanationKind, code: str, message: str, source: str) -> None:
        out.append(ExplanationItem(kind, code, message, source))

    compiled = record.get("compilation") or {}
    status = compiled.get("status")
    if status and status != "ready":
        for i, reason in _each(compiled.get("reasons")):
            add(_STATUS_KIND[status], f"compile.{status}", reason, f"/compilation/reasons/{i}")
    selection = compiled.get("selection") or {}
    chosen = selection.get("selected") is not None
    for c, candidate in _each(selection.get("candidates")):
        for r, rejection in _each(candidate.get("rejections")):
            # A rejected alternative is a finding when another candidate was
            # chosen; it is the claim's own failure only when nothing was.
            kind = (
                ExplanationKind.FINDING
                if chosen
                else ExplanationKind.VALIDITY_FAILURE
                if rejection["reason"] in ("outside_validity", "validity_unassessable")
                else ExplanationKind.MODEL_LIMITATION
            )
            add(kind, f"selection.{rejection['reason']}", f"{candidate['capability_id']}: {rejection['detail']}",
                f"/compilation/selection/candidates/{c}/rejections/{r}")
        if candidate.get("status") == "selected":
            for m, model in _each(candidate.get("models")):
                for a, text in _each(model.get("assumptions")):
                    add(ExplanationKind.MODEL_LIMITATION, "model.assumption", f"{model['model_id']}@{model['version']} assumes: {text}",
                        f"/compilation/selection/candidates/{c}/models/{m}/assumptions/{a}")
                for e, text in _each(model.get("exclusions")):
                    add(ExplanationKind.MODEL_LIMITATION, "model.exclusion", f"{model['model_id']}@{model['version']} excludes: {text}",
                        f"/compilation/selection/candidates/{c}/models/{m}/exclusions/{e}")
    # Predictions speak only until the run does: once there is a report, what it
    # observed replaces what the declarations predicted.
    if record.get("credibility") is None:
        for g, gap in _each(compiled.get("predicted_gaps")):
            add(_GAP_KIND[gap["kind"]], f"predicted.{gap['kind']}", gap["detail"], f"/compilation/predicted_gaps/{g}")

    claim = record.get("claim") or {}
    for a, assumption in _each(claim.get("assumptions")):
        add(ExplanationKind.ASSUMPTION, "caller.assumption",
            f"stated by the caller, not evidence: {assumption['statement']}", f"/claim/assumptions/{a}")
    discrepancy = claim.get("discrepancy")
    if discrepancy:
        if discrepancy["kind"] == "unknown":
            add(ExplanationKind.UNCERTAINTY_GAP, "discrepancy.unknown",
                "model-form discrepancy is UNKNOWN: not quantified, and never read as zero", "/claim/discrepancy/kind")
        else:
            add(ExplanationKind.ASSUMPTION, f"discrepancy.{discrepancy['kind']}",
                f"model-form discrepancy declared {discrepancy['kind']} by the caller: {discrepancy['rationale']}",
                "/claim/discrepancy/kind")

    plan = record.get("plan") or {}
    content = plan.get("content") or {}
    for n, path in _each(content.get("system_defaulted_numerics")):
        add(ExplanationKind.MODEL_LIMITATION, "numerics.system_default",
            f"{path} was not stated; the system chose its own value", f"/plan/content/system_defaulted_numerics/{n}")

    execution = record.get("execution") or {}
    if execution.get("outcome") == "refused_by_system":
        add(ExplanationKind.NUMERICAL_FAILURE, "execution.refused", str(execution.get("failure")), "/execution/failure")
    for b, problem in _each(execution.get("binding_problems")):
        add(ExplanationKind.NUMERICAL_FAILURE, "execution.unbound", problem, f"/execution/binding_problems/{b}")

    for v, model in _each(record.get("validity")):
        for w, name in _each(model.get("violated")):
            add(ExplanationKind.VALIDITY_FAILURE, "validity.violated",
                f"{model['model_id']}@{model['version']} violates {name}: the run is outside where the model holds",
                f"/validity/{v}/violated/{w}")
        for u, unknown in _each(model.get("unknown")):
            add(ExplanationKind.MISSING_EVIDENCE, f"validity.unknown.{unknown['reason']}",
                f"{model['model_id']}@{model['version']}: {unknown['condition']} is UNKNOWN ({unknown['reason']})",
                f"/validity/{v}/unknown/{u}")

    verification = record.get("verification") or {}
    for k, check in _each(verification.get("checks")):
        if check["outcome"] == "fail":
            add(ExplanationKind.NUMERICAL_FAILURE, "check.failed", f"check {check['name']} failed", f"/verification/checks/{k}")
        elif check["outcome"] == "not_run":
            add(ExplanationKind.MISSING_EVIDENCE, "check.not_run", f"check {check['name']} did not run", f"/verification/checks/{k}")
    for a, level in _each(verification.get("attained")):
        add(ExplanationKind.FINDING, "verification.attained", f"attained {level} (verification: the equations were solved as stated)",
            f"/verification/attained/{a}")

    validation = record.get("validation") or {}
    for a, level in _each(validation.get("attained")):
        add(ExplanationKind.FINDING, "validation.attained", f"attained {level} (validation against external evidence)",
            f"/validation/attained/{a}")
    if validation.get("evidence_basis") == "VERIFICATION_ONLY":
        add(ExplanationKind.VALIDATION_GAP, "validation.verification_only",
            "the evidence is verification only: nothing here compares the model with reality", "/validation/evidence_basis")
    for m, level in _each(validation.get("missing_required")):
        add(ExplanationKind.VALIDATION_GAP, "validation.required_level_missing",
            f"the decision requires {level}, which this run did not attain", f"/validation/missing_required/{m}")

    uncertainty = record.get("uncertainty") or {}
    reported = uncertainty.get("reported")
    if reported is not None and reported.get("kind") == "unknown":
        add(ExplanationKind.UNCERTAINTY_GAP, "uncertainty.reported_unknown",
            "the reported value's uncertainty is UNKNOWN; it is not zero", "/uncertainty/reported/kind")
    if uncertainty.get("evidence_problem") and not record.get("context_problems"):
        add(ExplanationKind.UNCERTAINTY_GAP, "uncertainty.not_transportable", uncertainty["evidence_problem"], "/uncertainty/evidence_problem")
    transport = uncertainty.get("transport") or {}
    for i, item in _each(transport.get("records")):
        if item["state"] in ("unattributed", "mixture"):
            add(ExplanationKind.UNCERTAINTY_GAP, f"uncertainty.{item['state']}",
                f"the reported {item['name']} uncertainty is quantified but {item['state']}: it is filed under no "
                f"channel, and no channel it might belong to is counted as known",
                f"/uncertainty/transport/records/{i}/state")
    for c, problem in _each(record.get("context_problems")):
        add(ExplanationKind.NUMERICAL_FAILURE, "context.foreign_evidence", problem, f"/context_problems/{c}")
    for o, oracle in _each(record.get("external_evidence")):
        if not oracle["trusted"]:
            continue
        add(ExplanationKind.FINDING, f"external_evidence.{oracle['applicability']}",
            f"trusted {oracle['kind']} {oracle['oracle_id']}@{oracle['version']} for {oracle['metric']} can establish "
            f"{oracle['establishes']}; it applies to this claim's stated conditions: {oracle['applicability']}",
            f"/external_evidence/{o}/applicability")

    assurance = record.get("assurance") or {}
    for o, obligation in _each(assurance.get("unmet_obligations")):
        kind = (
            ExplanationKind.VALIDATION_GAP if "validation_level" in obligation
            else ExplanationKind.UNCERTAINTY_GAP if obligation.startswith("uncertainty")
            else ExplanationKind.MISSING_EVIDENCE
        )
        add(kind, "assurance.unmet", f"assurance obligation not met: {obligation}", f"/assurance/unmet_obligations/{o}")
    if assurance.get("discrepancy_check"):
        check = assurance["discrepancy_check"]
        if check["outcome"] != "pass":
            add(ExplanationKind.UNCERTAINTY_GAP, "assurance.discrepancy_unsupported", check["detail"], "/assurance/discrepancy_check/detail")

    credibility = record.get("credibility") or {}
    if credibility.get("verdict"):
        add(ExplanationKind.FINDING, f"credibility.{credibility['verdict']}",
            f"the run's credibility report is {credibility['verdict']}", "/credibility/verdict")

    comparison = record.get("comparison")
    admissible = (record.get("basis") or {}).get("admissible")
    if comparison:
        outcome = comparison["outcome"]
        if outcome == "violated" and admissible:
            add(ExplanationKind.CONTRADICTION, "comparison.violated",
                "admissible evidence violates the claim's comparison", "/comparison/outcome")
        elif outcome == "violated":
            add(ExplanationKind.FINDING, "comparison.violated_inadmissible",
                "the reported value violates the comparison, but the evidence does not meet the claim's bar: this is not a contradiction",
                "/comparison/outcome")
        elif outcome == "satisfied":
            add(ExplanationKind.FINDING, "comparison.satisfied", "the reported value satisfies the claim's comparison", "/comparison/outcome")
        elif outcome == "undecided":
            add(ExplanationKind.UNCERTAINTY_GAP, "comparison.undecided",
                "the uncertainty band contains the decision boundary", "/comparison/outcome")
        else:
            add(ExplanationKind.UNCERTAINTY_GAP, "comparison.not_evaluated",
                "a demanded uncertainty channel is unusable; no band could be formed", "/comparison/outcome")
    add(ExplanationKind.FINDING, "verdict", f"claim verdict: {record.get('verdict')}", "/verdict")

    for r, repair in _each(record.get("repair_actions")):
        add(ExplanationKind.REPAIR_ACTION, f"repair.{repair['kind']}", f"{repair['target']}: {repair['reason']}", f"/repair_actions/{r}")
    return tuple(out)


__all__ = ["ExplanationItem", "ExplanationKind", "explain", "resolve"]
