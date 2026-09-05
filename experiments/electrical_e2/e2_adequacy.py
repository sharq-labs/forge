"""E2 decision path: prediction as commitment, and the adequacy verdict.

DECISION-PATH MODULE. It must never import :mod:`e2_truth`; a test parses the
import graph transitively.

PREDICTION AS COMMITMENT CONVERTS EXECUTION INTO A TEST
-------------------------------------------------------
A posterior-predictive check computed after the observation is a description,
not a test — the same numbers can always be made to look reasonable in
hindsight. What makes an execution a test is that the prediction existed first
and could not be revised.

:class:`CommitmentLedger` makes that mechanical rather than procedural:

* every predictive distribution is stored in full (mixture means, weights, sd)
  and content-hashed, so a later edit is detectable;
* every entry carries the digest of its predecessor, so removing or reordering
  history is detectable;
* entries carry a monotone sequence number, so "the prediction came first" is a
  comparison, not a claim;
* the ledger is SEALED before any challenge observation may be recorded, and a
  sealed ledger accepts no further commitments. Recomputing a predictive after
  seeing its observation is not caught by a reviewer noticing — it raises.

Every commitment is also bound to the digest of the exact admitted evidence set
it was computed from, so a prediction cannot be silently re-attributed to a
different evidence state than the one that produced it.

WHAT THIS MODULE DELIBERATELY CANNOT SEE
----------------------------------------
:func:`classify_adequacy` takes tail probabilities and nothing else.
:func:`certify` takes an adequacy state, an execution-validity state and a
decision label, and nothing else. Neither has a parameter for posterior sd,
entropy, P(decision), EVPI or EVSI — not by convention but by signature, and a
test asserts the signatures. A quantity that is not a parameter cannot become
an override, and "the posterior was very confident" is precisely the override
E2 exists to refuse.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

import numpy as np

from .e2_config import (
    AGGREGATE_STATISTIC,
    ALPHA_EXTREME,
    ALPHA_JOINT,
    ALPHA_JOINT_WEAK,
    ALPHA_MODERATE,
    DEPRECATED_ALPHA_AGGREGATE,
    DEPRECATED_FISHER_REFERENCE,
    DEPRECATED_FISHER_STATISTIC,
    ESCALATION_RULE,
    K_MIN_EXTREME,
    LOG_TAIL_FLOOR,
    NULL_CALIBRATION,
    NULL_SIMULATION_DRAWS,
    NULL_SIMULATION_SEED,
    SURPRISE_STATISTIC,
    config_hash,
)
from .e2_model import JointPredictive, PredictiveMixture


class PredictiveCommitmentViolation(Exception):
    """A commitment rule was broken.

    Raised for: committing after the ledger is sealed (a post-hoc predictive),
    recording an observation before sealing, overwriting an existing
    commitment, scoring against a tampered artifact, or scoring an observation
    that does not strictly follow its own prediction.
    """


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


# =====================================================================
# The commitment artifact
# =====================================================================

@dataclass(frozen=True)
class PredictiveCommitment:
    """One precommitted predictive distribution, in full and content-hashed.

    The mixture is stored component-by-component rather than summarized to a
    mean and sd, because the adequacy rule reads tail probabilities: a summary
    would force the later score to assume a shape the commitment never
    actually made.
    """

    commitment_id: str
    sequence: int
    action_id: str
    source_voltage_volt: float
    noise_sigma_volt: float
    evidence_snapshot_digest: str
    n_observations: int
    config_hash: str
    component_means: tuple[float, ...]
    component_weights: tuple[float, ...]
    artifact_hash: str = ""

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "commitment_id": self.commitment_id,
            "sequence": self.sequence,
            "action_id": self.action_id,
            "source_voltage_volt": self.source_voltage_volt,
            "noise_sigma_volt": self.noise_sigma_volt,
            "evidence_snapshot_digest": self.evidence_snapshot_digest,
            "n_observations": self.n_observations,
            "config_hash": self.config_hash,
            "component_means": list(self.component_means),
            "component_weights": list(self.component_weights),
        }

    def computed_hash(self) -> str:
        return _digest(self._hash_payload())

    def verify_integrity(self) -> bool:
        """Recompute the content hash. False means the artifact was edited."""
        return bool(self.artifact_hash) and self.artifact_hash == self.computed_hash()

    def mixture(self) -> PredictiveMixture:
        """Rebuild the exact predictive that was committed to. No refitting."""
        return PredictiveMixture(
            means=self.component_means,
            weights=self.component_weights,
            sigma=self.noise_sigma_volt,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = self._hash_payload()
        payload["artifact_hash"] = self.artifact_hash
        return payload

    def summary(self) -> dict[str, Any]:
        """Compact form for reports — never the scoring input."""
        mixture = self.mixture()
        return {
            "commitment_id": self.commitment_id,
            "sequence": self.sequence,
            "action_id": self.action_id,
            "source_voltage_volt": self.source_voltage_volt,
            "evidence_snapshot_digest": self.evidence_snapshot_digest,
            "n_observations": self.n_observations,
            "n_components": len(self.component_means),
            "predictive_mean_volt": mixture.mean,
            "predictive_sd_volt": mixture.sd,
            "predictive_latent_sd_volt": mixture.latent_sd,
            "artifact_hash": self.artifact_hash,
        }


def build_commitment(
    *,
    commitment_id: str,
    sequence: int,
    action_id: str,
    source_voltage_volt: float,
    noise_sigma_volt: float,
    evidence_snapshot_digest: str,
    n_observations: int,
    mixture: PredictiveMixture,
) -> PredictiveCommitment:
    draft = PredictiveCommitment(
        commitment_id=commitment_id,
        sequence=sequence,
        action_id=action_id,
        source_voltage_volt=float(source_voltage_volt),
        noise_sigma_volt=float(noise_sigma_volt),
        evidence_snapshot_digest=evidence_snapshot_digest,
        n_observations=int(n_observations),
        config_hash=config_hash(),
        component_means=tuple(float(m) for m in mixture.means),
        component_weights=tuple(float(w) for w in mixture.weights),
    )
    return dataclasses.replace(draft, artifact_hash=draft.computed_hash())


@dataclass(frozen=True)
class ChallengeObservation:
    """One executed challenge measurement, recorded after the seal."""

    observation_id: str
    sequence: int
    action_id: str
    y_volt: float
    execution_id: str
    execution_valid: bool

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# =====================================================================
# The ledger
# =====================================================================

class LedgerEntryKind(str, Enum):
    COMMITMENT = "commitment"
    SEAL = "seal"
    OBSERVATION = "observation"


@dataclass(frozen=True)
class LedgerEntry:
    kind: LedgerEntryKind
    sequence: int
    reference: str
    payload_digest: str
    prev_hash: str
    entry_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["kind"] = self.kind.value
        return payload


class CommitmentLedger:
    """Append-only, hash-chained record of predictions and the observations
    that later tested them.

    The chain is tamper-EVIDENCE, not tamper-proofing, and carries the same
    caveat as the campaign event log: code that deliberately rebuilds the whole
    chain can rewrite it. What it makes impossible is the accident and the
    quiet edit — a changed predictive, a resequenced history or a prediction
    slipped in after its observation all fail a check rather than passing
    unnoticed.
    """

    def __init__(self, ledger_id: str) -> None:
        self._ledger_id = ledger_id
        self._entries: list[LedgerEntry] = []
        self._commitments: dict[str, PredictiveCommitment] = {}
        self._observations: dict[str, ChallengeObservation] = {}
        self._sealed = False
        self._sealed_at: int | None = None

    # -- state --------------------------------------------------------------
    @property
    def ledger_id(self) -> str:
        return self._ledger_id

    @property
    def is_sealed(self) -> bool:
        return self._sealed

    @property
    def sealed_at_sequence(self) -> int | None:
        return self._sealed_at

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries)

    @property
    def commitments(self) -> Mapping[str, PredictiveCommitment]:
        return dict(self._commitments)

    @property
    def observations(self) -> Mapping[str, ChallengeObservation]:
        return dict(self._observations)

    @property
    def head_digest(self) -> str:
        return self._entries[-1].entry_hash if self._entries else ""

    def _next_sequence(self) -> int:
        return len(self._entries) + 1

    def _append(
        self, kind: LedgerEntryKind, reference: str, payload_digest: str
    ) -> LedgerEntry:
        prev = self.head_digest
        sequence = self._next_sequence()
        entry_hash = _digest(
            {
                "ledger_id": self._ledger_id,
                "kind": kind.value,
                "sequence": sequence,
                "reference": reference,
                "payload_digest": payload_digest,
                "prev_hash": prev,
            }
        )
        entry = LedgerEntry(
            kind=kind,
            sequence=sequence,
            reference=reference,
            payload_digest=payload_digest,
            prev_hash=prev,
            entry_hash=entry_hash,
        )
        self._entries.append(entry)
        return entry

    # -- phase 2a: commit ---------------------------------------------------
    def commit(
        self,
        *,
        action_id: str,
        source_voltage_volt: float,
        noise_sigma_volt: float,
        evidence_snapshot_digest: str,
        n_observations: int,
        mixture: PredictiveMixture,
    ) -> PredictiveCommitment:
        """Register one predictive BEFORE its observation exists."""
        if self._sealed:
            raise PredictiveCommitmentViolation(
                f"ledger {self._ledger_id!r} is sealed: a predictive for "
                f"{action_id!r} cannot be registered after the commitment "
                f"phase closed. A predictive computed once its observation is "
                f"available is a description of the data, not a test of the "
                f"model."
            )
        if action_id in self._commitments:
            raise PredictiveCommitmentViolation(
                f"a predictive for {action_id!r} is already committed; "
                f"commitments are write-once"
            )
        sequence = self._next_sequence()
        commitment = build_commitment(
            commitment_id=f"{self._ledger_id}-commit-{action_id}",
            sequence=sequence,
            action_id=action_id,
            source_voltage_volt=source_voltage_volt,
            noise_sigma_volt=noise_sigma_volt,
            evidence_snapshot_digest=evidence_snapshot_digest,
            n_observations=n_observations,
            mixture=mixture,
        )
        self._append(
            LedgerEntryKind.COMMITMENT, action_id, commitment.artifact_hash
        )
        self._commitments[action_id] = commitment
        return commitment

    def seal(self) -> LedgerEntry:
        """Close the commitment phase. Nothing may be predicted after this."""
        if self._sealed:
            raise PredictiveCommitmentViolation("ledger is already sealed")
        if not self._commitments:
            raise PredictiveCommitmentViolation(
                "refusing to seal a ledger with no commitments"
            )
        digest = _digest(
            {
                "committed_actions": sorted(self._commitments),
                "artifact_hashes": sorted(
                    c.artifact_hash for c in self._commitments.values()
                ),
            }
        )
        entry = self._append(LedgerEntryKind.SEAL, "seal", digest)
        self._sealed = True
        self._sealed_at = entry.sequence
        return entry

    # -- phase 2b: observe --------------------------------------------------
    def record_observation(
        self,
        *,
        action_id: str,
        y_volt: float,
        execution_id: str,
        execution_valid: bool,
    ) -> ChallengeObservation:
        """Record an executed challenge measurement. Only after the seal."""
        if not self._sealed:
            raise PredictiveCommitmentViolation(
                "challenge observations may only be recorded after the "
                "commitment phase is sealed; recording one first would leave "
                "the predictive free to be computed with the answer in hand"
            )
        if action_id not in self._commitments:
            raise PredictiveCommitmentViolation(
                f"no precommitted predictive exists for {action_id!r}; an "
                f"unpredicted observation cannot test a prediction"
            )
        if action_id in self._observations:
            raise PredictiveCommitmentViolation(
                f"an observation for {action_id!r} is already recorded"
            )
        sequence = self._next_sequence()
        observation = ChallengeObservation(
            observation_id=f"{self._ledger_id}-obs-{action_id}",
            sequence=sequence,
            action_id=action_id,
            y_volt=float(y_volt),
            execution_id=execution_id,
            execution_valid=bool(execution_valid),
        )
        self._append(
            LedgerEntryKind.OBSERVATION, action_id, _digest(observation.to_dict())
        )
        self._observations[action_id] = observation
        return observation

    # -- integrity ----------------------------------------------------------
    def verify_chain(self) -> bool:
        prev = ""
        for index, entry in enumerate(self._entries, start=1):
            if entry.sequence != index or entry.prev_hash != prev:
                return False
            expected = _digest(
                {
                    "ledger_id": self._ledger_id,
                    "kind": entry.kind.value,
                    "sequence": entry.sequence,
                    "reference": entry.reference,
                    "payload_digest": entry.payload_digest,
                    "prev_hash": entry.prev_hash,
                }
            )
            if expected != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True

    def verify_commitments(self) -> bool:
        """Every stored artifact still hashes to what the chain recorded."""
        by_reference = {
            e.reference: e.payload_digest
            for e in self._entries
            if e.kind is LedgerEntryKind.COMMITMENT
        }
        for action_id, commitment in self._commitments.items():
            if not commitment.verify_integrity():
                return False
            if by_reference.get(action_id) != commitment.artifact_hash:
                return False
        return True


# =====================================================================
# The surprise metric
# =====================================================================

class SurpriseLevel(str, Enum):
    CONSISTENT = "consistent"
    MODERATE = "moderate"
    EXTREME = "extreme"


@dataclass(frozen=True)
class ChallengeSurprise:
    """One condition's verdict, computed from its frozen predictive alone."""

    action_id: str
    source_voltage_volt: float
    y_observed_volt: float
    predictive_mean_volt: float
    predictive_sd_volt: float
    tail_probability: float
    nlpd: float
    standardized_residual: float
    level: SurpriseLevel
    commitment_sequence: int
    observation_sequence: int
    commitment_artifact_hash: str
    evidence_snapshot_digest: str

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["level"] = self.level.value
        return payload


