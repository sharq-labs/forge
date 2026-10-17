"""The persistent authority ledger: who may issue which scientific record, and every record they issued.

One append-only, hash-chained log of ed25519-SIGNED events.  The state it defines (issuers, their keys, their roles,
revocations) is a pure function of the event sequence, re-derived and re-verified on every load:

* ``genesis`` -- the ledger id, the PROFILE (``test`` / ``production``) and the ROOT key; signed by the root.
* ``register`` / ``set_roles`` / ``rotate`` / ``revoke`` -- issuer lifecycle; signed by the ROOT key.
* ``attest`` -- one :class:`Attestation`, signed by the ISSUER's key that is active at that sequence; admitted only if the
  issuer exists, is not revoked and holds the attestation's role THERE.

Old attestations stay verifiable against the state at THEIR sequence (rotation or revocation later does not rewrite
history); a revoked issuer or a retired key cannot append anything valid afterwards (ordering is the ledger's, so a
backdated attestation is impossible -- the sequence is assigned on append and signed over).

A consumer pins a :class:`TrustAnchor` (ledger id, profile, root key id, and a ``(sequence, head)`` it has already seen).
:meth:`AuthorityLedger.open` refuses a store that is not THAT ledger, has another root or profile, is shorter than the
anchor (truncation / rollback), or does not contain the anchored head (rewrite / reorder / key substitution).  Residual
(stated, not hidden): entries appended AFTER the consumer's newest anchor can be truncated without detection until the
consumer anchors again; the root key itself is not rotatable (a new root is a new ledger).

The ledger signs and orders DIGESTS of existing records (``record_digest`` of a ValidationCheck, an ApplicabilityReport,
a NodeReceipt, ...) together with the record itself; it is not a second evidence model.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import pathlib
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from .keys import (
    AuthorityRefused,
    Signer,
    key_id_of,
    verify_possession,
    verify_signature,
)

EVENT_SCHEMA = "engcore.authority.ledger_event/1"
ATTESTATION_SCHEMA = "engcore.authority.attestation/1"
ANCHOR_SCHEMA = "engcore.authority.trust_anchor/1"
PROFILES = ("test", "production")
GENESIS_PREVIOUS = "0" * 64
_HEX64 = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}")
_TAG = b"forge.authority.event/1\n"


def _jsonable(o: Any) -> Any:
    if isinstance(o, Mapping):                        # a MappingProxyType is a mapping, never its repr
        return dict(o)
    if isinstance(o, tuple):
        return list(o)
    if isinstance(o, (set, frozenset)):                # order-free collections hash in one order
        return sorted(o, key=lambda x: canonical(x))
    if isinstance(o, Enum):
        return o.value
    return str(o)


def _deep_freeze(o: Any) -> Any:
    """Read-only all the way down: what was verified cannot be edited in memory afterwards."""
    if isinstance(o, Mapping):
        return MappingProxyType({k: _deep_freeze(v) for k, v in o.items()})
    if isinstance(o, (list, tuple)):
        return tuple(_deep_freeze(v) for v in o)
    return o


def thaw(o: Any) -> Any:
    """A plain, mutable, JSON-native COPY of a frozen record."""
    return json.loads(canonical(o))


def canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False, default=_jsonable)


def record_digest_of(record: Mapping[str, Any]) -> str:
    """sha256 of the canonical JSON of a record dict -- the same digest ``credibility_vector.record_digest`` and
    ``system_runtime`` ``digest_of`` compute for JSON-native records."""
    return hashlib.sha256(canonical(record).encode()).hexdigest()


class Role(str, Enum):
    """The evidence roles an issuer can be authorized for."""

    EXECUTOR = "executor"                              # attests NodeReceipts it executed
    NUMERICAL_VERIFICATION = "numerical_verification"  # convergence / code verification / independent routes / numerical UQ
    VALIDATION = "validation"                          # benchmark / experimental validation checks
    APPLICABILITY = "applicability"                    # applicability reports
    MEASUREMENT = "measurement"                        # measurement (aleatoric) uncertainty, measurement releases
    UNCERTAINTY = "uncertainty"                        # parameter / model-form uncertainty entries
    RED_TEAM = "red_team"                              # trust envelopes
    EXPOSURE = "exposure"                              # exposure authority: evidence releases, sealed-falsifier campaigns
    ESCROW = "escrow"                                  # blindfold escrow identity
    OWNER = "owner"                                    # the campaign owner: approvals (e.g. releasing confirmatory data)


def _hex64(value: str, what: str, *, allow_empty: bool = False) -> str:
    v = str(value)
    if (allow_empty and v == "") or _HEX64.fullmatch(v):
        return v
    raise AuthorityRefused(f"{what} is a sha256 hex digest")


def _ident(value: str, what: str) -> str:
    v = str(value)
    if not _ID.fullmatch(v):
        raise AuthorityRefused(f"{what} {v!r} is not a normalized identifier")
    return v


@dataclass(frozen=True)
class Attestation:
    """What an issuer states: THIS record, about THIS result (``subject_digest``, output ``subject_output`` of the
    attested NodeReceipt ``receipt_digest``), in THIS context, in THIS role.  ``record`` is carried whole, so the ledger
    itself holds every record an issuer ever attested -- including the negative ones."""

    record_kind: str
    record_schema: str
    record: Mapping[str, Any] = field(hash=False)
    subject_digest: str
    context_digest: str
    role: Role
    receipt_digest: str = ""
    subject_output: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", Role(self.role))
        _ident(self.record_kind, "record kind")
        if not str(self.record_schema).strip():
            raise AuthorityRefused("an attestation names the record's schema")
        rec = json.loads(canonical(dict(self.record)))     # JSON-native copy: what the ledger stores is what is digested
        object.__setattr__(self, "record", _deep_freeze(rec))
        object.__setattr__(self, "_digest", record_digest_of(rec))   # frozen at construction, never recomputed from live data
        _hex64(self.subject_digest, "subject digest")
        _hex64(self.context_digest, "context digest")
        if not isinstance(self.receipt_digest, str) or not isinstance(self.subject_output, str):
            raise AuthorityRefused("an attestation's receipt digest and subject output are strings")
        _hex64(self.receipt_digest, "receipt digest", allow_empty=True)

    @property
    def record_digest(self) -> str:
        return self._digest  # type: ignore[attr-defined]

    def record_dict(self) -> dict[str, Any]:
        """A mutable COPY of the attested record (editing it changes nothing attested)."""
        return thaw(self.record)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ATTESTATION_SCHEMA, "record_kind": self.record_kind, "record_schema": self.record_schema,
                "record": thaw(self.record), "record_digest": self.record_digest, "subject_digest": self.subject_digest,
                "subject_output": self.subject_output, "receipt_digest": self.receipt_digest,
                "context_digest": self.context_digest, "role": self.role.value}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Attestation:
        if payload.get("schema") != ATTESTATION_SCHEMA:
            raise AuthorityRefused("not an attestation record")
        keys = {"schema", "record_kind", "record_schema", "record", "record_digest", "subject_digest", "subject_output",
                "receipt_digest", "context_digest", "role"}
        if set(payload) != keys:
            raise AuthorityRefused(f"attestation keys are exactly {sorted(keys)}")
        a = cls(payload["record_kind"], payload["record_schema"], payload["record"], payload["subject_digest"],
                payload["context_digest"], payload["role"], payload["receipt_digest"], payload["subject_output"])
        if a.record_digest != payload["record_digest"]:
            raise AuthorityRefused("the attested record does not hash to the attested record digest")
        return a


@dataclass(frozen=True)
class LedgerEvent:
    ledger_id: str
    sequence: int
    previous: str
    kind: str
    body: Mapping[str, Any] = field(hash=False)
    key_id: str = ""
    signature: str = ""

    def signed_bytes(self) -> bytes:
        return _TAG + canonical({"schema": EVENT_SCHEMA, "ledger_id": self.ledger_id, "sequence": self.sequence,
                                 "previous": self.previous, "kind": self.kind, "body": thaw(self.body),
                                 "key_id": self.key_id}).encode()

    def to_dict(self) -> dict[str, Any]:
        return {"schema": EVENT_SCHEMA, "ledger_id": self.ledger_id, "sequence": self.sequence, "previous": self.previous,
                "kind": self.kind, "body": thaw(self.body), "key_id": self.key_id, "signature": self.signature}

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical(self.to_dict()).encode()).hexdigest()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LedgerEvent:
        keys = {"schema", "ledger_id", "sequence", "previous", "kind", "body", "key_id", "signature"}
        if not isinstance(payload, Mapping) or set(payload) != keys or payload.get("schema") != EVENT_SCHEMA:
            raise AuthorityRefused("not a ledger event")
        seq = payload["sequence"]
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
            raise AuthorityRefused("a ledger event has a non-negative integer sequence")
        if not isinstance(payload["body"], Mapping):
            raise AuthorityRefused("a ledger event body is a mapping")
        return cls(str(payload["ledger_id"]), seq, str(payload["previous"]), str(payload["kind"]),
                   _deep_freeze(json.loads(canonical(payload["body"]))), str(payload["key_id"]), str(payload["signature"]))


@dataclass(frozen=True)
class TrustAnchor:
    """What a consumer pins: THIS ledger (id, profile, root key) and a point ``(sequence, head)`` it has already seen."""

    ledger_id: str
    profile: str
    root_key_id: str
    sequence: int
    head: str

    def __post_init__(self) -> None:
        if self.profile not in PROFILES:
            raise AuthorityRefused(f"profile is one of {PROFILES}")
        _hex64(self.root_key_id, "root key id")
        _hex64(self.head, "anchored head")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise AuthorityRefused("an anchor names a non-negative sequence")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": ANCHOR_SCHEMA, "ledger_id": self.ledger_id, "profile": self.profile, "root_key_id": self.root_key_id,
                "sequence": self.sequence, "head": self.head}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TrustAnchor:
        if payload.get("schema") != ANCHOR_SCHEMA:
            raise AuthorityRefused("not a trust anchor")
        return cls(payload["ledger_id"], payload["profile"], payload["root_key_id"], payload["sequence"], payload["head"])


# ---------------------------------------------------------------------------- stores


class MemoryLedgerStore:
    """In-memory store (tests, single process).  Lines are the serialized events, exactly as a file store holds them."""

    def __init__(self, lines: Iterable[str] = ()) -> None:
        self.lines = list(lines)

    def read(self) -> list[str]:
        return list(self.lines)

    def append(self, line: str, *, expected_lines: int) -> None:
        if len(self.lines) != expected_lines:
            raise AuthorityRefused("another writer appended to this ledger store; reopen it")
        self.lines.append(line)


class FileLedgerStore:
    """Append-only JSONL file: one event per line, flushed and fsynced on every append."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = pathlib.Path(path)

    def read(self) -> list[str]:
        if not self.path.exists():
            return []
        return [ln for ln in self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def append(self, line: str, *, expected_lines: int) -> None:
        """Append under an exclusive lock, and only if the file still holds exactly the lines this writer verified:
        a second writer (another ledger object on the same file) is refused instead of forking the chain."""
        if "\n" in line:
            raise AuthorityRefused("a ledger line holds one event")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # O_BINARY and newline="": the file holds the same LF-terminated bytes on every platform (Windows would
        # otherwise write CRLF at the descriptor and again in the text layer).
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(fd, "a+", encoding="utf-8", newline="") as fh, _exclusive(fh.fileno()):
            fh.seek(0)
            present = sum(1 for ln in fh.read().splitlines() if ln.strip())
            if present != expected_lines:
                raise AuthorityRefused(f"the ledger file holds {present} events, this writer verified {expected_lines}: "
                                       "another writer appended; reopen it")
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())


