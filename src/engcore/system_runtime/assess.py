"""Engineering checks over a run's results, and the hand-off to the existing credibility authority.

* **Constraints** reuse ``ConstraintDefinition.check`` on the observable the request bound to each
  system constraint binding.  A binding with no observable, or whose observable is not AVAILABLE,
  is ``unavailable`` - never a pass.  A constraint check is not validation.
* **Conservation** reuses ``ConservationBalance``.  Only terms the providers actually computed
  (AVAILABLE observables) may be used; a missing term makes the balance ``incomplete`` and nothing
  is invented, in particular no zero loss.
* **Trust hand-off** builds the existing ``CredibilityEvidenceReport``.  The verdict is derived by
  the existing ``derive_verdict``; nothing here can raise it.  With no validity records and no
  validation checks (the runtime supplies none) it is INSUFFICIENT_EVIDENCE however cleanly the run
  executed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..credibility.evidence import CredibilityEvidenceReport
from ..scientific.conservation import BalanceTerm, ConservationBalance
from ..scientific.errors import InvalidScientificProblem
from ..scientific.ir.constraints import ConstraintCheck, ConstraintDefinition
from ..scientific.results.provenance import ProvenanceRecord
from ..scientific.results.uncertainty import UncertaintyKind
from ..scientific.units.quantity import Quantity
from ._common import digest_of, identifier
from .request import SystemRunRequest
from .result import Availability, RunStatus, SystemRunResult

CONSTRAINT_CLASSIFICATION = "constraint_assessment_not_validation"
CONSERVATION_CLASSIFICATION = "conservation_diagnostic_not_validation"


@dataclass(frozen=True)
class ConstraintAssessment:
    binding_id: str
    instance_id: str
    constraint_id: str
    observable_id: str
    #: "satisfied" | "violated" | "unavailable"
    status: str
    check: ConstraintCheck | None
    reason: str
    #: "unknown" when the observable's uncertainty is UNKNOWN: the decision then rests on the point value only
    uncertainty_status: str
    classification: str = CONSTRAINT_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.status not in ("satisfied", "violated", "unavailable"):
            raise InvalidScientificProblem("constraint assessment status is satisfied, violated or unavailable")
        if (self.status == "unavailable") != (self.check is None):
            raise InvalidScientificProblem("a constraint assessment has a check exactly when it is not unavailable")
        if self.check is not None and self.check.satisfied != (self.status == "satisfied"):
            raise InvalidScientificProblem("constraint status disagrees with its check")

    def to_dict(self) -> dict[str, Any]:
        return {"binding_id": self.binding_id, "instance_id": self.instance_id, "constraint_id": self.constraint_id,
                "observable_id": self.observable_id, "status": self.status, "check": None if self.check is None else self.check.to_dict(),
                "reason": self.reason, "uncertainty_status": self.uncertainty_status, "classification": self.classification}


def assess_constraints(result: SystemRunResult, system: Any, definitions: Mapping[str, ConstraintDefinition]) -> tuple[ConstraintAssessment, ...]:
    """One assessment per system constraint binding.  ``definitions`` maps definition digest -> definition."""
    if dict(result.provenance).get("system") != system.digest:
        raise InvalidScientificProblem("the supplied system is not the system this result was produced for")
    observations = {o.binding_id: o for o in result.plan.constraint_observations}
    by_name = {c.name: c for c in system.constraints}
    out: list[ConstraintAssessment] = []
    for binding in system.constraint_bindings:
        obs = observations.get(binding.binding_id)
        if obs is None:
            out.append(ConstraintAssessment(binding.binding_id, binding.instance_id, binding.constraint_id, "", "unavailable", None,
                                            "the request bound no observable to this constraint", "unknown"))
            continue
        definition = definitions.get(obs.constraint_digest)
        if definition is not None and digest_of(definition.to_dict()) != obs.constraint_digest:
            raise InvalidScientificProblem(f"constraint definition filed under {obs.constraint_digest[:12]}.. does not have that digest")
        if definition is None or definition.name != binding.constraint_id or by_name.get(binding.constraint_id) is None:
            raise InvalidScientificProblem(f"constraint binding {binding.binding_id!r} does not resolve to the system's definition")
        observable = result.observable(obs.observable_id)
        if observable.availability is not Availability.AVAILABLE:
            out.append(ConstraintAssessment(binding.binding_id, binding.instance_id, binding.constraint_id, obs.observable_id, "unavailable", None,
                                            f"observable {obs.observable_id!r} is {observable.availability.value}: {observable.reason}", "unknown"))
            continue
        check = definition.check(observable.value.value)
        unc = "unknown" if observable.value.uncertainty.kind is UncertaintyKind.UNKNOWN else observable.value.uncertainty.kind.value
        out.append(ConstraintAssessment(binding.binding_id, binding.instance_id, binding.constraint_id, obs.observable_id,
                                        "satisfied" if check.satisfied else "violated", check, "", unc))
    return tuple(out)


@dataclass(frozen=True)
class TermSource:
    """A balance term read from an AVAILABLE observable.  ``scale`` is a declared, dimensionless factor."""

    name: str
    observable_id: str
    scale: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", identifier(self.name, "balance term name"))
        object.__setattr__(self, "observable_id", identifier(self.observable_id, "balance term observable"))
        if isinstance(self.scale, bool) or not isinstance(self.scale, (int, float)) or self.scale != self.scale or abs(self.scale) == float("inf") or self.scale == 0:
            raise InvalidScientificProblem("a balance term scale is a declared finite non-zero factor (0 would erase the term and close the balance)")


@dataclass(frozen=True)
class BalanceSpec:
    balance_id: str
    left: tuple[TermSource, ...]
    right: tuple[TermSource, ...]
    tolerance: Quantity


@dataclass(frozen=True)
class ConservationAssessment:
    balance_id: str
    #: "closed" | "not_closed" | "incomplete"
    status: str
    missing_terms: tuple[str, ...]
    residual: Quantity | None
    tolerance: Quantity
    reason: str
    classification: str = CONSERVATION_CLASSIFICATION

    def to_dict(self) -> dict[str, Any]:
        return {"balance_id": self.balance_id, "status": self.status, "missing_terms": list(self.missing_terms),
                "residual": None if self.residual is None else self.residual.to_dict(), "tolerance": self.tolerance.to_dict(),
                "reason": self.reason, "classification": self.classification}


def assess_conservation(result: SystemRunResult, specs: Sequence[BalanceSpec]) -> tuple[ConservationAssessment, ...]:
    out: list[ConservationAssessment] = []
    for spec in specs:
        missing: list[str] = []
        sides: list[list[BalanceTerm]] = [[], []]
        for index, terms in enumerate((spec.left, spec.right)):
            for term in terms:
                obs = result.observable(term.observable_id)
                if obs.availability is not Availability.AVAILABLE:
                    missing.append(f"{term.name} ({term.observable_id}: {obs.availability.value})")
                    continue
                q = obs.value.value
                sides[index].append(BalanceTerm(term.name, Quantity(q.magnitude * term.scale, q.units), f"observable:{term.observable_id}"))
        if missing:
            out.append(ConservationAssessment(spec.balance_id, "incomplete", tuple(missing), None, spec.tolerance,
                                              "a term was not computed, so the balance cannot be closed; no term is assumed zero"))
            continue
        balance = ConservationBalance(spec.balance_id, tuple(sides[0]), tuple(sides[1]), spec.tolerance)
        out.append(ConservationAssessment(spec.balance_id, "closed" if balance.closed else "not_closed", (),
                                          Quantity(balance.absolute_residual, balance.unit), spec.tolerance, ""))
    return tuple(out)


def trust_handoff(result: SystemRunResult, request: SystemRunRequest | None = None, *,
                  validity: tuple[Any, ...] = (), validation: tuple[Any, ...] = (), required_levels: tuple[Any, ...] = (),
                  allow_partial: bool = False) -> CredibilityEvidenceReport:
    """Assemble the existing credibility report from a run.  The verdict is the existing one and is never raised here.

    ``validity`` / ``validation`` are records produced by their own authorities; this runtime adds none.
    """
    if request is not None and request.digest != result.request_digest:
        raise InvalidScientificProblem("the request is not the one this result was produced for; model selections cannot be read from it")
    unavailable = [o for o in result.observables if o.availability is not Availability.AVAILABLE]
    if result.status is not RunStatus.SUCCEEDED and not allow_partial:
        raise InvalidScientificProblem(
            f"a {result.status.value} run is not assembled into a credibility report: dropping its unavailable observables would lower the evidence "
            f"bar. Pass allow_partial=True to assemble the available subset, which then states what is missing")
    values = {o.observable_id: o.value.value for o in result.observables if o.availability is Availability.AVAILABLE}
    uncertainty = {o.observable_id: o.value.uncertainty for o in result.observables if o.availability is Availability.AVAILABLE}
    solvers = sorted({(p.provider_id, p.provider_version) for p in result.provider_records}
                     | {(n.authority.authority_id, n.authority.identity_digest[:12]) for n in result.plan.nodes if not n.derived})
    models = tuple(sorted((s.model_id, s.model_version) for s in (request.model_selections if request is not None else ())))
    provenance = ProvenanceRecord(
        run_id=result.run_id, models=models, solvers=tuple(solvers),
        metadata={"request_digest": result.request_digest, "plan_digest": result.plan_digest, "result_digest": result.digest,
                  "execution_status": result.status.value, "classification": result.classification})
    return CredibilityEvidenceReport(
        run_id=result.run_id, values=values, provenance=provenance, validity=tuple(validity), validation=tuple(validation),
        required_levels=tuple(required_levels), uncertainty=uncertainty,
        notes=("assembled by the system runtime from execution facts; the runtime supplies no validity record and no validation check"
               + ("" if not unavailable else "; UNAVAILABLE observables (not in this report): " + ", ".join(f"{o.observable_id}={o.availability.value}" for o in unavailable))))
