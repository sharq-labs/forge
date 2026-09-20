"""Decision-context evaluation over engineering answers and scenario bounds."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..scientific.units.quantity import Quantity

__all__ = ["CONTEXT_SCHEMA", "evaluate_context"]

CONTEXT_SCHEMA = "engineering_context_evaluation/1"
_OPERATORS = {"<=", ">="}
_CREDIBILITY_ORDER = {
    "supported": 0,
    "insufficient_evidence": 1,
    "not_supported": 2,
}


def _credibility(answer: Mapping[str, Any], uncertainty: Mapping[str, Any] | None) -> str:
    if uncertainty and uncertainty.get("scenario_verdicts"):
        return max(
            (item["verdict"] for item in uncertainty["scenario_verdicts"]),
            key=lambda value: _CREDIBILITY_ORDER[value],
        )
    return str(answer.get("verdict"))


def _point_value(answer: Mapping[str, Any], subject: str, quantity: str) -> Quantity:
    for result in answer.get("results", []):
        if result.get("subject") == subject and quantity in result.get("values", {}):
            payload = result["values"][quantity]
            return Quantity(payload["magnitude"], payload["units"])
    raise ValueError(f"answer has no quantity {quantity!r} for subject {subject!r}")


def _bounds(
    answer: Mapping[str, Any], uncertainty: Mapping[str, Any] | None,
    subject: str, quantity: str,
) -> tuple[Quantity, Quantity, str]:
    if uncertainty:
        for interval in uncertainty.get("intervals", []):
            if interval["subject"] == subject and interval["quantity"] == quantity:
                low = interval["lower"]
                high = interval["upper"]
                return (
                    Quantity(low["magnitude"], low["units"]),
                    Quantity(high["magnitude"], high["units"]),
                    interval["method"],
                )
    point = _point_value(answer, subject, quantity)
    return point, point, "point_result"


def evaluate_context(
    answer: Mapping[str, Any],
    criteria: Sequence[Mapping[str, Any]],
    *,
    uncertainty: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate explicit thresholds, separately from evidential credibility."""
    if answer.get("status") != "completed":
        return {
            "schema": CONTEXT_SCHEMA,
            "status": "incomplete",
            "decision": "indeterminate",
            "criteria": [],
            "reason": "The engineering run did not complete.",
        }
    if not criteria:
        raise ValueError("context requires at least one decision criterion")

    evidence_status = _credibility(answer, uncertainty)
    evaluated = []
    for index, criterion in enumerate(criteria):
        subject = str(criterion.get("subject", "")).strip()
        quantity = str(criterion.get("quantity", "")).strip()
        operator = str(criterion.get("operator", "")).strip()
        threshold_text = criterion.get("threshold")
        if not subject or not quantity or operator not in _OPERATORS:
            raise ValueError(
                f"criteria[{index}] requires subject, quantity and operator <= or >="
            )
        if not isinstance(threshold_text, str):
            raise TypeError(f"criteria[{index}].threshold must be a unit-bearing string")
        threshold = Quantity.parse(threshold_text)
        lower, upper, basis = _bounds(answer, uncertainty, subject, quantity)
        threshold_value = threshold.magnitude_in(lower.units)
        low = lower.magnitude_in(lower.units)
        high = upper.magnitude_in(lower.units)
        if operator == "<=":
            numerical = (
                "satisfied" if high <= threshold_value
                else "not_satisfied" if low > threshold_value
                else "indeterminate"
            )
        else:
            numerical = (
                "satisfied" if low >= threshold_value
                else "not_satisfied" if high < threshold_value
                else "indeterminate"
            )
        evaluated.append({
            "criterion_id": str(criterion.get("criterion_id", f"criterion-{index + 1}")),
            "subject": subject,
            "quantity": quantity,
            "operator": operator,
            "threshold": threshold.to_dict(),
            "observed_lower": lower.to_dict(),
            "observed_upper": upper.to_dict(),
            "basis": basis,
            "numerical_status": numerical,
            "evidence_status": evidence_status,
        })

    numerical = {item["numerical_status"] for item in evaluated}
    if evidence_status != "supported":
        decision = "indeterminate_evidence"
    elif "indeterminate" in numerical:
        decision = "indeterminate_uncertainty"
    elif "not_satisfied" in numerical:
        decision = "does_not_meet_context"
    else:
        decision = "meets_context"
    return {
        "schema": CONTEXT_SCHEMA,
        "status": "completed",
        "decision": decision,
        "evidence_status": evidence_status,
        "criteria": evaluated,
        "advisory": True,
        "does_not_mean": (
            "This is not certification or an autonomous engineering decision; "
            "it evaluates caller-declared criteria against recorded evidence."
        ),
    }