def _level(tail: float) -> SurpriseLevel:
    if tail < ALPHA_EXTREME:
        return SurpriseLevel.EXTREME
    if tail < ALPHA_MODERATE:
        return SurpriseLevel.MODERATE
    return SurpriseLevel.CONSISTENT


def score_commitments(ledger: CommitmentLedger) -> tuple[ChallengeSurprise, ...]:
    """Score every precommitted predictive against its observation.

    Refuses to score anything whose ordering or integrity does not hold. The
    scalar this produces comes from the frozen artifact and the observed value
    and from nothing else — no critic confidence, no fitted variance, no
    judgement.
    """
    if not ledger.is_sealed:
        raise PredictiveCommitmentViolation(
            "cannot score an unsealed ledger: commitments could still change"
        )
    if not ledger.verify_chain():
        raise PredictiveCommitmentViolation("ledger hash chain is broken")
    if not ledger.verify_commitments():
        raise PredictiveCommitmentViolation(
            "a committed predictive artifact no longer matches its hash; the "
            "prediction was edited after it was made"
        )

    out: list[ChallengeSurprise] = []
    for action_id in sorted(ledger.observations):
        observation = ledger.observations[action_id]
        commitment = ledger.commitments[action_id]
        if commitment.sequence >= observation.sequence:
            raise PredictiveCommitmentViolation(
                f"predictive for {action_id!r} is not strictly earlier than "
                f"its observation (commit seq {commitment.sequence}, observe "
                f"seq {observation.sequence})"
            )
        if not commitment.verify_integrity():
            raise PredictiveCommitmentViolation(
                f"commitment artifact for {action_id!r} failed its hash check"
            )
        mixture = commitment.mixture()
        y = observation.y_volt
        tail = mixture.two_sided_tail(y)
        out.append(
            ChallengeSurprise(
                action_id=action_id,
                source_voltage_volt=commitment.source_voltage_volt,
                y_observed_volt=y,
                predictive_mean_volt=mixture.mean,
                predictive_sd_volt=mixture.sd,
                tail_probability=tail,
                nlpd=mixture.negative_log_density(y),
                standardized_residual=(y - mixture.mean) / mixture.sd,
                level=_level(tail),
                commitment_sequence=commitment.sequence,
                observation_sequence=observation.sequence,
                commitment_artifact_hash=commitment.artifact_hash,
                evidence_snapshot_digest=commitment.evidence_snapshot_digest,
            )
        )
    return tuple(out)


