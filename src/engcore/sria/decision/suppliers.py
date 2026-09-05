"""Cost and failure components sourced from the frozen M2 calibration.

No cost or failure model is defined here. These adapters ask M2 and translate
its answer — including its refusals — into score components.

The translation that matters is of M2's *epistemic state*, not just its
numbers:

* a ``TRUSTED`` cost model yields an ``AVAILABLE`` component;
* ``DEGRADED`` or ``UNTRUSTED`` yields ``DEGRADED``, which propagates into the
  recommendation and marks the whole decision degraded;
* ``INSUFFICIENT_DATA`` yields ``UNAVAILABLE`` — and on this repository's
  corpus that is exactly what the failure model reports, because it contains
  1,320 runs and zero failures.

So by default a candidate is **not scorable** for want of ``p_fail``. That is
the honest state, and the only sanctioned way past it is a
:class:`~engcore.sria.decision.utility.UtilityPolicy` that declares a
conservative fallback with a rationale — which then shows up as ``DEFAULTED``
in the decision record. There is no path that quietly invents a probability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..calibration.critic import CalibrationVerdict
from ..signatures import (
    ENVIRONMENT_SIGNATURE_VERSION,
    STRUCTURE_SIGNATURE_VERSION,
)
from .actions import CandidateAction, CompositeAction
from .belief_snapshot import BeliefSnapshot
from .terminal import TerminalObjective
from .replay import (
    DependencyIdentity,
    DependencyKind,
    canonical_digest,
    cost_model_state_digest,
)
from .utility import ComponentStatus, ScoreComponent


@dataclass(frozen=True)
class ApplicabilitySupport:
    """Where a calibrated model has actually been shown to work.

    M2's cost model is supported on one benchmark corpus, one execution
    environment and a known set of solver identities. A statistical backoff
    will happily return a number for a query far outside that envelope, and
    that number is not evidence — it is extrapolation wearing a prediction's
    clothes.

    So applicability is checked separately from the calibration verdict. A
    TRUSTED model queried outside its support is reported ``DEGRADED`` with the
    reason attached; it never appears decision-grade.
    """

    structure_digests: frozenset[str] = frozenset()
    environment_digests: frozenset[str] = frozenset()
    solver_ids: frozenset[str] = frozenset()
    structure_signature_version: int = STRUCTURE_SIGNATURE_VERSION
    environment_signature_version: int = ENVIRONMENT_SIGNATURE_VERSION
    description: str = ""

    def check(self, record: Any, snapshot: BeliefSnapshot) -> tuple[bool, str]:
        """Return (inside_support, reason)."""
        calibration = snapshot.calibration
        if (
            calibration.structure_signature_version
            != self.structure_signature_version
        ):
            return False, (
                f"structure signature version {calibration.structure_signature_version}"
                f" != supported {self.structure_signature_version}"
            )
        if (
            calibration.environment_signature_version
            != self.environment_signature_version
        ):
            return False, (
                f"environment signature version "
                f"{calibration.environment_signature_version} != supported "
                f"{self.environment_signature_version}"
            )
        if self.structure_digests and record.structure.digest not in self.structure_digests:
            return False, "structure is outside the model's demonstrated support"
        if (
            self.environment_digests
            and record.environment.digest not in self.environment_digests
        ):
            return False, (
                "execution environment is outside the model's demonstrated "
                "support (no cross-hardware evidence exists)"
            )
        if self.solver_ids and record.solver_identity[0] not in self.solver_ids:
            return False, (
                f"solver {record.solver_identity[0]!r} was not in the training "
                f"corpus"
            )
        return True, "query lies inside the demonstrated support envelope"


def _verdict_status(verdict: CalibrationVerdict | None) -> ComponentStatus:
    if verdict is None or verdict is CalibrationVerdict.INSUFFICIENT_DATA:
        return ComponentStatus.UNAVAILABLE
    if verdict is CalibrationVerdict.TRUSTED:
        return ComponentStatus.AVAILABLE
    return ComponentStatus.DEGRADED


class CalibrationCostSupplier:
    """Expected cost from the M2 cost model, with its verdict attached."""

    def __init__(
        self,
        cost_model: Any,
        *,
        record_builder,
        verdict: CalibrationVerdict | None = None,
        model_id: str = "cost.hierarchical",
        cost_unit: str = "second",
        support: "ApplicabilitySupport | None" = None,
    ) -> None:
        self._model = cost_model
        self._record_builder = record_builder
        self._verdict = verdict
        self._model_id = model_id
        self._cost_unit = cost_unit
        self._support = support

    def dependency_identity(self) -> DependencyIdentity:
        """Identify the *fitted state*, not just the version label.

        Two models can share a version string and a dataset id while holding
        different fitted cells; the digest is what separates them.
        """
        digest = cost_model_state_digest(self._model)
        provenance = getattr(self._model, "training_provenance", {}) or {}
        return DependencyIdentity(
            dependency_id=self._model_id,
            kind=DependencyKind.COST_MODEL,
            version=str(getattr(self._model, "model_version", "")),
            dataset_id=str(provenance.get("dataset_id", "")),
            state_digest=digest,
            restorable=True,
            detail=(
                "digest covers every fitted cell"
                if digest
                else "model exposes no fitted state to pin"
            ),
        )

    def _member_cost(self, member, snapshot: BeliefSnapshot) -> float:
        record = self._record_builder(member, snapshot)
        return float(self._model.predict(record).point)

    def expected_cost(
        self, candidate: CandidateAction, snapshot: BeliefSnapshot
    ) -> ScoreComponent:
        status = _verdict_status(self._verdict)
        if status is ComponentStatus.UNAVAILABLE:
            return ScoreComponent(
                name="expected_cost",
                value=None,
                status=status,
                source=f"m2:{self._model_id}",
                calibration_verdict=self._verdict,
                detail="cost calibration is insufficient to predict this cost",
            )

        support_notes: list[str] = []
        if self._support is not None:
            for member in candidate.members:
                try:
                    record = self._record_builder(member, snapshot)
                except Exception as exc:
                    return ScoreComponent(
                        name="expected_cost",
                        value=None,
                        status=ComponentStatus.UNAVAILABLE,
                        source=f"m2:{self._model_id}",
                        calibration_verdict=self._verdict,
                        detail=f"could not build a calibration query: {exc}",
                    )
                inside, reason = self._support.check(record, snapshot)
                if not inside:
                    support_notes.append(f"{member.action_id}: {reason}")
            if support_notes:
                # Outside the demonstrated envelope, a number is extrapolation.
                status = ComponentStatus.DEGRADED

        try:
            member_costs = {
                m.action_id: self._member_cost(m, snapshot)
                for m in candidate.members
            }
        except Exception as exc:  # a model that cannot predict must say so
            return ScoreComponent(
                name="expected_cost",
                value=None,
                status=ComponentStatus.UNAVAILABLE,
                source=f"m2:{self._model_id}",
                calibration_verdict=self._verdict,
                detail=f"cost model could not predict: {exc}",
            )

        if isinstance(candidate, CompositeAction):
            total = candidate.aggregate_cost(member_costs)
            detail = (
                f"composite cost aggregated by "
                f"{candidate.cost_aggregation.value}"
            )
        else:
            total = member_costs[candidate.action_id]
            detail = "single-action cost prediction"

        return ScoreComponent(
            name="expected_cost",
            value=total,
            status=status,
            source=f"m2:{self._model_id}",
            calibration_verdict=self._verdict,
            unit=self._cost_unit,
            assumptions=(
                "cost is predicted for the current structure x environment cell",
            )
            + tuple(f"outside support: {n}" for n in support_notes),
            detail=(
                detail
                + ("; outside demonstrated support" if support_notes else "")
            ),
        )


class CalibrationFailureSupplier:
    """p(failure) from the M2 failure model — usually UNAVAILABLE.

    M2 could not fit a failure model on this repository's corpus (zero
    failures in 1,320 runs), so the honest answer here is almost always "we do
    not know". That is preserved rather than smoothed over.
    """

    def __init__(
        self,
        failure_model: Any | None = None,
        *,
        record_builder=None,
        verdict: CalibrationVerdict | None = None,
        model_id: str = "failure.smoothed_rate",
        insufficient_reason: str = "",
    ) -> None:
        self._model = failure_model
        self._record_builder = record_builder
        self._verdict = verdict
        self._model_id = model_id
        self._reason = insufficient_reason

    def dependency_identity(self) -> DependencyIdentity:
        provenance = getattr(self._model, "training_provenance", {}) or {}
        if self._model is None:
            # No model at all is a perfectly stable dependency: it always
            # answers "unavailable", so it is pinnable.
            return DependencyIdentity(
                dependency_id=self._model_id,
                kind=DependencyKind.FAILURE_SOURCE,
                state_digest=canonical_digest({"failure_model": "absent"}),
                detail="no failure model; p_cf is always UNAVAILABLE",
            )
        return DependencyIdentity(
            dependency_id=self._model_id,
            kind=DependencyKind.FAILURE_SOURCE,
            version=str(getattr(self._model, "model_version", "")),
            dataset_id=str(provenance.get("dataset_id", "")),
            state_digest=canonical_digest(
                {
                    "version": str(getattr(self._model, "model_version", "")),
                    "provenance": dict(provenance),
                }
            ),
        )

    def computational_failure_probability(
        self, candidate: CandidateAction, snapshot: BeliefSnapshot
    ) -> ScoreComponent:
        status = _verdict_status(self._verdict)
        if self._model is None or status is ComponentStatus.UNAVAILABLE:
            return ScoreComponent(
                name="p_computational_failure",
                value=None,
                status=ComponentStatus.UNAVAILABLE,
                source=f"m2:{self._model_id}",
                calibration_verdict=self._verdict,
                detail=(
                    self._reason
                    or "failure calibration is insufficient; p_fail was not learned"
                ),
            )

        try:
            probabilities = [
                1.0
                - self._model.predict(
                    self._record_builder(m, snapshot)
                ).probability_success
                for m in candidate.members
            ]
        except Exception as exc:
            return ScoreComponent(
                name="p_computational_failure",
                value=None,
                status=ComponentStatus.UNAVAILABLE,
                source=f"m2:{self._model_id}",
                calibration_verdict=self._verdict,
                detail=f"failure model could not predict: {exc}",
            )

        if isinstance(candidate, CompositeAction):
            if not candidate.assumes_independence:
                # Reaching here means the engine already refused the candidate;
                # this is the second line of defence.
                return ScoreComponent(
                    name="p_computational_failure",
                    value=None,
                    status=ComponentStatus.UNAVAILABLE,
                    source=f"m2:{self._model_id}",
                    calibration_verdict=self._verdict,
                    detail=(
                        "composite failure cannot be combined without a declared "
                        "outcome dependence"
                    ),
                )
            joint_success = 1.0
            for probability in probabilities:
                joint_success *= 1.0 - probability
            value = 1.0 - joint_success
            detail = "composite p_fail under declared independence"
        else:
            value = probabilities[0]
            detail = "single-action failure probability"

        return ScoreComponent(
            name="p_computational_failure",
            value=value,
            status=status,
            source=f"m2:{self._model_id}",
            calibration_verdict=self._verdict,
            detail=detail,
        )
