"""The immutable record every computational learner consumes.

One record = one executed run, reduced to what is legitimately predictive of
*computational* behaviour. It is the only input type the M2 learners accept,
which is what keeps the outcome-bridge gate meaningful: there is no second
path by which a legacy status could reach a model.

Two separations do the real work here.

**Features vs. group key.** ``group_key`` carries the problem identity
(``bbob_f012``) and exists *solely* so held-out splits can keep near-identical
problems out of training. It is deliberately not a covariate. Benchmark
identity is exactly the kind of feature that makes a model look excellent in
cross-validation and useless on a new problem — and once the split is grouped
by it, a model that leaned on it would have nothing to lean on at test time
anyway.

**Covariates are numerical and domain-neutral.** A Domain Pack may compute
them (it knows what a stiffness proxy means for its physics), but what it
emits is a number describing computational shape. If ``voltage`` or
``reynolds`` appeared as a feature name, the learned cost model would silently
stop transferring between domains that share a computational structure, which
is the entire premise of keying calibration by structure × environment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from ...scientific.serialization import require_schema, schema_string
from ..outcomes import (
    AttributedCause,
    CensoringType,
    Disposition,
    Retryability,
)
from ..signatures import EnvironmentSignature, SemanticGuard, StructureSignature

LEARNING_RECORD_SCHEMA = schema_string("sria_computational_learning_record")


class LearningRecordError(Exception):
    """A record that cannot be safely learned from."""


@dataclass(frozen=True)
class ComputationalLearningRecord:
    """One run, normalized for computational learning."""

    record_id: str
    structure: StructureSignature
    environment: EnvironmentSignature
    solver_identity: tuple[str, str]          # (solver/config id, version)
    disposition: Disposition
    attributed_cause: AttributedCause = AttributedCause.NONE
    informative_for_pf: bool = True
    retryability: Retryability = Retryability.UNKNOWN
    covariates: Mapping[str, float] = field(default_factory=dict)
    fidelity_rung: str = ""
    realized_cost: float | None = None
    cost_unit: str = "second"
    cost_censoring: CensoringType = CensoringType.NONE
    completion_fraction: float = 1.0
    group_key: str = ""                        # split key, never a feature
    pairing_key: str = ""                      # problem-instance id, never a feature
    diagnostics_ref: str = ""
    provenance_ref: str = ""

    def __post_init__(self) -> None:
        record_id = str(self.record_id).strip()
        if not record_id:
            raise LearningRecordError("learning record requires a record_id")
        object.__setattr__(self, "record_id", record_id)

        if not isinstance(self.structure, StructureSignature):
            raise LearningRecordError("structure must be a StructureSignature")
        if not isinstance(self.environment, EnvironmentSignature):
            raise LearningRecordError("environment must be an EnvironmentSignature")

        solver = tuple(str(x) for x in self.solver_identity)
        if len(solver) != 2 or not solver[0].strip():
            raise LearningRecordError("solver_identity must be (id, version)")
        object.__setattr__(self, "solver_identity", solver)

        object.__setattr__(self, "disposition", Disposition(self.disposition))
        object.__setattr__(
            self, "attributed_cause", AttributedCause(self.attributed_cause)
        )
        object.__setattr__(self, "cost_censoring", CensoringType(self.cost_censoring))
        object.__setattr__(self, "retryability", Retryability(self.retryability))

        if not isinstance(self.informative_for_pf, bool):
            raise LearningRecordError("informative_for_pf must be an explicit bool")

        covariates: dict[str, float] = {}
        for name, value in self.covariates.items():
            name = str(name).strip()
            if not name:
                raise LearningRecordError("covariate name must be non-empty")
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise LearningRecordError(
                    f"covariate {name!r} must be numeric — a categorical "
                    f"domain label is not a computational covariate"
                ) from exc
            if not math.isfinite(numeric):
                raise LearningRecordError(
                    f"covariate {name!r} is not finite; a NaN feature silently "
                    f"propagates through every model that touches it"
                )
            covariates[name] = numeric
        object.__setattr__(self, "covariates", covariates)

        fraction = float(self.completion_fraction)
        if not 0.0 <= fraction <= 1.0:
            raise LearningRecordError(
                f"completion_fraction must lie in [0, 1], got {fraction}"
            )
        object.__setattr__(self, "completion_fraction", fraction)

        if self.realized_cost is not None:
            cost = float(self.realized_cost)
            if not math.isfinite(cost) or cost < 0.0:
                raise LearningRecordError(
                    f"realized_cost must be finite and non-negative, got {cost}"
                )
            object.__setattr__(self, "realized_cost", cost)
        elif self.cost_censoring is not CensoringType.NONE:
            raise LearningRecordError(
                "a censored cost still needs the observed lower bound; "
                "censoring without a value carries no information"
            )

        # UNATTRIBUTED can never be a supervised failure label. Same invariant
        # as the bridge, restated at the learner boundary so a record built by
        # any other path cannot slip past it.
        if (
            self.attributed_cause is AttributedCause.UNATTRIBUTED
            and self.informative_for_pf
        ):
            raise LearningRecordError(
                "an UNATTRIBUTED outcome cannot be eligible for supervised "
                "failure learning"
            )

    # ---- learner-facing views ------------------------------------------
    @property
    def pair_id(self) -> str:
        """Identity of the specific problem instance this run addressed.

        Used for *paired* comparisons between configurations, where
        ``group_key`` is too coarse: ten instances of one BBOB function belong
        to one split group but are ten separately pairable problems. Like
        ``group_key`` it is bookkeeping, never a feature.
        """
        return self.pairing_key or self.group_key

    @property
    def cost_is_observed(self) -> bool:
        """True only when the cost is a completed measurement.

        A right-censored cost is a lower bound, not a runtime. Treating a
        timeout as the true duration is the single most common way a cost
        model learns to be optimistic.
        """
        return (
            self.realized_cost is not None
            and self.cost_censoring is CensoringType.NONE
        )

    @property
    def computational_success(self) -> bool:
        """The M2 failure-model target: did the computation succeed?"""
        return self.disposition is Disposition.SUCCESS

    # ---- separated learning eligibilities -------------------------------
    #
    # ``informative_for_pf`` says "this outcome carries signal for *some*
    # failure model". It does not say *which*. Collapsing the two is a real
    # error: a scientifically infeasible design point whose solve executed
    # perfectly is strong evidence about the feasible region and no evidence
    # at all that the solver is unreliable. Training solver reliability on it
    # would make every well-explored infeasible region look like a broken
    # solver.

    @property
    def eligible_for_computational_failure_learning(self) -> bool:
        """May this row train ``P(solver/computational failure)``?

        Excludes infeasibility (a property of the design point, not the
        numerics), infrastructure loss (exogenous), and unattributed causes
        (unknown by construction).
        """
        if not self.informative_for_pf:
            return False
        return self.attributed_cause not in (
            AttributedCause.INFEASIBLE,
            AttributedCause.INFRASTRUCTURE,
            AttributedCause.UNATTRIBUTED,
        )

    @property
    def eligible_for_feasibility_learning(self) -> bool:
        """May this row train a feasibility model?

        Feasibility learning is **not implemented in M2**; the eligibility is
        declared now so infeasible rows are routed somewhere honest instead of
        being dropped into the solver-failure target.
        """
        if not self.informative_for_pf:
            return False
        if self.attributed_cause is AttributedCause.INFEASIBLE:
            return True
        # A clean success is also evidence that the point was feasible.
        return self.disposition is Disposition.SUCCESS

    @property
    def is_feasibility_evidence_only(self) -> bool:
        """Infeasible-but-numerically-fine: feasibility signal, not solver signal."""
        return (
            self.attributed_cause is AttributedCause.INFEASIBLE
            and not self.eligible_for_computational_failure_learning
        )

    def feature_key(self) -> tuple[str, str, str]:
        """The calibration cell: structure x environment x solver config."""
        return (
            self.structure.digest,
            self.environment.digest,
            self.solver_identity[0],
        )

    def check_domain_neutral(self, guard: SemanticGuard) -> None:
        """Refuse domain vocabulary in anything the model can see."""
        guard.check(self.covariates.keys(), context="learning-record covariates")
        guard.check([self.structure.structure_kind], context="record structure")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LEARNING_RECORD_SCHEMA,
            "record_id": self.record_id,
            "structure": self.structure.to_dict(),
            "environment": self.environment.to_dict(),
            "solver_identity": list(self.solver_identity),
            "disposition": self.disposition.value,
            "attributed_cause": self.attributed_cause.value,
            "informative_for_pf": self.informative_for_pf,
            "retryability": self.retryability.value,
            "covariates": dict(sorted(self.covariates.items())),
            "fidelity_rung": self.fidelity_rung,
            "realized_cost": self.realized_cost,
            "cost_unit": self.cost_unit,
            "cost_censoring": self.cost_censoring.value,
            "completion_fraction": self.completion_fraction,
            "group_key": self.group_key,
            "pairing_key": self.pairing_key,
            "diagnostics_ref": self.diagnostics_ref,
            "provenance_ref": self.provenance_ref,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ComputationalLearningRecord":
        require_schema(payload, LEARNING_RECORD_SCHEMA)
        return cls(
            record_id=payload["record_id"],
            structure=StructureSignature.from_dict(payload["structure"]),
            environment=EnvironmentSignature.from_dict(payload["environment"]),
            solver_identity=tuple(payload["solver_identity"]),
            disposition=Disposition(payload["disposition"]),
            attributed_cause=AttributedCause(payload.get("attributed_cause", "none")),
            informative_for_pf=bool(payload.get("informative_for_pf", True)),
            retryability=Retryability(payload.get("retryability", "unknown")),
            covariates=payload.get("covariates", {}),
            fidelity_rung=payload.get("fidelity_rung", ""),
            realized_cost=payload.get("realized_cost"),
            cost_unit=payload.get("cost_unit", "second"),
            cost_censoring=CensoringType(payload.get("cost_censoring", "none")),
            completion_fraction=payload.get("completion_fraction", 1.0),
            group_key=payload.get("group_key", ""),
            pairing_key=payload.get("pairing_key", ""),
            diagnostics_ref=payload.get("diagnostics_ref", ""),
            provenance_ref=payload.get("provenance_ref", ""),
        )


def record_from_bridged_outcome(
    *,
    record_id: str,
    bridged: Any,
    structure: StructureSignature,
    environment: EnvironmentSignature,
    solver_identity: tuple[str, str],
    covariates: Mapping[str, float] | None = None,
    realized_cost: float | None = None,
    group_key: str = "",
    provenance_ref: str = "",
    diagnostics_ref: str = "",
    fidelity_rung: str = "",
) -> ComputationalLearningRecord:
    """Build a record from a :class:`BridgedOutcome`.

    The only sanctioned route from a legacy outcome into a learner: the bridge
    decides eligibility, and this carries that decision through unchanged.
    """
    outcome = bridged.outcome
    return ComputationalLearningRecord(
        record_id=record_id,
        structure=structure,
        environment=environment,
        solver_identity=solver_identity,
        disposition=outcome.disposition,
        attributed_cause=outcome.attributed_cause,
        informative_for_pf=bridged.pf_eligible,
        retryability=outcome.retryability,
        covariates=covariates or {},
        fidelity_rung=fidelity_rung,
        realized_cost=realized_cost,
        cost_censoring=outcome.censoring_type,
        completion_fraction=outcome.completion_fraction,
        group_key=group_key,
        provenance_ref=provenance_ref,
        diagnostics_ref=diagnostics_ref,
    )
