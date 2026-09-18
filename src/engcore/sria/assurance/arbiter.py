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

**What a decision is about, and what may count (audit SRIA-TRUST-01..04).**
The audit showed that none of the following held, and each is now enforced
here rather than assumed of callers:

* An admission-bearing decision is made about ONE :class:`Evidence` record.
  ``decide(evidence=...)`` makes the decision's subject that record's
  ``record_hash``; ``authorize_admission`` accepts nothing else — never an
  ``evidence_id``, which a different record may reuse — and a decision
  authorizes at most once.
* Critics are registered with the Arbiter at construction, and an assessment
  counts only if this Arbiter ran the registered critic that produced it
  (:meth:`Arbiter.run_critic`) and recorded its exact digest. A hand-built
  ``CriticAssessment`` is a dataclass anyone can construct; it is refused.
* Every counted assessment is bound to the decision's subject: recorded for
  that subject, and structurally about it — its ``subject_ref`` is the
  record hash, or its provenance ``inputs_ref`` names the run the evidence
  came from (``evidence.provenance_ref``). A refused assessment is not
  counted, and a decision with a refused assessment cannot be VALID.
* A required domain check is resolved only among DOMAIN assessments for the
  evidence's own Domain Pack; a check name reported more than once is
  ambiguous and unmet; a required critic class needs every one of its
  assessments to PASS.
* The uncertainty budget must describe the quantity the evidence claims.
* The obligation set's digest — the policy the decision was made under — is
  part of the decision hash and of the authorization's policy version.

* An assessment made over a scientific result counts for a
  QOI/parameter claim that states a value and units only if that result holds
  the claimed quantity at the claimed value (unit-converted; equal up to
  rounding, or within the claim's own declared ``tolerance``). The budget must
  carry the evidence's own uncertainty declaration.

**The trust root (audit follow-up).** An :class:`AdmissionAuthority` declares,
at construction, the critic-registry digest and the policy digests it serves
(:func:`trusting_authority` computes them from the critics and obligation
sets). The authorization an Arbiter mints carries its registry digest and the
decision's policy digest, and the authority verifies neither a foreign
registry nor an undeclared policy. An authority serves one Arbiter: a second
Arbiter around it is refused at construction. So building a fresh Arbiter with
self-registered critics around a trusted authority ends in no admission.

Scope, as elsewhere in SRIA: a same-process architectural boundary. Whoever
constructs the authority chooses which critic registry and policies it trusts,
exactly as they choose its secret; the registry digest names each critic's
implementation (module and qualified name), not just its id, but Python cannot
prove that the object behind a name is the code you reviewed.
"""

from __future__ import annotations

import hashlib
import json
import math
import numbers
import secrets
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from ...scientific.serialization import require_schema, schema_string
from ..admission import (
    AdmissionAuthority,
    AdmissionDeclaration,
    DecisionBinding,
    _issue_registrar_capability,
)
from ..evidence import ClaimType, Evidence
from ..provenance import DecisionProvenance
from ..uncertainty import UncertaintyChannel
from .assessment import (
    CriticAssessment,
    CriticClass,
    CriticVerdict,
    FindingImpact,
    Severity,
)
from .obligations import ObligationKind, ObligationSet, parse_charter_context_ref
from .uncertainty_budget import UncertaintyBudget

ARBITER_DECISION_SCHEMA = schema_string("sria_arbiter_decision")
ARBITER_VERSION = "arbiter/1"

#: A decision about one Evidence record. Only these may authorize admission.
SUBJECT_EVIDENCE = "evidence"
#: A decision about something that is not an Evidence record — a stop
#: proposal, a result id. Recordable and reviewable; never admission-bearing.
SUBJECT_REFERENCE = "reference"
_SUBJECT_KINDS = frozenset({SUBJECT_EVIDENCE, SUBJECT_REFERENCE})

#: Registered critic entry points, in the order a critic object is probed.
_ENTRY_DOMAIN = "assess_domain"
_ENTRY_EVALUATOR = "evaluate"
_ENTRY_CRITIC = "assess"


def _canonical_digest(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def assessment_digest(assessment: CriticAssessment) -> str:
    """The identity the Arbiter records for a critic run's exact output."""
    return _canonical_digest(assessment.to_dict())


class AssuranceVerdict(str, Enum):
    """The final scientific assurance verdict. Only the Arbiter issues these."""

    VALID = "valid"
    INVALID = "invalid"
    INCONCLUSIVE = "inconclusive"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True)
class CriticRegistration:
    """What the Arbiter knows about one critic it was constructed to trust."""

    critic_id: str
    critic_version: str
    critic_class: CriticClass
    entry_point: str
    domain_pack_ref: str = ""
    #: ``module.qualname`` of the critic's class. Part of the registry digest,
    #: so a look-alike critic with the same id, version and class is a
    #: different registry.
    implementation: str = ""
    # Only a reviewed critic with this capability may discharge
    # validation_level:* obligations. A matching check name alone is not
    # scientific authority.
    validation_level_issuer: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "critic_id": self.critic_id,
            "critic_version": self.critic_version,
            "critic_class": self.critic_class.value,
            "entry_point": self.entry_point,
            "domain_pack_ref": self.domain_pack_ref,
            "implementation": self.implementation,
            "validation_level_issuer": self.validation_level_issuer,
        }


