"""CORE-5 -- the experiment plan: what will be run, checked and decided, before anything runs.

A READY :class:`~engcore.claims.compiler.CompiledClaim` says a claim *can* be
executed. An :class:`ExperimentPlan` says exactly *how*: the capability and its
digest, every model instance and version, the exact case payload, the route
classification, the validity assessments the run must perform, the checks that
would establish each required level, the uncertainty work each demanded channel
needs, the oracle comparisons, the decision charter the evidence will be judged
under -- and a deterministic step graph over all of it.

Planning never executes physics. It reads declarations, the claim, and the
compiled selection; the plan's steps are then carried out by execution, and
provenance binds to the plan's digest so a record can prove which plan it ran.

Identity
--------
``digest`` is a tagged SHA-256 over the plan's scientific content. It includes
the claim's *identity* digest -- not its id or prose -- so the same scientific
request always yields the same plan, and a changed input, target, evidence bar,
decision, discrepancy declaration or capability version yields a different one.
``run_id`` is derived from the plan content, so two executions of one plan are
two runs of one identity rather than two unrelated runs.

The decision charter is built here, deterministically, from the claim and the
plan's core content: its digest is the context identity (CORE-9) every piece of
evidence the plan produces must carry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..scientific.results.immutable import freeze
from ..scientific.results.validation import VALIDATION_LEVELS
from ..scientific.serialization import schema_string
from ..sria.assurance.obligations import charter_context_ref
from ..sria.charter import CampaignCharter, ConfidenceRequirement
from ._records import canonical_json, require_keys, require_mapping, require_schema_exact, tagged_digest
from .capabilities import CapabilityRegistry, InputRole, build_case, declared_path
from .uq_studies import run_inputs_for, study_spec
from .compiler import CompilationStatus, CompiledClaim
from .errors import ClaimLayerError
from .routes import RouteAssessment, RouteClass, assess_routes
from .selection import UnknownBasis

PLAN_SCHEMA = schema_string("experiment_plan")
_TAG = "crafty.claims.experiment_plan/1"
_CORE_TAG = "crafty.claims.experiment_plan.core/1"


class PlanningError(ClaimLayerError):
    """A plan was requested for a claim that cannot be planned, or a plan is forged."""


class StepKind(str, Enum):
    EXECUTE = "execute"
    ASSESS_VALIDITY = "assess_validity"
    VALIDATION_CHECK = "validation_check"
    VERIFICATION_ROUTE = "verification_route"
    ORACLE_COMPARISON = "oracle_comparison"
    UNCERTAINTY = "uncertainty"
    ASSEMBLE_EVIDENCE = "assemble_evidence"
    ASSURE = "assure"
    COMPARE = "compare"


class StepAvailability(str, Enum):
    #: The step will be carried out by the declared route.
    PLANNED = "planned"
    #: No declared route of this capability can carry it out. Recorded, not dropped:
    #: an unavailable required step is a gap the assessment must report.
    UNAVAILABLE = "unavailable"


_ORDER = {kind: index for index, kind in enumerate(StepKind)}

#: Content keys derived from the rest; everything else is the plan's core.
_DERIVED = ("core_digest", "run_id", "decision", "evidence_requirements")


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    kind: StepKind
    subject: str
    depends_on: tuple[str, ...] = ()
    availability: StepAvailability = StepAvailability.PLANNED
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", StepKind(self.kind))
        object.__setattr__(self, "availability", StepAvailability(self.availability))
        object.__setattr__(self, "depends_on", tuple(sorted(self.depends_on)))
        canonical_json(dict(self.detail))
        object.__setattr__(self, "detail", freeze(dict(self.detail)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "kind": self.kind.value,
            "subject": self.subject,
            "depends_on": list(self.depends_on),
            "availability": self.availability.value,
            "detail": _plain(self.detail),
        }


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def execution_order(steps: tuple[PlanStep, ...]) -> tuple[str, ...]:
    """A deterministic topological order: dependencies first, then kind, then id."""
    by_id = {s.step_id: s for s in steps}
    for step in steps:
        for dependency in step.depends_on:
            if dependency not in by_id:
                raise PlanningError(f"step {step.step_id} depends on undeclared step {dependency}")
    depth: dict[str, int] = {}

    def level(step_id: str, trail: tuple[str, ...] = ()) -> int:
        if step_id in trail:
            raise PlanningError(f"plan steps form a cycle through {step_id}")
        if step_id not in depth:
            deps = by_id[step_id].depends_on
            depth[step_id] = 0 if not deps else 1 + max(level(d, trail + (step_id,)) for d in deps)
        return depth[step_id]

    return tuple(sorted(by_id, key=lambda s: (level(s), _ORDER[by_id[s].kind], s)))


@dataclass(frozen=True)
class ExperimentPlan:
    """A deterministic, serializable plan for one READY claim. Built, never executed, here."""

    content: Mapping[str, Any]
    steps: tuple[PlanStep, ...]
    charter: CampaignCharter

    def __post_init__(self) -> None:
        canonical_json(_plain(self.content))
        object.__setattr__(self, "content", freeze(dict(self.content)))
        object.__setattr__(self, "steps", tuple(sorted(self.steps, key=lambda s: s.step_id)))
        ids = [s.step_id for s in self.steps]
        if len(set(ids)) != len(ids):
            raise PlanningError("plan step ids must be unique")
        execution_order(self.steps)  # refuses cycles and dangling dependencies
        self._require_bound()

    def _require_bound(self) -> None:
        """Every derived field must be what the plan's own core content derives.

        An edit to the case, a model version, a route, the QOI or a step moves the
        core digest; an edit to the decision or the evidence bar disagrees with
        the charter. Either is refused here, before any caller reads the plan.
        """
        content = self.content
        missing = [key for key in _DERIVED if key not in content]
        if missing:
            raise PlanningError(f"plan content lacks {missing}")
        core = {k: v for k, v in content.items() if k not in _DERIVED}
        core_digest = tagged_digest(_CORE_TAG, {"core": _plain(core), "steps": [s.to_dict() for s in self.steps]})
        if content["core_digest"] != core_digest:
            raise PlanningError("the plan's content was edited: its core digest no longer derives from it")
        if content["run_id"] != f"claim-{core_digest[:16]}":
            raise PlanningError("the plan's run_id is not the one its content derives")
        charter = self.charter
        if dict(charter.metadata).get("plan_core") != core_digest:
            raise PlanningError("the plan's charter was issued for another plan")
        if dict(charter.metadata).get("claim_identity") != content.get("claim_identity"):
            raise PlanningError("the plan's charter was issued for another claim")
        decision = content["decision"]
        if charter.digest != decision.get("charter_digest") or charter.campaign_id != decision.get("campaign_id"):
            raise PlanningError("the plan's charter is not the charter its content names")
        (terminal,) = charter.terminal_decisions
        if (terminal.decision_id, terminal.statement) != (decision.get("decision_id"), decision.get("statement")):
            raise PlanningError("the plan's decision is not the charter's terminal decision")
        requirements = content["evidence_requirements"]
        (confidence,) = charter.confidence_requirements
        if [l.value for l in confidence.required_levels] != list(requirements.get("required_levels", ())):
            raise PlanningError("the plan's required levels are not the charter's")
        if dict(charter.metadata).get("discrepancy") != requirements.get("discrepancy"):
            raise PlanningError("the plan's discrepancy declaration is not the charter's")
        demand = dict(charter.metadata).get("uncertainty_demand", {})
        if (
            list(demand.get("required_channels", ())) != list(requirements.get("required_channels", ()))
            or demand.get("coverage_factor") != requirements.get("coverage_factor")
            or demand.get("require_supported_discrepancy") != requirements.get("require_supported_discrepancy")
        ):
            raise PlanningError("the plan's uncertainty demand is not the charter's")

    # ---- views ----------------------------------------------------------------

    @property
    def order(self) -> tuple[str, ...]:
        return execution_order(self.steps)

    @property
    def run_id(self) -> str:
        return str(self.content["run_id"])

    @property
    def capability_id(self) -> str:
        return str(self.content["capability"]["capability_id"])

    @property
    def capability_digest(self) -> str:
        return str(self.content["capability"]["digest"])

    @property
    def case(self) -> Mapping[str, Any]:
        return self.content["case"]

    @property
    def instance(self) -> str | None:
        return self.content["qoi"]["instance"]

    @property
    def decision_id(self) -> str:
        return str(self.content["decision"]["decision_id"])

    @property
    def charter_digest(self) -> str:
        return self.charter.digest

    @property
    def context_ref(self) -> str:
        """The only context reference evidence produced by this plan may carry."""
        return charter_context_ref(self.charter.digest, self.decision_id)

    def step(self, step_id: str) -> PlanStep:
        for candidate in self.steps:
            if candidate.step_id == step_id:
                return candidate
        raise PlanningError(f"no step {step_id!r} in plan {self.digest[:12]}")

    def steps_of(self, kind: StepKind) -> tuple[PlanStep, ...]:
        return tuple(s for s in self.steps if s.kind is kind)

    @property
    def unavailable_steps(self) -> tuple[PlanStep, ...]:
        return tuple(s for s in self.steps if s.availability is StepAvailability.UNAVAILABLE)

    # ---- identity ---------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PLAN_SCHEMA,
            "content": _plain(self.content),
            "steps": [s.to_dict() for s in self.steps],
            "order": list(self.order),
            "charter": self.charter.to_dict(),
        }

    @property
    def digest(self) -> str:
        return tagged_digest(_TAG, {"content": _plain(self.content), "steps": [s.to_dict() for s in self.steps]})

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExperimentPlan":
        """Read a plan back. Its order is recomputed; a disagreeing stored order is refused."""
        payload = require_mapping(payload, field="plan", error=PlanningError)
        require_keys(payload, required=("schema", "content", "steps", "order", "charter"), record="plan", error=PlanningError)
        require_schema_exact(payload, PLAN_SCHEMA, record="plan", error=PlanningError)
        steps = []
        for raw in payload["steps"]:
            raw = require_mapping(raw, field="plan step", error=PlanningError)
            require_keys(raw, required=("step_id", "kind", "subject", "depends_on", "availability", "detail"), record="plan step", error=PlanningError)
            steps.append(
                PlanStep(
                    step_id=raw["step_id"],
                    kind=StepKind(raw["kind"]),
                    subject=raw["subject"],
                    depends_on=tuple(raw["depends_on"]),
                    availability=StepAvailability(raw["availability"]),
                    detail=raw["detail"],
                )
            )
        plan = cls(content=payload["content"], steps=tuple(steps), charter=CampaignCharter.from_dict(payload["charter"]))
        if list(plan.order) != list(payload["order"]):
            raise PlanningError("the stored execution order is not the order the steps imply")
        return plan


# ---------------------------------------------------------------------------
# The decision charter (CORE-9 identity)
# ---------------------------------------------------------------------------


def charter_for(compiled: CompiledClaim, core_digest: str) -> CampaignCharter:
    """The SRIA charter the plan's evidence is judged under.

    Its metadata binds the exact claim identity, the plan's core content (and so
    the QOI, capability, models, case and routes), the declared discrepancy and
    the demanded uncertainty -- so the charter digest, which becomes every piece
    of evidence's ``context_ref``, changes whenever any of them does.
    """
    claim = compiled.claim
    return CampaignCharter(
        campaign_id=f"claim:{claim.identity_digest[:24]}",
        terminal_decisions=(claim.decision.terminal_decision(),),
        confidence_requirements=(
            ConfidenceRequirement(
                requirement_id="claim_evidence_level",
                required_levels=claim.evidence.required_levels,
                description=(
                    "the claim's decision requires these evidentiary levels before "
                    "its evidence may be relied on"
                ),
            ),
        ),
        metadata={
            "claim_identity": claim.identity_digest,
            "plan_core": core_digest,
            "qoi": claim.qoi.to_dict(),
            "discrepancy": claim.discrepancy.to_dict(),
            "uncertainty_demand": claim.uncertainty.to_dict(),
        },
    )


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


def _routes_detail(routes: tuple[RouteAssessment, ...]) -> list[dict[str, Any]]:
    return [r.to_dict() for r in routes]


def plan_experiment(compiled: CompiledClaim, registry: CapabilityRegistry) -> ExperimentPlan:
    """Plan a READY claim. Refuses anything else: the compiled record carries its repairs."""
    if not isinstance(compiled, CompiledClaim):
        raise TypeError("plan_experiment needs a CompiledClaim")
    if compiled.status is not CompilationStatus.READY:
        raise PlanningError(
            f"only a READY claim can be planned; this one is {compiled.status.value}: {list(compiled.reasons)}"
        )
    if compiled.registry_digest != registry.digest:
        raise PlanningError("the claim was compiled against another registry; compile it again")
    claim = compiled.claim
    selected = compiled.capability
    declaration = registry.get(selected.capability_id)
    if declaration.digest != selected.digest:
        raise PlanningError("the selected capability changed after compilation")

    supplied = dict(claim.supplied_inputs)
    run_inputs = run_inputs_for(claim, declaration)
    case = build_case(declaration, run_inputs)
    routes = assess_routes(declaration, tuple(supplied))
    produced = declaration.produced(claim.qoi.name)
    stated = {declared_path(p) for p in supplied}
    # Numerics the system fills in when unstated (a coupling budget, a grid).
    # A route request is not among them: an unrequested route is not run, which
    # is absence, not a default.
    route_requests = {path for route in declaration.routes for path in route.activation}
    defaulted = sorted(
        i.path for i in declaration.inputs
        if i.role is InputRole.NUMERICS and i.path not in stated and i.path not in route_requests
    )

    steps: list[PlanStep] = []
    execute = "execute:" + declaration.primary_route.route_id
    steps.append(
        PlanStep(
            execute,
            StepKind.EXECUTE,
            declaration.primary_route.route_id,
            detail={"capability_id": declaration.capability_id, "run_inputs": sorted(run_inputs)},
        )
    )
    for model in selected.models:
        pending = [c.condition for c in model.unknown_of(UnknownBasis.PENDING_EXECUTION)]
        steps.append(
            PlanStep(
                f"validity:{model.model_id}" + ("" if model.instance is None else f"[{model.instance}]"),
                StepKind.ASSESS_VALIDITY,
                model.model_id,
                depends_on=(execute,),
                detail={
                    "version": model.version,
                    "instance": model.instance,
                    "pre_execution_status": model.status.value,
                    "decided_by_the_run": pending,
                },
            )
        )
    for route in routes:
        if route.route_class is RouteClass.PRIMARY:
            continue
        kind = StepKind.ORACLE_COMPARISON if route.route_class in (RouteClass.BENCHMARK, RouteClass.EXPERIMENTAL) else StepKind.VERIFICATION_ROUTE
        steps.append(
            PlanStep(
                f"route:{route.route_id}",
                kind,
                route.route_id,
                depends_on=(execute,),
                availability=StepAvailability.PLANNED if route.active else StepAvailability.UNAVAILABLE,
                detail=route.to_dict(),
            )
        )
    attainable = {a.level: a for a in declaration.attainable_levels}
    for level in claim.evidence.required_levels:
        found = attainable.get(level)
        steps.append(
            PlanStep(
                f"check:{level.value}",
                StepKind.VALIDATION_CHECK,
                level.value,
                depends_on=(execute,),
                availability=StepAvailability.PLANNED if found is not None else StepAvailability.UNAVAILABLE,
                detail={
                    "level": level.value,
                    "is_validation": level in VALIDATION_LEVELS,
                    "check_name": None if found is None else found.check_name,
                    "route_id": None if found is None else found.route_id,
                    "condition": None if found is None else found.condition,
                },
            )
        )
    for channel in claim.uncertainty.ordered_channels():
        # Phase 2: the step names the exact study that will quantify the channel,
        # so the plan digest (and the charter, and every context_ref) binds it.
        study, unavailable = study_spec(declaration, claim, channel)
        steps.append(
            PlanStep(
                f"uncertainty:{channel.value}",
                StepKind.UNCERTAINTY,
                channel.value,
                depends_on=(execute,),
                availability=StepAvailability.PLANNED if study is not None else StepAvailability.UNAVAILABLE,
                detail={
                    "channel": channel.value,
                    "coverage_factor": claim.uncertainty.coverage_factor,
                    "basis": declaration.uncertainty.basis,
                    "study": study,
                    "unavailable_reason": unavailable,
                },
            )
        )
    upstream = tuple(s.step_id for s in steps if s.step_id != execute) + (execute,)
    steps.append(PlanStep("assemble_evidence", StepKind.ASSEMBLE_EVIDENCE, claim.qoi.name, depends_on=upstream))
    steps.append(
        PlanStep(
            "assure",
            StepKind.ASSURE,
            claim.decision.decision_id,
            depends_on=("assemble_evidence",),
            detail={
                "required_levels": [l.value for l in claim.evidence.required_levels],
                "required_channels": [c.value for c in claim.uncertainty.ordered_channels()],
                "require_supported_discrepancy": claim.uncertainty.require_supported_discrepancy,
            },
        )
    )
    steps.append(PlanStep("compare", StepKind.COMPARE, claim.qoi.name, depends_on=("assure",)))

    core = {
        "claim_identity": claim.identity_digest,
        "capability": {
            "capability_id": declaration.capability_id,
            "version": declaration.version,
            "digest": declaration.digest,
        },
        "models": [
            {"model_id": m.model_id, "version": m.version, "instance": m.instance, "pre_execution_status": m.status.value}
            for m in selected.models
        ],
        "solvers": [s.to_dict() for s in declaration.solvers],
        "case": case,
        "case_digest": tagged_digest("crafty.claims.case/1", case),
        "system_defaulted_numerics": defaulted,
        "qoi": {
            "name": claim.qoi.name,
            "units": claim.qoi.units,
            "dimension": claim.qoi.dimension,
            "instance_key": produced.instance_key,
            "instance": compiled.instance,
        },
        "comparison": {
            "kind": claim.kind.value,
            "operator": claim.operator.value,
            "target": compiled.target.to_dict(),
            "target_ref": claim.target.input_ref,
            "tolerance": None if claim.tolerance is None else claim.tolerance.to_dict(),
        },
        "routes": _routes_detail(routes),
        "predicted_gaps": [g.to_dict() for g in compiled.predicted_gaps],
    }
    ordered = sorted(steps, key=lambda s: s.step_id)
    core_digest = tagged_digest(_CORE_TAG, {"core": _plain(core), "steps": [s.to_dict() for s in ordered]})
    charter = charter_for(compiled, core_digest)
    content = dict(core)
    content["core_digest"] = core_digest
    content["run_id"] = f"claim-{core_digest[:16]}"
    content["decision"] = {
        "decision_id": claim.decision.decision_id,
        "statement": claim.decision.statement,
        "charter_digest": charter.digest,
        "campaign_id": charter.campaign_id,
    }
    content["evidence_requirements"] = {
        "required_levels": [l.value for l in claim.evidence.required_levels],
        "required_channels": [c.value for c in claim.uncertainty.ordered_channels()],
        "coverage_factor": claim.uncertainty.coverage_factor,
        "require_supported_discrepancy": claim.uncertainty.require_supported_discrepancy,
        "discrepancy": claim.discrepancy.to_dict(),
    }
    return ExperimentPlan(content=content, steps=tuple(steps), charter=charter)


def verify_plan(plan: ExperimentPlan, compiled: CompiledClaim, registry: CapabilityRegistry) -> None:
    """Refuse a plan that is not the plan this claim and registry produce today."""
    expected = plan_experiment(compiled, registry)
    if expected.digest != plan.digest:
        raise PlanningError(
            f"plan {plan.digest[:12]} is not the plan this claim produces ({expected.digest[:12]}): "
            f"it was edited, or it was made for another claim, capability or registry"
        )


__all__ = [
    "PLAN_SCHEMA",
    "ExperimentPlan",
    "PlanStep",
    "PlanningError",
    "StepAvailability",
    "StepKind",
    "charter_for",
    "execution_order",
    "plan_experiment",
    "verify_plan",
]