# =====================================================================
# The aggregate statistic
# =====================================================================

def chi2_upper_tail_log(x: float, even_df: int) -> float:
    """log P(X > x) for X ~ chi-square with an EVEN number of degrees of freedom.

    Closed form, no special-function library: for df = 2k,

        P(X > x) = exp(-x/2) * sum_{j=0}^{k-1} (x/2)^j / j!

    evaluated by log-sum-exp so an aggregate of 1e-200 is representable rather
    than rounded to zero. A test cross-checks it against scipy's chi2.sf on the
    range where scipy still has precision.
    """
    if even_df <= 0 or even_df % 2 != 0:
        raise ValueError("this closed form requires a positive even df")
    if x <= 0.0:
        return 0.0
    k = even_df // 2
    half = x / 2.0
    log_half = math.log(half)
    terms = [j * log_half - math.lgamma(j + 1.0) for j in range(k)]
    peak = max(terms)
    total = sum(math.exp(t - peak) for t in terms)
    return -half + peak + math.log(total)


def build_joint_predictive(
    ledger: CommitmentLedger, order: Sequence[str]
) -> JointPredictive:
    """Assemble the joint predictive from the FROZEN commitments.

    Refuses to combine commitments that were not made against the same
    evidence snapshot: a joint density over conditions predicted from
    different belief states would not be a joint predictive of anything.
    """
    commitments = [ledger.commitments[action_id] for action_id in order]
    if not commitments:
        raise PredictiveCommitmentViolation("no commitments to combine")
    digests = {c.evidence_snapshot_digest for c in commitments}
    if len(digests) != 1:
        raise PredictiveCommitmentViolation(
            "challenge commitments were made against different evidence "
            "snapshots and cannot be combined into one joint predictive"
        )
    reference = commitments[0].component_weights
    for commitment in commitments:
        if not commitment.verify_integrity():
            raise PredictiveCommitmentViolation(
                f"commitment for {commitment.action_id!r} failed its hash check"
            )
        if commitment.component_weights != reference:
            raise PredictiveCommitmentViolation(
                "challenge commitments do not share one posterior support"
            )
    return JointPredictive(
        component_means=tuple(c.component_means for c in commitments),
        sigmas=tuple(c.noise_sigma_volt for c in commitments),
        weights=reference,
    )


