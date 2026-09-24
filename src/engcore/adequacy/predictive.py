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
    # R-24 (re-audit 2026-09-16): APPENDED. The two dataset ids above are STRINGS, so two calibration
    # campaigns labelled alike paired as one evidence and the difference in their training data was reported
    # as a model preference. Empty on a record written before this rule, and then absent from the canonical
    # form, so such a record keeps the digest it had.
    "split_content_digest",
)


#: R-34: the record digests this process bound to a split, by content. Written only at the end of
#: `assess_predictive_observation`'s split branch, read only by `content_binding_verified`. Module-private and
#: never serialized: a binding is an in-process fact about numbers, not a field on a record.
_CONTENT_BOUND_RECORDS: set[str] = set()


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
    #: R-24: a digest over the SPLIT's content -- its twin, both dataset ids and the canonical content digest
    #: of every observation in both halves. Set only where the split is in hand, so a comparison can require
    #: both sides to be bound to the same evidence and not merely to the same labels. Empty otherwise.
    split_content_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "split_content_digest", str(self.split_content_digest).strip())
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
        # an empty split_content_digest is LEFT OUT, so a record written before that field existed hashes to
        # what it hashed to. `differences` reads the same mapping with .get, so an absent value still differs
        # from a present one and the refusal names the field.
        return {name: _canonical_value(getattr(self, name)) for name in EVIDENCE_IDENTITY_FIELDS
                if not (name == "split_content_digest" and not self.split_content_digest)}

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
            **({"split_content_digest": self.split_content_digest} if self.split_content_digest else {}),
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
                split_content_digest=payload.get("split_content_digest", ""),
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
    #: CORE-007 (scientific core audit 2026-09-16): True only when the assessment was made with the split and the
    #: calibration table, so the posterior was shown BY CONTENT to be the calibration half's likelihood and the observation
    #: to be the split's held-out one. A read-back record's value is integrity-only, like every serialized digest.
    content_bound: bool = False
    #: I-03 (R-02, finding 33): why the content binding was WITHHELD, when it was.
    #:
    #: The binding branch now applies the V2 grid evidence checks it never had -- prior uniformity
    #: (CORE-010) and containment (CORE-002). A grid over the posterior mean +/- 0.6 sd passes
    #: content binding on its own terms, because its log-likelihood IS the calibration likelihood on
    #: those nodes, while reporting a parameter sd of 0.34x the honest one; the comparison then
    #: turned a non-decisive 2.872-nat difference into a decisive 6.259-nat preference. On such a
    #: finding this assessment is not bound, not registered, and says so here. Recorded rather than
    #: raised, because the round's strictness rule lowers a claim for unbound information instead of
    #: destroying the record. Serialized only when non-empty.
    content_binding_refused_because: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "content_binding_refused_because",
            str(self.content_binding_refused_because).strip(),
        )
        if self.content_bound and self.content_binding_refused_because:
            raise ModelAdequacyError(
                "an assessment cannot be content-bound AND carry a reason the binding was withheld; "
                "those are two answers to one question"
            )
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

    @property
    def record_digest(self) -> str:
        """SHA-256 over everything this record says EXCEPT the content_bound claim.

        The key of the in-process binding registry (R-34). Excluding the claim is what makes the registry a
        statement about the numbers rather than about the flag: a record reconstructed with the same numbers
        gets the same digest, and the binding it claims is then true of exactly those numbers.
        """
        payload = {k: v for k, v in self.to_dict().items() if k != "content_bound"}
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @property
    def content_binding_verified(self) -> bool:
        """Whether THIS PROCESS bound this record to a split, by content (R-34).

        ``content_bound`` is a field anyone can set -- ``dataclasses.replace``, ``from_dict``, the
        constructor -- and the comparison used to read it as proof. This reads a private registry that only
        :func:`assess_predictive_observation` writes, keyed by :attr:`record_digest`, so a flipped flag, a
        fabricated log density and a deserialized record are all unverified. A record read back from disk is
        never verified: content binding is an in-process fact, and the stored flag is integrity-only, which
        is what the audit document already says of it.
        """
        return self.record_digest in _CONTENT_BOUND_RECORDS

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
            **({"content_bound": True} if self.content_bound else {}),
            **({"content_binding_refused_because": self.content_binding_refused_because}
               if self.content_binding_refused_because else {}),
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
            content_bound=bool(payload.get("content_bound", False)),
            content_binding_refused_because=payload.get("content_binding_refused_because", ""),
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
    #: CORE-011: the number of paired observations and the standard error of the summed paired difference.
    n: int = 0
    standard_error: float = math.nan
    #: Why a preferred model was or was not named.
    why: str = ""
    #: R-32 (re-audit 2026-09-16): the paired standard error treats the held-out positions as independent
    #: measurements. RECORDED, never a reason to lower the verdict -- which is this program's rule for
    #: independence. CORE-012's flag existed only on routed predictive records; this standard error rests on
    #: the same assumption and said nothing about it.
    measurement_errors_assumed_independent: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_a": self.model_a.to_dict(),
            "model_b": self.model_b.to_dict(),
            "score_a": self.score_a,
            "score_b": self.score_b,
            "delta_a_minus_b": self.delta_a_minus_b,
            "preferred_model": self.preferred_model.to_dict() if self.preferred_model else None,
            "evidence_digest": self.evidence_digest,
            "n": int(self.n),
            "standard_error": None if not math.isfinite(self.standard_error) else float(self.standard_error),
            "why": self.why,
            "measurement_errors_assumed_independent": bool(self.measurement_errors_assumed_independent),
        }


