"""A deterministic engineering-facing view of an evidence response.

The view computes no physics and upgrades no verdict.  It groups facts already
present in a run response so a reader need not reverse-engineer the wire
format to find the answer, its applicability boundary, uncertainty status and
evidence.  The original response remains attached verbatim.
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = ["ANSWER_SCHEMA", "summarize_engineering_run"]

ANSWER_SCHEMA = "engineering_answer/1"
_VERDICT_ORDER = {
    "supported": 0,
    "insufficient_evidence": 1,
    "not_supported": 2,
}


def _report_view(
    *, subject: str, verdict: Mapping[str, Any], report: Mapping[str, Any]
) -> dict[str, Any]:
    validity = report.get("validity", [])
    boundaries = []
    exclusions = []
    for record in validity:
        assessment = record["assessment"]
        boundaries.append({
            "model_id": record["model_id"],
            "version": record["version"],
            "status": assessment["status"],
            "satisfied": assessment.get("satisfied", []),
            "violated": assessment.get("violated", []),
            "unknown": assessment.get("unknown", []),
            "unknown_reasons": assessment.get("unknown_reasons", []),
        })
        exclusions.extend(
            {"model_id": record["model_id"], "exclusion": item}
            for item in record.get("exclusions", [])
        )

    checks = report.get("validation", [])
    return {
        "subject": subject,
        "verdict": dict(verdict),
        "values": dict(report.get("values", {})),
        # This report schema carries no uncertainty record. Saying so is
        # materially different from returning an empty interval that a caller
        # might read as zero uncertainty.
        "uncertainty": {
            "status": "not_quantified",
            "reason": (
                "This credibility report carries no predictive uncertainty "
                "record for these values. Do not interpret absence as zero."
            ),
            "intervals": [],
        },
        "applicability": {
            "models": boundaries,
            "violated": [
                {"model_id": item["model_id"], "conditions": item["violated"]}
                for item in boundaries if item["violated"]
            ],
            "unknown": [
                {"model_id": item["model_id"], "conditions": item["unknown"]}
                for item in boundaries if item["unknown"]
            ],
            "exclusions": exclusions,
        },
        "evidence": {
            "run_id": report.get("run_id"),
            "report_schema": report.get("schema"),
            "contributing_models": report.get("contributing_models", []),
            "checks": checks,
            "established_levels": sorted({
                check["establishes"] for check in checks
                if check.get("outcome") == "pass" and check.get("establishes")
            }),
            "provenance": report.get("provenance", []),
        },
    }


def summarize_engineering_run(run: Mapping[str, Any]) -> dict[str, Any]:
    """Create one stable answer envelope from ``run_engineering_problem``."""
    status = run.get("status")
    if status != "completed":
        intent = run.get("intent") or {}
        questions = intent.get("questions")
        if questions is None and isinstance(intent.get("intent"), Mapping):
            questions = intent["intent"].get("questions")
        return {
            "schema": ANSWER_SCHEMA,
            "status": status,
            "system": None,
            "verdict": None,
            "results": [],
            "questions": questions or [],
            "message": "No simulation ran because the engineering intent is incomplete.",
            "execution": dict(run),
        }

    response = run["result"]
    if response["system"] == "electrothermal":
        results = [
            _report_view(
                subject=stage["component_id"],
                verdict=stage["verdict"],
                report=stage["report"],
            )
            for stage in response["stages"]
        ]
    else:
        results = [_report_view(
            subject="battery",
            verdict=response["verdict"],
            report=response["report"],
        )]

    aggregate = max(
        (item["verdict"]["value"] for item in results),
        key=lambda value: _VERDICT_ORDER[value],
    )
    return {
        "schema": ANSWER_SCHEMA,
        "status": "completed",
        "system": response["system"],
        "verdict": aggregate,
        "results": results,
        "questions": [],
        "message": (
            "Read each result's verdict, applicability, uncertainty and "
            "evidence before relying on its values."
        ),
        # Verbatim audit path. The answer is a view, never a replacement for
        # the record that justified it.
        "execution": dict(run),
    }