@dataclass(frozen=True)
class AggregateAdequacy:
    """The v1.1.0 aggregate: joint log score with a simulated null.

    ``p_joint`` is the load-bearing quantity. The Fisher fields are retained
    ONLY as diagnostics documenting the v1.0.0 error, and
    ``fisher_p_chi2_independent`` must never be used to decide anything.
    """

    statistic: str
    null_calibration: str
    joint_log_score: float
    null_draws: int
    null_seed: int
    n_null_at_least_as_extreme: int
    p_joint: float
    p_joint_is_mc_floor: bool
    null_mean: float
    null_sd: float
    null_q99: float
    n_conditions: int
    n_extreme: int
    n_moderate: int
    # --- deprecated diagnostics -----------------------------------------
    deprecated_statistic: str
    deprecated_reference: str
    fisher_x2: float
    degrees_of_freedom: int
    fisher_p_chi2_independent: float
    fisher_p_simulated: float
    chi2_reference_inflation_factor: float
    null_rejection_rate_chi2_at_0p05: float

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _fisher_x2(tails: np.ndarray) -> np.ndarray:
    logs = np.where(tails > 0.0, np.log(np.maximum(tails, 1e-300)), LOG_TAIL_FLOOR)
    return -2.0 * np.maximum(logs, LOG_TAIL_FLOOR).sum(axis=-1)


