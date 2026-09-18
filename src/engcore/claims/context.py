"""CORE-9 -- context of use: evidence counts only for the decision it was made for.

SRIA already makes ``Evidence.context_ref`` part of an evidence record's content
identity, so a record cannot be re-labelled after the fact. Whether the label is
*the right one* is now the Arbiter's own invariant (audit finding N2): charter-
bound evidence cannot be decided VALID under another charter's policy, and a
policy built with ``obligations_from_charter(..., context_decision_id=...)``
carries a ``REQUIRED_CONTEXT`` obligation naming the exact charter and decision.
The claim layer builds its policy that way.

This module is the claim layer's *earlier*, broader check, reusing existing identity rather
than adding a record: the plan's :class:`~engcore.sria.charter.CampaignCharter`
binds the exact claim identity, QOI, capability, models, case, required levels,
discrepancy declaration and uncertainty demand (its metadata carries the plan's
core digest), and ``charter:<digest>#decision:<id>`` is the one context
reference its evidence may carry. :func:`context_problems` refuses evidence
whose context, subject, run, capability, value or discrepancy is not the plan's
-- before any critic or arbiter sees it.

A typed ContextOfUse record was considered and not added: every field it would
carry is already bound by the charter digest, and a second identity for the
same thing would be a second thing to keep in step.
"""

from __future__ import annotations

from typing import Any

from .errors import ClaimLayerError
from .planning import ExperimentPlan


class ContextBindingError(ClaimLayerError):
    """Evidence was offered to a context it was not produced for."""


def context_problems(evidence: Any, plan: ExperimentPlan, report: Any | None = None) -> tuple[str, ...]:
    """Every way ``evidence`` fails to belong to ``plan``'s context. Empty means it belongs."""
    problems: list[str] = []
    if evidence.context_ref != plan.context_ref:
        problems.append(
            f"the evidence was produced for context {evidence.context_ref!r}, not this plan's {plan.context_ref!r}"
        )
    subject = plan.content["qoi"]["name"]
    if evidence.claim_binding.subject_ref != subject or evidence.claim_binding.subject_kind != "qoi":
        problems.append(f"the evidence is about {evidence.claim_binding.key!r}, not the QOI {subject!r}")
    if evidence.provenance_ref != plan.run_id:
        problems.append(f"the evidence comes from run {evidence.provenance_ref!r}, not the plan's run {plan.run_id!r}")
    expected_pack = f"capability:{plan.capability_id}@{plan.content['capability']['version']}"
    if evidence.domain_pack_ref != expected_pack:
        problems.append(f"the evidence names capability {evidence.domain_pack_ref!r}, not {expected_pack!r}")
    declared = plan.content["evidence_requirements"]["discrepancy"]
    if evidence.uncertainty.discrepancy.to_dict() != declared:
        problems.append("the evidence carries another model-discrepancy declaration than the claim's")
    if report is not None:
        value = report.values.get(subject)
        payload = dict(evidence.claim_payload)
        if value is None or payload.get("value") != value.magnitude or payload.get("units") != str(value.units):
            problems.append("the evidence's value is not the value the plan's report carries")
    return tuple(problems)


def require_context(evidence: Any, plan: ExperimentPlan, report: Any | None = None) -> None:
    problems = context_problems(evidence, plan, report)
    if problems:
        raise ContextBindingError("; ".join(problems))


__all__ = ["ContextBindingError", "context_problems", "require_context"]