def _registration_for(critic: Any) -> CriticRegistration:
    critic_id = str(getattr(critic, "critic_id", "") or "").strip()
    if not critic_id:
        raise TypeError(
            f"cannot register {type(critic).__name__}: a critic must declare a "
            f"critic_id, or its assessments cannot be attributed"
        )
    version = str(getattr(critic, "critic_version", "") or "")
    if callable(getattr(critic, _ENTRY_DOMAIN, None)):
        entry = _ENTRY_DOMAIN
        critic_class = CriticClass.DOMAIN
    elif callable(getattr(critic, _ENTRY_EVALUATOR, None)):
        entry = _ENTRY_EVALUATOR
        critic_class = CriticClass(getattr(critic, "critic_class", CriticClass.PROCESS))
    elif callable(getattr(critic, _ENTRY_CRITIC, None)):
        entry = _ENTRY_CRITIC
        declared = getattr(critic, "critic_class", None)
        if declared is None:
            raise TypeError(
                f"critic {critic_id!r} must declare its critic_class; the "
                f"Arbiter will not guess which kind of trust a critic speaks to"
            )
        critic_class = CriticClass(declared)
    else:
        raise TypeError(
            f"critic {critic_id!r} exposes none of assess_domain / evaluate / "
            f"assess, so the Arbiter has nothing it could run"
        )
    pack = ""
    if critic_class is CriticClass.DOMAIN:
        pack = str(getattr(critic, "domain_pack_ref", "") or "").strip()
        if not pack:
            raise TypeError(
                f"domain critic {critic_id!r} must declare the domain_pack_ref "
                f"it speaks for; a domain critic without a pack could discharge "
                f"any pack's obligations"
            )
    level_issuer = getattr(critic, "validation_level_issuer", False)
    if not isinstance(level_issuer, bool):
        raise TypeError(
            f"critic {critic_id!r} validation_level_issuer must be an explicit "
            "bool; truthiness cannot grant scientific issuing authority"
        )
    return CriticRegistration(
        critic_id=critic_id,
        critic_version=version,
        critic_class=critic_class,
        entry_point=entry,
        domain_pack_ref=pack,
        implementation=f"{type(critic).__module__}.{type(critic).__qualname__}",
        validation_level_issuer=level_issuer,
    )


def _registrations_for(critics: Iterable[Any]) -> dict[str, CriticRegistration]:
    registrations: dict[str, CriticRegistration] = {}
    for critic in critics:
        registration = _registration_for(critic)
        if registration.critic_id in registrations:
            raise ValueError(
                f"critic id {registration.critic_id!r} is registered twice; "
                f"an assessment must be attributable to exactly one critic"
            )
        registrations[registration.critic_id] = registration
    return registrations


def critic_registry_digest(critics: Iterable[Any]) -> str:
    """The digest an Arbiter constructed with ``critics`` records and presents."""
    registrations = _registrations_for(critics)
    return _canonical_digest(
        [registrations[k].to_dict() for k in sorted(registrations)]
    )


def trusting_authority(
    authority_id: str,
    critics: Iterable[Any],
    *,
    policies: Iterable[ObligationSet] = (),
    secret: str | None = None,
) -> AdmissionAuthority:
    """An AdmissionAuthority that trusts exactly these critics and policies.

    Construct it before the Arbiter, with the same critics the Arbiter will be
    built with and the obligation sets it may admit under.
    """
    return AdmissionAuthority(
        authority_id,
        secret,
        critic_registry_digest=critic_registry_digest(critics),
        policy_digests=tuple(policy.digest for policy in policies),
    )


@dataclass(frozen=True)
class _AssessedResult:
    """What the Arbiter saw a critic assess: the result's named quantities.

    The quantity objects are the result's own (immutable) values, kept so a
    claim can be converted into and compared with them. Recognised
    structurally — a result id, a provenance with a run id, and a mapping of
    values — which is the shape of a Scientific Core ``ScientificResult``;
    SRIA reaches the core only through its existing imports.
    """

    digest: str
    quantities: Mapping[str, Any]


def _looks_like_result(item: Any) -> bool:
    return (
        isinstance(getattr(item, "values", None), Mapping)
        and bool(str(getattr(item, "result_id", "") or "").strip())
        and hasattr(getattr(item, "provenance", None), "run_id")
    )


def _assessed_result(inputs: Sequence[Any]) -> _AssessedResult | None:
    """The scientific result a critic run read, if one was among its inputs."""
    for item in inputs:
        result = item if _looks_like_result(item) else getattr(item, "result", None)
        if not _looks_like_result(result):
            continue
        quantities = {str(name): value for name, value in dict(result.values).items()}
        try:
            digest = _canonical_digest(result.to_dict())
        except Exception:  # noqa: BLE001 — the quantities are what is compared
            digest = _canonical_digest(
                {
                    "result_id": result.result_id,
                    "values": {
                        name: [getattr(v, "magnitude", None), str(getattr(v, "units", ""))]
                        for name, v in quantities.items()
                    },
                }
            )
        return _AssessedResult(digest=digest, quantities=quantities)
    return None