def _marginal_tails(joint: JointPredictive, ys: np.ndarray) -> np.ndarray:
    """Two-sided marginal tail per condition, vectorized over draws.

    Each of these is EXACTLY Uniform(0,1) under the null on its own. What is
    not true — and what v1.0.0 assumed — is that they are jointly independent.
    """
    from scipy.special import erfc

    means = np.asarray(joint.component_means, float)          # k x n
    sigmas = np.asarray(joint.sigmas, float)                  # k
    weights = np.asarray(joint.weights, float)                # n
    out = np.empty(ys.shape, float)
    for j in range(joint.n_conditions):
        scale = sigmas[j] * math.sqrt(2.0)
        delta = ys[:, j][:, None] - means[j][None, :]
        lower = (0.5 * erfc(-delta / scale)) @ weights
        upper = (0.5 * erfc(delta / scale)) @ weights
        out[:, j] = np.minimum(1.0, 2.0 * np.minimum(lower, upper))
    return out


def aggregate_adequacy(
    surprises: Sequence[ChallengeSurprise],
    joint: JointPredictive,
) -> AggregateAdequacy:
    """Score the COMPLETE challenge vector jointly, then calibrate by simulation.

    Every condition enters, including the ones that look fine: keeping only the
    damning ones would guarantee a damning aggregate.

    The null is generated from the same joint predictive, one shared theta per
    draw. The p-value is (1 + #{S* >= S_obs}) / (1 + N), which is exactly valid
    in finite samples — the observation is treated as one more exchangeable
    draw under the null, so no asymptotic argument is needed anywhere.
    """
    if not surprises:
        raise ValueError("no challenge conditions to aggregate")
    if joint.n_conditions != len(surprises):
        raise ValueError("joint predictive and scored conditions disagree")

    observed = np.array([s.y_observed_volt for s in surprises], float)
    score = float(joint.log_score(observed))

    draws = joint.simulate(NULL_SIMULATION_DRAWS, NULL_SIMULATION_SEED)
    null_scores = -joint.log_density_batch(draws)
    n_ge = int(np.count_nonzero(null_scores >= score))
    p_joint = (1.0 + n_ge) / (1.0 + NULL_SIMULATION_DRAWS)

    # --- deprecated Fisher diagnostics, and the size of the v1.0.0 error --
    observed_tails = np.array([s.tail_probability for s in surprises], float)
    x2 = float(_fisher_x2(observed_tails[None, :])[0])
    df = 2 * len(surprises)
    log_p_chi2 = chi2_upper_tail_log(x2, df)
    p_chi2 = math.exp(log_p_chi2) if log_p_chi2 > -700.0 else 0.0

    null_tails = _marginal_tails(joint, draws)
    null_x2 = _fisher_x2(null_tails)
    p_fisher_sim = (1.0 + int(np.count_nonzero(null_x2 >= x2))) / (
        1.0 + NULL_SIMULATION_DRAWS
    )
    # Under independence Var(X2) would be 2*df. Measured against the true null
    # it is larger, and the ratio is the concrete size of the invalid step.
    inflation = float(np.var(null_x2, ddof=1) / (2.0 * df))
    nominal = np.array(
        [math.exp(chi2_upper_tail_log(float(x), df)) for x in null_x2[:4000]]
    )
    rejection_rate = float(np.mean(nominal < 0.05))

    return AggregateAdequacy(
        statistic=AGGREGATE_STATISTIC,
        null_calibration=NULL_CALIBRATION,
        joint_log_score=score,
        null_draws=NULL_SIMULATION_DRAWS,
        null_seed=NULL_SIMULATION_SEED,
        n_null_at_least_as_extreme=n_ge,
        p_joint=p_joint,
        p_joint_is_mc_floor=(n_ge == 0),
        null_mean=float(np.mean(null_scores)),
        null_sd=float(np.std(null_scores, ddof=1)),
        null_q99=float(np.quantile(null_scores, 0.99)),
        n_conditions=len(surprises),
        n_extreme=sum(1 for s in surprises if s.level is SurpriseLevel.EXTREME),
        n_moderate=sum(1 for s in surprises if s.level is SurpriseLevel.MODERATE),
        deprecated_statistic=DEPRECATED_FISHER_STATISTIC,
        deprecated_reference=DEPRECATED_FISHER_REFERENCE,
        fisher_x2=x2,
        degrees_of_freedom=df,
        fisher_p_chi2_independent=p_chi2,
        fisher_p_simulated=p_fisher_sim,
        chi2_reference_inflation_factor=inflation,
        null_rejection_rate_chi2_at_0p05=rejection_rate,
    )


