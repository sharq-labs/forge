"""Phase 6 -- the next best experiment: the smallest declared action that could close a gap.

Given an assessment record and the capability registry, propose actions --
each derived from one or more gaps (:mod:`.gaps`) and from what the registry
*declares* it can do: a refinement study, perturbable inputs, a route and the
input that activates it, a trusted oracle's operating point, an attainable
level. Nothing is invented and no language model is consulted: an action no
declaration supports is reported as requiring work outside Forge
(``executable_by_forge = False``), and a gap nothing addresses is listed as
unaddressed.

A recommendation **does not guarantee support**. It names the gaps it
addresses and the evidence it would produce; whether that evidence supports the
claim is decided when it exists.

Ranking, "smallest first": Forge-executable before external; blocking gaps
before non-blocking; fewer executions first; more gaps addressed first; then a
fixed action order -- deterministic, so two readers of one record get one plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ._records import tagged_digest
from .capabilities import CapabilityRegistry, declared_path
from .gaps import EvidenceGapAnalysis, GapClass, analyze_gaps
from .parameter_uq import minimum_samples

_TAG = "crafty.claims.next_experiment/1"


class ExperimentAction(str, Enum):
    PROVIDE_INPUT = "provide_input"
    ESTABLISH_APPLICABILITY = "establish_applicability"
    MOVE_OPERATING_POINT = "move_operating_point"
    REFINE_DISCRETIZATION = "refine_discretization"
    DECLARE_INPUT_DISTRIBUTIONS = "declare_input_distributions"
    SENSITIVITY_ANALYSIS = "sensitivity_analysis"
    RUN_INDEPENDENT_ROUTE = "run_independent_route"
    TEST_AT_BENCHMARK_POINT = "test_at_benchmark_point"
    COLLECT_MEASUREMENT = "collect_measurement"
    OBTAIN_BENCHMARK_EVIDENCE = "obtain_benchmark_evidence"
    QUANTIFY_MODEL_FORM = "quantify_model_form"
    REASSESS_UNDER_PLAN = "reassess_under_plan"
    RESTATE_CLAIM = "restate_claim"
    EXTEND_CAPABILITY = "extend_capability"


@dataclass(frozen=True)
class ExperimentRecommendation:
    action: ExperimentAction
    target: str
    addresses_gaps: tuple[str, ...]
    required_capability: str | None
    expected_evidence_type: str
    executable_by_forge: bool
    executions: int | None
    cost_class: str | None
    reason: str
    source: str
    addresses_blocking: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "target": self.target,
            "addresses_gaps": list(self.addresses_gaps),
            "required_capability": self.required_capability,
            "expected_evidence_type": self.expected_evidence_type,
            "executable_by_forge": self.executable_by_forge,
            "executions": self.executions,
            "cost_class": self.cost_class,
            "reason": self.reason,
            "source": self.source,
            "addresses_blocking": self.addresses_blocking,
            "guarantees_support": False,
        }


@dataclass(frozen=True)
class NextExperimentPlan:
    recommendations: tuple[ExperimentRecommendation, ...]
    unaddressed_gaps: tuple[str, ...]
    analysis_digest: str

    @property
    def first(self) -> ExperimentRecommendation | None:
        return self.recommendations[0] if self.recommendations else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendations": [r.to_dict() for r in self.recommendations],
            "unaddressed_gaps": list(self.unaddressed_gaps),
            "analysis_digest": self.analysis_digest,
            "notice": "each recommendation addresses named evidence gaps; none guarantees that the claim will be supported",
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_TAG, self.to_dict())


def _capability(record: Mapping[str, Any], registry: CapabilityRegistry):
    ref = (record.get("compilation") or {}).get("capability")
    if not ref or ref["capability_id"] not in registry:
        return None
    declaration = registry.get(ref["capability_id"])
    return declaration if declaration.digest == ref["digest"] else None


def _stated(record: Mapping[str, Any]) -> dict[str, Any]:
    claim = record.get("claim") or {}
    out = dict(claim.get("known_inputs") or {})
    out.update(claim.get("operating_context") or {})
    return out


def recommend_next(record: Mapping[str, Any], registry: CapabilityRegistry, analysis: EvidenceGapAnalysis | None = None) -> NextExperimentPlan:
    analysis = analysis or analyze_gaps(record)
    declaration = _capability(record, registry)
    cap_id = None if declaration is None else declaration.capability_id
    qoi = ((record.get("claim") or {}).get("qoi") or {}).get("name")
    recs: list[ExperimentRecommendation] = []
    addressed: set[str] = set()

    def add(action, target, gaps, *, capability=cap_id, evidence, forge, executions, reason, source, cost=None):
        blocking = any(g.blocking for g in gaps)
        recs.append(ExperimentRecommendation(action, str(target), tuple(g.gap_id for g in gaps), capability, evidence,
                                             forge, executions, cost, reason, source, blocking))
        addressed.update(g.gap_id for g in gaps)

    repairs = record.get("repair_actions") or []

    for gap in analysis.of_kind(GapClass.MISSING_INPUT):
        add(ExperimentAction.PROVIDE_INPUT, gap.target, [gap], evidence=f"input:{gap.target}", forge=True, executions=1,
            reason=gap.reason, source=gap.source)
    for gap in analysis.of_kind(GapClass.INPUT_INVALID) + analysis.of_kind(GapClass.CLAIM_AMBIGUOUS) + analysis.of_kind(GapClass.CLAIM_REFUSED):
        add(ExperimentAction.RESTATE_CLAIM, gap.target, [gap], evidence="claim", forge=False, executions=None,
            reason=gap.reason, source=gap.source)
    for gap in analysis.of_kind(GapClass.CAPABILITY_MISSING):
        add(ExperimentAction.EXTEND_CAPABILITY, gap.target, [gap], capability=None, evidence="capability_declaration", forge=False,
            executions=None, reason=gap.reason, source=gap.source)
    for gap in analysis.of_kind(GapClass.CONTEXT_MISMATCH):
        add(ExperimentAction.REASSESS_UNDER_PLAN, gap.target, [gap], evidence="simulation", forge=True, executions=1,
            reason="evidence must be produced under this claim's own plan: " + gap.reason, source=gap.source)

    for gap in analysis.of_kind(GapClass.MODEL_APPLICABILITY_UNKNOWN):
        paths = [(i, r) for i, r in enumerate(repairs) if r["kind"] == "supply_validity_evidence" and any(gap.target in q for q in r["required_for"])]
        if paths:
            for i, repair in paths:
                add(ExperimentAction.ESTABLISH_APPLICABILITY, repair["target"], [gap], evidence=f"input:{repair['target']}", forge=True,
                    executions=1, reason=f"{repair['reason']} (unlocks the applicability of {gap.target})", source=f"/repair_actions/{i}")
        elif declaration is not None and declaration.unassessable(gap.target):
            reasons = dict(declaration.unassessable(gap.target))
            add(ExperimentAction.EXTEND_CAPABILITY, gap.target, [gap], capability=None, evidence="capability_declaration", forge=False,
                executions=None, reason=f"{cap_id} can never assess {sorted(reasons)}: {'; '.join(reasons.values())}",
                source=f"capability:{cap_id}#unassessable_conditions")
    for gap in analysis.of_kind(GapClass.MODEL_OUTSIDE_DOMAIN):
        moves = [
            (i, r) for i, r in enumerate(repairs)
            if r["kind"] == "move_inside_validity"
            and (r["target"].startswith(gap.target) or any(gap.target in q for q in r["required_for"]))
        ]
        # A compile-time rejection names its candidate in the gap's source; the move is executable by that capability.
        owner = cap_id
        if owner is None and gap.source.startswith("/compilation/selection/candidates/"):
            index = int(gap.source.split("/")[4])
            owner = record["compilation"]["selection"]["candidates"][index]["capability_id"]
        for i, repair in moves:
            add(ExperimentAction.MOVE_OPERATING_POINT, repair["target"], [gap], capability=owner, evidence="simulation",
                forge=owner is not None and owner in registry, executions=1, reason=repair["reason"], source=f"/repair_actions/{i}")

    for gap in analysis.of_kind(GapClass.NUMERICAL_UQ_MISSING) + analysis.of_kind(GapClass.UNCERTAINTY_BAND_STRADDLES):
        if gap.kind is GapClass.UNCERTAINTY_BAND_STRADDLES and not _dominant(record, "numerical"):
            continue
        study = None if declaration is None else declaration.refinement
        if study is not None and qoi in study.quantities:
            finer = {path: value * study.ratio for path, value in _baseline(record, study).items()}
            add(ExperimentAction.REFINE_DISCRETIZATION, "numerics", [gap], evidence="uncertainty:numerical", forge=True,
                executions=study.levels,
                reason=(f"restate the numerics one level finer ({finer}): the declared {study.levels}-level ladder then "
                        f"moves into a finer range; {gap.reason}"),
                source=f"capability:{cap_id}#refinement")
        else:
            others = [d.capability_id for d in registry.producing(qoi or "") if d.refinement is not None and qoi in d.refinement.quantities]
            if others:
                add(ExperimentAction.REFINE_DISCRETIZATION, "numerics", [gap], capability=others[0], evidence="uncertainty:numerical",
                    forge=True, executions=None, reason=f"{others[0]} declares a refinement study for {qoi}", source=f"capability:{others[0]}#refinement")
            else:
                add(ExperimentAction.EXTEND_CAPABILITY, "refinement_study", [gap], capability=None, evidence="uncertainty:numerical",
                    forge=False, executions=None, reason=f"no registered capability declares a refinement study for {qoi}: {gap.reason}",
                    source="/compilation/capability")

    for gap in analysis.of_kind(GapClass.PARAMETER_UQ_MISSING) + analysis.of_kind(GapClass.UNCERTAINTY_BAND_STRADDLES):
        if gap.kind is GapClass.UNCERTAINTY_BAND_STRADDLES and not _dominant(record, "epistemic_parameter"):
            continue
        stated = _stated(record)
        perturbable = [] if declaration is None else [
            path for path in sorted(stated) if declared_path(path) in {p.path for p in declaration.perturbable}
        ]
        if perturbable:
            action = ExperimentAction.DECLARE_INPUT_DISTRIBUTIONS if gap.kind is GapClass.PARAMETER_UQ_MISSING else ExperimentAction.SENSITIVITY_ANALYSIS
            add(action, ",".join(perturbable), [gap], evidence="uncertainty:epistemic_parameter" if action is ExperimentAction.DECLARE_INPUT_DISTRIBUTIONS else "sensitivity",
                forge=True, executions=minimum_samples() if action is ExperimentAction.DECLARE_INPUT_DISTRIBUTIONS else 2 * len(perturbable) + 1,
                reason=(f"{cap_id} accepts perturbed values at {perturbable}; "
                        + ("declare their distributions (a caller statement with its rationale) and the channel is propagated"
                           if action is ExperimentAction.DECLARE_INPUT_DISTRIBUTIONS
                           else "find which input dominates the band before narrowing its declared uncertainty")),
                source=f"capability:{cap_id}#perturbable")
        elif gap.kind is GapClass.PARAMETER_UQ_MISSING:
            add(ExperimentAction.EXTEND_CAPABILITY, "perturbable_inputs", [gap], capability=None, evidence="uncertainty:epistemic_parameter",
                forge=False, executions=None, reason=f"{cap_id} declares no perturbable input the claim states", source="/compilation/capability")

    for gap in analysis.of_kind(GapClass.MEASUREMENT_UQ_MISSING):
        add(ExperimentAction.COLLECT_MEASUREMENT, qoi, [gap], capability=None, evidence="measurement", forge=False, executions=None,
            reason="an aleatoric channel is quantified only by a measurement's own uncertainty: " + gap.reason, source=gap.source)
    for gap in analysis.of_kind(GapClass.MODEL_FORM_UNCERTAINTY_UNKNOWN):
        add(ExperimentAction.QUANTIFY_MODEL_FORM, gap.target, [gap], capability=None, evidence="uncertainty:model_form", forge=False,
            executions=None, reason="model-form discrepancy needs validation data and a constrained, referenced prior: " + gap.reason,
            source=gap.source)

    routes = (((record.get("plan") or {}).get("content") or {}).get("routes")) or []
    for gap in analysis.of_kind(GapClass.INDEPENDENT_ROUTE_MISSING) + analysis.of_kind(GapClass.VALIDATION_LEVEL_MISSING):
        target_level = gap.target if gap.kind is GapClass.VALIDATION_LEVEL_MISSING else None
        inactive = [
            r for r in routes
            if r["route_class"] in ("independent", "analytic_reference", "benchmark", "experimental") and not r["active"]
            and (target_level is None or r["could_establish"] == target_level)
        ]
        closer = [r for r in inactive if r["attainable_here"]]
        if closer:
            route = closer[0]
            decl_route = None if declaration is None else declaration.route(route["route_id"])
            activation = [] if decl_route is None else list(decl_route.activation)
            add(ExperimentAction.RUN_INDEPENDENT_ROUTE, route["route_id"], [gap], evidence=f"level:{route['could_establish']}", forge=True,
                executions=1, reason=f"state {activation} to activate {route['route_id']}: {route['reason']}", source="/plan/content/routes")
            continue
        oracles = [(i, m) for i, m in enumerate(record.get("external_evidence") or []) if m["trusted"] and m["applicability"] != "exact"
                   and (target_level is None or m["establishes"] == target_level)]
        if oracles:
            i, match = oracles[0]
            add(ExperimentAction.TEST_AT_BENCHMARK_POINT, match["oracle_id"], [gap], evidence=f"level:{match['establishes']}", forge=True,
                executions=1, reason=(f"the trusted oracle {match['oracle_id']} speaks only at its own conditions "
                                      f"(mismatched {match['mismatched']}, unstated {match['unstated']}); a run there tests the model, "
                                      f"not this claim's operating point"), source=f"/external_evidence/{i}")
        elif target_level in (None, "experimentally_validated") or gap.kind is GapClass.INDEPENDENT_ROUTE_MISSING:
            add(ExperimentAction.COLLECT_MEASUREMENT, qoi, [gap], capability=None, evidence="measurement", forge=False, executions=None,
                reason="no declared route can close this; a curated, pinned measurement at the claim's conditions could: " + gap.reason,
                source=gap.source)
        else:
            add(ExperimentAction.OBTAIN_BENCHMARK_EVIDENCE, qoi, [gap], capability=None, evidence="benchmark", forge=False, executions=None,
                reason="no declared route attains this level; a trusted benchmark for this QOI would need to be pinned: " + gap.reason,
                source=gap.source)
    for gap in analysis.of_kind(GapClass.EXTERNAL_EVIDENCE_MISSING):
        add(ExperimentAction.COLLECT_MEASUREMENT, qoi, [gap], capability=None, evidence="measurement", forge=False, executions=None,
            reason="validation evidence compares the model with something outside it: " + gap.reason, source=gap.source)

    order = list(ExperimentAction)
    unique: dict[tuple, ExperimentRecommendation] = {}
    for r in recs:
        key = (r.action, r.target, r.required_capability)
        if key in unique:
            merged = tuple(sorted(set(unique[key].addresses_gaps) | set(r.addresses_gaps)))
            unique[key] = ExperimentRecommendation(r.action, r.target, merged, r.required_capability, r.expected_evidence_type,
                                                   r.executable_by_forge, r.executions, r.cost_class, unique[key].reason, unique[key].source,
                                                   unique[key].addresses_blocking or r.addresses_blocking)
        else:
            unique[key] = r
    ranked = sorted(
        unique.values(),
        key=lambda r: (not r.executable_by_forge, not r.addresses_blocking, r.executions if r.executions is not None else 10**9,
                       -len(r.addresses_gaps), order.index(r.action), r.target),
    )
    unaddressed = tuple(g.gap_id for g in analysis.gaps if g.gap_id not in addressed and g.blocking)
    return NextExperimentPlan(tuple(ranked), unaddressed, analysis.digest)


def _baseline(record: Mapping[str, Any], study: Any) -> dict[str, int]:
    stated = _stated(record)
    return {path: stated.get(path, default) if isinstance(stated.get(path, default), int) else default
            for path, default in study.refined_inputs.items()}


def _dominant(record: Mapping[str, Any], channel: str) -> bool:
    """Whether ``channel`` carries the widest usable half-width in the claim's band."""
    uses = [c for c in ((record.get("comparison") or {}).get("channels") or []) if c["usable"]]
    if not uses:
        return False
    widest = max(uses, key=lambda c: max(c["lower_half_width"], c["upper_half_width"]))
    return widest["channel"] == channel


__all__ = ["ExperimentAction", "ExperimentRecommendation", "NextExperimentPlan", "recommend_next"]