#: Claim types whose payload may state the value of one bound quantity.
_VALUE_CLAIMS = frozenset({ClaimType.QOI_VALUE, ClaimType.PARAMETER_VALUE})


def _real(value: Any) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def claim_backing_problem(evidence: Evidence, assessed: _AssessedResult) -> str:
    """Why an assessed result does not back a value claim, or "" if it does.

    Applies to QOI/parameter claims whose payload states ``value`` (a real
    number) and ``units``. The bound quantity is the claim binding's
    ``subject_ref``; the result's quantity is converted into the claim's units.
    Equality is exact up to floating-point rounding, unless the claim declares
    a non-negative ``tolerance`` in its own units.
    """
    if evidence.claim_type not in _VALUE_CLAIMS:
        return ""
    payload = evidence.claim_payload
    if "value" not in payload or "units" not in payload:
        return ""
    value = payload["value"]
    if not _real(value):
        return ""
    name = evidence.claim_binding.subject_ref
    claim_units = str(payload["units"])
    if name not in assessed.quantities:
        return f"the assessed result holds no quantity {name!r}"
    quantity = assessed.quantities[name]
    if not _real(getattr(quantity, "magnitude", None)) or not callable(
        getattr(quantity, "to", None)
    ):
        return f"the assessed result's {name!r} is not a scalar quantity"
    try:
        held = float(quantity.to(claim_units).magnitude)
    except Exception:  # noqa: BLE001 — incomparable units are a mismatch
        return (
            f"the claim's units {claim_units!r} are not comparable with the "
            f"assessed {name!r} in {getattr(quantity, 'units', '')!r}"
        )
    tolerance = payload.get("tolerance")
    if tolerance is None:
        backed = math.isclose(float(value), held, rel_tol=1e-9, abs_tol=0.0)
    else:
        if not _real(tolerance) or not math.isfinite(float(tolerance)) or tolerance < 0:
            return f"the claim declares an invalid tolerance {tolerance!r}"
        backed = abs(float(value) - held) <= float(tolerance)
    if not backed:
        return (
            f"the claim states {name} = {value} {claim_units}, but the assessed "
            f"result holds {held} {claim_units}"
        )
    return ""


def _declaration_digest(declaration: Any) -> str:
    return _canonical_digest(declaration.to_dict())


def _context_results(
    evidence: "Evidence | None",
    obligations: ObligationSet,
    results: list,
    reasons: list,
) -> None:
    """Append the context-of-use results for one decision (see ``decide``)."""
    claimed = None if evidence is None else parse_charter_context_ref(evidence.context_ref)
    if claimed is not None and (claimed == ("", "") or claimed[0] != obligations.charter_digest):
        if claimed == ("", ""):
            why = f"evidence context {evidence.context_ref!r} claims a charter but does not name one"
        elif not obligations.charter_digest:
            why = (
                f"evidence was produced under charter {claimed[0][:16]}..., and this policy was "
                f"derived from no charter"
            )
        else:
            why = (
                f"evidence was produced under charter {claimed[0][:16]}..., not this policy's "
                f"charter {obligations.charter_digest[:16]}..."
            )
        results.append(ObligationResult(obligation_id="context:charter", satisfied=False, detail=why))
        reasons.append(f"context of use: {why}")
    for obligation in obligations.of_kind(ObligationKind.REQUIRED_CONTEXT):
        required = obligation.target
        bound_charter = parse_charter_context_ref(required)
        if evidence is None:
            ok, why = False, "a context is bound to an evidence record; this decision has none"
        elif bound_charter is not None and bound_charter[0] != obligations.charter_digest:
            ok, why = False, "the required context names another charter than the policy's own"
        elif evidence.context_ref != required:
            ok, why = False, f"evidence context {evidence.context_ref!r} is not the required {required!r}"
        else:
            ok, why = True, "evidence context is the required context"
        results.append(
            ObligationResult(
                obligation_id=obligation.obligation_id,
                satisfied=ok,
                evidence_ref="" if evidence is None else evidence.evidence_id,
                detail=why,
            )
        )
        if not ok:
            reasons.append(f"context of use: {why}")


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
    """A replayable record of one assurance decision.

    ``subject_ref`` is the record hash when ``subject_kind`` is
    ``"evidence"``; otherwise it is an opaque reference and the decision can
    never authorize admission. ``policy_digest`` is the digest of the
    obligation set applied, ``critic_registry_digest`` the digest of the
    critics the Arbiter trusted, and ``refused_assessments`` the ids of
    assessments offered but not counted. All of them are inside
    :attr:`decision_hash`.
    """

    decision_id: str
    subject_ref: str
    verdict: AssuranceVerdict
    obligation_results: tuple[ObligationResult, ...]
    assessment_refs: tuple[str, ...]
    reasons: tuple[str, ...]
    arbiter_version: str = ARBITER_VERSION
    campaign_id: str = ""
    decided_at: str | None = None
    subject_kind: str = SUBJECT_REFERENCE
    evidence_id: str = ""
    policy_digest: str = ""
    critic_registry_digest: str = ""
    refused_assessments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "verdict", AssuranceVerdict(self.verdict))
        object.__setattr__(self, "obligation_results", tuple(self.obligation_results))
        object.__setattr__(self, "assessment_refs", tuple(self.assessment_refs))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(
            self, "refused_assessments", tuple(self.refused_assessments)
        )
        if self.subject_kind not in _SUBJECT_KINDS:
            raise ValueError(
                f"decision subject_kind must be one of {sorted(_SUBJECT_KINDS)}, "
                f"got {self.subject_kind!r}"
            )

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

    @property
    def is_about_evidence(self) -> bool:
        return self.subject_kind == SUBJECT_EVIDENCE

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
            "subject_kind": self.subject_kind,
            "evidence_id": self.evidence_id,
            "policy_digest": self.policy_digest,
            "critic_registry_digest": self.critic_registry_digest,
            "refused_assessments": list(self.refused_assessments),
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
            # A payload written before the audit repair names no subject kind,
            # so it reads as a reference decision and can authorize nothing.
            subject_kind=payload.get("subject_kind", SUBJECT_REFERENCE),
            evidence_id=payload.get("evidence_id", ""),
            policy_digest=payload.get("policy_digest", ""),
            critic_registry_digest=payload.get("critic_registry_digest", ""),
            refused_assessments=tuple(payload.get("refused_assessments", ())),
        )


