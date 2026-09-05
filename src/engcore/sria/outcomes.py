"""Run outcome contract — orthogonal, not a single FAILED enum.

A flat status enum forces one axis to stand in for three, and the collapse is
lossy in exactly the places that matter:

* a solver that diverged and a machine that lost power are both "FAILED", yet
  only one of them says anything about the science;
* a run killed at the wall-clock limit is *censored*, not failed — treating it
  as an observed failure biases any future failure model upward;
* an infeasible design point is a legitimate scientific finding, not an error.

So an outcome is a product, not a value:

    Disposition  ×  Attributed Cause  ×  Consequences

The axes are deliberately independent. This module enforces only *structural*
invariants (a censored run must say how it was censored, a fraction must lie
in [0, 1]); it never infers a cause from a disposition. Nothing here learns —
the failure model is a later milestone and needs this structure to exist first.

Standing constraint for M2
--------------------------
The Scientific Core still carries the older flat
:class:`~engcore.scientific.experiments.evaluation.EvaluationStatus`, and M1
deliberately did not migrate it. While **two failure vocabularies remain in
the repository, no learned failure model may be introduced.** Feeding a
learner a mixture of ``EvaluationStatus.FAILED`` (which conflates numerical
divergence with infrastructure loss) and :class:`RunOutcome` (which separates
them, and marks infrastructure loss non-informative) would train it on a
label set whose meaning depends on which producer happened to emit the row —
and the resulting failure probabilities would be unattributable.

M2 must resolve the bridge or the migration *before* any ``p(failure)``
estimator is built, not alongside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ..scientific.serialization import require_schema, schema_string
from .errors import OutcomeContractError

OUTCOME_SCHEMA = schema_string("sria_run_outcome")


class Disposition(str, Enum):
    """What happened to the run, as an execution fact."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    KILLED_CENSORED = "killed_censored"
    INDETERMINATE = "indeterminate"


class AttributedCause(str, Enum):
    """Why it happened — orthogonal to what happened.

    The distinctions the platform must never lose are the ones between a
    failure of the science, a failure of the numerics, a failure of the
    machinery, a genuinely infeasible point, a contradicted hypothesis, and
    evidence that simply did not settle the question.
    """

    NONE = "none"
    SCIENTIFIC = "scientific"
    NUMERICAL = "numerical"
    INFRASTRUCTURE = "infrastructure"
    INFEASIBLE = "infeasible"
    HYPOTHESIS_CONTRADICTION = "hypothesis_contradiction"
    INCONCLUSIVE = "inconclusive"
    #: Added in M2A. "It failed and we do not know why" — the honest reading of
    #: a legacy flat FAILED with no corroborating provenance. Distinct from
    #: NONE, which asserts there was no failure to attribute. Records carrying
    #: this are structurally ineligible for supervised failure learning:
    #: guessing a cause here is how historical ambiguity becomes mislabeled
    #: training data.
    UNATTRIBUTED = "unattributed"


class BlameAssignment(str, Enum):
    """Which layer owns the outcome. Used later for routing, never for shame."""

    UNASSIGNED = "unassigned"
    MODEL = "model"
    SOLVER = "solver"
    PARAMETERS = "parameters"
    PLATFORM = "platform"
    EXTERNAL = "external"


class CensoringType(str, Enum):
    """How an observation was truncated. ``NONE`` means fully observed."""

    NONE = "none"
    RIGHT_CENSORED_BUDGET = "right_censored_budget"
    RIGHT_CENSORED_WALLCLOCK = "right_censored_wallclock"
    RIGHT_CENSORED_MANUAL = "right_censored_manual"
    INTERVAL_CENSORED = "interval_censored"


class Retryability(str, Enum):
    RETRYABLE = "retryable"
    RETRYABLE_WITH_CHANGES = "retryable_with_changes"
    NOT_RETRYABLE = "not_retryable"
    UNKNOWN = "unknown"


class DetectedBy(str, Enum):
    UNKNOWN = "unknown"
    SOLVER = "solver"
    VALIDATION_CHECK = "validation_check"
    CRITIC = "critic"
    RUNTIME = "runtime"
    HUMAN = "human"


