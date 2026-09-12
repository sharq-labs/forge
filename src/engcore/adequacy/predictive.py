"""Shared model-adequacy math pulled by K4.

Adequacy is evaluated against observations that were not used to fit the
posterior.  The scored path keeps the exact finite Gaussian-mixture predictive
distribution: no Gaussian approximation replaces its CDF or log density.

The result is deliberately study-bounded evidence.  It does not mutate a
model's global validation status or convert predictive support into a truth
probability.

Evidence identity
-----------------
A model comparison is a statement about two models on **one** body of evidence.
``compare_log_predictive_scores`` used to check that the paired assessments
named the same observation keys in the same order and carried the right model
references, and nothing about the evidence itself. Two assessments that shared
a key and differed in the observed value, the likelihood's noise, the held-out
partition, the posterior's dataset or the twin were compared, and the difference
in evidence came back as a difference between models: a held-out reading of
30 K against 12 K under one key produced a preference of +31.8 nats.

So every assessment carries a :class:`PredictiveEvidenceIdentity`, built from
the inputs its score was computed from rather than supplied beside them, and
checked against the assessment's own fields at construction. A comparison
refuses any pair whose identities differ, in any field, values included.

``source_ref`` is deliberately not part of the identity. It names who produced
an assessment, and K4 writes a different one per model for one held-out set; an
identity that included it would refuse every comparison K4 makes. Nor is the
credible mass: it sets the interval the coverage flag is read against, and the
log score does not read it.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.special import logsumexp, ndtr

from ..inference import AdmittedForwardTable, PosteriorGrid
from ..scientific.ir.problem import ModelReference
from ..scientific.sequences import duplicates
from ..scientific.serialization import require_schema, schema_string
from ..scientific.twins import TwinReference
from ..scientific.units.quantity import Quantity, normalize_unit
from ..uq import PredictiveObservableSpec, posterior_predictive_uq
from ..uq.predictive import UQProblemError


class ModelAdequacyError(ValueError):
    """Raised when an adequacy/comparison request is scientifically invalid."""


class StudyAdequacyStatus(str):
    ADEQUATE_FOR_DECLARED_STUDY = "adequate_for_declared_study"
    INADEQUATE_FOR_DECLARED_STUDY = "inadequate_for_declared_study"
    INCONCLUSIVE = "inconclusive"


PREDICTIVE_EVIDENCE_SCHEMA = schema_string("predictive_evidence_identity")
PREDICTIVE_ASSESSMENT_SCHEMA = schema_string("predictive_observation_assessment")

#: What makes two scored held-out observations the same evidence, in the order a
#: refusal names them. One list, read by the digest and by the pairing check
#: alike, so neither can consult a field the other ignores.
EVIDENCE_IDENTITY_FIELDS = (
    "observation_key",
    "observed_value",
    "unit",
    "likelihood_sigma",
    "heldout_dataset_id",
    "posterior_dataset_id",
    "twin",
)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, TwinReference):
        return [value.twin_id, value.version]
    return value


@dataclass(frozen=True)
class PredictiveEvidenceIdentity:
    """What one scored held-out observation is, as evidence.

    ``observed_value`` and ``likelihood_sigma`` are magnitudes in ``unit``, the
    observable's declared unit: the two numbers the log density was computed
    from. ``heldout_dataset_id`` names the held-out partition the observation
    belongs to, ``posterior_dataset_id`` the data the model was conditioned on,
    and ``twin`` the system both describe.

    Two identities are the same evidence only when every field agrees. A shared
    observation key is a label, and a label is not evidence.
    """

    observation_key: str
    observed_value: float
    unit: str
    likelihood_sigma: float
    heldout_dataset_id: str
    posterior_dataset_id: str
    twin: TwinReference

    def __post_init__(self) -> None:
        for label in ("observation_key", "heldout_dataset_id", "posterior_dataset_id"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise ModelAdequacyError(f"evidence identity requires a non-empty {label}")
            object.__setattr__(self, label, text)
        object.__setattr__(self, "unit", normalize_unit(self.unit))
        for label in ("observed_value", "likelihood_sigma"):
            value = float(getattr(self, label))
            if not math.isfinite(value):
                raise ModelAdequacyError(f"evidence identity {label} must be finite")
            object.__setattr__(self, label, value)
        if self.likelihood_sigma <= 0.0:
            raise ModelAdequacyError("evidence identity likelihood_sigma must be positive")
        if not isinstance(self.twin, TwinReference):
            raise ModelAdequacyError("evidence identity requires a TwinReference")

    def _canonical(self) -> dict[str, Any]:
        return {name: _canonical_value(getattr(self, name)) for name in EVIDENCE_IDENTITY_FIELDS}

    @property
    def digest(self) -> str:
        """SHA-256 over the identity fields, recomputed on every read."""
        blob = json.dumps(self._canonical(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def differences(self, other: "PredictiveEvidenceIdentity") -> tuple[str, ...]:
        """The identity fields on which ``other`` is different evidence."""
        mine, theirs = self._canonical(), other._canonical()
        return tuple(
            name for name in EVIDENCE_IDENTITY_FIELDS if mine.get(name) != theirs.get(name)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PREDICTIVE_EVIDENCE_SCHEMA,
            "observation_key": self.observation_key,
            "observed_value": self.observed_value,
            "unit": self.unit,
            "likelihood_sigma": self.likelihood_sigma,
            "heldout_dataset_id": self.heldout_dataset_id,
            "posterior_dataset_id": self.posterior_dataset_id,
            "twin": self.twin.to_dict(),
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PredictiveEvidenceIdentity":
        require_schema(payload, PREDICTIVE_EVIDENCE_SCHEMA)
        try:
            identity = cls(
                observation_key=payload["observation_key"],
                observed_value=payload["observed_value"],
                unit=payload["unit"],
                likelihood_sigma=payload["likelihood_sigma"],
                heldout_dataset_id=payload["heldout_dataset_id"],
                posterior_dataset_id=payload["posterior_dataset_id"],
                twin=TwinReference.from_dict(payload["twin"]),
            )
        except KeyError as exc:
            raise ModelAdequacyError(
                f"serialized evidence identity is missing {exc.args[0]!r}"
            ) from None
        declared = payload.get("digest")
        if declared != identity.digest:
            raise ModelAdequacyError(
                f"serialized evidence identity for {identity.observation_key!r} carries "
                f"digest {str(declared)[:12]}… but its fields hash to "
                f"{identity.digest[:12]}…; evidence whose identity was edited is not "
                f"the evidence it names"
            )
        return identity


@dataclass(frozen=True)
class PredictiveObservationAssessment:
    observation_key: str
    observed: Quantity
    predictive_mean: Quantity
    total_standard_uncertainty: Quantity
    standardized_residual: float
    predictive_cdf: float
    two_sided_tail_probability: float
    log_predictive_density: float
    covered_by_central_interval: bool
    confidence_level: float
    posterior_dataset_id: str
    twin: TwinReference
    model: ModelReference
    source_ref: str
    #: The evidence this assessment was scored against. Required, and checked
    #: against the fields above: an assessment names its own evidence, and a
    #: record whose fields describe other evidence than its identity states is
    #: refused rather than believed.
    evidence: PredictiveEvidenceIdentity

    def __post_init__(self) -> None:
        if not str(self.observation_key).strip():
            raise ModelAdequacyError("adequacy assessment requires observation_key")
        for value in (self.observed, self.predictive_mean, self.total_standard_uncertainty):
            if not isinstance(value, Quantity):
                raise ModelAdequacyError("adequacy quantities must be Quantity")
        self.predictive_mean.require_compatible(self.observed, context="adequacy observation")
        self.predictive_mean.require_compatible(
            self.total_standard_uncertainty, context="adequacy predictive uncertainty"
        )
        for label in (
            "standardized_residual",
            "predictive_cdf",
            "two_sided_tail_probability",
            "log_predictive_density",
        ):
            value = float(getattr(self, label))
            if not math.isfinite(value):
                raise ModelAdequacyError(f"{label} must be finite")
            object.__setattr__(self, label, value)
        if not 0.0 <= self.predictive_cdf <= 1.0:
            raise ModelAdequacyError("predictive_cdf must lie in [0, 1]")
        if not 0.0 <= self.two_sided_tail_probability <= 1.0:
            raise ModelAdequacyError("two_sided_tail_probability must lie in [0, 1]")
        level = float(self.confidence_level)
        if not 0.0 < level < 1.0:
            raise ModelAdequacyError("confidence_level must lie in (0, 1)")
        object.__setattr__(self, "confidence_level", level)
        if not str(self.posterior_dataset_id).strip() or not str(self.source_ref).strip():
            raise ModelAdequacyError("adequacy assessment requires dataset/source binding")
        if not isinstance(self.twin, TwinReference) or not isinstance(self.model, ModelReference):
            raise ModelAdequacyError("adequacy assessment requires TwinReference and ModelReference")
        if not isinstance(self.evidence, PredictiveEvidenceIdentity):
            raise ModelAdequacyError(
                "adequacy assessment requires a PredictiveEvidenceIdentity: the "
                "evidence it was scored against"
            )
        mismatched = self._evidence_mismatches()
        if mismatched:
            raise ModelAdequacyError(
                f"adequacy assessment for {self.observation_key!r} does not match its "
                f"evidence identity: {list(mismatched)} differ. An assessment names the "
                f"evidence it was scored against, and a record describing other "
                f"evidence than it names cannot be paired with anything"
            )

    def _evidence_mismatches(self) -> tuple[str, ...]:
        evidence = self.evidence
        mismatched: list[str] = []
        if evidence.observation_key != str(self.observation_key).strip():
            mismatched.append("observation_key")
        try:
            if self.observed.magnitude_in(evidence.unit) != evidence.observed_value:
                mismatched.append("observed_value")
            total = self.total_standard_uncertainty.magnitude_in(evidence.unit)
        except Exception:  # noqa: BLE001 - an incompatible unit is a mismatch, not a crash
            mismatched.append("unit")
        else:
            # The total predictive uncertainty adds the likelihood's noise in
            # quadrature, so it can never be smaller than that noise. A stated
            # sigma above it is a sigma this score was not computed with.
            if total < evidence.likelihood_sigma * (1.0 - 1.0e-12):
                mismatched.append("likelihood_sigma")
        if evidence.posterior_dataset_id != str(self.posterior_dataset_id).strip():
            mismatched.append("posterior_dataset_id")
        if evidence.twin != self.twin:
            mismatched.append("twin")
        return tuple(mismatched)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PREDICTIVE_ASSESSMENT_SCHEMA,
            "observation_key": self.observation_key,
            "observed": self.observed.to_dict(),
            "predictive_mean": self.predictive_mean.to_dict(),
            "total_standard_uncertainty": self.total_standard_uncertainty.to_dict(),
            "standardized_residual": self.standardized_residual,
            "predictive_cdf": self.predictive_cdf,
            "two_sided_tail_probability": self.two_sided_tail_probability,
            "log_predictive_density": self.log_predictive_density,
            "covered_by_central_interval": bool(self.covered_by_central_interval),
            "confidence_level": self.confidence_level,
            "posterior_dataset_id": self.posterior_dataset_id,
            "twin": self.twin.to_dict(),
            "model": self.model.to_dict(),
            "source_ref": self.source_ref,
            "evidence": self.evidence.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PredictiveObservationAssessment":
        """Rebuild an assessment, revalidating its evidence identity on the way in.

        The identity's digest is recomputed, and the rebuilt record is checked
        against the identity it carries, so an edited value, dataset or twin is
        refused whether or not the digest was edited to match.
        """
        require_schema(payload, PREDICTIVE_ASSESSMENT_SCHEMA)
        if "evidence" not in payload:
            raise ModelAdequacyError(
                "serialized adequacy assessment carries no evidence identity, so "
                "nothing states which evidence it was scored against; it cannot be "
                "compared with anything"
            )
        return cls(
            observation_key=payload["observation_key"],
            observed=Quantity.from_dict(payload["observed"]),
            predictive_mean=Quantity.from_dict(payload["predictive_mean"]),
            total_standard_uncertainty=Quantity.from_dict(payload["total_standard_uncertainty"]),
            standardized_residual=payload["standardized_residual"],
            predictive_cdf=payload["predictive_cdf"],
            two_sided_tail_probability=payload["two_sided_tail_probability"],
            log_predictive_density=payload["log_predictive_density"],
            covered_by_central_interval=bool(payload["covered_by_central_interval"]),
            confidence_level=payload["confidence_level"],
            posterior_dataset_id=payload["posterior_dataset_id"],
            twin=TwinReference.from_dict(payload["twin"]),
            model=ModelReference.from_dict(payload["model"]),
            source_ref=payload["source_ref"],
            evidence=PredictiveEvidenceIdentity.from_dict(payload["evidence"]),
        )


@dataclass(frozen=True)
class ModelScoreComparison:
    model_a: ModelReference
    model_b: ModelReference
    score_a: float
    score_b: float
    delta_a_minus_b: float
    preferred_model: ModelReference | None
    #: SHA-256 over the ordered evidence identities both models were scored on.
    evidence_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_a": self.model_a.to_dict(),
            "model_b": self.model_b.to_dict(),
            "score_a": self.score_a,
            "score_b": self.score_b,
            "delta_a_minus_b": self.delta_a_minus_b,
            "preferred_model": self.preferred_model.to_dict() if self.preferred_model else None,
            "evidence_digest": self.evidence_digest,
        }


def assess_predictive_observation(
    posterior: PosteriorGrid,
    predictive_table: AdmittedForwardTable,
    spec: PredictiveObservableSpec,
    observed: Quantity,
    *,
    twin: TwinReference,
    model: ModelReference,
    source_ref: str,
    heldout_dataset_id: str,
    credible_mass: float = 0.95,
) -> PredictiveObservationAssessment:
    """Score one held-out observation against an exact predictive mixture.

    ``heldout_dataset_id`` names the held-out partition ``observed`` belongs to.
    It is required: it is part of what makes this assessment comparable with
    another model's, and the score alone cannot say which partition it came from.
    """

    if spec.observation_sigma is None:
        raise ModelAdequacyError(
            "predictive adequacy requires declared observation noise; latent-only "
            "uncertainty has no observational likelihood"
        )
    if not isinstance(observed, Quantity):
        raise ModelAdequacyError("held-out observation must be Quantity")
    try:
        observed.require_compatible(Quantity(1.0, spec.unit), context="held-out observation")
        predictive = posterior_predictive_uq(
            posterior,
            predictive_table,
            spec,
            twin=twin,
            model=model,
            source_ref=source_ref,
            credible_mass=credible_mass,
        )
    except UQProblemError as exc:
        raise ModelAdequacyError(str(exc)) from exc

    try:
        column = predictive_table.observation_keys.index(spec.observation_key)
    except ValueError as exc:
        raise ModelAdequacyError(
            f"predictive table has no observable {spec.observation_key!r}"
        ) from exc

    weights = np.asarray(posterior.weights, dtype=np.float64)
    positive = weights > 0.0
    if not np.any(positive):
        raise ModelAdequacyError("posterior has no positive predictive mass")
    means = np.asarray(predictive_table.values[:, column], dtype=np.float64)[positive]
    weights = weights[positive]
    weights = weights / float(np.sum(weights, dtype=np.float64))

    sigma = float(spec.observation_sigma.magnitude_in(spec.unit))
    y = float(observed.magnitude_in(spec.unit))
    if not math.isfinite(sigma) or sigma <= 0.0:
        raise ModelAdequacyError("observation sigma must be finite and positive")
    if not math.isfinite(y) or not np.all(np.isfinite(means)):
        raise ModelAdequacyError("predictive adequacy received non-finite support/observation")

    z_components = (y - means) / sigma
    cdf = float(np.sum(weights * ndtr(z_components)))
    cdf = min(max(cdf, 0.0), 1.0)
    tail = 2.0 * min(cdf, 1.0 - cdf)

    log_components = (
        np.log(weights)
        - 0.5 * z_components * z_components
        - math.log(sigma)
        - 0.5 * math.log(2.0 * math.pi)
    )
    log_density = float(logsumexp(log_components))

    unit = predictive.mean.units
    total_std = predictive.total_standard_uncertainty.magnitude_in(unit)
    if total_std <= 0.0:
        raise ModelAdequacyError("total predictive standard uncertainty must be positive")
    standardized = (
        observed.magnitude_in(unit) - predictive.mean.magnitude_in(unit)
    ) / total_std

    interval = predictive.total_interval
    if interval.lower is None or interval.upper is None:
        raise ModelAdequacyError("total predictive interval is missing bounds")
    value = observed.magnitude_in(unit)
    covered = (
        interval.lower.magnitude_in(unit) <= value <= interval.upper.magnitude_in(unit)
    )

    stored_observation = observed.to(spec.unit)
    return PredictiveObservationAssessment(
        observation_key=spec.observation_key,
        observed=stored_observation,
        predictive_mean=predictive.mean,
        total_standard_uncertainty=predictive.total_standard_uncertainty,
        standardized_residual=float(standardized),
        predictive_cdf=cdf,
        two_sided_tail_probability=tail,
        log_predictive_density=log_density,
        covered_by_central_interval=covered,
        confidence_level=float(credible_mass),
        posterior_dataset_id=posterior.dataset_id,
        twin=twin,
        model=model,
        source_ref=str(source_ref).strip(),
        evidence=PredictiveEvidenceIdentity(
            observation_key=spec.observation_key,
            observed_value=stored_observation.magnitude_in(spec.unit),
            unit=spec.unit,
            likelihood_sigma=sigma,
            heldout_dataset_id=heldout_dataset_id,
            posterior_dataset_id=posterior.dataset_id,
            twin=twin,
        ),
    )


def compare_log_predictive_scores(
    model_a: ModelReference,
    assessments_a: Sequence[PredictiveObservationAssessment],
    model_b: ModelReference,
    assessments_b: Sequence[PredictiveObservationAssessment],
) -> ModelScoreComparison:
    """Compare paired out-of-sample log predictive scores.

    A positive delta favors ``model_a``.  The function does not convert score
    differences into model probabilities.

    Paired means paired on evidence: position ``i`` of each side must be an
    assessment of the same canonical evidence (:class:`PredictiveEvidenceIdentity`),
    and no evidence may appear twice. Anything short of that is refused -- a
    shared key or a shared count is not the same evidence.
    """

    a = tuple(assessments_a)
    b = tuple(assessments_b)
    if not a or not b or len(a) != len(b):
        raise ModelAdequacyError("model comparison requires equally sized non-empty assessments")
    for side, items in (("model_a", a), ("model_b", b)):
        strangers = sorted(
            {type(item).__name__ for item in items if not isinstance(item, PredictiveObservationAssessment)}
        )
        if strangers:
            raise ModelAdequacyError(
                f"{side} assessments include {strangers}, not PredictiveObservationAssessment "
                f"records; only a typed assessment carries a verified evidence identity"
            )
    keys_a = tuple(item.observation_key for item in a)
    keys_b = tuple(item.observation_key for item in b)
    if keys_a != keys_b:
        raise ModelAdequacyError("model comparison observation order/keys differ")
    repeated = duplicates(list(keys_a))
    if repeated:
        raise ModelAdequacyError(
            f"model comparison lists observation(s) {repeated} more than once, so one "
            f"piece of evidence would be counted twice in both scores"
        )
    if any(item.model != model_a for item in a):
        raise ModelAdequacyError("model_a assessments carry a different ModelReference")
    if any(item.model != model_b for item in b):
        raise ModelAdequacyError("model_b assessments carry a different ModelReference")
    for index, (item_a, item_b) in enumerate(zip(a, b)):
        differing = item_a.evidence.differences(item_b.evidence)
        if differing:
            raise ModelAdequacyError(
                f"model comparison pair {index} ({item_a.observation_key!r}) was assessed "
                f"against different evidence: {list(differing)} differ. Two models receive "
                f"a comparative conclusion only on the same canonical evidence"
            )

    score_a = float(sum(item.log_predictive_density for item in a))
    score_b = float(sum(item.log_predictive_density for item in b))
    if not math.isfinite(score_a) or not math.isfinite(score_b):
        raise ModelAdequacyError("model comparison score is non-finite")
    delta = score_a - score_b
    preferred = model_a if delta > 0.0 else model_b if delta < 0.0 else None
    evidence_digest = hashlib.sha256(
        json.dumps([item.evidence.digest for item in a], separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ModelScoreComparison(
        model_a, model_b, score_a, score_b, delta, preferred, evidence_digest
    )
