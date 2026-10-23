"""Authority bindings: where every projected fact of a world came from, and whether its owner still says it.

A :class:`~.world.ScientificWorld` is a PROJECTION of canonical FORGE owners.  Each fact it projects (a current
value, a model record, a provider status, a budget statement, the problem/protocol declaration, the unit registry)
carries an :class:`AuthorityBinding`: the owner kind and instance, the authoritative record's identity and revision,
the owner's OWN digest of that record, the projected fields and a digest of exactly what was projected.  The binding
time is metadata, never identity.  Nothing in a world is authoritative because the world holds it.

:class:`Authorities` is the execution side's set of read-only owner readers (:mod:`.owners`).  It answers, for one
binding, whether the owner still states exactly what was projected (:class:`BindingStatus`).  Proposers never hold
or supply it.  It can be frozen into a snapshot of the records it served, so a historical admission can be replayed
exactly while a new one is verified against the owners as they are now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol

from .base import HEX64, WorldRefused, digest, expect_schema, schema, text

BINDING_SCHEMA = schema("authority_binding")
CHECK_SCHEMA = schema("authority_check")
REPORT_SCHEMA = schema("authority_report")
SNAPSHOT_SCHEMA = schema("authority_snapshot")


class OwnerKind(str, Enum):
    """The canonical owner a projected fact is read from.  Each member names an existing owner; none is new."""

    DECLARATION = "declaration"          # the problem / protocol declaration in force (declaration.ProtocolDeclaration)
    UNIT_REGISTRY = "unit_registry"      # scientific.units sealed registry (registry_fingerprint)
    SYSTEM_STATE = "system_state"        # system_runtime: a run's committed state head (SystemRunResult / SystemCheckpoint)
    MODEL_RECORD = "model_record"        # scientific.models.ModelRegistry
    PROVIDER_STATUS = "provider_status"  # providers.ProviderRegistry + providers.health.assess_health
    BUDGET_LEDGER = "budget_ledger"      # sria.campaign.BudgetLedger
    EXPERIMENT = "experiment"            # scientific.experiments.ScientificExperiment (observation accounting)


class BindingStatus(str, Enum):
    VERIFIED = "verified"                      # the owner states exactly what was projected, now
    #: The owner now states another record under this record identity.  An owner that keeps a history (the run's
    #: committed states) tells superseded (STALE) from never held (MISSING); one that keeps none cannot, and a digest
    #: it never held is also reported STALE: either way the owner does not state it now.
    STALE = "stale"
    MISSING = "missing"                        # no such record (or owner instance) exists
    MISMATCH = "mismatch"                      # the owner states something other than what the world holds
    UNVERIFIABLE = "unverifiable"              # nothing an owner could verify (an unbound or synthetic fact)
    OWNER_UNAVAILABLE = "owner_unavailable"    # the execution side supplied no reader for this owner kind


#: What a VERIFIED declaration binding means: the world is the projection of the declaration the execution side holds
#: in force.  No canonical FORGE owner states experiment protocols, so this is a caller declaration, not an owner fact.
DECLARATION_HELD = "caller_declared_held_in_force_by_the_execution_side"


class OwnerUnavailable(WorldRefused):
    """An owner reader could not consult its owner (the execution side could not state the current record)."""


def projection_digest(payload: Mapping[str, Any]) -> str:
    """Digest of exactly the projected fields (the world's rule over the owner's payload; never the owner's digest)."""
    return digest(dict(payload))


@dataclass(frozen=True)
class AuthorityBinding:
    owner_kind: OwnerKind
    owner_id: str
    record_id: str
    revision: str
    record_digest: str
    fields: tuple[str, ...]
    projection: str
    bound_at: str = ""                                    # metadata only: never identity, never compared

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "owner_kind", OwnerKind(self.owner_kind))
        except ValueError:
            raise WorldRefused(f"unknown owner kind {self.owner_kind!r}") from None
        for name in ("owner_id", "record_id", "revision"):
            if type(getattr(self, name)) is not str:
                raise WorldRefused(f"an authority binding's {name} is exactly a str")
            text(getattr(self, name), f"authority binding {name}")
        for name in ("record_digest", "projection"):
            value = getattr(self, name)
            if type(value) is not str or not HEX64.match(value):
                raise WorldRefused(f"an authority binding's {name} is a 64-hex digest, got {value!r}")
        fields_ = tuple(self.fields)
        if not fields_ or any(type(f) is not str or not f for f in fields_) or len(set(fields_)) != len(fields_):
            raise WorldRefused("an authority binding names the distinct fields it projects")
        object.__setattr__(self, "fields", tuple(sorted(fields_)))
        if type(self.bound_at) is not str:
            raise WorldRefused("bound_at is text metadata")

    def identity(self) -> dict[str, Any]:
        return {"owner_kind": self.owner_kind.value, "owner_id": self.owner_id, "record_id": self.record_id,
                "revision": self.revision, "record_digest": self.record_digest, "fields": list(self.fields),
                "projection": self.projection}

    @property
    def digest(self) -> str:
        return digest(self.identity())

    @property
    def key(self) -> tuple[str, str, str, tuple[str, ...]]:
        """What one projection may never carry two values under: owner, record, record digest and fields."""
        return (self.owner_kind.value, self.owner_id, self.record_id, self.record_digest) + self.fields  # type: ignore

    def to_dict(self) -> dict[str, Any]:
        return {"schema": BINDING_SCHEMA, **self.identity(), "bound_at": self.bound_at}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AuthorityBinding":
        expect_schema(payload.get("schema"), BINDING_SCHEMA)
        return cls(OwnerKind(payload["owner_kind"]), payload["owner_id"], payload["record_id"], payload["revision"],
                   payload["record_digest"], tuple(payload["fields"]), payload["projection"],
                   payload.get("bound_at", ""))


