"""Explicit posterior conditioning on predictive admission.

K3 discovered a boundary case that a posterior point can be scientifically
admissible at fitting conditions yet fail the numerical-admission gate at a new
predictive condition.  This module implements the separately preregistered K3.1
policy: measure unsupported posterior mass, fail closed above a declared budget,
and otherwise condition explicitly on the predictive-admitted event.

Nothing here fabricates a rejected prediction or weakens a domain gate.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..inference import AdmittedForwardTable, PosteriorGrid
from .predictive import UQProblemError

#: R-59 (re-audit 2026-09-16): the most posterior mass a conditioning may discard and still be reported as a
#: posterior for the same question. There was NO maximum: any finite non-negative budget was accepted, and at
#: 1.0 this module conditioned away 99.9997% of a posterior, renormalized by 3.4e5, and returned the result
#: as an ordinary grid. 0.05 is not a new number -- it is the complement of the 95% coverage every credible
#: interval in this repository is declared at, so the rule is that a conditioning may not discard more mass
#: than the entire tail a 95% claim already excludes. Beyond that the record is a statement about a minority
#: of the original mass, which is a different question and needs the observations that support it. Both
#: in-repo callers declare 1e-12.
MAXIMUM_CONDITIONED_UNSUPPORTED_MASS = 0.05


@dataclass(frozen=True)
class PredictiveAdmissionAudit:
    """Auditable record of conditioning a posterior on predictive admission."""

    posterior_dataset_id: str
    maximum_unsupported_mass: float
    supported_mass: float
    unsupported_mass: float
    conditioning_factor: float
    rejected_point_count: int
    rejected_point_indices: tuple[int, ...]
    positive_weight_rejected_point_count: int
    positive_weight_rejected_point_indices: tuple[int, ...]
    rejection_reasons: tuple[str, ...]
    conditional_on_predictive_admission: bool
    #: R-59: the digest of the weights this audit describes. The audit was bound to its posterior by nothing
    #: at all, so an audit recording a 1e-12 conditioning could travel beside a posterior conditioned by
    #: 3.4e5. Trailing, with an empty default, and written only when a conditioning actually happened.
    conditioned_weights_digest: str = ""

    def __post_init__(self) -> None:
        for label in (
            "maximum_unsupported_mass",
            "supported_mass",
            "unsupported_mass",
            "conditioning_factor",
        ):
            value = float(getattr(self, label))
            if not math.isfinite(value):
                raise UQProblemError(f"{label} must be finite")
            object.__setattr__(self, label, value)
        if self.maximum_unsupported_mass < 0.0:
            raise UQProblemError("maximum_unsupported_mass cannot be negative")
        if self.maximum_unsupported_mass > MAXIMUM_CONDITIONED_UNSUPPORTED_MASS:
            raise UQProblemError(
                f"maximum_unsupported_mass={self.maximum_unsupported_mass!r} exceeds the core's maximum "
                f"{MAXIMUM_CONDITIONED_UNSUPPORTED_MASS!r} (R-59). A conditioning may not discard more "
                f"posterior mass than the tail a 95% claim already excludes: beyond that the conditioned "
                f"record is a statement about a minority of the original mass, which is a different question"
            )
        if not 0.0 <= self.supported_mass <= 1.0 + 1.0e-12:
            raise UQProblemError("supported_mass is outside probability bounds")
        if not 0.0 <= self.unsupported_mass <= 1.0 + 1.0e-12:
            raise UQProblemError("unsupported_mass is outside probability bounds")
        # Direct float64 summation of an already-normalized posterior can place
        # supported_mass a final bit above one (for example
        # 1.0000000000000002).  Then the mathematically expected factor >= 1
        # is represented as 0.9999999999999998.  The same 1e-12 accounting
        # tolerance used by the K3.1 preregistration admits this rounding dust;
        # materially sub-unit factors still fail closed.
        if self.conditioning_factor < 1.0 - 1.0e-12:
            raise UQProblemError(
                "conditioning_factor is materially below one beyond probability-accounting tolerance"
            )
        if len(self.rejected_point_indices) != len(self.rejection_reasons):
            raise UQProblemError("rejected-point indices/reasons length mismatch")
        if int(self.rejected_point_count) != len(self.rejected_point_indices):
            raise UQProblemError("rejected_point_count is inconsistent")
        if int(self.positive_weight_rejected_point_count) != len(
            self.positive_weight_rejected_point_indices
        ):
            raise UQProblemError("positive-weight rejected-point count is inconsistent")

    def to_dict(self) -> dict[str, Any]:
        return {
            "posterior_dataset_id": self.posterior_dataset_id,
            "maximum_unsupported_mass": self.maximum_unsupported_mass,
            "supported_mass": self.supported_mass,
            "unsupported_mass": self.unsupported_mass,
            "conditioning_factor": self.conditioning_factor,
            "rejected_point_count": int(self.rejected_point_count),
            "rejected_point_indices": list(self.rejected_point_indices),
            "positive_weight_rejected_point_count": int(
                self.positive_weight_rejected_point_count
            ),
            "positive_weight_rejected_point_indices": list(
                self.positive_weight_rejected_point_indices
            ),
            "rejection_reasons": list(self.rejection_reasons),
            "conditional_on_predictive_admission": bool(
                self.conditional_on_predictive_admission
            ),
            # R-59: written only when a conditioning happened, so an unconditioned record keeps its bytes.
            **({"conditioned_weights_digest": self.conditioned_weights_digest}
               if self.conditioned_weights_digest else {}),
        }


def _digest_of(payload: dict) -> str:
    """A canonical SHA-256 over a JSON-serializable payload, as the other record digests here are taken."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def conditioned_weights_digest(posterior: PosteriorGrid) -> str:
    """The digest that binds a conditioning audit to the weights it describes (R-59)."""
    weights = np.asarray(posterior.weights, dtype=np.float64)
    return _digest_of({
        "dataset_id": str(posterior.dataset_id),
        "parameter_names": [str(name) for name in posterior.parameter_names],
        "weights": [float(value).hex() for value in weights.reshape(-1)],
    })


