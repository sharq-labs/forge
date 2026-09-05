"""Admission declarations and the authority that may issue them.

A gateway that accepts any well-formed declaration is not an authority
boundary — it only checks that the caller filled in the right fields. M1.1
adds the missing half: a declaration carries a verifiable issuer, and the
gateway refuses declarations it cannot attribute to a registered authority.

Two semantics are fixed here, and they are the point of this module.

**A declaration is bound to one evidence record.** It carries the
``subject_record_hash`` it was issued for, so an admission granted to one
record cannot be replayed onto another — including onto a different record
that happens to make the identical scientific claim.

**Failing admission is not a scientific verdict.** Refusal, forgery and
malformation are *procedural* outcomes. They are recorded as
:class:`AdmissionAttempt` entries and they leave the evidence's scientific
standing exactly where it was. Only a scientific authority may move evidence
to ``INVALID``, and it does so through an explicit epistemic decision, never
as a side effect of a failed admission.

Scope of the mechanism, stated plainly. Two separate things happen here:

* The declaration **signature** is an HMAC keyed by the authority. It is an
  integrity and attribution check, and the authority can obviously produce
  its own signatures — that is its job.
* The **authorization commitment** is one-way. The Arbiter draws a random
  code and registers only ``sha256(code | payload)``. The authority stores
  digests and no key material, so it can verify a presented code but cannot
  mint one without inverting SHA-256.

This is a same-process Python architectural authenticity boundary, not
public-key cryptography and not a production security system. Code that
monkey-patches this module, mutates ``_commitments`` directly, or reads
another object's attributes can still defeat it; Python provides no
isolation. What it does guarantee is that possession of a trusted
AdmissionAuthority no longer confers the ability to authorize admission
through the supported interfaces.

Historical note: the signature is an integrity and
attribution check between components inside one trusted process. It prevents
a component from manufacturing admission through the supported API, and makes
forgery attempts visible in an audit log. It is not a cryptographic security
control and it does not defend against code that can read process memory,
monkey-patch this module, or import private names deliberately. Authority
secrets are per-process and are not persisted, so declarations verify within
the run that issued them; durable, signed admission records are deferred.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from ..scientific.serialization import require_schema, schema_string
from .errors import AdmissionAuthorityError, AdmissionError

ADMISSION_SCHEMA = schema_string("sria_admission", 3)
DECISION_BINDING_SCHEMA = schema_string("sria_admission_authorization")
ADMISSION_ATTEMPT_SCHEMA = schema_string("sria_admission_attempt")


#: The only assurance verdict that may back an accepting declaration. A
#: plain string because this module must not import the assurance layer
#: that sits above it.
ACCEPTING_VERDICT = "valid"


#: Opaque right to register an authorization commitment.
#:
#: M3.3 made commitments one-way, so a verifier cannot *derive* a code. It left
#: a separate hole: ``register_authorization`` was public, so anyone holding a
#: trusted authority could choose their own code, compute its digest, register
#: it, and be signed. Registration authority and verification authority are
#: different capabilities and must not travel together.
#:
#: Following the ``_GatewayToken`` precedent already in this codebase: the
#: capability class refuses construction without a module-private key, so it
#: cannot be obtained through any supported interface — in particular, an
#: ``AdmissionAuthority`` exposes no method that returns one. The Arbiter
#: obtains it through a single, auditable seam (``_issue_registrar_capability``)
#: and never releases it.
#:
#: Scope, as everywhere in this module: a Python-private capability. Code that
#: deliberately imports the private factory or manipulates the interpreter can
#: still forge one. It stops registration through the supported API, which is
#: what an architectural boundary can provide.
_CAPABILITY_KEY = object()


class _RegistrarCapability:
    """Held by an Arbiter. Required to register a commitment."""

    __slots__ = ("registrar_id",)

    def __init__(self, registrar_id: str, key: Any = None) -> None:
        if key is not _CAPABILITY_KEY:
            raise AdmissionAuthorityError(
                "a registrar capability cannot be constructed directly; only "
                "the Arbiter authorization path may register commitments"
            )
        object.__setattr__(self, "registrar_id", str(registrar_id))


def _issue_registrar_capability(registrar_id: str) -> _RegistrarCapability:
    """The single seam through which an Arbiter obtains registration rights."""
    return _RegistrarCapability(registrar_id, _CAPABILITY_KEY)


class AdmissionOutcome(str, Enum):
    """What happened when admission was attempted.

    All four are procedural facts about the admission process. None of them is
    a statement about whether the science is right.
    """

    ADMITTED = "admitted"
    REFUSED = "refused"            # a real authority declined
    UNAUTHORIZED = "unauthorized"  # issuer could not be verified
    MALFORMED = "malformed"        # declaration did not match its subject


@dataclass(frozen=True)
class DecisionBinding:
    """The assurance decision an admission declaration rests on.

    Added in M3.1 to close a real gap: in M1 any code holding a *trusted*
    authority could mint an accepting declaration with no assurance decision
    behind it. Registration proved who was speaking, not that anything had
    been assessed.

    Carried inside the signed payload, so it cannot be attached, altered or
    stripped after issuance. ``verdict`` is a plain string rather than the
    assurance enum: this module must not import the layer above it.

    ``authorization_code`` is what makes the binding non-forgeable *from the
    verification side*.

    M3.2 used an HMAC whose key the authority also held. That was symmetric:
    any holder of the verification key can mint, so the authority could
    forge authorizations. M3.3 replaces it with a **hash commitment**:

    * the Arbiter draws a random ``authorization_code`` per authorization;
    * it registers only ``sha256(code | payload)`` with the authority;
    * the authority verifies by recomputing that digest from the presented
      code, and stores no key material at all.

    The asymmetry is one-way-function preimage resistance, not public-key
    cryptography: the verifier holds digests it cannot invert. See the
    module docstring for the scope and limits of that claim.
    """

    decision_id: str
    decision_hash: str
    verdict: str
    policy_id: str = ""
    policy_version: str = ""
    arbiter_id: str = ""
    authorization_code: str = ""

    def __post_init__(self) -> None:
        for label in ("decision_id", "decision_hash", "verdict"):
            if not str(getattr(self, label)).strip():
                raise AdmissionError(
                    f"decision binding requires {label}; an admission that "
                    f"cannot name the decision behind it is unverifiable"
                )

    @property
    def is_accepting(self) -> bool:
        return str(self.verdict).strip().lower() == ACCEPTING_VERDICT

    def to_dict(self):
        return {
            "schema": DECISION_BINDING_SCHEMA,
            "decision_id": self.decision_id,
            "decision_hash": self.decision_hash,
            "verdict": self.verdict,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "arbiter_id": self.arbiter_id,
            "authorization_code": self.authorization_code,
        }

    @classmethod
    def from_dict(cls, payload):
        require_schema(payload, DECISION_BINDING_SCHEMA)
        return cls(
            decision_id=payload["decision_id"],
            decision_hash=payload["decision_hash"],
            verdict=payload["verdict"],
            policy_id=payload.get("policy_id", ""),
            policy_version=payload.get("policy_version", ""),
            arbiter_id=payload.get("arbiter_id", ""),
            authorization_code=payload.get("authorization_code", ""),
        )


@dataclass(frozen=True)
class AdmissionDeclaration:
    """An Arbiter's decision to admit or decline one evidence record."""

    admitted: bool
    arbiter_id: str
    subject_record_hash: str = ""
    authorization: DecisionBinding | None = None
    issuer_id: str = ""
    issued_signature: str = ""
    arbiter_version: str = ""
    rationale: str = ""
    criteria_ref: tuple[str, ...] = ()
    decided_at: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.admitted, bool):
            raise AdmissionError("admission must be an explicit bool")
        arbiter = str(self.arbiter_id).strip()
        if not arbiter:
            raise AdmissionError(
                "admission requires an arbiter_id: evidence is never admitted "
                "by nobody"
            )
        object.__setattr__(self, "arbiter_id", arbiter)
        object.__setattr__(self, "criteria_ref", tuple(self.criteria_ref))

    def signing_payload(self) -> dict[str, Any]:
        """The fields an authority signs. Excludes the signature itself."""
        return {
            "authorization": (
                self.authorization.to_dict() if self.authorization else None
            ),
            "admitted": self.admitted,
            "arbiter_id": self.arbiter_id,
            "subject_record_hash": self.subject_record_hash,
            "issuer_id": self.issuer_id,
            "arbiter_version": self.arbiter_version,
            "rationale": self.rationale,
            "criteria_ref": list(self.criteria_ref),
            "decided_at": self.decided_at,
        }

    @property
    def is_signed(self) -> bool:
        return bool(self.issuer_id and self.issued_signature)

    def to_dict(self) -> dict[str, Any]:
        payload = self.signing_payload()
        payload.update(
            {"schema": ADMISSION_SCHEMA, "issued_signature": self.issued_signature}
        )
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AdmissionDeclaration":
        require_schema(payload, ADMISSION_SCHEMA)
        return cls(
            admitted=bool(payload["admitted"]),
            arbiter_id=payload["arbiter_id"],
            subject_record_hash=payload.get("subject_record_hash", ""),
            authorization=(
                DecisionBinding.from_dict(payload["authorization"])
                if payload.get("authorization")
                else None
            ),
            issuer_id=payload.get("issuer_id", ""),
            issued_signature=payload.get("issued_signature", ""),
            arbiter_version=payload.get("arbiter_version", ""),
            rationale=payload.get("rationale", ""),
            criteria_ref=tuple(payload.get("criteria_ref", ())),
            decided_at=payload.get("decided_at"),
        )