# ---- owner reads ---------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class OwnerRecord:
    """One authoritative record as its owner states it NOW: its revision, the owner's own digest, and the payload
    of the fields a world may project from it."""

    owner_kind: OwnerKind
    owner_id: str
    record_id: str
    revision: str
    record_digest: str
    payload: Any

    def binding(self, fields: Iterable[str], projected: Mapping[str, Any], bound_at: str = "") -> AuthorityBinding:
        return AuthorityBinding(self.owner_kind, self.owner_id, self.record_id, self.revision, self.record_digest,
                                tuple(fields), projection_digest(projected), bound_at)

    def to_dict(self) -> dict[str, Any]:
        return {"owner_kind": self.owner_kind.value, "owner_id": self.owner_id, "record_id": self.record_id,
                "revision": self.revision, "record_digest": self.record_digest, "payload": self.payload}


class OwnerReader(Protocol):
    """A narrow read-only adapter over one canonical owner.  It reads, projects allowed fields and states identity;
    it never invents, converts, decides applicability, budgets or availability, or issues a verdict."""

    kinds: frozenset[OwnerKind]
    owner_id: str

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None: ...

    def superseded(self, kind: OwnerKind, record_id: str) -> frozenset[str] | None:
        """Digests the owner states this record superseded; None when the owner keeps no history."""
        ...

    def project(self, record: OwnerRecord, fields: tuple[str, ...]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class BindingCheck:
    status: BindingStatus
    owner_kind: OwnerKind
    record_id: str
    subject: str
    binding_digest: str
    detail: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", BindingStatus(self.status))
        object.__setattr__(self, "owner_kind", OwnerKind(self.owner_kind))

    @property
    def ok(self) -> bool:
        return self.status is BindingStatus.VERIFIED

    def to_dict(self) -> dict[str, Any]:
        return {"schema": CHECK_SCHEMA, "status": self.status.value, "owner_kind": self.owner_kind.value,
                "record_id": self.record_id, "subject": self.subject, "binding_digest": self.binding_digest,
                "detail": self.detail}


@dataclass(frozen=True)
class AuthorityReport:
    """Every binding of one world, checked against the owners as they are now.  ``ok`` only if every check is
    VERIFIED and the world is exactly the projection of those owners."""

    world_revision: str
    checks: tuple[BindingCheck, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", tuple(sorted(self.checks, key=lambda c: (
            c.owner_kind.value, c.record_id, c.subject, c.status.value, c.binding_digest))))

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)

    def failures(self) -> tuple[BindingCheck, ...]:
        return tuple(c for c in self.checks if not c.ok)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": REPORT_SCHEMA, "world_revision": self.world_revision,
                "checks": [c.to_dict() for c in self.checks]}

    @property
    def digest(self) -> str:
        return digest(self.to_dict())