@dataclass(frozen=True)
class ConditionedPosterior:
    """Posterior plus the evidence record authorizing its predictive use."""

    posterior: PosteriorGrid
    audit: PredictiveAdmissionAudit

    def __post_init__(self) -> None:
        """R-59: the pair is inseparable, so it cannot be recombined.

        The audit says how much mass was discarded and by what factor, and nothing tied it to the posterior
        it describes -- an audit recording a 1e-12 conditioning could travel beside one conditioned by 3.4e5.
        A digest over the weights is what makes the two one record; it is integrity-only, as every digest
        here is, which is why the mask and the derived dataset identity are re-derived rather than asserted.
        """
        if not isinstance(self.posterior, PosteriorGrid):
            raise UQProblemError("a conditioned posterior holds a PosteriorGrid")
        if not isinstance(self.audit, PredictiveAdmissionAudit):
            raise UQProblemError("a conditioned posterior holds a PredictiveAdmissionAudit")
        carried = str(self.audit.conditioned_weights_digest)
        if self.audit.conditional_on_predictive_admission:
            expected = conditioned_weights_digest(self.posterior)
            if carried != expected:
                raise UQProblemError(
                    f"the audit describes weights whose digest is {carried!r} and this posterior's weights "
                    f"digest to {expected!r}: an audit and a posterior that were not produced together are "
                    f"not one record"
                )
        elif carried:
            raise UQProblemError(
                "an audit that records no conditioning carries no conditioned-weights digest"
            )


def _validate_binding(posterior: PosteriorGrid, table: AdmittedForwardTable) -> None:
    if not isinstance(posterior, PosteriorGrid):
        raise UQProblemError("predictive admission requires PosteriorGrid")
    if not isinstance(table, AdmittedForwardTable):
        raise UQProblemError("predictive admission requires AdmittedForwardTable")
    if posterior.parameter_names != table.parameter_names:
        raise UQProblemError("posterior and predictive table parameter names differ")
    if posterior.points.shape != table.points.shape or not np.array_equal(
        posterior.points, table.points
    ):
        raise UQProblemError(
            "posterior and predictive table are not on identical parameter support"
        )
    # R-71 (I-28 part B): a table that declares no observation units says nothing about what its numbers
    # are, and this is the path where a table decides which posterior nodes are predictively supported.
    if not table.observation_units:
        raise UQProblemError(
            "the predictive table declares no observation units, so nothing says what its numbers are in "
            "or which observation set it was built against. A predictive-admission decision is not made "
            "from a table bound to nothing: rebuild it with `AdmittedForwardTable.from_rows`"
        )