def _split_content_digest(split) -> str:
    """SHA-256 over what the SPLIT is: its twin, both dataset ids and the content of every observation (R-24).

    ``inference.split.observation_content_digest`` is already canonical -- value and sigma in the dimension's
    base unit, rounded to twelve significant digits, and deliberately independent of the condition label -- so
    this is a digest of the evidence and not of a spelling of it. Both halves are covered: the held-out half is
    in the evidence identity value by value, but only for the ONE observation an assessment scores, and a
    comparison sums over the whole half.
    """
    from ..inference.split import observation_content_digest

    payload = {
        "twin": split.twin.to_dict(),
        "calibration_dataset_id": split.calibration.dataset_id,
        "heldout_dataset_id": split.held_out.dataset_id,
        "calibration_content": sorted(observation_content_digest(o) for o in split.calibration.observations),
        "heldout_content": sorted(observation_content_digest(o) for o in split.held_out.observations),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


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
    split=None,
    calibration_table: AdmittedForwardTable | None = None,
) -> PredictiveObservationAssessment:
    """Score one held-out observation against an exact predictive mixture.

    ``heldout_dataset_id`` names the held-out partition ``observed`` belongs to.
    It is required: it is part of what makes this assessment comparable with
    another model's, and the score alone cannot say which partition it came from.

    ``split`` and ``calibration_table`` (CORE-007): given both, the posterior must be the split's calibration-half
    likelihood by content, and ``observed`` must be the split's held-out observation of this key; the assessment is then
    ``content_bound``. A comparison names a preferred model only over content-bound assessments.
    """
    content_bound = False
    split_content_digest = ""
    content_binding_refused_because = ""
    if (split is None) != (calibration_table is None):
        raise ModelAdequacyError("content binding needs both the split and the calibration table, or neither")
    if split is not None:
        from ..inference.split import _require_posterior_conditioned_on_calibration, require_split

        require_split(split)
        _require_posterior_conditioned_on_calibration(split, posterior, calibration_table)
        if str(heldout_dataset_id).strip() != split.heldout_dataset_id:
            raise ModelAdequacyError(
                f"held-out dataset {heldout_dataset_id!r} is not the split's held-out set {split.heldout_dataset_id!r}")
        # R-24 (finding 40): the split's own docstring says a split whose halves describe different twins is
        # two studies and that scoring one against the other's posterior is refused. The branch never compared
        # them, and the evidence identity then recorded the caller's twin.
        if twin != split.twin:
            raise ModelAdequacyError(
                f"the assessment names twin {twin.twin_id!r}@{twin.version} and the split describes "
                f"{split.twin.twin_id!r}@{split.twin.version}; a score against another twin's split is not this "
                f"twin's held-out evidence")
        matching = [o for o in split.held_out.observations if o.key == spec.observation_key]
        if not matching:
            raise ModelAdequacyError(
                f"{spec.observation_key!r} is not an observation of the split's held-out set; a score on it is not "
                f"held-out evidence")
        held = matching[0].value
        try:
            same = isinstance(observed, Quantity) and math.isclose(
                observed.magnitude_in(held.units), held.magnitude, rel_tol=1e-12, abs_tol=0.0)
        except Exception:  # noqa: BLE001 - an incompatible value is another value
            same = False
        if not same:
            raise ModelAdequacyError(
                f"{spec.observation_key!r} is scored at {observed}, but the split's held-out observation is {held}")
        # R-24 (finding 29): the declared sigma is as much the split's evidence as the value is -- it is what
        # makes the log density a likelihood rather than a distance. A caller-chosen sigma created a decisive
        # preference (0.05 K against a declared 0.5 K) and erased a genuine one (5 K), content-bound both times.
        declared = matching[0].sigma
        try:
            same_sigma = spec.observation_sigma is not None and math.isclose(
                spec.observation_sigma.magnitude_in(declared.units), declared.magnitude, rel_tol=1e-12, abs_tol=0.0)
        except Exception:  # noqa: BLE001 - an incompatible sigma is another sigma
            same_sigma = False
        if not same_sigma:
            raise ModelAdequacyError(
                f"{spec.observation_key!r} is scored with likelihood sigma {spec.observation_sigma}, but the split's "
                f"held-out observation declares {declared}; the declared noise is part of the evidence, and a log "
                f"density computed with another sigma is not a score on it")
        # I-03 (R-02, finding 33): the V2 grid evidence checks this branch never had. Content
        # binding shows the posterior is THIS split's calibration likelihood; it says nothing about
        # whether the grid's own box holds that posterior, or whether equal node mass is the
        # declared prior. A box over the mean +/- 0.6 sd satisfies the binding exactly -- its
        # log-likelihood IS the calibration likelihood on those nodes -- while truncating the
        # parameter sd to 0.34x, and the comparison then named a preferred model on a 6.259-nat
        # difference that the honest box puts at 2.872 with a standard error of 0.940.
        #
        # Withheld rather than raised: the round's strictness rule lowers a claim for unbound
        # information, and `content_binding_verified` is already the gate `compare` reads, so
        # withholding IS the lowering. Goodness of fit is not applied here: it needs the calibration
        # OBSERVATIONS and the forward evaluator, and this function receives a calibration table.
        from ..hybrid_uq._grid_evidence import grid_containment, grid_prior_uniformity

        finding = (grid_prior_uniformity(posterior, None) or grid_containment(posterior, None))
        if finding is not None:
            content_binding_refused_because = f"{finding[0].value}: {finding[1]}"
        else:
            content_bound = True
            split_content_digest = _split_content_digest(split)

    if spec.observation_sigma is None:
        raise ModelAdequacyError(
            "predictive adequacy requires declared observation noise; latent-only "
            "uncertainty has no observational likelihood"
        )
    if not isinstance(observed, Quantity):
        raise ModelAdequacyError("held-out observation must be Quantity")
    # INF-07: an observation from the dataset the posterior was conditioned on
    # is fitting data, whatever this call names it. This function receives no
    # calibration observations, so it can refuse only the identity it is given;
    # the content binding lives where both halves are known
    # (inference.split._require_posterior_conditioned_on_calibration).
    if str(heldout_dataset_id).strip() == str(posterior.dataset_id).strip():
        raise ModelAdequacyError(
            f"held-out dataset {str(heldout_dataset_id).strip()!r} is the dataset the "
            f"posterior was conditioned on; a score on the fitting data is not "
            f"held-out predictive evidence"
        )
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
    try:
        means = predictive_table.values_in_unit(
            spec.observation_key, spec.unit
        )[positive]
    except Exception as exc:
        raise ModelAdequacyError(str(exc)) from exc
    weights = weights[positive]
    weights = weights / float(np.sum(weights, dtype=np.float64))

    sigma = float(spec.observation_sigma.magnitude_as_spread_in(spec.unit))
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
    total_std = predictive.total_standard_uncertainty.magnitude_as_spread_in(unit)
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
    assessment = PredictiveObservationAssessment(
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
            split_content_digest=split_content_digest,
        ),
        content_bound=content_bound,
        content_binding_refused_because=content_binding_refused_because,
    )
    if content_bound:
        # R-34: the binding is recorded HERE, where it was established, keyed by what the record says. The
        # `content_bound` field stays a recorded claim -- it is V1-frozen -- and the comparison reads this.
        _CONTENT_BOUND_RECORDS.add(assessment.record_digest)
    return assessment