@dataclass(frozen=True)
class AdmissionAttempt:
    """One append-only audit entry for an admission attempt."""

    outcome: AdmissionOutcome
    reason: str = ""
    arbiter_id: str = ""
    issuer_id: str = ""
    subject_record_hash: str = ""
    at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", AdmissionOutcome(self.outcome))

    @property
    def succeeded(self) -> bool:
        return self.outcome is AdmissionOutcome.ADMITTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": ADMISSION_ATTEMPT_SCHEMA,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "arbiter_id": self.arbiter_id,
            "issuer_id": self.issuer_id,
            "subject_record_hash": self.subject_record_hash,
            "at": self.at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AdmissionAttempt":
        require_schema(payload, ADMISSION_ATTEMPT_SCHEMA)
        return cls(
            outcome=AdmissionOutcome(payload["outcome"]),
            reason=payload.get("reason", ""),
            arbiter_id=payload.get("arbiter_id", ""),
            issuer_id=payload.get("issuer_id", ""),
            subject_record_hash=payload.get("subject_record_hash", ""),
            at=payload.get("at"),
        )


class AdmissionAuthority:
    """Issues attributable admission declarations.

    M1.1 deliberately implements only issuance and verification — no admission
    *policy*. Deciding whether the critics justify admission is the Arbiter's
    job and belongs to a later milestone.
    """

    def __init__(self, authority_id: str, secret: str | None = None) -> None:
        authority_id = str(authority_id).strip()
        if not authority_id:
            raise AdmissionAuthorityError("admission authority requires an id")
        self._authority_id = authority_id
        self._secret = secret if secret is not None else secrets.token_hex(32)
        # Commitments registered by Arbiters: payload digest -> commitment.
        # These are one-way digests. The authority holds NO key material and
        # cannot invert them, so it cannot mint an authorization.
        self._commitments: dict[str, str] = {}

    @property
    def authority_id(self) -> str:
        return self._authority_id

    def _sign(self, payload: Mapping[str, Any]) -> str:
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hmac.new(
            str(self._secret).encode("utf-8"),
            blob.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    # ---- arbiter authorization (M3.3, one-way) --------------------------
    @staticmethod
    def authorization_payload(
        *,
        decision_id: str = "",
        decision_hash: str,
        subject_record_hash: str,
        verdict: str,
        policy_id: str = "",
        policy_version: str = "",
        arbiter_id: str = "",
    ) -> str:
        """Everything an authorization is bound to.

        Binding all of these together means an authorization cannot be moved to
        another record, reused for another verdict, or re-attributed to a
        different decision or policy version.
        """
        return "|".join(
            [
                decision_id,
                decision_hash,
                subject_record_hash,
                verdict,
                policy_id,
                policy_version,
                arbiter_id,
            ]
        )

    @staticmethod
    def commitment_for(code: str, payload: str) -> str:
        """``sha256(code | payload)`` — what the authority is allowed to know."""
        return hashlib.sha256(f"{code}|{payload}".encode("utf-8")).hexdigest()

    def register_authorization(
        self, capability: Any, commitment: str, payload: str
    ) -> None:
        """Accept an Arbiter's commitment to an authorization it will present.

        Deliberately takes a *digest*, never a key. An authority that has only
        commitments can check a presented code but cannot produce one, because
        doing so would require inverting SHA-256.

        Requires a :class:`_RegistrarCapability` (M3.4): holding the authority
        confers verification, not the right to create new commitments.
        """
        if not isinstance(capability, _RegistrarCapability):
            raise AdmissionAuthorityError(
                "registering an authorization requires a registrar capability; "
                "possession of an AdmissionAuthority does not confer the "
                "right to create commitments"
            )
        commitment = str(commitment).strip()
        payload = str(payload)
        if not commitment or not payload:
            raise AdmissionAuthorityError(
                "registering an authorization requires a commitment and payload"
            )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self._commitments[digest] = commitment

    def verifies_authorization(
        self, binding: "DecisionBinding", *, subject_record_hash: str
    ) -> bool:
        if binding is None or not binding.authorization_code:
            return False
        payload = self.authorization_payload(
            decision_id=binding.decision_id,
            decision_hash=binding.decision_hash,
            subject_record_hash=subject_record_hash,
            verdict=binding.verdict,
            policy_id=binding.policy_id,
            policy_version=binding.policy_version,
            arbiter_id=binding.arbiter_id,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        committed = self._commitments.get(digest)
        if committed is None:
            return False
        return hmac.compare_digest(
            committed, self.commitment_for(binding.authorization_code, payload)
        )

    def consume_authorization(
        self, binding: "DecisionBinding", *, subject_record_hash: str
    ) -> bool:
        """Retire a commitment once it has been used to admit.

        Single-use, deliberately. A stale accepting authorization must not be
        replayed to re-activate evidence that has since been SUSPENDED,
        SUPERSEDED or INVALIDATED — reinstatement is a fresh scientific
        decision and needs a fresh Arbiter decision behind it.
        """
        if binding is None:
            return False
        payload = self.authorization_payload(
            decision_id=binding.decision_id,
            decision_hash=binding.decision_hash,
            subject_record_hash=subject_record_hash,
            verdict=binding.verdict,
            policy_id=binding.policy_id,
            policy_version=binding.policy_version,
            arbiter_id=binding.arbiter_id,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return self._commitments.pop(digest, None) is not None

    def issue(
        self,
        *,
        admitted: bool,
        subject_record_hash: str,
        authorization: DecisionBinding | None = None,
        arbiter_id: str | None = None,
        arbiter_version: str = "",
        rationale: str = "",
        criteria_ref: Iterable[str] = (),
        decided_at: str | None = None,
    ) -> AdmissionDeclaration:
        """Produce a signed declaration bound to one evidence record."""
        subject = str(subject_record_hash).strip()
        if not subject:
            raise AdmissionAuthorityError(
                "an admission declaration must name the evidence record it "
                "applies to, otherwise it can be replayed onto another record"
            )

        # M3.2: refuse to sign an accepting declaration whose authorization
        # cannot be traced to a recognised Arbiter. Signing it would turn
        # possession of this authority into the power to admit.
        if admitted and not self.verifies_authorization(
            authorization, subject_record_hash=subject
        ):
            raise AdmissionAuthorityError(
                "refusing to sign an accepting admission: its decision binding "
                "carries no authorization code traceable to a recognised "
                "Arbiter. A fabricated binding cannot be laundered through a "
                "trusted authority."
            )
        unsigned = AdmissionDeclaration(
            admitted=admitted,
            arbiter_id=arbiter_id or self._authority_id,
            subject_record_hash=subject,
            authorization=authorization,
            issuer_id=self._authority_id,
            arbiter_version=arbiter_version,
            rationale=rationale,
            criteria_ref=tuple(criteria_ref),
            decided_at=decided_at,
        )
        signature = self._sign(unsigned.signing_payload())
        return AdmissionDeclaration(
            admitted=unsigned.admitted,
            arbiter_id=unsigned.arbiter_id,
            subject_record_hash=unsigned.subject_record_hash,
            authorization=unsigned.authorization,
            issuer_id=unsigned.issuer_id,
            issued_signature=signature,
            arbiter_version=unsigned.arbiter_version,
            rationale=unsigned.rationale,
            criteria_ref=unsigned.criteria_ref,
            decided_at=unsigned.decided_at,
        )

    def verifies(self, declaration: AdmissionDeclaration) -> bool:
        if declaration.issuer_id != self._authority_id:
            return False
        expected = self._sign(declaration.signing_payload())
        return hmac.compare_digest(expected, declaration.issued_signature or "")


class AdmissionAuthorityRegistry:
    """The set of authorities a gateway is willing to trust."""

    def __init__(self, authorities: Iterable[AdmissionAuthority] = ()) -> None:
        self._authorities: dict[str, AdmissionAuthority] = {}
        for authority in authorities:
            self.register(authority)

    def register(self, authority: AdmissionAuthority) -> None:
        if not isinstance(authority, AdmissionAuthority):
            raise AdmissionAuthorityError(
                "only an AdmissionAuthority may be registered"
            )
        self._authorities[authority.authority_id] = authority

    @property
    def authority_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._authorities))

    def consume(
        self, declaration: AdmissionDeclaration, *, subject_record_hash: str
    ) -> bool:
        """Retire the authorization behind an accepted declaration."""
        authority = self._authorities.get(declaration.issuer_id)
        if authority is None or declaration.authorization is None:
            return False
        return authority.consume_authorization(
            declaration.authorization, subject_record_hash=subject_record_hash
        )

    def verify(
        self, declaration: AdmissionDeclaration, *, subject_record_hash: str
    ) -> AdmissionAttempt:
        """Check issuer and binding. Returns the attempt; never raises."""
        base = {
            "arbiter_id": declaration.arbiter_id,
            "issuer_id": declaration.issuer_id,
            "subject_record_hash": declaration.subject_record_hash,
            "at": declaration.decided_at,
        }

        if not declaration.is_signed:
            return AdmissionAttempt(
                outcome=AdmissionOutcome.UNAUTHORIZED,
                reason="declaration carries no issuer signature",
                **base,
            )
        authority = self._authorities.get(declaration.issuer_id)
        if authority is None:
            return AdmissionAttempt(
                outcome=AdmissionOutcome.UNAUTHORIZED,
                reason=f"issuer {declaration.issuer_id!r} is not registered",
                **base,
            )
        if not authority.verifies(declaration):
            return AdmissionAttempt(
                outcome=AdmissionOutcome.UNAUTHORIZED,
                reason=f"signature does not verify for issuer "
                f"{declaration.issuer_id!r}",
                **base,
            )
        if declaration.subject_record_hash != subject_record_hash:
            return AdmissionAttempt(
                outcome=AdmissionOutcome.MALFORMED,
                reason=(
                    "declaration was issued for a different evidence record "
                    f"({declaration.subject_record_hash[:12]}… != "
                    f"{subject_record_hash[:12]}…)"
                ),
                **base,
            )
        if declaration.admitted:
            binding = declaration.authorization
            if binding is None:
                return AdmissionAttempt(
                    outcome=AdmissionOutcome.UNAUTHORIZED,
                    reason=(
                        "accepting declaration carries no assurance decision; "
                        "holding a trusted authority is not by itself grounds "
                        "for admission"
                    ),
                    **base,
                )
            if not binding.is_accepting:
                return AdmissionAttempt(
                    outcome=AdmissionOutcome.UNAUTHORIZED,
                    reason=(
                        f"assurance decision {binding.decision_id!r} is "
                        f"{binding.verdict!r}, not {ACCEPTING_VERDICT!r}"
                    ),
                    **base,
                )
            # Independent of whether issue() was careful: the Gateway
            # re-verifies the capability itself.
            if not authority.verifies_authorization(
                binding, subject_record_hash=subject_record_hash
            ):
                return AdmissionAttempt(
                    outcome=AdmissionOutcome.UNAUTHORIZED,
                    reason=(
                        "decision binding carries no authorization code "
                        "traceable to a recognised Arbiter for this record"
                    ),
                    **base,
                )

        if not declaration.admitted:
            return AdmissionAttempt(
                outcome=AdmissionOutcome.REFUSED,
                reason=declaration.rationale or "authority declined admission",
                **base,
            )
        return AdmissionAttempt(
            outcome=AdmissionOutcome.ADMITTED,
            reason=declaration.rationale or "admitted",
            **base,
        )
