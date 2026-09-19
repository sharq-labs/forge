from __future__ import annotations

from typing import Any, Mapping

from engcore.scientific.serialization import require_schema, schema_string
from .attempt import AttemptState, SimulationAttempt
from .report import OrchestrationReport

ORCHESTRATION_REPORT_SCHEMA=schema_string("simulation_orchestration_report")


def orchestration_to_dict(report:OrchestrationReport)->dict[str,Any]:
    return {
        "schema":ORCHESTRATION_REPORT_SCHEMA,
        "attempts":[{"attempt_id":a.attempt_id,"state":a.state.value,
                     "refinement_level":a.refinement_level,
                     "failure_code":a.failure_code} for a in report.attempts],
        "converged":report.converged,
    }


def orchestration_from_dict(payload:Mapping[str,Any])->OrchestrationReport:
    require_schema(payload,ORCHESTRATION_REPORT_SCHEMA)
    report=OrchestrationReport(tuple(
        SimulationAttempt(i["attempt_id"],AttemptState(i["state"]),
                          i.get("refinement_level",0),i.get("failure_code",""))
        for i in payload.get("attempts",())
    ))
    if "converged" in payload and bool(payload["converged"]) != report.converged:
        raise ValueError("serialized orchestration convergence does not match attempts")
    return report