# =====================================================================
# The adequacy verdict
# =====================================================================

class AdequacyState(str, Enum):
    """Experiment-local. NOT a new production model-management subsystem."""

    MODEL_ADEQUACY_ACCEPTABLE = "model_adequacy_acceptable"
    MODEL_ADEQUACY_NOT_ESTABLISHED = "model_adequacy_not_established"
    MODEL_SPACE_INADEQUATE = "model_space_inadequate"


class ExecutionValidity(str, Enum):
    """A SEPARATE axis. Whether the computation ran correctly and the number
    was extracted from a passing solve — nothing about whether the model that
    predicted it was any good."""

    VALID = "valid"
    INVALID = "invalid"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True)
class AdequacyVerdict:
    state: AdequacyState
    rule: str
    aggregate: AggregateAdequacy
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "rule": self.rule,
            "aggregate": self.aggregate.to_dict(),
            "rationale": self.rationale,
        }


def classify_adequacy(
    surprises: Sequence[ChallengeSurprise],
    joint: JointPredictive | AggregateAdequacy,
) -> AdequacyVerdict:
    """Apply the preregistered rule.

    The only arguments are the scored challenge conditions and the joint
    predictive they were committed under (or a precomputed aggregate). There is
    deliberately no parameter for posterior sd, entropy, P(decision), EVPI or
    EVSI: a quantity that cannot be passed in cannot be used to override the
    result, and every one of those is computed inside the very model family
    under suspicion.
    """
    aggregate = (
        joint
        if isinstance(joint, AggregateAdequacy)
        else aggregate_adequacy(surprises, joint)
    )
    floor_note = (
        f" (Monte Carlo floor: 0 of {aggregate.null_draws} null draws were as "
        f"extreme, so the true value is below "
        f"{1.0 / (1 + aggregate.null_draws):.1e})"
        if aggregate.p_joint_is_mc_floor
        else ""
    )
    inadequate = (
        aggregate.n_extreme >= K_MIN_EXTREME and aggregate.p_joint < ALPHA_JOINT
    )
    if inadequate:
        state = AdequacyState.MODEL_SPACE_INADEQUATE
        rationale = (
            f"{aggregate.n_extreme} of {aggregate.n_conditions} preregistered "
            f"conditions fell in the far tail of their own pre-observation "
            f"predictive (threshold {ALPHA_EXTREME:g}), AND the complete "
            f"challenge vector scored {aggregate.joint_log_score:.3f} against a "
            f"simulated null of {aggregate.null_mean:.3f} +/- "
            f"{aggregate.null_sd:.3f}, giving p_joint = "
            f"{aggregate.p_joint:.3e}{floor_note}. The joint score already "
            f"allows the family to move theta anywhere its own calibration "
            f"posterior permits, so this is not something a shared-parameter "
            f"shift can explain away."
        )
    elif aggregate.n_extreme >= 1 or aggregate.p_joint < ALPHA_JOINT_WEAK:
        state = AdequacyState.MODEL_ADEQUACY_NOT_ESTABLISHED
        rationale = (
            f"{aggregate.n_extreme} extreme and {aggregate.n_moderate} moderate "
            f"of {aggregate.n_conditions} conditions, p_joint = "
            f"{aggregate.p_joint:.3e}{floor_note}. Enough to withhold the claim "
            f"that the family is adequate, not enough to conclude it is "
            f"inadequate: the strongest verdict requires at least "
            f"{K_MIN_EXTREME} individually extreme conditions, so no single "
            f"observation can produce it however extreme the aggregate."
        )
    else:
        state = AdequacyState.MODEL_ADEQUACY_ACCEPTABLE
        rationale = (
            f"no condition fell below {ALPHA_EXTREME:g} and the joint score "
            f"{aggregate.joint_log_score:.3f} sits inside its simulated null "
            f"({aggregate.null_mean:.3f} +/- {aggregate.null_sd:.3f}), "
            f"p_joint = {aggregate.p_joint:.3e}. The tested conditions gave the "
            f"family no reason to be rejected — which is not the same as "
            f"establishing that it is right."
        )
    return AdequacyVerdict(
        state=state,
        rule=ESCALATION_RULE,
        aggregate=aggregate,
        rationale=rationale,
    )