#: CORE-011, preregistered in benchmarks/core_v4_false_confidence/BATCH4_THRESHOLD_PROTOCOL.json (class C, from the
#: elpd-difference practice of Vehtari, Gelman and Gabry 2017 and Sivula, Magnusson and Vehtari 2022).
#: R-33 (re-audit 2026-09-16): 2 -> 10. delta / SE is a t statistic on n - 1 degrees of freedom, and the gate is
#: only as good as the sd it divides by: the relative standard error of a sample sd on n - 1 degrees of freedom is
#: 1 / sqrt(2 (n - 1)) -- 0.707 at n = 2, 0.500 at n = 3, 0.236 at n = 10. 10 is the smallest n at which that is
#: below a quarter, so the standard error is a measurement rather than a coin flip. It also matches the audit's
#: reading of the elpd literature ("tens of points").
COMPARISON_MINIMUM_N = 10
COMPARISON_MINIMUM_ABS_DELTA = 4.0
#: The NORMAL multiple the level below is declared from. Kept at its preregistered value: the level does not change,
#: only the small-sample correction that was missing.
COMPARISON_MINIMUM_SE_MULTIPLE = 2.0
#: R-33: the two-sided level the multiple above states, 2 * (1 - Phi(2)). The gate used to compare a t statistic with
#: the NORMAL quantile, which at n = 2 is a Cauchy tail: P(|t| > 2) is about 0.295, and the audit measured a preferred
#: model in 27.5 % of runs between exact mirror-image models.
COMPARISON_ALPHA = 2.0 * (1.0 - float(ndtr(COMPARISON_MINIMUM_SE_MULTIPLE)))