def budget_describes_claim(budget: UncertaintyBudget, evidence: Evidence) -> bool:
    """Whether an uncertainty budget is about the quantity the evidence claims.

    Accepted names are the evidence's belief key or its claim-binding key, or
    the bare binding ``subject_ref`` when the binding carries no qualifiers
    (with qualifiers, the bare name no longer identifies one quantity).
    """
    name = str(budget.value_name).strip()
    binding = evidence.claim_binding
    accepted = {evidence.belief_key, binding.key}
    if not binding.qualifiers:
        accepted.add(binding.subject_ref)
    return name in accepted


class Arbiter:
    """Evaluates obligations against critic assessments and authorizes admission."""

    def __init__(
        self,
        authority: AdmissionAuthority,
        *,
        critics: Iterable[Any] = (),
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
        # The critic registry. Fixed at construction: which critics an
        # Arbiter trusts is part of what the Arbiter *is*, and a registry that
        # could grow later would let any holder of the Arbiter add a critic
        # that says whatever it is told to (audit SRIA-TRUST-01).
        critics = tuple(critics)
        self._registrations: dict[str, CriticRegistration] = _registrations_for(critics)
        self._critics: dict[str, Any] = {
            _registration_for(critic).critic_id: critic for critic in critics
        }
        self._registry_digest = critic_registry_digest(critics)
        # The registration capability. Held privately and never returned, so
        # possession of the authority alone cannot register commitments. The
        # authority refuses a second Arbiter once one with its declared
        # registry holds a capability (audit follow-up, trust root).
        self._registrar = _issue_registrar_capability(
            authority, self._arbiter_id, self._registry_digest
        )
        # Decisions this Arbiter actually produced, by hash. Without this,
        # any caller could hand-build an ArbiterDecision(verdict=VALID) and
        # have it signed — a fabricated-decision bypass.
        self._issued: dict[str, ArbiterDecision] = {}
        # Decisions that have already authorized once (audit SRIA-TRUST-04).
        self._authorized: set[str] = set()
        # Digest of each assessment a registered critic produced through
        # run_critic -> the subject keys it was produced for.
        self._recorded: dict[str, set[str]] = {}
        # Digest of each such assessment -> the ScientificResult it read.
        self._assessed_results: dict[str, _AssessedResult] = {}

    @property
    def authority_id(self) -> str:
        return self._authority.authority_id

    @property
    def authority(self) -> AdmissionAuthority:
        """The authority this Arbiter asks to sign. Holding it confers nothing:
        it registers no commitment and serves no second Arbiter."""
        return self._authority

    # ---- critic registry -------------------------------------------------
    @property
    def registered_critics(self) -> tuple[CriticRegistration, ...]:
        return tuple(self._registrations[k] for k in sorted(self._registrations))

    @property
    def critic_registry_digest(self) -> str:
        return self._registry_digest

    def is_registered(self, critic: Any) -> bool:
        """Whether this exact critic object is one the Arbiter was built with."""
        critic_id = str(getattr(critic, "critic_id", "") or "").strip()
        return self._critics.get(critic_id) is critic

    def issued(self, decision: "ArbiterDecision") -> bool:
        """Whether this Arbiter produced exactly this decision."""
        return (
            isinstance(decision, ArbiterDecision)
            and decision.decision_hash in self._issued
        )

    def issued_decision(self, decision_hash: str) -> "ArbiterDecision | None":
        """This Arbiter's own copy of a decision it issued, by hash."""
        return self._issued.get(str(decision_hash))

    @staticmethod
    def _subject_key(subject: Any) -> str:
        if isinstance(subject, Evidence):
            return f"{SUBJECT_EVIDENCE}:{subject.record_hash}"
        reference = str(subject if subject is not None else "").strip()
        if not reference:
            raise ValueError(
                "a critic run must name its subject: an Evidence record, or a "
                "non-empty reference"
            )
        return f"{SUBJECT_REFERENCE}:{reference}"

    def run_critic(
        self,
        critic_id: str,
        *inputs: Any,
        subject: Evidence | str,
        assessment_id: str,
        **options: Any,
    ) -> CriticAssessment:
        """Run one registered critic and record what it produced.

        The Arbiter calls the registered object's own entry point
        (``assess_domain`` for a domain critic, ``evaluate`` for a stopping
        criterion evaluator, ``assess`` otherwise) with ``inputs`` and
        ``options``, verifies the output is attributable to that registration,
        stamps a domain critic's pack, and records the output's digest for
        ``subject``. Only a recorded assessment can count in :meth:`decide`.

        Recording is not acceptance: whether the assessment is actually about
        the subject is checked when a decision is made.
        """
        critic_id = str(critic_id)
        registration = self._registrations.get(critic_id)
        if registration is None:
            raise KeyError(
                f"critic {critic_id!r} is not registered with this Arbiter; "
                f"registered: {sorted(self._registrations)}"
            )
        subject_key = self._subject_key(subject)
        entry = getattr(self._critics[critic_id], registration.entry_point)
        produced = entry(*inputs, assessment_id=assessment_id, **options)
        if not isinstance(produced, CriticAssessment):
            raise TypeError(
                f"critic {critic_id!r} returned {type(produced).__name__}, not a "
                f"CriticAssessment"
            )
        mismatches = []
        if produced.assessment_id != assessment_id:
            mismatches.append(f"assessment_id {produced.assessment_id!r}")
        if produced.critic_id != registration.critic_id:
            mismatches.append(f"critic_id {produced.critic_id!r}")
        if produced.critic_version != registration.critic_version:
            mismatches.append(f"critic_version {produced.critic_version!r}")
        if produced.critic_class is not registration.critic_class:
            mismatches.append(f"critic_class {produced.critic_class.value!r}")
        if produced.domain_pack_ref and (
            produced.domain_pack_ref != registration.domain_pack_ref
        ):
            mismatches.append(f"domain_pack_ref {produced.domain_pack_ref!r}")
        if mismatches:
            raise ValueError(
                f"critic {critic_id!r} produced an assessment that does not match "
                f"its registration ({', '.join(mismatches)}); it cannot be "
                f"attributed to the critic this Arbiter trusts"
            )
        if registration.domain_pack_ref and not produced.domain_pack_ref:
            produced = replace(produced, domain_pack_ref=registration.domain_pack_ref)
        assessed = _assessed_result(inputs)
        if assessed is not None:
            # The assessment says which result it read; the Arbiter keeps what
            # that result holds, to check the claim it is offered for.
            produced = replace(
                produced,
                provenance=replace(
                    produced.provenance,
                    metadata={
                        **dict(produced.provenance.metadata),
                        "assessed_result_digest": assessed.digest,
                    },
                ),
            )
        digest = assessment_digest(produced)
        self._recorded.setdefault(digest, set()).add(subject_key)
        if assessed is not None:
            self._assessed_results[digest] = assessed
        return produced

    # ---- decide ---------------------------------------------------------
    def _refusal(
        self,
        assessment: CriticAssessment,
        *,
        subject_key: str,
        subject_ref: str,
        evidence: Evidence | None,
    ) -> str:
        """Why an offered assessment may not count, or "" if it may."""
        label = assessment.assessment_id
        digest = assessment_digest(assessment)
        subjects = self._recorded.get(digest)
        if subjects is None:
            return (
                f"assessment {label!r} was not produced by a critic registered "
                f"with and run through this Arbiter"
            )
        if subject_key not in subjects:
            return (
                f"assessment {label!r} was run for a different subject than this "
                f"decision's"
            )
        if evidence is not None:
            bound = (
                assessment.subject_ref == subject_ref
                or evidence.provenance_ref in assessment.provenance.inputs_ref
            )
            if not bound:
                return (
                    f"assessment {label!r} is about {assessment.subject_ref!r} "
                    f"(inputs {list(assessment.provenance.inputs_ref)}), not "
                    f"evidence {evidence.evidence_id!r} from run "
                    f"{evidence.provenance_ref!r}"
                )
            if (
                assessment.critic_class is CriticClass.DOMAIN
                and assessment.domain_pack_ref != evidence.domain_pack_ref
            ):
                return (
                    f"domain assessment {label!r} speaks for pack "
                    f"{assessment.domain_pack_ref!r}; evidence "
                    f"{evidence.evidence_id!r} belongs to pack "
                    f"{evidence.domain_pack_ref!r}"
                )
            report_digest = evidence.claim_payload.get(
                "_credibility_report_digest"
            )
            if report_digest:
                assessed_report_digest = assessment.provenance.metadata.get(
                    "credibility_report_digest"
                )
                if assessed_report_digest != report_digest:
                    return (
                        f"assessment {label!r} is not bound to the credibility "
                        "report that produced this evidence"
                    )
            assessed = self._assessed_results.get(digest)
            if assessed is not None:
                problem = claim_backing_problem(evidence, assessed)
                if problem:
                    return (
                        f"assessment {label!r} does not back evidence "
                        f"{evidence.evidence_id!r}: {problem}"
                    )
        elif assessment.subject_ref != subject_ref:
            return (
                f"assessment {label!r} is about {assessment.subject_ref!r}, not "
                f"{subject_ref!r}"
            )
        return ""

    @staticmethod
    def _resolve_check(
        target: str, scope: Sequence[CriticAssessment]
    ) -> tuple[str, Any, str]:
        """(state, record, evidence_ref) for one named check within ``scope``.

        state is ``"missing"``, ``"ambiguous"`` or ``"found"``. A name reported
        more than once is never resolved by order: the first and last report
        can disagree, and picking either is choosing an answer.
        """
        found = [(a, c) for a in scope for c in a.checks if c.name == target]
        if not found:
            return "missing", None, ""
        refs = ",".join(sorted({a.assessment_id for a, _c in found}))
        if len(found) > 1:
            return "ambiguous", None, refs
        return "found", found[0][1], refs

    def decide(
        self,
        *,
        decision_id: str,
        assessments: Sequence[CriticAssessment],
        obligations: ObligationSet,
        evidence: Evidence | None = None,
        subject_ref: str = "",
        budget: UncertaintyBudget | None = None,
        decided_at: str | None = None,
    ) -> ArbiterDecision:
        """Decide about one subject.

        Pass ``evidence`` for an admission-bearing decision: its subject is
        ``evidence.record_hash``. Pass only ``subject_ref`` for a decision about
        anything else; such a decision can never authorize admission.
        """
        if not isinstance(obligations, ObligationSet):
            raise TypeError("decide requires an ObligationSet")
        if evidence is not None:
            if not isinstance(evidence, Evidence):
                raise TypeError("decide(evidence=...) requires an Evidence record")
            record_hash = evidence.record_hash
            if subject_ref and str(subject_ref) != record_hash:
                raise ValueError(
                    f"a decision about evidence {evidence.evidence_id!r} is about "
                    f"its record hash; subject_ref {subject_ref!r} names something "
                    f"else"
                )
            subject = record_hash
            subject_kind = SUBJECT_EVIDENCE
        else:
            subject = str(subject_ref).strip()
            if not subject:
                raise ValueError(
                    "decide requires evidence, or a subject_ref for a decision "
                    "that is not about an evidence record"
                )
            subject_kind = SUBJECT_REFERENCE
        subject_key = f"{subject_kind}:{subject}"

        results: list[ObligationResult] = []
        reasons: list[str] = []

        # --- which assessments may count ------------------------------------
        counted: list[CriticAssessment] = []
        refused: list[str] = []
        seen_ids: set[str] = set()
        for assessment in assessments:
            if not isinstance(assessment, CriticAssessment):
                raise TypeError(
                    f"decide received {type(assessment).__name__}, not a "
                    f"CriticAssessment"
                )
            if assessment.assessment_id in seen_ids:
                why = (
                    f"assessment id {assessment.assessment_id!r} was offered more "
                    f"than once"
                )
            else:
                why = self._refusal(
                    assessment,
                    subject_key=subject_key,
                    subject_ref=subject,
                    evidence=evidence,
                )
            seen_ids.add(assessment.assessment_id)
            if why:
                refused.append(assessment.assessment_id)
                reasons.append(f"refused: {why}")
            else:
                counted.append(assessment)

        # --- required critics -------------------------------------------
        for obligation in obligations.of_kind(ObligationKind.REQUIRED_CRITIC):
            critic_class = CriticClass(obligation.target)
            of_class = [a for a in counted if a.critic_class is critic_class]
            if not of_class:
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
                continue
            # Every assessment of the class must pass; a later PASS does not
            # overwrite an earlier FAIL (audit SRIA-TRUST-03).
            not_passing = [a for a in of_class if a.verdict is not CriticVerdict.PASS]
            ok = not not_passing
            verdicts = ", ".join(
                f"{a.assessment_id}={a.verdict.value}" for a in of_class
            )
            results.append(
                ObligationResult(
                    obligation_id=obligation.obligation_id,
                    satisfied=ok,
                    evidence_ref=",".join(a.assessment_id for a in of_class),
                    detail=f"{critic_class.value} verdicts {verdicts}",
                )
            )
            if not ok:
                for a in not_passing:
                    reasons.append(
                        f"critic {critic_class.value} returned {a.verdict.value}"
                    )

        # --- required named checks --------------------------------------
        for obligation in obligations.of_kind(ObligationKind.REQUIRED_CHECK):
            target = obligation.target
            check_scope = counted
            if target.startswith("validation_level:"):
                check_scope = [
                    assessment
                    for assessment in counted
                    if self._registrations[
                        assessment.critic_id
                    ].validation_level_issuer
                ]
            state, record, refs = self._resolve_check(target, check_scope)
            if state == "missing":
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=False,
                        detail="required check was never performed",
                    )
                )
                reasons.append(f"required check {target!r} was not performed")
            elif state == "ambiguous":
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=False,
                        evidence_ref=refs,
                        detail=(
                            f"ambiguous: {target!r} was reported more than once "
                            f"(by {refs}), so no single outcome can be certified"
                        ),
                    )
                )
                reasons.append(f"required check {target!r} is ambiguous")
            else:
                ok = record.outcome is CriticVerdict.PASS
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=ok,
                        evidence_ref=refs,
                        detail=f"{target} -> {record.outcome.value}",
                    )
                )
                if not ok:
                    reasons.append(f"check {target!r} is {record.outcome.value}")

        # --- required domain checks --------------------------------------
        # Resolved ONLY among DOMAIN assessments for the evidence's own pack.
        # A check of the same name from any other critic class, or from a
        # domain critic for another pack, is not this pack's judgement.
        domain_scope = [a for a in counted if a.critic_class is CriticClass.DOMAIN]
        for obligation in obligations.of_kind(ObligationKind.REQUIRED_DOMAIN_CHECK):
            target = obligation.target
            if evidence is None:
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=False,
                        detail=(
                            "a domain check is resolved against an evidence "
                            "record's domain pack; this decision has no evidence"
                        ),
                    )
                )
                reasons.append(f"domain check {target!r} has no domain pack to resolve in")
                continue
            if not domain_scope:
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=False,
                        detail=(
                            f"domain critic for pack {evidence.domain_pack_ref!r} "
                            f"did not run"
                        ),
                    )
                )
                reasons.append(f"domain check {target!r} was skipped")
                continue
            state, record, refs = self._resolve_check(target, domain_scope)
            if state == "missing":
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=False,
                        detail="domain critic ran but did not perform this check",
                    )
                )
                reasons.append(f"domain check {target!r} was not performed")
            elif state == "ambiguous":
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=False,
                        evidence_ref=refs,
                        detail=(
                            f"ambiguous: domain check {target!r} was reported more "
                            f"than once (by {refs})"
                        ),
                    )
                )
                reasons.append(f"domain check {target!r} is ambiguous")
            else:
                ok = record.outcome is CriticVerdict.PASS
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=ok,
                        evidence_ref=refs,
                        detail=f"{target} -> {record.outcome.value}",
                    )
                )
                if not ok:
                    reasons.append(f"domain check {target!r} is {record.outcome.value}")

        # --- required uncertainty channels --------------------------------
        for obligation in obligations.of_kind(
            ObligationKind.REQUIRED_UNCERTAINTY_CHANNEL
        ):
            channel = UncertaintyChannel(obligation.target)
            if budget is None:
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=False,
                        detail="no uncertainty budget was supplied",
                    )
                )
                reasons.append(
                    f"uncertainty channel {channel.value} required but no budget given"
                )
                continue
            if evidence is not None and budget_describes_claim(budget, evidence) and (
                _declaration_digest(budget.declaration)
                != _declaration_digest(evidence.uncertainty)
            ):
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=False,
                        detail=(
                            "the uncertainty budget's declaration is not the "
                            "evidence's own uncertainty declaration"
                        ),
                    )
                )
                reasons.append(
                    f"uncertainty channel {channel.value}: the budget's declaration "
                    f"differs from evidence {evidence.evidence_id!r}'s"
                )
                continue
            if evidence is None or not budget_describes_claim(budget, evidence):
                claimed = evidence.belief_key if evidence is not None else "no claim"
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=False,
                        detail=(
                            f"the uncertainty budget describes "
                            f"{budget.value_name!r}, not the claimed quantity "
                            f"({claimed})"
                        ),
                    )
                )
                reasons.append(
                    f"uncertainty channel {channel.value}: budget "
                    f"{budget.value_name!r} is not about this claim"
                )
                continue
            entry = budget.entry(channel)
            ok = entry.is_quantified
            results.append(
                ObligationResult(
                    obligation_id=obligation.obligation_id,
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
        calibration = [a for a in counted if a.critic_class is CriticClass.CALIBRATION]
        for obligation in obligations.of_kind(
            ObligationKind.REQUIRED_CALIBRATION_STATUS
        ):
            if not calibration:
                results.append(
                    ObligationResult(
                        obligation_id=obligation.obligation_id,
                        satisfied=False,
                        detail="calibration critic did not run",
                    )
                )
                reasons.append("required calibration assessment was skipped")
                continue
            not_passing = [
                a for a in calibration if a.verdict is not CriticVerdict.PASS
            ]
            ok = not not_passing
            verdicts = ", ".join(a.verdict.value for a in calibration)
            results.append(
                ObligationResult(
                    obligation_id=obligation.obligation_id,
                    satisfied=ok,
                    evidence_ref=",".join(a.assessment_id for a in calibration),
                    detail=f"calibration verdict {verdicts}",
                )
            )
            if not ok:
                reasons.append(
                    f"calibration assessment is {verdicts}; "
                    f"a successful solve does not substitute for trusted "
                    f"calibration"
                )

        # --- context of use ------------------------------------------------
        # Evidence belongs to the charter and decision it was produced for
        # (audit N2). Two rules, both INCONCLUSIVE and never INVALID: evidence
        # judged under the wrong policy is not disproven, it is unaccounted for.
        #
        # 1. Unconditional: charter-bound evidence may only be judged under a
        #    policy derived from that same charter. Nothing is recorded on a
        #    match, so decisions over correctly bound evidence are unchanged.
        # 2. A REQUIRED_CONTEXT obligation demands the exact reference,
        #    decision included.
        _context_results(evidence, obligations, results, reasons)

        # --- findings ------------------------------------------------------
        # Only evidence-invalidating findings may drive INVALID. Blocking
        # findings that merely prevent certification are reported, and stop
        # at INCONCLUSIVE. Refused assessments contribute nothing.
        invalidating = [
            (a.critic_id, f)
            for a in counted
            for f in a.invalidating_findings
        ]
        blocking = [
            (a.critic_id, f)
            for a in counted
            for f in a.findings
            if f.severity is Severity.BLOCKING and not f.invalidates_subject
        ]
        for critic_id, finding in invalidating:
            reasons.append(f"{critic_id}: {finding.code} (invalidating)")
        for critic_id, finding in blocking:
            reasons.append(f"{critic_id}: {finding.code} (blocks certification)")

        verdict = self._verdict(
            assessments=counted,
            obligations=obligations,
            results=results,
            invalidating=bool(invalidating),
            refused=bool(refused),
        )
        decision = ArbiterDecision(
            decision_id=decision_id,
            subject_ref=subject,
            verdict=verdict,
            obligation_results=tuple(results),
            assessment_refs=tuple(a.assessment_id for a in counted),
            reasons=tuple(reasons),
            arbiter_version=self._version,
            campaign_id=obligations.campaign_id,
            decided_at=decided_at,
            subject_kind=subject_kind,
            evidence_id=evidence.evidence_id if evidence is not None else "",
            policy_digest=obligations.digest,
            critic_registry_digest=self._registry_digest,
            refused_assessments=tuple(refused),
        )
        self._issued[decision.decision_hash] = decision
        return decision

    @staticmethod
    def _verdict(
        *,
        assessments: Sequence[CriticAssessment],
        obligations: ObligationSet,
        results: Sequence[ObligationResult],
        invalidating: bool,
        refused: bool = False,
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
        * an offered assessment the Arbiter refused to count

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

        # An assessment that was offered and refused is a judgement the
        # decision could not account for. VALID over it would certify a
        # record while ignoring part of what was said about it.
        if refused:
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

    def _policy_version(self, decision: ArbiterDecision) -> str:
        """The authorization's policy version: Arbiter version plus policy digest."""
        return f"{self._version}#policy={decision.policy_digest}"

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
            policy_version=self._policy_version(decision),
            arbiter_id=self._arbiter_id,
            critic_registry_digest=self._registry_digest,
            policy_digest=decision.policy_digest,
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

        The decision must have been made about this exact record — its subject
        is the record hash, never the evidence id, which another record may
        share — and a decision authorizes at most once (audit SRIA-TRUST-04).
        """
        if not isinstance(evidence, Evidence):
            raise TypeError("authorize_admission requires an Evidence record")
        record_hash = evidence.record_hash
        if not (
            decision.subject_kind == SUBJECT_EVIDENCE
            and decision.subject_ref == record_hash
        ):
            raise ValueError(
                f"decision {decision.decision_id!r} was made about "
                f"{decision.subject_kind} {decision.subject_ref!r}, not about "
                f"evidence record {evidence.evidence_id!r} ({record_hash[:12]}…)"
            )

        # A decision this Arbiter did not produce cannot authorize anything.
        if decision.decision_hash not in self._issued:
            raise ValueError(
                f"decision {decision.decision_id!r} was not issued by this "
                f"Arbiter; a fabricated decision cannot authorize admission"
            )
        if decision.decision_hash in self._authorized:
            raise ValueError(
                f"decision {decision.decision_id!r} has already authorized "
                f"admission once; a fresh judgement needs a fresh decision"
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
            policy_version=self._policy_version(decision),
            arbiter_id=self._arbiter_id,
            authorization_code=self._mint_authorization(
                decision=decision,
                subject_record_hash=record_hash,
            ),
            critic_registry_digest=self._registry_digest,
            policy_digest=decision.policy_digest,
        )
        declaration = self._authority.issue(
            admitted=admitted,
            subject_record_hash=record_hash,
            authorization=binding,
            arbiter_version=self._version,
            rationale=reason,
            criteria_ref=tuple(r.obligation_id for r in decision.obligation_results),
            decided_at=decision.decided_at,
        )
        self._authorized.add(decision.decision_hash)
        return declaration