def condition_posterior_on_predictive_admission(
    posterior: PosteriorGrid,
    predictive_table: AdmittedForwardTable,
    *,
    maximum_unsupported_mass: float,
) -> ConditionedPosterior:
    """Condition explicitly on predictive admission or fail closed.

    ``unsupported_mass`` is computed by direct summation of stored posterior
    weights at rejected predictive points, exactly as preregistered.  A non-zero
    mass is never described as zero; when it is within the declared budget the
    returned posterior has rejected weights set to zero and admitted weights
    divided by the measured supported mass.
    """

    _validate_binding(posterior, predictive_table)
    budget = float(maximum_unsupported_mass)
    if not math.isfinite(budget) or budget < 0.0:
        raise UQProblemError("maximum_unsupported_mass must be finite and non-negative")

    weights = np.asarray(posterior.weights, dtype=np.float64)
    admitted = np.asarray(predictive_table.admissible_mask, dtype=bool)
    rejected = ~admitted

    unsupported_mass = float(np.sum(weights[rejected], dtype=np.float64))
    supported_mass = float(np.sum(weights[admitted], dtype=np.float64))
    total = supported_mass + unsupported_mass
    if not math.isfinite(total) or abs(total - 1.0) > 1.0e-12:
        raise UQProblemError(
            "predictive support accounting does not sum to one within 1e-12: "
            f"supported={supported_mass:.17g}, unsupported={unsupported_mass:.17g}"
        )
    if unsupported_mass > budget:
        raise UQProblemError(
            "unsupported predictive posterior mass exceeds declared budget: "
            f"mass={unsupported_mass:.17g}, budget={budget:.17g}"
        )
    if supported_mass <= 0.0:
        raise UQProblemError("no posterior mass remains on predictive-admitted support")

    rejected_indices = tuple(int(i) for i in np.flatnonzero(rejected))
    positive_rejected = rejected & (weights > 0.0)
    positive_rejected_indices = tuple(
        int(i) for i in np.flatnonzero(positive_rejected)
    )
    reasons = tuple(
        str(predictive_table.rejection_reasons[i]) for i in rejected_indices
    )

    if unsupported_mass == 0.0:
        conditioned = posterior
        factor = 1.0
    else:
        conditioned_weights = np.array(weights, copy=True)
        conditioned_weights[rejected] = 0.0
        conditioned_weights[admitted] = conditioned_weights[admitted] / supported_mass
        # Last-bit normalization keeps PosteriorGrid's strict sum contract while
        # preserving the explicit conditioning factor in the audit record.
        conditioned_weights = conditioned_weights / float(
            np.sum(conditioned_weights, dtype=np.float64)
        )
        # The conditioned record states the conditioning in its likelihood as
        # well as its weights: a rejected node has no likelihood under the
        # predictive-admitted event. PosteriorGrid refuses weights that are not
        # the normalized likelihood (HUQ-04), and zeroed weights beside the
        # unconditioned likelihood would be exactly that.
        conditioned_log_likelihood = np.array(posterior.log_likelihood, dtype=np.float64, copy=True)
        conditioned_log_likelihood[rejected] = -np.inf
        # R-59: the conditioned posterior is a DIFFERENT posterior -- it answers "given predictive
        # admission" -- and it used to be indistinguishable from the unconditioned fit to the same dataset:
        # same dataset id, no field recording the conditioning, while its standard deviation moved from 0.1
        # to 0.5 in the audit's own reproduction. The identity is derived, because the dataset id is the
        # field every downstream route reads to decide what a posterior is about.
        #
        # THE ADMISSIBLE MASK IS DELIBERATELY NOT NARROWED, and the reason is a finding of its own
        # (amendment 1): the mask means admissibility AT THE FITTING CONDITIONS, and `PosteriorGrid`'s
        # likelihood-consistency rule (HUQ-04) is enforced over `mask & isfinite(log_likelihood)`. Narrowing
        # the mask therefore takes the rejected node OUT of the support the rule covers -- and the certified
        # mutation G32d, which removes the `-inf` assignment below, stopped being killed. Predictive support
        # is reported separately instead, which is the audit's own alternative: the audit record carries the
        # supported mass, the rejected indices and their reasons, and is now bound to these weights.
        conditioned_mask = posterior.admissible_mask
        identity = _digest_of({
            "admitted": [bool(value) for value in admitted.reshape(-1)],
            "supported_mass": float(supported_mass).hex(),
            "rejected_point_indices": list(rejected_indices),
        })
        conditioned = PosteriorGrid(
            parameter_names=posterior.parameter_names,
            points=posterior.points,
            weights=conditioned_weights,
            log_likelihood=conditioned_log_likelihood,
            admissible_mask=conditioned_mask,
            dataset_id=f"{posterior.dataset_id}|predictive-admitted:{identity}",
        )
        factor = 1.0 / supported_mass

    audit = PredictiveAdmissionAudit(
        posterior_dataset_id=posterior.dataset_id,
        maximum_unsupported_mass=budget,
        supported_mass=supported_mass,
        unsupported_mass=unsupported_mass,
        conditioning_factor=factor,
        rejected_point_count=len(rejected_indices),
        rejected_point_indices=rejected_indices,
        positive_weight_rejected_point_count=len(positive_rejected_indices),
        positive_weight_rejected_point_indices=positive_rejected_indices,
        rejection_reasons=reasons,
        conditional_on_predictive_admission=unsupported_mass > 0.0,
        conditioned_weights_digest=(
            conditioned_weights_digest(conditioned) if unsupported_mass > 0.0 else ""
        ),
    )
    return ConditionedPosterior(posterior=conditioned, audit=audit)
