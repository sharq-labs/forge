"""M3C — the Arbiter: the only issuer of a final assurance verdict.

The Arbiter reads critic assessments and declared obligations, and decides
whether the evidence is admissible. That is all it does. It runs no solver,
edits no evidence, selects no next experiment, and writes no belief. It cannot
even admit evidence by itself — it *authorizes* admission by asking a
registered :class:`~engcore.sria.admission.AdmissionAuthority` to issue a
signed declaration, which the M1 Gateway then verifies independently.

The path is unchanged from M1, with the Arbiter now filled in:

    Evidence -> Critics -> Arbiter -> authorized AdmissionDeclaration
             -> Belief Update Gateway -> Scientific Belief

No second admission route exists. The Arbiter holds an authority *reference*,
not a bypass: if the Gateway does not trust that authority, the Arbiter's
approval buys nothing.

Verdict semantics, and why VALID is hard to reach:

* ``VALID`` requires every declared obligation to be *satisfied by evidence*.
  A skipped mandatory critic, an unquantified required uncertainty channel, or
  a calibration that failed its required status all make VALID unreachable.
* ``INVALID`` is evidence-backed — some check actually failed. It is never a
  generic error state; a missing critic yields NOT_ASSESSED, not INVALID.
* ``INCONCLUSIVE`` is a legal, common, honest outcome.
* ``NOT_ASSESSED`` means the obligations were never evaluated against evidence.

An empty obligation set cannot produce VALID: with nothing required, there is
no standard to certify against, and "valid" would mean only "nobody asked".
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from ...scientific.serialization import require_schema, schema_string
from ..admission import (
    AdmissionAuthority,
    AdmissionDeclaration,
    DecisionBinding,
    _issue_registrar_capability,
)
from ..evidence import Evidence
from ..provenance import DecisionProvenance
from ..uncertainty import UncertaintyChannel
from .assessment import (
    CriticAssessment,
    CriticClass,
    CriticVerdict,
    FindingImpact,
    Severity,
)
from .obligations import ObligationKind, ObligationSet
from .uncertainty_budget import UncertaintyBudget

ARBITER_DECISION_SCHEMA = schema_string("sria_arbiter_decision")
ARBITER_VERSION = "arbiter/1"


class AssuranceVerdict(str, Enum):
    """The final scientific assurance verdict. Only the Arbiter issues these."""

    VALID = "valid"
    INVALID = "invalid"
    INCONCLUSIVE = "inconclusive"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True)
class ObligationResult:
    """Whether one declared obligation was met, and on what evidence."""

    obligation_id: str
    satisfied: bool
    evidence_ref: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "satisfied": self.satisfied,
            "evidence_ref": self.evidence_ref,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ArbiterDecision:
    """A replayable record of one assurance decision."""

    decision_id: str
    subject_ref: str
    verdict: AssuranceVerdict
    obligation_results: tuple[ObligationResult, ...]
    assessment_refs: tuple[str, ...]
    reasons: tuple[str, ...]
    arbiter_version: str = ARBITER_VERSION
    campaign_id: str = ""
    decided_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "verdict", AssuranceVerdict(self.verdict))
        object.__setattr__(self, "obligation_results", tuple(self.obligation_results))
        object.__setattr__(self, "assessment_refs", tuple(self.assessment_refs))
        object.__setattr__(self, "reasons", tuple(self.reasons))

    @property
    def decision_hash(self) -> str:
        """Stable identity of this decision, signed into the admission."""
        blob = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @property
    def unmet_obligations(self) -> tuple[str, ...]:
        return tuple(r.obligation_id for r in self.obligation_results if not r.satisfied)

    @property
    def admits(self) -> bool:
        return self.verdict is AssuranceVerdict.VALID

    def to_decision_provenance(self) -> DecisionProvenance:
        """Reuse the M1 reserved decision-provenance layout for replay."""
        return DecisionProvenance(
            decision_id=self.decision_id,
            belief_snapshot_ref="",
            candidate_actions=self.assessment_refs,
            scores={},
            chosen_action=self.verdict.value,
            reason="; ".join(self.reasons) if self.reasons else "",
            policy_id="sria.arbiter",
            policy_version=self.arbiter_version,
            human_override=False,
            decided_at=self.decided_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ARBITER_DECISION_SCHEMA,
            "decision_id": self.decision_id,
            "subject_ref": self.subject_ref,
            "verdict": self.verdict.value,
            "obligation_results": [r.to_dict() for r in self.obligation_results],
            "assessment_refs": list(self.assessment_refs),
            "reasons": list(self.reasons),
            "arbiter_version": self.arbiter_version,
            "campaign_id": self.campaign_id,
            "decided_at": self.decided_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArbiterDecision":
        require_schema(payload, ARBITER_DECISION_SCHEMA)
        return cls(
            decision_id=payload["decision_id"],
            subject_ref=payload["subject_ref"],
            verdict=AssuranceVerdict(payload["verdict"]),
            obligation_results=tuple(
                ObligationResult(
                    obligation_id=r["obligation_id"],
                    satisfied=bool(r["satisfied"]),
                    evidence_ref=r.get("evidence_ref", ""),
                    detail=r.get("detail", ""),
                )
                for r in payload.get("obligation_results", ())
            ),
            assessment_refs=tuple(payload.get("assessment_refs", ())),
            reasons=tuple(payload.get("reasons", ())),
            arbiter_version=payload.get("arbiter_version", ARBITER_VERSION),
            campaign_id=payload.get("campaign_id", ""),
            decided_at=payload.get("decided_at"),
        )


class Arbiter:
    """Evaluates obligations against critic assessments and authorizes admission."""

    def __init__(
        self,
        authority: AdmissionAuthority,
        *,
        arbiter_version: str = ARBITER_VERSION,
    ) -> None:
        if not isinstance(authority, AdmissionAuthority):
            raise TypeError(
                "the Arbiter must hold a real AdmissionAuthority; a hand-rolled "
                "stand-in would be a second admission path"
            )
        self._authority = authority
        self._version = arbiter_version
        # M3.3: the Arbiter's minting capability is a per-authorization
        # random code. It registers only a one-way commitment with the
        # authority, so the verification side holds no key material and
        # cannot mint. No long-lived shared secret exists.
        self._arbiter_id = f"{arbiter_version}:{secrets.token_hex(8)}"
        # The registration capability. Held privately and never returned,
        # so possession of the authority alone cannot register commitments.
        self._registrar = _issue_registrar_capability(self._arbiter_id)
        # Hashes of decisions this Arbiter actually produced. Without this,
        # any caller could hand-build an ArbiterDecision(verdict=VALID) and
        # have it signed — a fabricated-decision bypass.
        self._issued: set[str] = set()

    @property
    def authority_id(self) -> str:
        return self._authority.authority_id

    # ---- decide ---------------------------------------------------------
    def decide(
        self,
        *,
        decision_id: str,
        subject_ref: str,
        assessments: Sequence[CriticAssessment],
        obligations: ObligationSet,
        budget: UncertaintyBudget | None = None,
        decided_at: str | None = None,
    ) -> ArbiterDecision:
        results: list[ObligationResult] = []
        reasons: list[str] = []
        by_class = {a.critic_class: a for a in assessments}

        # --- required critics -------------------------------------------
        for obligation in obligations.of_kind(ObligationKind.REQUIRED_CRITIC):
            critic_class = CriticClass(obligation.target)
            assessment = by_class.get(critic_class)
            if assessment is None:
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=False,
                        detail=f"required critic {critic_class.value} did not run",
                    )
                )
                reasons.append(
                    f"mandatory critic {critic_class.value} was skipped"
                )
            else:
                ok = assessment.verdict is CriticVerdict.PASS
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=ok,
                        evidence_ref=assessment.assessment_id,
                        detail=f"{critic_class.value} verdict {assessment.verdict.value}",
                    )
                )
                if not ok:
                    reasons.append(
                        f"critic {critic_class.value} returned "
                        f"{assessment.verdict.value}"
                    )

        # --- required named checks --------------------------------------
        all_checks = {c.name: (a, c) for a in assessments for c in a.checks}
        for target in obligations.required_checks:
            if target.startswith("validation_level:"):
                # Recorded for provenance; M3 does not evaluate ValidationLevel.
                results.append(
                    ObligationResult(
                        obligation_id=f"check:{target}",
                        satisfied=False,
                        detail=(
                            "validation-level obligations are recorded but not "
                            "evaluated in M3; cannot be certified"
                        ),
                    )
                )
                reasons.append(f"obligation {target} is not evaluable in M3")
                continue
            found = all_checks.get(target)
            if found is None:
                results.append(
                    ObligationResult(
                        obligation_id=f"check:{target}",
                        satisfied=False,
                        detail="required check was never performed",
                    )
                )
                reasons.append(f"required check {target!r} was not performed")
            else:
                assessment, record = found
                ok = record.outcome is CriticVerdict.PASS
                results.append(
                    ObligationResult(
                        obligation_id=f"check:{target}",
                        satisfied=ok,
                        evidence_ref=assessment.assessment_id,
                        detail=f"{target} -> {record.outcome.value}",
                    )
                )
                if not ok:
                    reasons.append(f"check {target!r} is {record.outcome.value}")

        # --- required domain checks --------------------------------------
        for target in obligations.required_domain_checks:
            found = all_checks.get(target)
            domain_ran = CriticClass.DOMAIN in by_class
            if not domain_ran:
                results.append(
                    ObligationResult(
                        obligation_id=f"domain_check:{target}",
                        satisfied=False,
                        detail="domain critic did not run",
                    )
                )
                reasons.append(f"domain check {target!r} was skipped")
            elif found is None:
                results.append(
                    ObligationResult(
                        obligation_id=f"domain_check:{target}",
                        satisfied=False,
                        detail="domain critic ran but did not perform this check",
                    )
                )
                reasons.append(f"domain check {target!r} was not performed")
            else:
                assessment, record = found
                ok = record.outcome is CriticVerdict.PASS
                results.append(
                    ObligationResult(
                        obligation_id=f"domain_check:{target}",
                        satisfied=ok,
                        evidence_ref=assessment.assessment_id,
                        detail=f"{target} -> {record.outcome.value}",
                    )
                )
                if not ok:
                    reasons.append(f"domain check {target!r} is {record.outcome.value}")

        # --- required uncertainty channels --------------------------------
        for channel in obligations.required_uncertainty_channels:
            if budget is None:
                results.append(
                    ObligationResult(
                        obligation_id=f"uncertainty:{channel.value}",
                        satisfied=False,
                        detail="no uncertainty budget was supplied",
                    )
                )
                reasons.append(
                    f"uncertainty channel {channel.value} required but no budget given"
                )
                continue
            entry = budget.entry(channel)
            ok = entry.is_quantified
            results.append(
                ObligationResult(
                    obligation_id=f"uncertainty:{channel.value}",
                    satisfied=ok,
                    detail=f"channel state {entry.state.value}",
                )
            )
            if not ok:
                # UNKNOWN where quantification is required blocks VALID; it is
                # never silently treated as zero or ignored.
                reasons.append(
                    f"uncertainty channel {channel.value} is {entry.state.value} "
                    f"but the campaign requires it quantified"
                )

        # --- required calibration status -----------------------------------
        required_verdicts = obligations.required_calibration_verdicts
        if required_verdicts:
            calibration = by_class.get(CriticClass.CALIBRATION)
            if calibration is None:
                results.append(
                    ObligationResult(
                        obligation_id="calibration:status",
                        satisfied=False,
                        detail="calibration critic did not run",
                    )
                )
                reasons.append("required calibration assessment was skipped")
            else:
                ok = calibration.verdict is CriticVerdict.PASS
                results.append(
                    ObligationResult(
                        obligation_id="calibration:status",
                        satisfied=ok,
                        evidence_ref=calibration.assessment_id,
                        detail=f"calibration verdict {calibration.verdict.value}",
                    )
                )
                if not ok:
                    reasons.append(
                        f"calibration assessment is {calibration.verdict.value}; "
                        f"a successful solve does not substitute for trusted "
                        f"calibration"
                    )

        # --- findings ------------------------------------------------------
        # Only evidence-invalidating findings may drive INVALID. Blocking
        # findings that merely prevent certification are reported, and stop
        # at INCONCLUSIVE.
        invalidating = [
            (a.critic_id, f)
            for a in assessments
            for f in a.invalidating_findings
        ]
        blocking = [
            (a.critic_id, f)
            for a in assessments
            for f in a.findings
            if f.severity is Severity.BLOCKING and not f.invalidates_subject
        ]
        for critic_id, finding in invalidating:
            reasons.append(f"{critic_id}: {finding.code} (invalidating)")
        for critic_id, finding in blocking:
            reasons.append(f"{critic_id}: {finding.code} (blocks certification)")

        verdict = self._verdict(
            assessments=assessments,
            obligations=obligations,
            results=results,
            invalidating=bool(invalidating),
        )
        decision = ArbiterDecision(
            decision_id=decision_id,
            subject_ref=subject_ref,
            verdict=verdict,
            obligation_results=tuple(results),
            assessment_refs=tuple(a.assessment_id for a in assessments),
            reasons=tuple(reasons),
            arbiter_version=self._version,
            campaign_id=obligations.campaign_id,
            decided_at=decided_at,
        )
        self._issued.add(decision.decision_hash)
        return decision

    @staticmethod
    def _verdict(
        *,
        assessments: Sequence[CriticAssessment],
        obligations: ObligationSet,
        results: Sequence[ObligationResult],
        invalidating: bool,
    ) -> AssuranceVerdict:
        """The INVALID invariant (M3.1).

        ``INVALID`` requires at least one **evidence-invalidating** finding —
        something that shows the subject itself is wrong. None of the
        following is sufficient on its own, and all of them merely block VALID:

        * missing diagnostics
        * a skipped critic
        * insufficient data
        * an untrusted auxiliary cost/failure calibration
        * an unsupported (but uncontradicted) assumption
        * an unevaluated charter obligation

        The reason is epistemic, not stylistic. "We cannot certify this" and
        "this has been disproven" license completely different actions, and a
        system that reports the second when it means the first will eventually
        discard a correct result because a runtime cost model was untrustworthy.
        """
        if not assessments:
            return AssuranceVerdict.NOT_ASSESSED

        # Evidence-backed invalidation outranks everything, including the
        # absence of obligations: a refuted subject is refuted regardless of
        # what anyone asked for.
        if invalidating:
            return AssuranceVerdict.INVALID

        if obligations.is_empty:
            # Nothing was required, so nothing can be certified.
            return AssuranceVerdict.INCONCLUSIVE

        unmet = [r for r in results if not r.satisfied]
        if unmet:
            return AssuranceVerdict.INCONCLUSIVE

        if any(a.verdict is CriticVerdict.NOT_ASSESSED for a in assessments):
            return AssuranceVerdict.INCONCLUSIVE
        if any(a.verdict is CriticVerdict.INCONCLUSIVE for a in assessments):
            return AssuranceVerdict.INCONCLUSIVE
        if any(a.verdict is CriticVerdict.FAIL for a in assessments):
            # A FAIL with no invalidating finding is an assurance failure, not
            # a scientific refutation.
            return AssuranceVerdict.INCONCLUSIVE

        return AssuranceVerdict.VALID

    def _mint_authorization(
        self, *, decision, subject_record_hash: str
    ) -> str:
        """Draw a fresh code and register only its commitment.

        The authority is told ``sha256(code | payload)``. It never sees the
        code until one is presented for verification, and it cannot derive it.
        """
        payload = self._authority.authorization_payload(
            decision_id=decision.decision_id,
            decision_hash=decision.decision_hash,
            subject_record_hash=subject_record_hash,
            verdict=decision.verdict.value,
            policy_id="sria.arbiter",
            policy_version=self._version,
            arbiter_id=self._arbiter_id,
        )
        code = secrets.token_hex(32)
        self._authority.register_authorization(
            self._registrar,
            self._authority.commitment_for(code, payload),
            payload,
        )
        return code

    # ---- authorize admission -------------------------------------------
    def authorize_admission(
        self,
        decision: ArbiterDecision,
        evidence: Evidence,
        *,
        rationale: str = "",
    ) -> AdmissionDeclaration:
        """Issue a signed declaration — only for a VALID decision.

        The declaration is bound to this evidence record, so it cannot be
        replayed onto another. A non-VALID decision produces a *declining*
        declaration rather than an exception: refusal is a normal, recordable
        outcome, and the M1 semantics say a decline leaves scientific standing
        untouched.
        """
        if not isinstance(evidence, Evidence):
            raise TypeError("authorize_admission requires an Evidence record")
        if decision.subject_ref not in (evidence.evidence_id, evidence.record_hash):
            raise ValueError(
                f"decision {decision.decision_id!r} was made about "
                f"{decision.subject_ref!r}, not about evidence "
                f"{evidence.evidence_id!r}"
            )

        # A decision this Arbiter did not produce cannot authorize anything.
        if decision.decision_hash not in self._issued:
            raise ValueError(
                f"decision {decision.decision_id!r} was not issued by this "
                f"Arbiter; a fabricated decision cannot authorize admission"
            )

        admitted = decision.admits
        reason = rationale or (
            f"arbiter verdict {decision.verdict.value}"
            + (
                ""
                if admitted
                else f"; unmet: {list(decision.unmet_obligations)[:4]}"
            )
        )
        # The binding travels inside the signed payload, so the Gateway can
        # verify the chain without trusting the caller: it sees which decision
        # this rests on and what that decision concluded.
        binding = DecisionBinding(
            decision_id=decision.decision_id,
            decision_hash=decision.decision_hash,
            verdict=decision.verdict.value,
            policy_id="sria.arbiter",
            policy_version=self._version,
            arbiter_id=self._arbiter_id,
            authorization_code=self._mint_authorization(
                decision=decision,
                subject_record_hash=evidence.record_hash,
            ),
        )
        return self._authority.issue(
            admitted=admitted,
            subject_record_hash=evidence.record_hash,
            authorization=binding,
            arbiter_version=self._version,
            rationale=reason,
            criteria_ref=tuple(r.obligation_id for r in decision.obligation_results),
            decided_at=decision.decided_at,
        )
