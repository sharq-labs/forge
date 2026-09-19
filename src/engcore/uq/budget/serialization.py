from __future__ import annotations

from typing import Any, Mapping

from engcore.scientific.serialization import require_schema, schema_string
from .component import UncertaintyComponent
from .correlation import Correlation
from .report import UncertaintyBudgetReport
from .source import UncertaintySource

UQ_BUDGET_SCHEMA=schema_string("uncertainty_budget_report")


def budget_to_dict(report:UncertaintyBudgetReport)->dict[str,Any]:
    return {
        "schema":UQ_BUDGET_SCHEMA,
        "components":[{"component_id":c.component_id,"source":c.source.value,
                       "standard_uncertainty":c.standard_uncertainty} for c in report.components],
        "correlations":[{"left_id":c.left_id,"right_id":c.right_id,
                         "coefficient":c.coefficient} for c in report.correlations],
        "aggregate":{"standard_uncertainty":report.aggregate.standard_uncertainty,
                     "variance":report.aggregate.variance},
    }


def budget_from_dict(payload:Mapping[str,Any])->UncertaintyBudgetReport:
    require_schema(payload,UQ_BUDGET_SCHEMA)
    components=tuple(
        UncertaintyComponent(i["component_id"],UncertaintySource(i["source"]),i["standard_uncertainty"])
        for i in payload.get("components",())
    )
    correlations=tuple(
        Correlation(i["left_id"],i["right_id"],i["coefficient"])
        for i in payload.get("correlations",())
    )
    rebuilt=UncertaintyBudgetReport.build(components,correlations)
    declared=payload.get("aggregate") or {}
    if declared:
        if float(declared.get("standard_uncertainty")) != rebuilt.aggregate.standard_uncertainty:
            raise ValueError("serialized uncertainty aggregate does not match its components")
        if float(declared.get("variance")) != rebuilt.aggregate.variance:
            raise ValueError("serialized uncertainty variance does not match its components")
    return rebuilt
