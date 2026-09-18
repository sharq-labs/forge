"""Phase 5 -- evidence gap analysis: exactly why a claim is not decided.

``INSUFFICIENT_EVIDENCE`` is an answer, but not an explanation. This module
reads an assessment record -- nothing else -- and names every gap, each with
the JSON pointer of the authoritative field that caused it. It adds no facts:
every reason is assembled from values the record already carries.

Two consistency rules make the analysis checkable:

* an INSUFFICIENT_EVIDENCE verdict has at least one *blocking* gap;
* a SUPPORTED or CONTRADICTED verdict has none.

A record that breaks either is reported as ``complete = False`` with an
``UNEXPLAINED`` gap, never silently: an unexplained insufficiency is a defect
in this analysis, not a property of the claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ._records import tagged_digest

_TAG = "crafty.claims.evidence_gaps/1"


class GapClass(str, Enum):
    # The claim itself
    MISSING_INPUT = "missing_input"
    INPUT_INVALID = "input_invalid"
    CLAIM_AMBIGUOUS = "claim_ambiguous"
    CLAIM_REFUSED = "claim_refused"
    CAPABILITY_MISSING = "capability_missing"
    # The run
    EXECUTION_REFUSED = "execution_refused"
    BINDING_PROBLEM = "binding_problem"
    CONTEXT_MISMATCH = "context_mismatch"
    EVIDENCE_NOT_ASSEMBLED = "evidence_not_assembled"
    # Applicability and checks
    MODEL_APPLICABILITY_UNKNOWN = "model_applicability_unknown"
    MODEL_OUTSIDE_DOMAIN = "model_outside_domain"
    CHECK_FAILED = "check_failed"
    CHECK_NOT_RUN = "check_not_run"
    VALIDATION_LEVEL_MISSING = "validation_level_missing"
    # Uncertainty
    NUMERICAL_UQ_MISSING = "numerical_uq_missing"
    PARAMETER_UQ_MISSING = "parameter_uq_missing"
    MEASUREMENT_UQ_MISSING = "measurement_uq_missing"
    MODEL_FORM_UNCERTAINTY_UNKNOWN = "model_form_uncertainty_unknown"
    UNCERTAINTY_BAND_STRADDLES = "uncertainty_band_straddles"
    # Policy and assurance
    EXTERNAL_EVIDENCE_MISSING = "external_evidence_missing"
    INDEPENDENT_ROUTE_MISSING = "independent_route_missing"
    ASSURANCE_OBLIGATION_UNMET = "assurance_obligation_unmet"
    # Recorded, not blocking
    SOURCE_CLOSURE_INCOMPLETE = "source_closure_incomplete"
    # A defect in this analysis
    UNEXPLAINED = "unexplained"


_CHANNEL_GAP = {
    "numerical": GapClass.NUMERICAL_UQ_MISSING,
    "epistemic_parameter": GapClass.PARAMETER_UQ_MISSING,
    "aleatoric": GapClass.MEASUREMENT_UQ_MISSING,
    "model_form": GapClass.MODEL_FORM_UNCERTAINTY_UNKNOWN,
}


@dataclass(frozen=True)
class EvidenceGap:
    kind: GapClass
    target: str
    blocking: bool
    reason: str
    source: str

    @property
    def gap_id(self) -> str:
        return f"{self.kind.value}:{self.target}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "kind": self.kind.value,
            "target": self.target,
            "blocking": self.blocking,
            "reason": self.reason,
            "source": self.source,
        }


@dataclass(frozen=True)
class EvidenceGapAnalysis:
    verdict: str
    gaps: tuple[EvidenceGap, ...]
    complete: bool

    @property
    def blocking(self) -> tuple[EvidenceGap, ...]:
        return tuple(g for g in self.gaps if g.blocking)

    def of_kind(self, kind: GapClass) -> tuple[EvidenceGap, ...]:
        return tuple(g for g in self.gaps if g.kind is kind)

    def to_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "complete": self.complete, "gaps": [g.to_dict() for g in self.gaps]}

    @property
    def digest(self) -> str:
        return tagged_digest(_TAG, self.to_dict())


def _get(record: Mapping[str, Any], *path: Any) -> Any:
    node: Any = record
    for key in path:
        if node is None:
            return None
        node = node[key] if isinstance(node, list) else node.get(key)
    return node


def analyze_gaps(record: Mapping[str, Any]) -> EvidenceGapAnalysis:
    """Every gap in one assessment record, deduplicated by id, in a deterministic order."""
    gaps: list[EvidenceGap] = []

    def add(kind: GapClass, target: str, reason: str, source: str, blocking: bool = True) -> None:
        gaps.append(EvidenceGap(kind, str(target), blocking, reason, source))

    status = _get(record, "compilation", "status")
    repairs = record.get("repair_actions") or []
    if status != "ready":
        for i, repair in enumerate(repairs):
            kind = repair["kind"]
            if kind in ("supply_input", "resolve_target"):
                add(GapClass.MISSING_INPUT, repair["target"], repair["reason"], f"/repair_actions/{i}")
            elif kind == "remove_unaccepted_input" and status == "unsupported_capability":
                continue  # relative to no selected capability: a consequence of CAPABILITY_MISSING, not a gap of its own
            elif kind in ("correct_input", "remove_unaccepted_input", "restate_claim", "select_instance"):
                add(GapClass.INPUT_INVALID, repair["target"], repair["reason"], f"/repair_actions/{i}")
            elif kind == "extend_capability":
                add(GapClass.CAPABILITY_MISSING, repair["target"], repair["reason"], f"/repair_actions/{i}")
        # A candidate the selection rejected because a stated value lies outside its model's validated domain
        # is not a missing capability: the capability exists, and this operating point is outside it.
        for ci, candidate in enumerate(_get(record, "compilation", "selection", "candidates") or []):
            for mi, model in enumerate(candidate.get("models") or []):
                if model.get("status") == "outside_validated_domain":
                    violated = [c["condition"] for c in model.get("conditions", []) if c.get("outcome") == "violated"]
                    add(GapClass.MODEL_OUTSIDE_DOMAIN, model["model_id"],
                        f"{model['model_id']} (via {candidate['capability_id']}) violates {violated} on the stated inputs",
                        f"/compilation/selection/candidates/{ci}/models/{mi}")
        if status == "ambiguous":
            add(GapClass.CLAIM_AMBIGUOUS, "capability", "; ".join(_get(record, "compilation", "reasons") or []), "/compilation/reasons")
        elif status == "unsupported_capability" and not any(g.kind in (GapClass.CAPABILITY_MISSING, GapClass.MODEL_OUTSIDE_DOMAIN) for g in gaps):
            add(GapClass.CAPABILITY_MISSING, "capability", "; ".join(_get(record, "compilation", "reasons") or []), "/compilation/reasons")
        elif status == "refused" and not gaps:
            add(GapClass.CLAIM_REFUSED, "claim", str(_get(record, "compilation", "claim_error") or "; ".join(_get(record, "compilation", "reasons") or [])), "/compilation")
        elif status == "needs_input" and not any(g.kind is GapClass.MISSING_INPUT for g in gaps):
            for i, name in enumerate(_get(record, "compilation", "missing_inputs") or []):
                add(GapClass.MISSING_INPUT, name, "the claim states this input is unknown", f"/compilation/missing_inputs/{i}")

    execution = record.get("execution")
    if execution is not None:
        if execution.get("outcome") == "refused_by_system":
            add(GapClass.EXECUTION_REFUSED, "execution", str(execution.get("failure")), "/execution/failure")
        for i, problem in enumerate(execution.get("binding_problems") or []):
            add(GapClass.BINDING_PROBLEM, f"binding[{i}]", problem, f"/execution/binding_problems/{i}")
    for i, problem in enumerate(record.get("context_problems") or []):
        add(GapClass.CONTEXT_MISMATCH, f"context[{i}]", problem, f"/context_problems/{i}")
    evidence_problem = _get(record, "uncertainty", "evidence_problem")
    if evidence_problem and not record.get("context_problems"):
        add(GapClass.EVIDENCE_NOT_ASSEMBLED, "evidence", evidence_problem, "/uncertainty/evidence_problem")

    for i, validity in enumerate(record.get("validity") or []):
        model = validity["model_id"]
        if validity["status"] == "unknown":
            conditions = [f"{u['condition']} ({u['reason']})" for u in validity.get("unknown", [])]
            add(GapClass.MODEL_APPLICABILITY_UNKNOWN, model, f"{model} applicability is unknown: {conditions}", f"/validity/{i}/unknown")
        elif validity["status"] == "outside_validated_domain":
            add(GapClass.MODEL_OUTSIDE_DOMAIN, model, f"{model} violates {validity.get('violated')}", f"/validity/{i}/violated")

    for i, check in enumerate(_get(record, "verification", "checks") or []):
        if check["outcome"] == "fail":
            add(GapClass.CHECK_FAILED, check["name"], f"check {check['name']} failed", f"/verification/checks/{i}")
        elif check["outcome"] == "not_run":
            add(GapClass.CHECK_NOT_RUN, check["name"], f"check {check['name']} did not run", f"/verification/checks/{i}")
    for i, level in enumerate(_get(record, "validation", "missing_required") or []):
        add(GapClass.VALIDATION_LEVEL_MISSING, level, f"the decision requires {level} and the run did not attain it", f"/validation/missing_required/{i}")

    channels = _get(record, "uncertainty", "channels") or {}
    demanded = _get(record, "uncertainty", "demanded") or []
    studies = {s["channel"]: (i, s) for i, s in enumerate(record.get("uncertainty_studies") or [])}
    for channel in demanded:
        if channels.get(channel):
            continue
        if channel in studies:
            i, study = studies[channel]
            why = study.get("problem") or study["estimate"].get("failure_reason") or "the study quantified nothing"
            add(_CHANNEL_GAP[channel], channel, f"{channel} demanded; the study left it UNKNOWN: {why}", f"/uncertainty_studies/{i}")
        else:
            step = next((s for s in _get(record, "plan", "steps") or [] if s["step_id"] == f"uncertainty:{channel}"), None)
            why = (step or {}).get("detail", {}).get("unavailable_reason") or "no study quantifies it here"
            add(_CHANNEL_GAP[channel], channel, f"{channel} demanded and UNKNOWN: {why}", f"/uncertainty/channels/{channel}")
    discrepancy = _get(record, "assurance", "discrepancy_check")
    if _get(record, "basis", "discrepancy_supported") is False:
        add(GapClass.MODEL_FORM_UNCERTAINTY_UNKNOWN, "discrepancy", (discrepancy or {}).get("detail", "the demanded discrepancy is not supported"), "/assurance/discrepancy_check")

    for i, finding in enumerate(_get(record, "policy", "findings") or []):
        kind = {
            "validation_evidence": GapClass.EXTERNAL_EVIDENCE_MISSING,
            "independent_route": GapClass.INDEPENDENT_ROUTE_MISSING,
            "applicability": GapClass.MODEL_APPLICABILITY_UNKNOWN,
        }[finding["requirement"]]
        add(kind, finding["requirement"], finding["reason"], f"/policy/findings/{i}")

    covered_prefixes = ("uncertainty:", "confidence:", "context:")
    for i, obligation in enumerate(_get(record, "assurance", "unmet_obligations") or []):
        if not obligation.startswith(covered_prefixes):
            add(GapClass.ASSURANCE_OBLIGATION_UNMET, obligation, f"assurance obligation {obligation} is unmet", f"/assurance/unmet_obligations/{i}")
        elif obligation.startswith("context:"):
            add(GapClass.CONTEXT_MISMATCH, obligation, f"assurance obligation {obligation} is unmet", f"/assurance/unmet_obligations/{i}")

    if _get(record, "comparison", "outcome") == "undecided":
        comparison = record["comparison"]
        add(GapClass.UNCERTAINTY_BAND_STRADDLES, "comparison",
            f"the band [{comparison['band_lower']['magnitude']}, {comparison['band_upper']['magnitude']}] contains the decision boundary",
            "/comparison/outcome")

    evidence = record.get("evidence")
    if evidence is not None and evidence.get("source_closure_complete") is False:
        add(GapClass.SOURCE_CLOSURE_INCOMPLETE, "evidence", "the evidence's source lineage is not closed; independence cannot be established from it",
            "/evidence/source_closure_complete", blocking=False)

    unique: dict[str, EvidenceGap] = {}
    for gap in gaps:
        unique.setdefault(gap.gap_id, gap)
    ordered = tuple(sorted(unique.values(), key=lambda g: (list(GapClass).index(g.kind), g.target)))
    verdict = str(record.get("verdict"))
    blocking = any(g.blocking for g in ordered)
    complete = blocking if verdict == "insufficient_evidence" else not blocking
    if not complete:
        ordered = ordered + (EvidenceGap(
            GapClass.UNEXPLAINED, "verdict", blocking=verdict == "insufficient_evidence",
            reason=f"verdict {verdict} with {'no' if not blocking else 'a'} blocking gap: the analysis does not account for the record",
            source="/basis",
        ),)
    return EvidenceGapAnalysis(verdict, ordered, complete)


__all__ = ["EvidenceGap", "EvidenceGapAnalysis", "GapClass", "analyze_gaps"]