def _critical_se_multiple(n: int) -> float:
    """The two-sided Student-t quantile on ``n - 1`` degrees of freedom at :data:`COMPARISON_ALPHA`.

    13.968 at n = 2, 4.527 at n = 3, 2.320 at n = 10, 2.026 at n = 100 -- against the fixed 2 the gate used.
    """
    from scipy.stats import t as _student_t

    return float(_student_t.ppf(1.0 - COMPARISON_ALPHA / 2.0, int(n) - 1))


def _decisive_preference(delta: float, n: int, standard_error: float) -> tuple[bool, str]:
    """Whether a summed paired difference is decisive, and why or why not (CORE-011, audit R-33).

    A pure function of three numbers, so the gate can be read at its own boundary rather than only through
    data that happens to land near it. Three conditions, in the order a refusal names them: enough paired
    observations for the standard error to be a measurement, a difference above the absolute floor, and a
    difference above the two-sided t quantile on ``n - 1`` degrees of freedom -- not the fixed normal 2, which
    at n = 2 is a Cauchy tail.
    """
    if int(n) < COMPARISON_MINIMUM_N:
        return False, (
            f"no preferred model: {int(n)} paired observation(s), fewer than the {COMPARISON_MINIMUM_N} at which a "
            f"standard error of the difference has its own relative error below a quarter")
    if abs(float(delta)) <= COMPARISON_MINIMUM_ABS_DELTA:
        return False, (
            f"no preferred model: |delta| {abs(float(delta)):.3g} nats does not exceed "
            f"{COMPARISON_MINIMUM_ABS_DELTA:g} nats")
    critical = _critical_se_multiple(n)
    if abs(float(delta)) <= critical * float(standard_error):
        return False, (
            f"no preferred model: |delta| {abs(float(delta)):.3g} nats is within {critical:.4g} standard errors "
            f"({float(standard_error):.3g}); {critical:.4g} is the two-sided t quantile on {int(n) - 1} degrees of "
            f"freedom at alpha {COMPARISON_ALPHA:.4g}, which is the level {COMPARISON_MINIMUM_SE_MULTIPLE:g} normal "
            f"standard errors declares")
    return True, (
        f"|delta| {abs(float(delta)):.3g} nats over {int(n)} content-bound paired observations exceeds "
        f"{COMPARISON_MINIMUM_ABS_DELTA:g} nats and {critical:.4g} standard errors ({float(standard_error):.3g}), the "
        f"t quantile on {int(n) - 1} degrees of freedom at alpha {COMPARISON_ALPHA:.4g}")


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
    evidence_digest = hashlib.sha256(
        json.dumps([item.evidence.digest for item in a], separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    # CORE-011 (scientific core audit 2026-09-16): a preference only when the difference is decisive. It used to be
    # named for any delta > 0, including 1.5e-9 nats on one observation.
    n = len(a)
    differences = np.asarray([x.log_predictive_density - y.log_predictive_density for x, y in zip(a, b)], dtype=np.float64)
    standard_error = float(math.sqrt(n * float(np.var(differences, ddof=1)))) if n >= 2 else math.nan
    leader = model_a if delta > 0.0 else model_b if delta < 0.0 else None
    # R-32: one reading listed twice is one measurement counted twice in both scores, and its paired
    # differences are identical, so the sample variance falls toward zero and the standard-error test goes
    # vacuous. The split refuses such a half unless the study DECLARED replicates; where it did, the
    # declaration is honoured here.
    repeated_content = duplicates([(item.evidence.observed_value, item.evidence.unit,
                                    item.evidence.likelihood_sigma) for item in a])
    # R-24: "bound to the SAME split" needs no gate of its own here. `split_content_digest` is an
    # EVIDENCE_IDENTITY_FIELD, so the pairing loop above already refuses two assessments bound to different
    # split content -- and names the field. A guard mutation showed a gate here to be dead code, which is
    # what a surviving mutation is for.
    if not all(item.content_binding_verified for item in (*a, *b)):
        preferred, why = None, (
            "no preferred model: not every assessment was content-bound to its split IN THIS PROCESS (CORE-007, "
            "R-34), so nothing shows the held-out scores were not computed on data the posteriors were fitted to. A "
            "recorded content_bound flag is a claim, not a binding")
    elif repeated_content:
        preferred, why = None, (
            f"no preferred model: {len(repeated_content)} held-out reading(s) appear more than once among the paired "
            f"positions (R-32), so one measurement would be counted several times and the paired standard error "
            f"treats the copies as independent")
    else:
        decisive, why = _decisive_preference(delta, n, standard_error)
        preferred = leader if decisive else None
    return ModelScoreComparison(
        model_a, model_b, score_a, score_b, delta, preferred, evidence_digest, n=n, standard_error=standard_error, why=why
    )