# =====================================================================
# The certification gate
# =====================================================================

class Certification(str, Enum):
    CERTIFIABLE = "certifiable"
    NOT_CERTIFIABLE = "not_certifiable"


class Disposition(str, Enum):
    PROCEED = "proceed"
    MODEL_REVISION_REQUIRED = "model_revision_required"
    ADEQUACY_EVIDENCE_REQUIRED = "adequacy_evidence_required"
    EXECUTION_REPAIR_REQUIRED = "execution_repair_required"


@dataclass(frozen=True)
class CertificationResult:
    posterior_decision: str
    scientific_certification: Certification
    reason: str
    disposition: Disposition
    adequacy_state: AdequacyState
    execution_validity: ExecutionValidity
    statement: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "posterior_decision": self.posterior_decision,
            "scientific_certification": self.scientific_certification.value,
            "reason": self.reason,
            "disposition": self.disposition.value,
            "adequacy_state": self.adequacy_state.value,
            "execution_validity": self.execution_validity.value,
            "statement": self.statement,
        }


#: The exact parameter names :func:`certify` is permitted to have. A test
#: compares this against the live signature, so adding a posterior-strength
#: input to the certification gate breaks the build rather than the argument.
CERTIFY_ALLOWED_PARAMETERS = (
    "posterior_decision",
    "adequacy_state",
    "execution_validity",
)


