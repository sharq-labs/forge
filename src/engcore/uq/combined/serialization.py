from __future__ import annotations
from typing import Any,Mapping

from engcore.scientific.errors import InvalidScientificProblem
from engcore.scientific.results.uncertainty import Uncertainty
from engcore.scientific.serialization import require_schema,schema_string
from engcore.scientific.units.quantity import Quantity
from engcore.uq.budget import Correlation
from .combine import combine_uncertainties
from .contribution import UncertaintyContribution
from .policy import CombinationMode,CombinationPolicy,MissingCorrelationPolicy
from .report import CombinationReport

COMBINATION_REPORT_SCHEMA=schema_string("combined_uq_report")


def report_to_dict(report:CombinationReport)->dict[str,Any]:
    return {"schema":COMBINATION_REPORT_SCHEMA,"nominal":report.nominal.to_dict(),
        "contributions":[c.to_dict() for c in report.contributions],
        "policy":{"mode":report.policy.mode.value,"missing_correlation":report.policy.missing_correlation.value,
                  "standard_coverage_factor":report.policy.standard_coverage_factor,
                  "required_sources":[x.value for x in report.policy.required_sources]},
        "correlations":[{"left_id":c.left_id,"right_id":c.right_id,"coefficient":c.coefficient} for c in report.correlations],
        "output":report.output.to_dict(),"assumptions":list(report.assumptions)}

def report_from_dict(payload:Mapping[str,Any])->CombinationReport:
    require_schema(payload,COMBINATION_REPORT_SCHEMA)
    p=payload["policy"]
    policy=CombinationPolicy(CombinationMode(p["mode"]),MissingCorrelationPolicy(p["missing_correlation"]),
        p.get("standard_coverage_factor"),tuple(p.get("required_sources",())))
    correlations=tuple(Correlation(x["left_id"],x["right_id"],x["coefficient"]) for x in payload.get("correlations",()))
    rebuilt=combine_uncertainties(Quantity.from_dict(payload["nominal"]),
        tuple(UncertaintyContribution.from_dict(x) for x in payload.get("contributions",())),policy,correlations)
    if rebuilt.output.to_dict()!=payload.get("output"):
        raise InvalidScientificProblem("serialized combined uncertainty output is forged or stale")
    if list(rebuilt.assumptions)!=list(payload.get("assumptions",())):
        raise InvalidScientificProblem("serialized combined uncertainty assumptions are forged or stale")
    return rebuilt