#: Windows byte-range locks are mandatory, so locking the ledger's own bytes would also fail every concurrent
#: reader. The lock is taken on one byte far past any real ledger's end instead (locking beyond EOF is allowed); a
#: ledger that ever grew past it would still be locked correctly, only with readers briefly refused during an append.
_WINDOWS_LOCK_OFFSET = 2**31 - 2


@contextlib.contextmanager
def _exclusive(fd: int) -> Iterator[None]:
    """One writer at a time on this ledger file: ``flock`` on POSIX, ``msvcrt.locking`` on Windows.

    Until 2026-10-13 this was ``fcntl`` alone, imported inside ``append``, so every file-backed ledger raised
    ``ModuleNotFoundError`` on Windows the first time it wrote.
    """
    if os.name == "nt":
        import msvcrt

        def release() -> None:
            os.lseek(fd, _WINDOWS_LOCK_OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

        here = os.lseek(fd, 0, os.SEEK_CUR)
        os.lseek(fd, _WINDOWS_LOCK_OFFSET, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)  # retries for about 10 s, then raises
        except OSError as exc:
            raise AuthorityRefused(f"another writer holds this ledger's lock: {exc}") from exc
        finally:
            os.lseek(fd, here, os.SEEK_SET)
    else:
        import fcntl

        def release() -> None:
            fcntl.flock(fd, fcntl.LOCK_UN)

        fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        yield
    except BaseException:
        # The refusal or failure that is already in flight is what the caller needs; an unlock that fails on the way
        # out must not replace it. Closing the descriptor, which follows, releases the lock on both platforms.
        with contextlib.suppress(OSError):
            release()
        raise
    release()


# ---------------------------------------------------------------------------- state


@dataclass
class _Key:
    public_hex: str
    key_class: str
    active_from: int
    retired_at: int | None = None
    compromised_from: int | None = None          # root-declared: what this key signed from here on is not evidence


@dataclass
class _Issuer:
    issuer_id: str
    keys: dict[str, _Key] = field(default_factory=dict)
    active_key: str = ""
    roles: list[tuple[frozenset[Role], int]] = field(default_factory=list)   # (roles, from sequence), newest last
    revoked_at: int | None = None

    def roles_at(self, sequence: int) -> frozenset[Role]:
        current: frozenset[Role] = frozenset()
        for roles, since in self.roles:
            if since <= sequence:
                current = roles
        return current

    def key_valid_at(self, key_id: str, sequence: int) -> bool:
        k = self.keys.get(key_id)
        return k is not None and k.active_from <= sequence and (k.retired_at is None or sequence < k.retired_at)

    def key_compromised_at(self, key_id: str, sequence: int) -> bool:
        k = self.keys.get(key_id)
        return k is not None and k.compromised_from is not None and sequence >= k.compromised_from


@dataclass(frozen=True)
class AttestationRecord:
    """An attestation as admitted by the ledger: its sequence, issuer and the key that signed it."""

    sequence: int
    event_digest: str
    issuer_id: str
    key_id: str
    attestation: Attestation

    @property
    def record_digest(self) -> str:
        return self.attestation.record_digest


ADMIN_KINDS = ("register", "set_roles", "rotate", "revoke", "compromise")


class AuthorityLedger:
    """See the module docstring.  Construct with :meth:`create` or :meth:`open`; never directly."""

    def __init__(self, _store: Any, _token: object) -> None:
        if _token is not _CONSTRUCT:
            raise AuthorityRefused("an authority ledger is created (AuthorityLedger.create) or opened against an anchor "
                                   "(AuthorityLedger.open)")
        self._store = _store
        self._events: list[LedgerEvent] = []
        self._issuers: dict[str, _Issuer] = {}
        self._attestations: list[AttestationRecord] = []
        self._ledger_id = ""
        self._profile = ""
        self._root_public = ""
        self._verified_anchor: TrustAnchor | None = None   # set only by open(): the anchor this ledger was verified against
        self._poisoned = ""

    # -- construction
    @classmethod
    def create(cls, store: Any, *, ledger_id: str, profile: str, root: Signer) -> AuthorityLedger:
        if store.read():
            raise AuthorityRefused("a new ledger needs an empty store; an existing ledger is opened against its anchor")
        if profile not in PROFILES:
            raise AuthorityRefused(f"profile is one of {PROFILES}")
        if profile == "production" and root.key_class != "production":
            raise AuthorityRefused("a production ledger's root key is production key material, never a test key")
        led = cls(store, _CONSTRUCT)
        body = {"ledger_id": _ident(ledger_id, "ledger id"), "profile": profile, "root_public": root.public_hex,
                "root_key_class": root.key_class}
        led._append_signed(LedgerEvent(ledger_id, 0, GENESIS_PREVIOUS, "genesis", body, root.key_id), root)
        return led

    @classmethod
    def open(cls, store: Any, *, anchor: TrustAnchor, require_profile: str | None = None) -> AuthorityLedger:
        """Load and RE-VERIFY every event; the store must be the anchored ledger and extend the anchored head."""
        if require_profile is not None and anchor.profile != require_profile:
            raise AuthorityRefused(f"the anchor is a {anchor.profile} ledger; {require_profile} is required")
        led = cls(store, _CONSTRUCT)
        lines = store.read()
        if not lines:
            raise AuthorityRefused("the store holds no ledger")
        for n, line in enumerate(lines):
            try:
                ev = LedgerEvent.from_dict(json.loads(line))
                led._apply(ev)
            except AuthorityRefused:
                raise
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise AuthorityRefused(f"ledger line {n} is not a valid ledger event: {type(exc).__name__}: {exc}") from exc
        if (led._ledger_id, led._profile, key_id_of(led._root_public)) != (anchor.ledger_id, anchor.profile, anchor.root_key_id):
            raise AuthorityRefused("the store is another ledger (ledger id, profile or root key differs from the anchor)")
        if anchor.sequence >= len(led._events):
            raise AuthorityRefused(f"the ledger has {len(led._events)} events but the anchor saw sequence {anchor.sequence}: "
                                   "truncated or rolled back")
        if led._events[anchor.sequence].digest != anchor.head:
            raise AuthorityRefused(f"event {anchor.sequence} is not the anchored head: the ledger was rewritten")
        led._verified_anchor = anchor
        return led

    @property
    def verified_anchor(self) -> TrustAnchor | None:
        """The consumer anchor this ledger was OPENED against (None for a ledger only created in this process)."""
        return self._verified_anchor

    def extends(self, anchor: TrustAnchor) -> bool:
        """This ledger is the anchored one (id, profile, root) and contains the anchored head at its sequence."""
        return ((self._ledger_id, self._profile, self.root_key_id) == (anchor.ledger_id, anchor.profile, anchor.root_key_id)
                and anchor.sequence < len(self._events) and self._events[anchor.sequence].digest == anchor.head)

    # -- read
    @property
    def ledger_id(self) -> str:
        return self._ledger_id

    @property
    def profile(self) -> str:
        return self._profile

    @property
    def root_key_id(self) -> str:
        return key_id_of(self._root_public)

    @property
    def length(self) -> int:
        return len(self._events)

    @property
    def head(self) -> str:
        return self._events[-1].digest

    def anchor(self) -> TrustAnchor:
        """The anchor a consumer should store NOW (after this, nothing before the head can be dropped undetected)."""
        return TrustAnchor(self._ledger_id, self._profile, self.root_key_id, len(self._events) - 1, self.head)

    def events(self) -> tuple[LedgerEvent, ...]:
        return tuple(self._events)

    def issuer_state(self, issuer_id: str, at: int | None = None) -> dict[str, Any] | None:
        iss = self._issuers.get(issuer_id)
        if iss is None:
            return None
        seq = len(self._events) if at is None else at
        return {"issuer_id": issuer_id, "roles": sorted(r.value for r in iss.roles_at(seq)),
                "revoked": iss.revoked_at is not None and iss.revoked_at <= seq, "active_key": iss.active_key}

    def attestations(self, *, record_kind: str | None = None, subject_digest: str | None = None,
                     context_digest: str | None = None, record_digest: str | None = None) -> tuple[AttestationRecord, ...]:
        return tuple(a for a in self._attestations
                     if (record_kind is None or a.attestation.record_kind == record_kind)
                     and (subject_digest is None or a.attestation.subject_digest == subject_digest)
                     and (context_digest is None or a.attestation.context_digest == context_digest)
                     and (record_digest is None or a.record_digest == record_digest))

    def compromised_at(self, issuer_id: str, key_id: str, sequence: int) -> bool:
        """True when the root declared ``key_id`` compromised from a sequence at or before ``sequence`` (``revoke`` /
        ``rotate_key`` with ``compromised_from``): what it signed in that window stays in the chain but is not evidence."""
        iss = self._issuers.get(issuer_id)
        return iss is not None and iss.key_compromised_at(key_id, sequence)

    def role_at(self, issuer_id: str, role: Role, sequence: int) -> bool:
        iss = self._issuers.get(issuer_id)
        return iss is not None and (iss.revoked_at is None or sequence < iss.revoked_at) and Role(role) in iss.roles_at(sequence)

    # -- write
    def register_issuer(self, root: Signer, issuer_id: str, possession: Mapping[str, str], *, roles: Iterable[Role]) -> LedgerEvent:
        """``possession`` is ``issuer_signer.possession(ledger_id, issuer_id)``: the issuer's key signs its own identity and
        key class, so a key is registered only by whoever holds it, in the class its provider gave it."""
        return self._admin(root, "register", {"issuer_id": _ident(issuer_id, "issuer id"), "possession": dict(possession),
                                              "roles": sorted(Role(r).value for r in roles)})

    def set_roles(self, root: Signer, issuer_id: str, roles: Iterable[Role]) -> LedgerEvent:
        return self._admin(root, "set_roles", {"issuer_id": issuer_id, "roles": sorted(Role(r).value for r in roles)})

    def rotate_key(self, root: Signer, issuer_id: str, possession: Mapping[str, str], *,
                   compromised_from: int | None = None) -> LedgerEvent:
        """``compromised_from``: the retired key was compromised from that ledger sequence on; consumers refuse what it
        signed from there (the events stay in the chain).  Without it, a rotation retires the key from now on only."""
        body: dict[str, Any] = {"issuer_id": issuer_id, "possession": dict(possession)}
        if compromised_from is not None:
            body["compromised_from"] = compromised_from
        return self._admin(root, "rotate", body)

    def revoke(self, root: Signer, issuer_id: str, reason: str, *, compromised_from: int | None = None) -> LedgerEvent:
        """``compromised_from``: as for :meth:`rotate_key`.  Without it, what the issuer attested BEFORE the revocation
        stays admitted -- a revocation alone is not a statement that earlier records were forged."""
        if not str(reason).strip():
            raise AuthorityRefused("a revocation states its reason")
        body: dict[str, Any] = {"issuer_id": issuer_id, "reason": str(reason)}
        if compromised_from is not None:
            body["compromised_from"] = compromised_from
        return self._admin(root, "revoke", body)

    def declare_compromise(self, root: Signer, issuer_id: str, key_id: str, *, compromised_from: int, reason: str) -> LedgerEvent:
        """Root-signed: ``key_id`` (active OR retired, the issuer revoked or not) was compromised from ``compromised_from``
        on.  What it signed from there stays in the chain but is not evidence (consumers check :meth:`compromised_at`)."""
        return self._admin(root, "compromise", {"issuer_id": issuer_id, "key_id": str(key_id), "compromised_from": compromised_from,
                                                "reason": str(reason)})

    def attest(self, signer: Signer, issuer_id: str, attestation: Attestation) -> AttestationRecord:
        iss = self._issuers.get(issuer_id)
        registered = iss.keys.get(signer.key_id) if iss is not None else None
        if registered is not None and registered.key_class != signer.key_class:
            raise AuthorityRefused("the signing key's class differs from the class it was registered with")
        body = {"issuer_id": issuer_id, "attestation": attestation.to_dict()}
        self._append_signed(LedgerEvent(self._ledger_id, len(self._events), self.head, "attest", body, signer.key_id), signer)
        return self._attestations[-1]

    def _admin(self, root: Signer, kind: str, body: Mapping[str, Any]) -> LedgerEvent:
        return self._append_signed(LedgerEvent(self._ledger_id, len(self._events), self.head, kind, body, root.key_id), root)

    def _append_signed(self, unsigned: LedgerEvent, signer: Signer) -> LedgerEvent:
        if self._poisoned:
            raise AuthorityRefused(f"this ledger object is unusable after a failed append ({self._poisoned}); reopen it")
        if unsigned.kind == "genesis" and signer.key_class not in ("test", "production"):
            raise AuthorityRefused("unknown key class")
        ev = LedgerEvent(unsigned.ledger_id, unsigned.sequence, unsigned.previous, unsigned.kind,
                         _deep_freeze(json.loads(canonical(dict(unsigned.body)))), unsigned.key_id, signer.sign(unsigned.signed_bytes()))
        expected = len(self._events)
        self._apply(ev)                                   # the SAME checks as on load, before anything is persisted
        try:
            self._store.append(canonical(ev.to_dict()), expected_lines=expected)
        except AuthorityRefused:
            self._unapply()                               # refused before any write: nothing happened
            raise
        except Exception as exc:
            self._unapply()
            self._poisoned = f"{type(exc).__name__}: {str(exc)[:80]}"   # the write may have landed: never append again blind
            raise
        return ev

    # -- the state machine (shared by append and load)
    def _snapshot(self) -> tuple:
        import copy
        return (len(self._events), copy.deepcopy(self._issuers), len(self._attestations), self._ledger_id, self._profile, self._root_public)

    def _unapply(self) -> None:
        n, issuers, na, lid, prof, root = self.__dict__.pop("_last_snapshot")
        del self._events[n:]
        self._issuers = issuers
        del self._attestations[na:]
        self._ledger_id, self._profile, self._root_public = lid, prof, root

    def _apply(self, ev: LedgerEvent) -> None:
        snap = self._snapshot()
        try:
            self._apply_checked(ev)
        except Exception:
            self.__dict__["_last_snapshot"] = snap          # a refused event leaves no trace in the state
            self._unapply()
            raise
        self.__dict__["_last_snapshot"] = snap

    def _apply_checked(self, ev: LedgerEvent) -> None:
        seq = len(self._events)
        if ev.sequence != seq:
            raise AuthorityRefused(f"event sequence {ev.sequence} where {seq} was expected (reordered, dropped or duplicated)")
        if ev.previous != (GENESIS_PREVIOUS if seq == 0 else self._events[-1].digest):
            raise AuthorityRefused(f"event {seq} does not link to the previous head (reordered or rewritten)")
        if seq == 0:
            if ev.kind != "genesis":
                raise AuthorityRefused("a ledger starts with its genesis")
            b = ev.body
            if set(b) != {"ledger_id", "profile", "root_public", "root_key_class"} or b["profile"] not in PROFILES:
                raise AuthorityRefused("malformed genesis")
            if b["profile"] == "production" and b["root_key_class"] != "production":
                raise AuthorityRefused("a production ledger with a test root key")
            if ev.ledger_id != b["ledger_id"] or ev.key_id != key_id_of(b["root_public"]):
                raise AuthorityRefused("the genesis is not signed by the root key it declares")
            if not verify_signature(b["root_public"], ev.signature, ev.signed_bytes()):
                raise AuthorityRefused("genesis signature invalid")
            self._ledger_id, self._profile, self._root_public = b["ledger_id"], b["profile"], b["root_public"]
        else:
            if ev.ledger_id != self._ledger_id:
                raise AuthorityRefused(f"event {seq} belongs to another ledger")
            if ev.kind in ADMIN_KINDS:
                self._apply_admin(ev, seq)
            elif ev.kind == "attest":
                self._apply_attest(ev, seq)
            else:
                raise AuthorityRefused(f"event {seq}: unknown kind {ev.kind!r}")
        self._events.append(ev)

    def _possessed(self, proof: Mapping[str, Any], issuer_id: str, seq: int) -> tuple[str, str]:
        if not isinstance(proof, Mapping) or set(proof) != {"public", "key_class", "signature"}:
            raise AuthorityRefused(f"event {seq}: a key is registered with its proof of possession")
        if not verify_possession(self._ledger_id, issuer_id, dict(proof)):
            raise AuthorityRefused(f"event {seq}: the proof of possession does not verify (the key did not sign this identity "
                                   "and class)")
        self._check_key_class(proof["key_class"])
        return str(proof["public"]), str(proof["key_class"])

    def _check_key_class(self, key_class: str) -> None:
        if key_class not in ("test", "production"):
            raise AuthorityRefused("key class is test or production")
        if self._profile == "production" and key_class != "production":
            raise AuthorityRefused("a production ledger refuses test key material")

    def _apply_admin(self, ev: LedgerEvent, seq: int) -> None:
        if ev.key_id != self.root_key_id or not verify_signature(self._root_public, ev.signature, ev.signed_bytes()):
            raise AuthorityRefused(f"event {seq} ({ev.kind}) is not signed by the ledger's root key")
        b = ev.body
        issuer_id = str(b.get("issuer_id", ""))
        if ev.kind == "register":
            if set(b) != {"issuer_id", "possession", "roles"}:
                raise AuthorityRefused("malformed register")
            _ident(issuer_id, "issuer id")
            if issuer_id in self._issuers:
                raise AuthorityRefused(f"issuer {issuer_id!r} is already registered (rotate its key instead)")
            pub, key_class = self._possessed(b["possession"], issuer_id, seq)
            kid = key_id_of(pub)
            if any(kid in i.keys for i in self._issuers.values()) or kid == self.root_key_id:
                raise AuthorityRefused("this key already belongs to another identity")
            iss = _Issuer(issuer_id)
            iss.keys[kid] = _Key(pub, key_class, seq)
            iss.active_key = kid
            iss.roles.append((frozenset(Role(r) for r in b["roles"]), seq))
            self._issuers[issuer_id] = iss
            return
        iss = self._issuers.get(issuer_id)
        if iss is None:
            raise AuthorityRefused(f"event {seq}: unknown issuer {issuer_id!r}")
        if ev.kind == "compromise":                     # allowed after revocation: discovering a theft is never too late
            if set(b) != {"issuer_id", "key_id", "compromised_from", "reason"} or not str(b["reason"]).strip():
                raise AuthorityRefused("malformed compromise declaration")
            key = iss.keys.get(str(b["key_id"]))
            start = b["compromised_from"]
            end = key.retired_at if key is not None and key.retired_at is not None else seq
            if key is None or isinstance(start, bool) or not isinstance(start, int) or not key.active_from <= start <= end:
                raise AuthorityRefused(f"event {seq}: compromised_from is a sequence inside that key's active life")
            if key.compromised_from is None or start < key.compromised_from:
                key.compromised_from = start            # a window only ever widens
            return
        if iss.revoked_at is not None:
            raise AuthorityRefused(f"event {seq}: issuer {issuer_id!r} is revoked; a revocation is final")
        if ev.kind == "set_roles":
            if set(b) != {"issuer_id", "roles"}:
                raise AuthorityRefused("malformed set_roles")
            iss.roles.append((frozenset(Role(r) for r in b["roles"]), seq))
        elif ev.kind == "rotate":
            if set(b) - {"compromised_from"} != {"issuer_id", "possession"}:
                raise AuthorityRefused("malformed rotate")
            pub, key_class = self._possessed(b["possession"], issuer_id, seq)
            kid = key_id_of(pub)
            if any(kid in i.keys for i in self._issuers.values()) or kid == self.root_key_id:
                raise AuthorityRefused("a rotated-in key must be new")
            self._compromise(iss, b, seq)
            iss.keys[iss.active_key].retired_at = seq
            iss.keys[kid] = _Key(pub, key_class, seq)
            iss.active_key = kid
        elif ev.kind == "revoke":
            if set(b) - {"compromised_from"} != {"issuer_id", "reason"}:
                raise AuthorityRefused("malformed revoke")
            self._compromise(iss, b, seq)
            iss.revoked_at = seq
            iss.keys[iss.active_key].retired_at = seq

    @staticmethod
    def _compromise(iss: _Issuer, body: Mapping[str, Any], seq: int) -> None:
        if "compromised_from" not in body:
            return
        start = body["compromised_from"]
        key = iss.keys[iss.active_key]
        if isinstance(start, bool) or not isinstance(start, int) or not key.active_from <= start <= seq:
            raise AuthorityRefused(f"event {seq}: compromised_from is a sequence inside the key's active life "
                                   f"[{key.active_from}, {seq}]")
        if key.compromised_from is None or start < key.compromised_from:
            key.compromised_from = start            # a window only ever widens, whichever event declares it

    def _apply_attest(self, ev: LedgerEvent, seq: int) -> None:
        b = ev.body
        if set(b) != {"issuer_id", "attestation"}:
            raise AuthorityRefused("malformed attest")
        issuer_id = str(b["issuer_id"])
        iss = self._issuers.get(issuer_id)
        if iss is None:
            raise AuthorityRefused(f"event {seq}: unknown issuer {issuer_id!r}")
        if iss.revoked_at is not None and seq >= iss.revoked_at:
            raise AuthorityRefused(f"event {seq}: issuer {issuer_id!r} was revoked at {iss.revoked_at}")
        if not iss.key_valid_at(ev.key_id, seq):
            raise AuthorityRefused(f"event {seq}: key {ev.key_id[:12]} is not {issuer_id!r}'s active key here")
        if not verify_signature(iss.keys[ev.key_id].public_hex, ev.signature, ev.signed_bytes()):
            raise AuthorityRefused(f"event {seq}: attestation signature invalid")
        att = Attestation.from_dict(b["attestation"])
        if att.role not in iss.roles_at(seq):
            raise AuthorityRefused(f"event {seq}: issuer {issuer_id!r} is not authorized for role {att.role.value} here")
        self._attestations.append(AttestationRecord(seq, ev.digest, issuer_id, ev.key_id, att))


_CONSTRUCT = object()


__all__ = ["ADMIN_KINDS", "ANCHOR_SCHEMA", "ATTESTATION_SCHEMA", "EVENT_SCHEMA", "PROFILES", "Attestation", "AttestationRecord",
           "AuthorityLedger", "FileLedgerStore", "LedgerEvent", "MemoryLedgerStore", "Role", "TrustAnchor", "canonical",
           "record_digest_of"]