# ---- the execution side's readers --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Authorities:
    """The execution side's owner readers, one per owner kind.  Read-only; held by the admitting party only.

    ``live`` is DERIVED, never asserted, at every call: True only when every reader is one of the shipped owner readers
    in a mode that consults its owner at every read (``owners.is_live``).  It certifies the MODE: a following reader
    asks the execution side again at every read, and which record is current is the execution side's statement.  Readers rebuilt from a snapshot, a fixed run record, a fixed
    declaration set or any look-alike reader state what an owner said THEN: projection, verification and replay may use
    them; a dispatch never may (a stale admission would otherwise stay dispatchable)."""

    readers: tuple[Any, ...]
    _by_kind: Mapping[OwnerKind, Any] = field(init=False, repr=False, compare=False, default=None)  # type: ignore

    def __post_init__(self) -> None:
        by_kind: dict[OwnerKind, Any] = {}
        for reader in self.readers:
            for kind in reader.kinds:
                if kind in by_kind:
                    raise WorldRefused(f"two readers claim the {kind.value} owner")
                by_kind[OwnerKind(kind)] = reader
        object.__setattr__(self, "_by_kind", by_kind)

    @property
    def live(self) -> bool:
        """Derived now (a memo holds one verification's reads and is never live)."""
        from .owners import is_live

        return bool(self.readers) and all(is_live(r) for r in self.readers)

    @classmethod
    def of(cls, *readers: Any) -> "Authorities":
        return cls(tuple(readers))

    def memoized(self) -> "Authorities":
        """The same readers, each owner pinned once and each record read once: one verification sees one consistent
        state of every owner (a followed run head or declaration set is asked once, not once per binding).  Every
        reader is pinned when the verification starts, whichever records it will read (a following reader observes
        its owner at every verification, never only when a world happens to bind it); a pin an owner refuses is
        recorded and raised only to a read of that owner (round 7, R7-C-F2)."""
        if all(type(r) is _Memo for r in self.readers):
            return self
        memos = tuple(r if type(r) is _Memo else _Memo(r) for r in self.readers)
        for memo in memos:
            try:
                memo._current()
            except OwnerUnavailable:
                pass                                  # recorded on the memo; raised to a read of this owner
        return Authorities(memos)

    def reader(self, kind: OwnerKind) -> Any | None:
        return self._by_kind.get(OwnerKind(kind))

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        reader = self.reader(kind)
        return None if reader is None else reader.read(OwnerKind(kind), record_id)

    def require(self, kind: OwnerKind, record_id: str) -> tuple[Any, OwnerRecord]:
        reader = self.reader(kind)
        if reader is None:
            raise WorldRefused(f"no {OwnerKind(kind).value} owner reader is supplied")
        record = reader.read(OwnerKind(kind), record_id)
        if record is None:
            raise WorldRefused(f"the {OwnerKind(kind).value} owner holds no record {record_id!r}")
        return reader, record

    def check(self, binding: AuthorityBinding, subject: str, projected: Mapping[str, Any] | None = None) -> BindingCheck:
        """Whether the owner still states exactly this binding.  ``projected`` is what the world holds under it."""
        def result(status: BindingStatus, **detail: Any) -> BindingCheck:
            return BindingCheck(status, binding.owner_kind, binding.record_id, subject, binding.digest, detail or None)

        if type(binding) is not AuthorityBinding:
            return BindingCheck(BindingStatus.UNVERIFIABLE, OwnerKind.DECLARATION, "-", subject, "0" * 64,
                                {"why": "not an authority binding"})
        if projected is not None and projection_digest(projected) != binding.projection:
            return result(BindingStatus.MISMATCH, why="the world's copy is not what this binding projected")
        reader = self.reader(binding.owner_kind)
        if reader is None:
            return result(BindingStatus.OWNER_UNAVAILABLE, why="no reader for this owner kind")
        if reader.owner_id != binding.owner_id:
            return result(BindingStatus.MISSING, why="the governing owner instance is another one",
                          bound_owner=binding.owner_id, current_owner=reader.owner_id)
        try:
            record = reader.read(binding.owner_kind, binding.record_id)
        except OwnerUnavailable as exc:
            return result(BindingStatus.OWNER_UNAVAILABLE, why=str(exc))
        except WorldRefused as exc:
            return result(BindingStatus.MISMATCH, why=str(exc))
        if record is None:
            return result(BindingStatus.MISSING, why="the owner holds no such record")
        if record.record_digest != binding.record_digest:
            history = reader.superseded(binding.owner_kind, binding.record_id)
            if history is None:
                return result(BindingStatus.STALE, why="the owner now states another record under this identity; "
                              "it keeps no history, so whether the bound record was superseded or never held cannot "
                              "be told (either way the owner does not state it now)",
                              bound=binding.record_digest, current=record.record_digest, history="none kept")
            if binding.record_digest in history:
                return result(BindingStatus.STALE, why="the owner has moved on from the bound revision",
                              bound=binding.record_digest, current=record.record_digest)
            return result(BindingStatus.MISSING, why="no record the owner holds or held has the bound digest",
                          bound=binding.record_digest, current=record.record_digest)
        if record.revision != binding.revision:
            return result(BindingStatus.MISMATCH, why="the bound revision is not the record's revision",
                          bound=binding.revision, current=record.revision)
        projected_now = reader.project(record, binding.fields)
        if projection_digest(projected_now) != binding.projection:
            return result(BindingStatus.MISMATCH, why="the owner projects other values under this very record")
        if binding.owner_kind is OwnerKind.DECLARATION:      # held in force by the execution side, not an owner fact
            return result(BindingStatus.VERIFIED, provenance=DECLARATION_HELD)
        return result(BindingStatus.VERIFIED)

    def snapshot(self, bindings: Iterable[AuthorityBinding]) -> dict[str, Any]:
        """The records these bindings resolve to now (one consistent read of each owner), as a frozen reader needs."""
        pinned = self.memoized()
        for b in bindings:
            reader = pinned.reader(b.owner_kind)
            if reader is None:
                continue
            try:
                reader.read(b.owner_kind, b.record_id)
            except WorldRefused:
                continue
        return pinned.served()

    def served(self) -> dict[str, Any]:
        """Every record this memoized set of readers served (and every owner it found unavailable): exactly what a
        frozen reader needs to answer the same reads, in the same order of outcomes, on replay."""
        if not all(type(r) is _Memo for r in self.readers):
            raise WorldRefused("only a memoized set of readers knows what it served")
        records: list[dict[str, Any]] = []
        unavailable: list[list[str]] = []
        refused: list[list[str]] = []
        for memo in sorted(self.readers, key=lambda m: sorted(k.value for k in m.kinds)):
            if memo._failure is not None:
                unavailable.extend([k.value, str(memo._failure)] for k in sorted(memo.kinds, key=lambda k: k.value))
            for (kind, record_id), exc in sorted(memo._refused.items(), key=lambda kv: (kv[0][0].value, kv[0][1])):
                refused.append([kind.value, record_id, type(exc).__name__, str(exc)])
            for (kind, record_id), record in sorted(memo._reads.items(), key=lambda kv: (kv[0][0].value, kv[0][1])):
                if record is None:
                    continue
                history = memo._history.get((kind, record_id))
                records.append({"record": record.to_dict(), "owner_kind": kind.value,
                                "superseded": None if history is None else sorted(history)})
        owners = sorted({(k.value, r.owner_id) for k, r in self._by_kind.items()})
        return {"schema": SNAPSHOT_SCHEMA, "owners": [list(o) for o in owners], "records": records,
                "unavailable": unavailable, "refused": refused}

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, Any]) -> "Authorities":
        from .owners import frozen_readers

        expect_schema(payload.get("schema"), SNAPSHOT_SCHEMA)
        return cls(frozen_readers(payload))