def certify(
    posterior_decision: str,
    adequacy_state: AdequacyState,
    execution_validity: ExecutionValidity,
) -> CertificationResult:
    """Decide whether the posterior's preferred decision may be certified.

    Both quantities are reported either way. The posterior decision is a real
    output of coherent inference and is not suppressed just because the family
    is in question — but it is reported as what it is:

        the decision preferred by p(R2 | data, M_const)

    which is a conditional statement, and becomes a scientific conclusion only
    if M_const survives its own predictions.
    """
    if execution_validity is not ExecutionValidity.VALID:
        return CertificationResult(
            posterior_decision=posterior_decision,
            scientific_certification=Certification.NOT_CERTIFIABLE,
            reason=f"EXECUTION_VALIDITY={execution_validity.value.upper()}",
            disposition=Disposition.EXECUTION_REPAIR_REQUIRED,
            adequacy_state=adequacy_state,
            execution_validity=execution_validity,
            statement=(
                "the computation itself did not produce trustworthy output; "
                "this is a computational failure, not a model-adequacy finding"
            ),
        )
    if adequacy_state is AdequacyState.MODEL_SPACE_INADEQUATE:
        return CertificationResult(
            posterior_decision=posterior_decision,
            scientific_certification=Certification.NOT_CERTIFIABLE,
            reason=AdequacyState.MODEL_SPACE_INADEQUATE.name,
            disposition=Disposition.MODEL_REVISION_REQUIRED,
            adequacy_state=adequacy_state,
            execution_validity=execution_validity,
            statement=(
                "the declared model family is not adequate to support the "
                "scientific conclusion under the tested conditions. The data "
                "are not wrong, the solver is not wrong, and the replacement "
                "model is not known; what is established is that this family "
                "predicted these conditions and was wrong about them"
            ),
        )
    if adequacy_state is AdequacyState.MODEL_ADEQUACY_NOT_ESTABLISHED:
        return CertificationResult(
            posterior_decision=posterior_decision,
            scientific_certification=Certification.NOT_CERTIFIABLE,
            reason=AdequacyState.MODEL_ADEQUACY_NOT_ESTABLISHED.name,
            disposition=Disposition.ADEQUACY_EVIDENCE_REQUIRED,
            adequacy_state=adequacy_state,
            execution_validity=execution_validity,
            statement=(
                "the predictive checks were not clean enough to certify and "
                "not systematic enough to condemn the family; more "
                "preregistered conditions are needed before either claim"
            ),
        )
    return CertificationResult(
        posterior_decision=posterior_decision,
        scientific_certification=Certification.CERTIFIABLE,
        reason="MODEL_ADEQUACY_ACCEPTABLE",
        disposition=Disposition.PROCEED,
        adequacy_state=adequacy_state,
        execution_validity=execution_validity,
        statement=(
            "execution was valid and the family survived its own precommitted "
            "predictions at the tested conditions; the conditional decision "
            "may be certified FOR THOSE CONDITIONS"
        ),
    )


@dataclass
class AdequacyReport:
    """Everything the adequacy layer produced, in one serializable place."""

    surprises: tuple[ChallengeSurprise, ...]
    verdict: AdequacyVerdict
    certification: CertificationResult
    ledger_head: str
    ledger_sealed_at: int | None
    chain_verified: bool
    commitments: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "statistic": SURPRISE_STATISTIC,
            "surprises": [s.to_dict() for s in self.surprises],
            "verdict": self.verdict.to_dict(),
            "certification": self.certification.to_dict(),
            "ledger_head": self.ledger_head,
            "ledger_sealed_at": self.ledger_sealed_at,
            "chain_verified": self.chain_verified,
            "commitments": list(self.commitments),
        }