@dataclass(frozen=True)
class RunOutcome:
    """The full outcome of one executed research action."""

    disposition: Disposition
    attributed_cause: AttributedCause = AttributedCause.NONE
    blame_assignment: BlameAssignment = BlameAssignment.UNASSIGNED
    censoring_type: CensoringType = CensoringType.NONE
    completion_fraction: float = 1.0
    retryability: Retryability = Retryability.UNKNOWN
    informative_for_pf: bool = True
    detected_by: DetectedBy = DetectedBy.UNKNOWN
    salvageable_artifacts: tuple[str, ...] = ()
    detail: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "disposition", Disposition(self.disposition))
        object.__setattr__(
            self, "attributed_cause", AttributedCause(self.attributed_cause)
        )
        object.__setattr__(
            self, "blame_assignment", BlameAssignment(self.blame_assignment)
        )
        object.__setattr__(self, "censoring_type", CensoringType(self.censoring_type))
        object.__setattr__(self, "retryability", Retryability(self.retryability))
        object.__setattr__(self, "detected_by", DetectedBy(self.detected_by))

        if not isinstance(self.informative_for_pf, bool):
            raise OutcomeContractError(
                "informative_for_pf must be an explicit bool: whether an "
                "outcome carries signal for a failure model is a judgement, "
                "not something to infer from the disposition"
            )

        fraction = float(self.completion_fraction)
        if not 0.0 <= fraction <= 1.0:
            raise OutcomeContractError(
                f"completion_fraction must lie in [0, 1], got {fraction}"
            )
        object.__setattr__(self, "completion_fraction", fraction)

        # The one structural coupling: a censored run must say how it was cut
        # short, otherwise downstream survival analysis cannot use it.
        if (
            self.disposition is Disposition.KILLED_CENSORED
            and self.censoring_type is CensoringType.NONE
        ):
            raise OutcomeContractError(
                "KILLED_CENSORED requires a censoring_type; an unqualified "
                "censored observation cannot be used without bias"
            )

        object.__setattr__(
            self, "salvageable_artifacts", tuple(self.salvageable_artifacts)
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def is_censored(self) -> bool:
        return self.censoring_type is not CensoringType.NONE

    @property
    def yielded_information(self) -> bool:
        """Whether anything scientific can be read from this run.

        Note this is *not* ``disposition is SUCCESS``: a contradicted
        hypothesis and an infeasible point are both informative.
        """
        if self.disposition is Disposition.SUCCESS:
            return True
        return self.attributed_cause in (
            AttributedCause.SCIENTIFIC,
            AttributedCause.INFEASIBLE,
            AttributedCause.HYPOTHESIS_CONTRADICTION,
        ) or self.completion_fraction > 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": OUTCOME_SCHEMA,
            "disposition": self.disposition.value,
            "attributed_cause": self.attributed_cause.value,
            "blame_assignment": self.blame_assignment.value,
            "censoring_type": self.censoring_type.value,
            "completion_fraction": self.completion_fraction,
            "retryability": self.retryability.value,
            "informative_for_pf": self.informative_for_pf,
            "detected_by": self.detected_by.value,
            "salvageable_artifacts": list(self.salvageable_artifacts),
            "detail": self.detail,
            "metadata": dict(sorted(self.metadata.items(), key=lambda kv: kv[0])),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunOutcome":
        require_schema(payload, OUTCOME_SCHEMA)
        return cls(
            disposition=Disposition(payload["disposition"]),
            attributed_cause=AttributedCause(payload.get("attributed_cause", "none")),
            blame_assignment=BlameAssignment(
                payload.get("blame_assignment", "unassigned")
            ),
            censoring_type=CensoringType(payload.get("censoring_type", "none")),
            completion_fraction=payload.get("completion_fraction", 1.0),
            retryability=Retryability(payload.get("retryability", "unknown")),
            informative_for_pf=bool(payload.get("informative_for_pf", True)),
            detected_by=DetectedBy(payload.get("detected_by", "unknown")),
            salvageable_artifacts=tuple(payload.get("salvageable_artifacts", ())),
            detail=payload.get("detail", ""),
            metadata=dict(payload.get("metadata", {})),
        )