class _Memo:
    """A reader pinned once (``pinned()``: a followed owner is asked for its current record once) and reading each
    record once (successful reads only; a refusal is re-raised every time)."""

    def __init__(self, reader: Any) -> None:
        self._reader = reader
        self._pinned: Any = None
        self._failure: OwnerUnavailable | None = None
        self.kinds = reader.kinds
        self.owner_id = reader.owner_id
        self._reads: dict[tuple[OwnerKind, str], Any] = {}
        self._history: dict[tuple[OwnerKind, str], Any] = {}
        self._refused: dict[tuple[OwnerKind, str], WorldRefused] = {}

    def _current(self) -> Any:
        if self._failure is not None:
            raise self._failure
        if self._pinned is None:
            pin = getattr(self._reader, "pinned", None)
            try:
                self._pinned = self._reader if pin is None else pin()
            except OwnerUnavailable as exc:
                self._failure = exc
                raise
        return self._pinned

    def read(self, kind: OwnerKind, record_id: str) -> OwnerRecord | None:
        key = (OwnerKind(kind), record_id)
        if key in self._refused:
            raise self._refused[key]
        if key not in self._reads:
            try:
                self._reads[key] = self._current().read(kind, record_id)
            except WorldRefused as exc:
                if self._failure is None:              # a pin failure is recorded for the whole owner, not per read
                    self._refused[key] = exc
                raise
        return self._reads[key]

    def superseded(self, kind: OwnerKind, record_id: str) -> frozenset[str] | None:
        key = (OwnerKind(kind), record_id)
        if key not in self._history:
            self._history[key] = self._current().superseded(kind, record_id)
        return self._history[key]

    def project(self, record: OwnerRecord, fields: tuple[str, ...]) -> dict[str, Any]:
        return self._reader.project(record, fields)


__all__ = [
    "Authorities", "AuthorityBinding", "AuthorityReport", "BindingCheck", "BindingStatus", "DECLARATION_HELD",
    "OwnerKind", "OwnerReader", "OwnerRecord", "OwnerUnavailable", "projection_digest",
]
