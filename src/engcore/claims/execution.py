"""Executing a plan, and proving the report is the plan's.

``execute_plan`` runs exactly one thing: the selected capability's executor on
the plan's case, under the plan's run id. It does not choose, retry, or repair.
Then it checks that what came back *is* the answer to the plan -- because a
credibility report that describes a different run is not evidence for this
claim, however good its verdict:

* the capability that ran is the one the plan names, by digest;
* the report's provenance run id is the plan's;
* every model the report assessed is one the plan named, at the plan's version,
  and every model the plan named was assessed;
* every stated input the report's provenance records was run at the stated value;
* the report carries the claim's quantity in the claim's dimension.

Any disagreement is a *binding problem*: recorded, and the report is kept for the
reader but never used as evidence.

Expected refusals by a system -- a payload it will not accept, an operating point
it will not run at -- are outcomes, not exceptions. An unexpected exception is a
defect and propagates, exactly as the existing claim-assessment boundary treats
one: a code fault is never disguised as scientific insufficiency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..scientific.errors import ScientificCoreError
from ..scientific.units.quantity import Quantity, dimensionality
from .capabilities import CapabilityRegistry, InstanceReport
from .errors import CapabilityExecutionRefused, CapabilityInputError
from .planning import ExperimentPlan, PlanningError


class ExecutionOutcome(str, Enum):
    COMPLETED = "completed"
    #: The system refused the case before or while running it (a payload refusal).
    REFUSED_BY_SYSTEM = "refused_by_system"


@dataclass(frozen=True)
class PlanExecution:
    """What running a plan produced, and whether it is bound to the plan."""

    plan_digest: str
    run_id: str
    capability_id: str
    outcome: ExecutionOutcome
    instance: str | None = None
    report: Any = None
    reports: tuple[InstanceReport, ...] = ()
    condition_repairs: tuple[tuple[str | None, Any], ...] = ()
    failure: str | None = None
    binding_problems: tuple[str, ...] = ()

    @property
    def bound(self) -> bool:
        return self.outcome is ExecutionOutcome.COMPLETED and self.report is not None and not self.binding_problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_digest": self.plan_digest,
            "run_id": self.run_id,
            "capability_id": self.capability_id,
            "outcome": self.outcome.value,
            "instance": self.instance,
            "report_run_id": None if self.report is None else self.report.run_id,
            "reports": [
                {"instance": item.instance, "run_id": item.report.run_id, "verdict": item.report.verdict.value}
                for item in self.reports
            ],
            "failure": self.failure,
            "binding_problems": list(self.binding_problems),
            "bound": self.bound,
        }


def _same(a: Quantity, b: Any) -> bool:
    if not isinstance(b, Quantity) or dimensionality(a.units) != dimensionality(b.units):
        return False
    return math.isclose(a.magnitude, b.to(a.units).magnitude, rel_tol=1e-12, abs_tol=0.0)


def binding_problems(
    plan: ExperimentPlan, registry: CapabilityRegistry, report: Any, stated: dict[str, Any], *, run_id: str | None = None
) -> tuple[str, ...]:
    """Every way ``report`` fails to be the answer to ``plan``. Empty means bound.

    ``run_id`` names a planned *variant* run (a refinement level, a propagated
    sample); it defaults to the plan's own run.
    """
    problems: list[str] = []
    declaration = registry.get(plan.capability_id)
    expected_run = plan.run_id if run_id is None else run_id
    if report.provenance.run_id != expected_run:
        problems.append(f"the report's run {report.provenance.run_id!r} is not the planned run {expected_run!r}")
    planned = {(m["model_id"], m["version"]) for m in plan.content["models"]}
    assessed = {(r.model_id, r.version) for r in report.validity}
    for model_id, version in sorted(assessed - planned):
        problems.append(f"the report assessed {model_id}@{version}, which the plan did not name")
    for model_id, version in sorted(planned - assessed):
        problems.append(f"the plan named {model_id}@{version}, which the report did not assess")
    qoi = plan.content["qoi"]
    value = report.values.get(qoi["name"])
    if value is None:
        problems.append(f"the report carries no {qoi['name']!r}")
    elif dimensionality(value.units) != qoi["dimension"]:
        problems.append(f"the report's {qoi['name']!r} is [{dimensionality(value.units)}], the claim's is [{qoi['dimension']}]")
    recorded = dict(report.provenance.inputs)
    by_model_input: dict[str, list[Any]] = {}
    for path, value in stated.items():
        item = declaration.input(path)
        if item is not None and item.model_input is not None:
            by_model_input.setdefault(item.model_input, []).append(value)
    for name, values in sorted(by_model_input.items()):
        if len(values) != 1 or name not in recorded or not isinstance(values[0], Quantity):
            continue
        if not _same(values[0], recorded[name]):
            problems.append(f"the claim states {name}={values[0]}, the report was run at {recorded[name]}")
    return tuple(problems)


def execute_plan(plan: ExperimentPlan, registry: CapabilityRegistry, stated: dict[str, Any]) -> PlanExecution:
    """Run the plan's case once, and check the result is bound to the plan."""
    declaration = registry.get(plan.capability_id)
    if declaration.digest != plan.capability_digest:
        raise PlanningError(
            f"{plan.capability_id} changed after planning ({declaration.digest[:12]} != "
            f"{plan.capability_digest[:12]}); a plan runs only against the capability it names"
        )
    if declaration.executor is None:
        raise PlanningError(f"{plan.capability_id} has no executor in this registry")
    base = dict(plan_digest=plan.digest, run_id=plan.run_id, capability_id=plan.capability_id)
    try:
        run = declaration.executor(dict(plan.case), run_id=plan.run_id)
    except (CapabilityExecutionRefused, CapabilityInputError) as exc:
        return PlanExecution(outcome=ExecutionOutcome.REFUSED_BY_SYSTEM, failure=f"{type(exc).__name__}: {exc}", **base)
    except ScientificCoreError as exc:
        return PlanExecution(outcome=ExecutionOutcome.REFUSED_BY_SYSTEM, failure=f"{type(exc).__name__}: {exc}", **base)

    wanted = plan.instance
    chosen = [item for item in run.reports if item.instance == wanted]
    if not chosen and len(run.reports) == 1 and run.reports[0].instance is None:
        # One report stands for the whole case (the system refused the coupling).
        chosen = list(run.reports)
    problems: tuple[str, ...]
    report = None
    if len(chosen) != 1:
        problems = (f"the run returned no single report for instance {wanted!r}",)
    else:
        report = chosen[0].report
        problems = binding_problems(plan, registry, report, stated)
    return PlanExecution(
        outcome=ExecutionOutcome.COMPLETED,
        instance=wanted,
        report=report,
        reports=run.reports,
        condition_repairs=tuple(run.condition_repairs),
        binding_problems=problems,
        **base,
    )


__all__ = ["ExecutionOutcome", "PlanExecution", "binding_problems", "execute_plan"]
